"""Ingest ODOT bid data exports into the local database.

ODOT publishes bid data as Excel/CSV exports (and interactive Power BI). This
module reads a *flat* export (one row per project, item, bidder) and
normalizes it into the projects / pay_items / bid_lines tables.

The expected input columns are listed in COLUMNS below. They mirror the fields
ODOT exposes (item code, description, unit, quantity, unit price, district,
sale date, bidder rank). If a real ODOT export uses different headers, pass a
mapping via --map "their_header=our_field,..." rather than editing this file.

CSV is handled with the standard library (zero install). .xlsx is supported
when `openpyxl` is installed; otherwise convert to CSV first.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect  # noqa: E402

# Canonical field -> description. These are the fields the loader needs.
COLUMNS = [
    "project_id", "sale_date", "district", "county", "work_type",
    "total_award", "num_bidders",
    "item_code", "description", "unit",
    "quantity", "unit_price", "bidder_rank", "is_awarded",
]


def _read_rows(path: Path):
    """Yield dict rows from a CSV or XLSX file."""
    if path.suffix.lower() in (".csv", ".tsv"):
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open(newline="", encoding="utf-8-sig") as fh:
            yield from csv.DictReader(fh, delimiter=delim)
        return
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            sys.exit("openpyxl not installed. `pip install openpyxl` or export the sheet to CSV.")
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows)]
        for r in rows:
            yield dict(zip(header, r))
        return
    sys.exit(f"Unsupported file type: {path.suffix}")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def ingest(path: Path, db_path: Path | None, colmap: dict[str, str]) -> dict:
    conn = connect(db_path) if db_path else connect()
    seen_projects: set[str] = set()
    seen_items: set[str] = set()
    n_lines = 0

    with conn:
        for raw in _read_rows(path):
            # Apply optional header remapping (their_header -> our_field).
            row = {colmap.get(k, k): v for k, v in raw.items()}

            pid = (row.get("project_id") or "").strip()
            item = (row.get("item_code") or "").strip()
            if not pid or not item:
                continue

            if pid not in seen_projects:
                conn.execute(
                    """INSERT OR REPLACE INTO projects
                       (project_id, sale_date, district, county, work_type, total_award, num_bidders)
                       VALUES (?,?,?,?,?,?,?)""",
                    (pid, (row.get("sale_date") or "").strip() or None,
                     (row.get("district") or "").strip() or None,
                     (row.get("county") or "").strip() or None,
                     (row.get("work_type") or "").strip() or None,
                     _num(row.get("total_award")),
                     int(_num(row.get("num_bidders")) or 0) or None),
                )
                seen_projects.add(pid)

            if item not in seen_items:
                conn.execute(
                    "INSERT OR REPLACE INTO pay_items (item_code, description, unit) VALUES (?,?,?)",
                    (item, (row.get("description") or "").strip() or None,
                     (row.get("unit") or "").strip() or None),
                )
                seen_items.add(item)

            conn.execute(
                """INSERT INTO bid_lines
                   (project_id, item_code, quantity, unit_price, bidder_rank, is_awarded)
                   VALUES (?,?,?,?,?,?)""",
                (pid, item, _num(row.get("quantity")), _num(row.get("unit_price")),
                 int(_num(row.get("bidder_rank")) or 0) or None,
                 1 if str(row.get("is_awarded")).strip() in ("1", "Y", "y", "True", "true") else 0),
            )
            n_lines += 1

    return {"projects": len(seen_projects), "items": len(seen_items), "bid_lines": n_lines}


def main(argv=None):
    p = argparse.ArgumentParser(description="Ingest an ODOT bid export (CSV/XLSX).")
    p.add_argument("file", type=Path, help="Path to the export file")
    p.add_argument("--db", type=Path, default=None, help="Database path (default data/bid_intel.db)")
    p.add_argument("--map", default="", help='Header remap, e.g. "Item Code=item_code,Unit Price=unit_price"')
    args = p.parse_args(argv)

    colmap = {}
    if args.map:
        for pair in args.map.split(","):
            their, _, ours = pair.partition("=")
            if ours:
                colmap[their.strip()] = ours.strip()

    stats = ingest(args.file, args.db, colmap)
    print(f"Ingested {stats['bid_lines']} bid lines across "
          f"{stats['projects']} projects and {stats['items']} pay items.")


if __name__ == "__main__":
    main()
