from __future__ import annotations
import sqlite3
import os
from datetime import datetime
from typing import Optional
from app.config import settings


DB_PATH = os.path.abspath(os.path.join(os.getcwd(), settings.DATABASE_URL.replace("sqlite:///", "")))


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    # files_processed
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files_processed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product TEXT,
            remote_path TEXT,
            filename TEXT,
            size INTEGER,
            checksum TEXT,
            downloaded_at TIMESTAMP,
            parsed_at TIMESTAMP,
            status TEXT,
            error TEXT
        )
        """
    )
    # instruments
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS instruments (
            symbol TEXT PRIMARY KEY,
            isin TEXT,
            name TEXT,
            series TEXT,
            segment TEXT,
            updated_at TIMESTAMP
        )
        """
    )
    # eod_bars
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eod_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            trade_date DATE,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            prev_close REAL,
            volume INTEGER,
            traded_value REAL,
            source_file INTEGER
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_eod_symbol_date ON eod_bars(symbol, trade_date)")

    # trades
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            trade_date DATE,
            trade_time TEXT,
            price REAL,
            qty INTEGER,
            side TEXT,
            traded_value REAL,
            source_file INTEGER
        )
        """
    )

    # snapshots
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            ts TIMESTAMP,
            open REAL,
            high REAL,
            low REAL,
            last REAL,
            prev_close REAL,
            change REAL,
            change_pct REAL,
            volume INTEGER,
            traded_value REAL,
            source_file INTEGER
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snap_symbol_ts ON snapshots(symbol, ts)")

    # analytics cache
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            metric TEXT,
            symbol TEXT,
            rank INTEGER,
            score REAL,
            extra_json TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def mark_file_downloaded(product: str, remote_path: str, filename: str, size: int, checksum: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow()
    cur.execute(
        "INSERT INTO files_processed (product, remote_path, filename, size, checksum, downloaded_at, status) VALUES (?,?,?,?,?,?,?)",
        (product, remote_path, filename, size, checksum, now, "downloaded"),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def update_file_status(file_id: int, status: str, parsed_at: Optional[datetime] = None, error: Optional[str] = None) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE files_processed SET status=?, parsed_at=?, error=? WHERE id=?",
        (status, parsed_at, error, file_id),
    )
    conn.commit()
    conn.close()
