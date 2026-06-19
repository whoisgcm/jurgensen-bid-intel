# jurgensen-bid-intel

A standalone tool that turns **public Ohio DOT (ODOT) bid data** into a searchable
unit-price history, so estimators can see **where any number lands relative to what
the market has actually bid** for the same pay item, quantity, district, and era.

Built for The Jurgensen Company (heavy-highway / asphalt, ODOT District 8 region).

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

## Quick start

No dependencies needed for CSV (standard library only). Python 3.9+.

```bash
# 1. Load the included sample dataset (realistic ODOT-style asphalt data)
python3 -m src.ingest tests/sample_bid_data.csv

# 2. Find a pay item
python3 -m src.query search asphalt

# 3. See the historical price distribution for an item
python3 -m src.query price 441E10100

# 4. Narrow to District 8, 2024 only
python3 -m src.query price 441E10100 --district 08 --since 2024-01-01

# 5. Benchmark your own number against history (Phase 3 preview)
python3 -m src.query price 441E10100 --estimate 105.00
```

To ingest a real ODOT export with different column headers, remap them:

```bash
python3 -m src.ingest data/raw/odot_export.xlsx \
  --map "Item Code=item_code,Unit Price=unit_price,Sale Date=sale_date"
```

(`.xlsx` ingestion needs `pip install -r requirements.txt`; CSV needs nothing.)

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

- [ ] Confirm the exact column layout of ODOT's current Excel export and lock the
      default header map (sample uses our canonical names).
- [ ] Build the scheduled ingest from BidX / ODOT for bidder-level tabs (the
      aggregated price layer is Excel-exportable; per-bidder tabs may need scraping).
- [ ] Inflation / asphalt-index normalization so old prices compare fairly to today.
- [ ] Phase 2 takeoff sheet → full estimate.

## Status

Phase 1 scaffold. Standalone (not tied to HCSS HeavyBid). Runs end-to-end on the
included sample data.
