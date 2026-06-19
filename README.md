# jurgensen-bid-intel

A standalone tool that turns **public Ohio DOT (ODOT) bid data** into a searchable
unit-price history, so estimators can see **where any number lands relative to what
the market has actually bid** for the same pay item, quantity, district, and era.

Built for The Jurgensen Company (heavy-highway / asphalt, ODOT District 8 region).

**▶ Live app: https://zgiglio.github.io/jurgensen-bid-intel/**  (no install — just open it)

---

## Why this works

ODOT publishes bid data on a standardized **pay-item** system — every line of work
has a code, description, and unit (e.g. `441E10100 – Asphalt Concrete Surface Course,
CY`). For each let project, ODOT posts **bid tabulations** showing *every bidder's
unit price for every item*, plus aggregated **average/weighted item prices** in
Excel/PDF (and an interactive Power BI tool).

That gives us the full price *spread* — not just the winner — across hundreds of
projects and years. The hard ingredient (clean, structured historical pricing) is
already published; this tool just makes it queryable and benchmarkable.

Data sources:
- ODOT Bid Data (estimating): https://www.transportation.ohio.gov/working/contracts/estimating/bid-data
- ODOT Bid Tabs (sold projects): https://www.transportation.ohio.gov/working/contracts/sold-projects/bid-tabs
- BidX (AASHTOWare / Infotech): https://www.bidx.com

---

## Phases

- **Phase 1 (this repo): the price-history foundation.** Ingest ODOT bid exports
  into a clean, queryable database. Search items; pull min / p25 / median / p75 /
  max + quantity-weighted average for any item, filtered by date, district, and
  quantity band. Independently useful to estimators on day one.
- **Phase 2:** takeoff input → cost estimate built from unit prices.
- **Phase 3:** the benchmarking overlay — your estimate vs. the historical
  distribution, with low/competitive/high flags. (Already prototyped via
  `price --estimate`.)

---

## Real ODOT data

ODOT publishes the **Official Bid Tabulations** as one PDF per year (2001–present,
~5,500 pages each), free and login-free, from the estimating "Additional Downloads"
section. Each project's header (letting date, work type, award) and every item's
per-bidder unit prices extract cleanly. `src/parse_bidtabs.py` turns those PDFs into
the database.

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# Download a year (example) and parse it (~3 min/year, 5,500 pages)
curl -L -o data/raw/bidtabs_2025.pdf \
  "https://www.dot.state.oh.us/Divisions/ConstructionMgt/Estimating/CIS/Bid%20Tabs%202025.pdf"
./.venv/bin/python -m src.parse_bidtabs data/raw/bidtabs_2025.pdf
```

Current local build: **2023–2025 = 1,462 projects, ~349k bid lines, ~4,000 pay items.**

## Run the web app (the demo)

```bash
./.venv/bin/python -m src.server          # then open http://localhost:8000
```

Search a pay item → see its full historical unit-price distribution (min/p25/median/
p75/max + quantity-weighted average), a histogram with **your number marked**, a
percentile verdict (competitive / mid / high), a line-total vs. median comparison,
and a median-by-year trend. Zero web dependencies — pure standard library.

## CLI (same engine, no browser)

```bash
python3 -m src.query search asphalt
python3 -m src.query price 441E70000
python3 -m src.query price 441E70000 --since 2025-01-01 --estimate 350.00
```

To ingest a tabular export (CSV/XLSX) instead of a PDF, remap its headers:

```bash
python3 -m src.ingest data/raw/odot_export.xlsx \
  --map "Item Code=item_code,Unit Price=unit_price,Sale Date=sale_date"
```

---

## Data model

| table       | grain                          | key fields                                            |
|-------------|--------------------------------|-------------------------------------------------------|
| `projects`  | one let contract               | sale_date, district, county, work_type, num_bidders   |
| `pay_items` | ODOT item catalog              | item_code, description, unit                          |
| `bid_lines` | project × item × **bidder**    | quantity, unit_price, bidder_rank, is_awarded         |

Keeping the per-bidder grain is what makes "where does my number land" possible — we
retain the whole spread, not just the awarded price. See [`schema.sql`](schema.sql).

---

## Roadmap / open items

- [x] Parse ODOT annual Bid Tabs PDFs into the DB (per-bidder grain) — `src/parse_bidtabs.py`.
- [x] Web app with item search, distribution histogram, percentile benchmarking, year trend.
- [ ] Backfill more years (2001–2022 PDFs already located) for deeper history.
- [ ] Capture **district/county** (derivable from the route prefix, e.g. `DEL-SR 521`)
      to enable regional filtering.
- [ ] Quantity-band filter in the UI (API already supports `min_qty`/`max_qty`) so
      prices compare at similar scale.
- [ ] Inflation / asphalt-index normalization so old prices compare fairly to today.
- [ ] Phase 2: takeoff sheet → full estimate.

## Status

**Phase 1 working** on real ODOT data (2023–2025). Standalone (not tied to HCSS
HeavyBid). `python -m src.server` launches the demo UI.
