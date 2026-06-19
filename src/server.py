"""Tiny zero-dependency web app for the ODOT bid-intelligence demo.

Standard-library HTTP server only (no Flask/uvicorn) so it runs anywhere Python
does. Serves a single-page UI from web/ and a small JSON API over the SQLite DB.

    python -m src.server          # then open http://localhost:8000

Endpoints:
    GET /api/search?q=...                       -> matching pay items
    GET /api/price?item=CODE&since=&until=&min_qty=&max_qty=&awarded_only=
                                                 -> distribution + raw prices
    GET /api/trend?item=CODE                     -> median unit price by year
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def percentile(vals, pct):
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def search_items(conn, q, limit=25):
    kw = f"%{q}%"
    rows = conn.execute(
        """SELECT p.item_code, p.description, p.unit, COUNT(b.id) n
           FROM pay_items p LEFT JOIN bid_lines b ON b.item_code = p.item_code
           WHERE p.item_code LIKE ? OR p.description LIKE ?
           GROUP BY p.item_code HAVING n > 0 ORDER BY n DESC LIMIT ?""",
        (kw, kw, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def price_stats(conn, item, qs):
    where = ["b.item_code = ?", "b.unit_price IS NOT NULL"]
    params = [item]
    if qs.get("since"):
        where.append("p.sale_date >= ?"); params.append(qs["since"][0])
    if qs.get("until"):
        where.append("p.sale_date <= ?"); params.append(qs["until"][0])
    if qs.get("min_qty"):
        where.append("b.quantity >= ?"); params.append(float(qs["min_qty"][0]))
    if qs.get("max_qty"):
        where.append("b.quantity <= ?"); params.append(float(qs["max_qty"][0]))
    if qs.get("awarded_only", ["0"])[0] in ("1", "true"):
        where.append("b.is_awarded = 1")

    rows = conn.execute(
        f"""SELECT b.unit_price, b.quantity, p.sale_date
            FROM bid_lines b JOIN projects p ON p.project_id = b.project_id
            WHERE {' AND '.join(where)}""",
        params,
    ).fetchall()
    meta = conn.execute(
        "SELECT description, unit FROM pay_items WHERE item_code = ?", (item,)
    ).fetchone()

    prices = sorted(r["unit_price"] for r in rows)
    if not prices:
        return {"item": item, "count": 0,
                "description": meta["description"] if meta else "",
                "unit": meta["unit"] if meta else ""}
    qsum = sum(r["quantity"] for r in rows if r["quantity"])
    wsum = sum(r["unit_price"] * r["quantity"] for r in rows if r["quantity"])
    dates = [r["sale_date"] for r in rows if r["sale_date"]]
    return {
        "item": item,
        "description": meta["description"] if meta else "",
        "unit": meta["unit"] if meta else "",
        "count": len(prices),
        "min": prices[0], "p25": percentile(prices, 25),
        "median": percentile(prices, 50), "p75": percentile(prices, 75),
        "max": prices[-1],
        "wavg": (wsum / qsum) if qsum else None,
        "window": [min(dates), max(dates)] if dates else None,
        "prices": prices,
    }


def trend(conn, item):
    rows = conn.execute(
        """SELECT substr(p.sale_date,1,4) yr, b.unit_price
           FROM bid_lines b JOIN projects p ON p.project_id = b.project_id
           WHERE b.item_code = ? AND b.unit_price IS NOT NULL AND p.sale_date IS NOT NULL""",
        (item,),
    ).fetchall()
    by_year = {}
    for r in rows:
        by_year.setdefault(r["yr"], []).append(r["unit_price"])
    out = []
    for yr in sorted(by_year):
        vals = sorted(by_year[yr])
        out.append({"year": yr, "median": percentile(vals, 50), "n": len(vals)})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        conn = connect()
        try:
            if u.path == "/api/search":
                self._json(search_items(conn, qs.get("q", [""])[0]))
            elif u.path == "/api/price":
                self._json(price_stats(conn, qs.get("item", [""])[0], qs))
            elif u.path == "/api/trend":
                self._json(trend(conn, qs.get("item", [""])[0]))
            elif u.path in ("/", "/index.html"):
                self._serve_file(WEB / "index.html", "text/html")
            else:
                f = WEB / u.path.lstrip("/")
                if f.is_file() and WEB in f.resolve().parents:
                    ctype = "text/css" if f.suffix == ".css" else "application/javascript"
                    self._serve_file(f, ctype)
                else:
                    self._json({"error": "not found"}, 404)
        finally:
            conn.close()

    def _serve_file(self, path, ctype):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"ODOT Bid Intelligence: http://localhost:{port}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
