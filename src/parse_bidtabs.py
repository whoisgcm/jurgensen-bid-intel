"""Parse an ODOT annual 'Official Bid Tabulation' PDF into the database.

ODOT publishes bid tabs as one big PDF per year (5000+ pages). The text layer
is clean and regular:

  Project header:
    Project No. 240576
    Type: BRIDGE REPLACEMENT (2 BRIDGES)
    Letting Date: 1/16/2025
    Contract Awarded To: MILLER BROS CONST INC
    Award Amount: $2,571,925.84
    Bidder 1 ... Bidder 7         (one block per bidder)

  Item lines:
    Ref #5 203E10000 EXCAVATION, (1502 CY)
    Awd $35.00 $52,570.00          <- awarded (low) bidder unit price + extension
    2   $20.00 $30,040.00          <- bidder 2 ...
    ...

We parse that grammar straight into projects / pay_items / bid_lines.

Usage:
    python -m src.parse_bidtabs data/raw/bidtabs_2025.pdf [--limit N] [--db PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.db import connect  # noqa: E402

RE_PROJECT = re.compile(r"Project No\.\s+(\S+)")
RE_TYPE = re.compile(r"^Type:\s+(.*)")
RE_LETTING = re.compile(r"Letting Date:\s+(\d{1,2})/(\d{1,2})/(\d{4})")
RE_AWARD = re.compile(r"Award Amount:\s+\$([\d,]+\.\d{2})")
RE_BIDDER = re.compile(r"Bidder (\d+)")
RE_ITEM = re.compile(r"^Ref #\d+\s+(\w+)\s+(.*)$")
RE_BID = re.compile(r"^(Awd|\d+)\s+\$([\d,]+(?:\.\d+)?)\s+\$([\d,]+(?:\.\d+)?)")
RE_QTY_UNIT = re.compile(r"\(([\d,]+(?:\.\d+)?)\s+([A-Z]+)\)\s*$")


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def parse(pdf_path: Path, db_path: Path | None, limit: int | None) -> dict:
    conn = connect(db_path) if db_path else connect()
    stats = {"projects": 0, "items": 0, "bid_lines": 0}
    items_seen: set[str] = set()

    # Current project context
    cur = None  # dict with project_id, sale_date, work_type, total_award, max_bidder
    cur_item = None  # dict with item_code, quantity, unit

    def flush_project():
        # Update the metadata onto the already-inserted project row (the row is
        # created on detection so bid_lines can reference it without an FK error).
        if not cur or not cur.get("project_id"):
            return
        conn.execute(
            """UPDATE projects
               SET sale_date=?, work_type=?, total_award=?, num_bidders=?
               WHERE project_id=?""",
            (cur.get("sale_date"), cur.get("work_type"), cur.get("total_award"),
             cur.get("max_bidder") or None, cur["project_id"]),
        )
        stats["projects"] += 1

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages if not limit else pdf.pages[:limit]
        for page in pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()

                m = RE_PROJECT.search(line)
                if m:
                    flush_project()
                    conn.commit()
                    cur = {"project_id": m.group(1), "max_bidder": 0}
                    conn.execute(
                        "INSERT OR IGNORE INTO projects (project_id) VALUES (?)",
                        (cur["project_id"],),
                    )
                    cur_item = None
                    continue
                if cur is None:
                    continue

                m = RE_TYPE.match(line)
                if m:
                    cur["work_type"] = m.group(1).strip()
                    continue
                m = RE_LETTING.search(line)
                if m:
                    mo, d, y = m.groups()
                    cur["sale_date"] = f"{y}-{int(mo):02d}-{int(d):02d}"
                    continue
                m = RE_AWARD.search(line)
                if m:
                    cur["total_award"] = _money(m.group(1))
                    continue
                for b in RE_BIDDER.findall(line):
                    cur["max_bidder"] = max(cur["max_bidder"], int(b))

                m = RE_ITEM.match(line)
                if m:
                    code, rest = m.group(1), m.group(2)
                    qty, unit = None, None
                    qm = RE_QTY_UNIT.search(rest)
                    if qm:
                        qty, unit = _money(qm.group(1)), qm.group(2)
                        desc = rest[: qm.start()].rstrip(", ").strip()
                    elif rest.endswith("(LUMP SUM)"):
                        qty, unit = 1.0, "LS"
                        desc = rest[: rest.rfind("(")].rstrip(", ").strip()
                    else:
                        desc = rest.strip()
                    cur_item = {"code": code, "qty": qty, "unit": unit}
                    if code not in items_seen:
                        conn.execute(
                            "INSERT OR REPLACE INTO pay_items (item_code, description, unit) VALUES (?,?,?)",
                            (code, desc, unit),
                        )
                        items_seen.add(code)
                        stats["items"] += 1
                    continue

                m = RE_BID.match(line)
                if m and cur_item:
                    tok, unit_price = m.group(1), _money(m.group(2))
                    rank = 1 if tok == "Awd" else int(tok)
                    conn.execute(
                        """INSERT INTO bid_lines
                           (project_id, item_code, quantity, unit_price, bidder_rank, is_awarded)
                           VALUES (?,?,?,?,?,?)""",
                        (cur["project_id"], cur_item["code"], cur_item["qty"],
                         unit_price, rank, 1 if tok == "Awd" else 0),
                    )
                    stats["bid_lines"] += 1

        flush_project()
        conn.commit()

    return stats


def main(argv=None):
    p = argparse.ArgumentParser(description="Parse an ODOT annual Bid Tabs PDF into the DB.")
    p.add_argument("pdf", type=Path)
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--limit", type=int, default=None, help="only parse first N pages (testing)")
    args = p.parse_args(argv)
    s = parse(args.pdf, args.db, args.limit)
    print(f"Parsed {s['bid_lines']:,} bid lines across {s['projects']:,} projects "
          f"and {s['items']:,} distinct pay items.")


if __name__ == "__main__":
    main()
