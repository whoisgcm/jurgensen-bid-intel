"""SQLite connection and schema initialization for jurgensen-bid-intel."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "bid_intel.db"
SCHEMA = ROOT / "schema.sql"


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Open a connection, ensuring the schema exists."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn
