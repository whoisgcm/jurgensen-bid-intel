"""Export the SQLite database into static JSON for GitHub Pages.

GitHub Pages serves only static files (no Python, no SQLite), so we bake the
data the UI needs into JSON:

    docs/data/index.json         search index: [{code,desc,unit,n}, ...]
    docs/data/meta.json          headline dataset stats for the landing screen
    docs/data/items/<code>.json  per item: (quantity, unit_price) observations
                                  + yearly trend. The browser filters the
                                  observations by quantity band and recomputes
                                  the distribution / benchmark client-side.

Re-run whenever the database changes:  python -m src.export_static
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect    # noqa: E402
from src.server import trend  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
MIN_OBS = 5   # items with fewer bids aren't useful to benchmark against


def main():
    conn = connect()
    items = conn.execute(
        """SELECT p.item_code, p.description, p.unit, COUNT(b.id) n
           FROM pay_items p JOIN bid_lines b ON b.item_code = p.item_code
           WHERE b.unit_price IS NOT NULL
           GROUP BY p.item_code HAVING n >= ? ORDER BY n DESC""",
        (MIN_OBS,),
    ).fetchall()

    (OUT / "items").mkdir(parents=True, exist_ok=True)
    index = []
    for r in items:
        code = r["item_code"]
        rows = conn.execute(
            "SELECT quantity, unit_price FROM bid_lines WHERE item_code = ? AND unit_price IS NOT NULL",
            (code,),
        ).fetchall()
        # [quantity, unit_price] pairs; quantity may be null (kept, but unbandable)
        obs = [[round(o["quantity"], 2) if o["quantity"] is not None else None,
                round(o["unit_price"], 2)] for o in rows]
        rng = conn.execute(
            """SELECT MIN(p.sale_date), MAX(p.sale_date)
               FROM bid_lines b JOIN projects p ON p.project_id = b.project_id
               WHERE b.item_code = ? AND p.sale_date IS NOT NULL""",
            (code,),
        ).fetchone()
        rec = {
            "item": code, "description": r["description"], "unit": r["unit"],
            "count": len(obs), "window": list(rng) if rng and rng[0] else None,
            "trend": trend(conn, code), "obs": obs,
        }
        (OUT / "items" / f"{code}.json").write_text(json.dumps(rec, separators=(",", ":")))
        index.append({"code": code, "desc": r["description"], "unit": r["unit"], "n": r["n"]})

    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))

    # meta.json: headline dataset stats for the landing screen (kept accurate
    # by regenerating here whenever the data changes).
    one = lambda s: conn.execute(s).fetchone()[0]
    rng = conn.execute("SELECT MIN(sale_date), MAX(sale_date) FROM projects WHERE sale_date IS NOT NULL").fetchone()
    by_year = [{"year": r[0], "projects": r[1], "bids": r[2]} for r in conn.execute(
        """SELECT substr(p.sale_date,1,4) y, COUNT(DISTINCT p.project_id),
                  SUM((SELECT COUNT(*) FROM bid_lines b WHERE b.project_id=p.project_id AND b.unit_price IS NOT NULL))
           FROM projects p WHERE p.sale_date IS NOT NULL GROUP BY y ORDER BY y""")]
    meta = {
        "bid_lines": one("SELECT COUNT(*) FROM bid_lines WHERE unit_price IS NOT NULL"),
        "projects": one("SELECT COUNT(*) FROM projects"),
        "pay_items": len(index),
        "date_range": list(rng),
        "by_year": by_year,
        "avg_bidders": round(one("SELECT AVG(num_bidders) FROM projects WHERE num_bidders IS NOT NULL"), 1),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, separators=(",", ":")))

    total = sum(f.stat().st_size for f in (OUT / "items").glob("*.json"))
    print(f"Exported {len(index):,} items to {OUT}  "
          f"(index {(OUT/'index.json').stat().st_size//1024} KB, "
          f"items {total//1024//1024} MB across {len(index):,} files)")


if __name__ == "__main__":
    main()
