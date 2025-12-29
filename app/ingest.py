from __future__ import annotations
import os
import logging
import json
from datetime import datetime
from typing import Optional

from app.db import get_conn, update_file_status
from app.parsers.csv_parser import CSVParser
from app.parsers.binary_placeholder import BinaryPlaceholderParser

LOG = logging.getLogger(__name__)


def _get_unparsed_files() -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM files_processed WHERE status='downloaded'")
    rows = cur.fetchall()
    conn.close()
    return rows


def ingest_once():
    rows = _get_unparsed_files()
    for r in rows:
        fid = r["id"]
        product = r["product"]
        filename = r["filename"]
        local_path = os.path.join(os.getcwd(), "data", "downloads", product, filename)
        try:
            if not os.path.exists(local_path):
                update_file_status(fid, "missing_local", None, "local file missing")
                continue

            # choose parser by extension
            ext = os.path.splitext(filename)[1].lower()
            parser = None
            if ext in (".csv", ".txt", ".tsv"):
                parser = CSVParser()
            else:
                parser = BinaryPlaceholderParser()

            records = parser.parse_file(local_path)
            # basic ingest heuristics: decide where to store records
            conn = get_conn()
            cur = conn.cursor()
            # figure out record shape by first record
            if records:
                sample = records[0]
                if "price" in sample or ("qty" in sample and "price" in sample):
                    # trades
                    for rec in records:
                        cur.execute(
                            "INSERT INTO trades (symbol, trade_date, trade_time, price, qty, side, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?)",
                            (
                                rec.get("symbol"),
                                rec.get("trade_date"),
                                rec.get("trade_time"),
                                rec.get("price") or rec.get("last"),
                                rec.get("qty") or rec.get("volume"),
                                rec.get("side"),
                                rec.get("traded_value"),
                                fid,
                            ),
                        )
                elif "last" in sample or "close" in sample:
                    for rec in records:
                        cur.execute(
                            "INSERT INTO snapshots (symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                rec.get("symbol"),
                                datetime.utcnow(),
                                rec.get("last") or rec.get("close"),
                                rec.get("prev_close"),
                                None,
                                None,
                                rec.get("volume") or 0,
                                rec.get("traded_value") or 0.0,
                                fid,
                            ),
                        )
                else:
                    # fallback: store as snapshot with minimal fields
                    for rec in records:
                        cur.execute(
                            "INSERT INTO snapshots (symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                rec.get("symbol"),
                                datetime.utcnow(),
                                rec.get("last") or rec.get("close"),
                                rec.get("prev_close"),
                                None,
                                None,
                                rec.get("volume") or 0,
                                rec.get("traded_value") or 0.0,
                                fid,
                            ),
                        )

            conn.commit()
            conn.close()
            update_file_status(fid, "parsed", datetime.utcnow(), None)
        except RuntimeError as e:
            # binary placeholder raises RuntimeError when spec missing
            LOG.warning("Parsing error for file %s: %s", filename, e)
            update_file_status(fid, "parse_error", None, str(e))
        except Exception as e:
            LOG.exception("Unexpected ingest error for %s: %s", filename, e)
            update_file_status(fid, "parse_error", None, str(e))
