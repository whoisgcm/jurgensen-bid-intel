"""Query the ODOT bid price history.

Two subcommands:

  search <keyword>     find pay items by code or description text
  price  <item_code>   show the historical unit-price distribution for an item,
                       with optional filters (date range, district, quantity
                       band, awarded-only). This is the Phase-1 core: it returns
                       min / p25 / median / p75 / max plus a quantity-weighted
                       average, so an estimator can see where any number lands.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect  # noqa: E402


def percentile(sorted_vals, pct):
    """Linear-interpolated percentile (pct in 0..100). Expects a sorted list."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def cmd_search(conn, args):
    kw = f"%{args.keyword}%"
    rows = conn.execute(
        """SELECT p.item_code, p.description, p.unit, COUNT(b.id) AS n
           FROM pay_items p LEFT JOIN bid_lines b ON b.item_code = p.item_code
           WHERE p.item_code LIKE ? OR p.description LIKE ?
           GROUP BY p.item_code ORDER BY n DESC""",
        (kw, kw),
    ).fetchall()
    if not rows:
        print(f"No pay items match '{args.keyword}'.")
        return
    print(f"{'ITEM CODE':<12} {'UNIT':<5} {'OBS':>5}  DESCRIPTION")
    print("-" * 72)
    for r in rows:
        print(f"{r['item_code']:<12} {r['unit'] or '':<5} {r['n']:>5}  {r['description'] or ''}")


def cmd_price(conn, args):
    where = ["b.item_code = ?", "b.unit_price IS NOT NULL"]
    params = [args.item_code]
    if args.since:
        where.append("p.sale_date >= ?"); params.append(args.since)
    if args.until:
        where.append("p.sale_date <= ?"); params.append(args.until)
    if args.district:
        where.append("p.district = ?"); params.append(args.district)
    if args.min_qty is not None:
        where.append("b.quantity >= ?"); params.append(args.min_qty)
    if args.max_qty is not None:
        where.append("b.quantity <= ?"); params.append(args.max_qty)
    if args.awarded_only:
        where.append("b.is_awarded = 1")

    sql = f"""SELECT b.unit_price, b.quantity, p.sale_date, p.district
              FROM bid_lines b JOIN projects p ON p.project_id = b.project_id
              WHERE {' AND '.join(where)}"""
    rows = conn.execute(sql, params).fetchall()

    meta = conn.execute(
        "SELECT description, unit FROM pay_items WHERE item_code = ?",
        (args.item_code,),
    ).fetchone()

    if not rows:
        print(f"No bid observations for {args.item_code} with those filters.")
        return

    prices = sorted(r["unit_price"] for r in rows)
    wsum = sum(r["unit_price"] * r["quantity"] for r in rows if r["quantity"])
    qsum = sum(r["quantity"] for r in rows if r["quantity"])
    wavg = wsum / qsum if qsum else None
    dates = [r["sale_date"] for r in rows if r["sale_date"]]

    desc = (meta["description"] if meta else "") or ""
    unit = (meta["unit"] if meta else "") or ""
    print(f"\n{args.item_code}  {desc}  (per {unit})")
    if dates:
        print(f"window: {min(dates)} .. {max(dates)}", end="   ")
    print(f"observations: {len(prices)}")
    print("-" * 56)
    print(f"  min      ${prices[0]:>12,.2f}")
    print(f"  p25      ${percentile(prices, 25):>12,.2f}")
    print(f"  median   ${percentile(prices, 50):>12,.2f}")
    print(f"  p75      ${percentile(prices, 75):>12,.2f}")
    print(f"  max      ${prices[-1]:>12,.2f}")
    if wavg is not None:
        print(f"  wtd avg  ${wavg:>12,.2f}   (quantity-weighted)")
    print("-" * 56)

    if args.estimate is not None:
        below = sum(1 for x in prices if x < args.estimate)
        pctile = 100.0 * below / len(prices)
        print(f"\n  Your number ${args.estimate:,.2f}/{unit} lands at the "
              f"~{pctile:.0f}th percentile of history.")
        if pctile <= 30:
            print("  -> On the low end. Competitive, but check you're covering cost.")
        elif pctile >= 80:
            print("  -> On the high end. You may be leaving the award on the table.")
        else:
            print("  -> Mid-pack relative to historical bids.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Query ODOT bid price history.")
    p.add_argument("--db", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="find pay items by code or description")
    s.add_argument("keyword")
    s.set_defaults(func=cmd_search)

    q = sub.add_parser("price", help="historical unit-price distribution for an item")
    q.add_argument("item_code")
    q.add_argument("--since", help="earliest sale_date (YYYY-MM-DD)")
    q.add_argument("--until", help="latest sale_date (YYYY-MM-DD)")
    q.add_argument("--district")
    q.add_argument("--min-qty", type=float, dest="min_qty")
    q.add_argument("--max-qty", type=float, dest="max_qty")
    q.add_argument("--awarded-only", action="store_true",
                   help="only winning bidders' prices")
    q.add_argument("--estimate", type=float,
                   help="your unit price; report where it lands in history")
    q.set_defaults(func=cmd_price)

    args = p.parse_args(argv)
    conn = connect(args.db) if args.db else connect()
    args.func(conn, args)


if __name__ == "__main__":
    main()
