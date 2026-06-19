"""Export the SQLite database into static JSON for GitHub Pages.

GitHub Pages serves only static files — no Python, no SQLite. So we bake the
data the UI needs into JSON:

    docs/data/index.json         search index: [{code,desc,unit,n}, ...]
    docs/data/items/<code>.json  per item: full price stats + sorted prices + yearly trend

The browser then does search (filter the index) and benchmarking (percentile of
the user's price against the sorted list) entirely client-side. Re-run this
whenever the database changes:

    python -m src.export_static
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect           # noqa: E402
from src.server import price_stats, trend  # noqa: E402  (reuse the exact same math)

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
        s = price_stats(conn, code, {})
        if not s.get("count"):
            continue
        s["trend"] = trend(conn, code)
        # round prices to cut file size; keep cents
        s["prices"] = [round(x, 2) for x in s["prices"]]
        (OUT / "items" / f"{code}.json").write_text(json.dumps(s, separators=(",", ":")))
        index.append({"code": code, "desc": r["description"], "unit": r["unit"], "n": r["n"]})

    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    total = sum(f.stat().st_size for f in (OUT / "items").glob("*.json"))
    print(f"Exported {len(index):,} items to {OUT}  "
          f"(index {(OUT/'index.json').stat().st_size//1024} KB, "
          f"items {total//1024//1024} MB across {len(index):,} files)")


if __name__ == "__main__":
    main()
