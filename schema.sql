-- jurgensen-bid-intel : ODOT bid price-history schema (Phase 1)
--
-- Three tables model the ODOT bid universe:
--   projects   one row per let contract
--   pay_items  ODOT standardized item catalog (code/description/unit)
--   bid_lines  every bidder's unit price for every item on every project
--
-- The grain of bid_lines (project x item x bidder) is what makes the
-- "where does my number land vs. history" benchmarking possible: we keep
-- the full spread, not just the winning price.

CREATE TABLE IF NOT EXISTS projects (
    project_id    TEXT PRIMARY KEY,   -- ODOT contract / sale id
    sale_date     TEXT,               -- ISO YYYY-MM-DD (the letting date)
    district      TEXT,               -- ODOT district, "01".."12"
    county        TEXT,
    work_type     TEXT,               -- e.g. "Asphalt Resurfacing"
    total_award   REAL,               -- awarded contract total ($)
    num_bidders   INTEGER
);

CREATE TABLE IF NOT EXISTS pay_items (
    item_code     TEXT PRIMARY KEY,   -- e.g. "441E10100"
    description   TEXT,
    unit          TEXT                -- e.g. "CY", "SY", "LS", "LB"
);

CREATE TABLE IF NOT EXISTS bid_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT REFERENCES projects(project_id),
    item_code     TEXT REFERENCES pay_items(item_code),
    quantity      REAL,               -- plan quantity for this item on this project
    unit_price    REAL,               -- this bidder's unit price ($/unit)
    bidder_rank   INTEGER,            -- 1 = apparent low bidder
    is_awarded    INTEGER             -- 1 if this bidder won the contract, else 0
);

CREATE INDEX IF NOT EXISTS idx_bid_lines_item    ON bid_lines(item_code);
CREATE INDEX IF NOT EXISTS idx_bid_lines_project ON bid_lines(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_date     ON projects(sale_date);
