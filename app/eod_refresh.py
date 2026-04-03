from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import date, datetime, timedelta
from typing import Optional

import requests

from app.db import get_conn


LOG = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}

BASE = "https://archives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MMM}/CM{DD}{MMM}{YYYY}bhav.csv.zip"
SEC_BHAV = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv"


def prev_business_days(start: date, count: int = 10):
    d = start
    tried = 0
    while tried < count:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            tried += 1
            yield d


def build_url(d: date) -> str:
    dd = d.strftime("%d")
    mmm = d.strftime("%b").upper()
    yyyy = d.strftime("%Y")
    return BASE.replace("{YYYY}", yyyy).replace("{MMM}", mmm).replace("{DD}", dd)


def latest_db_trade_date() -> Optional[date]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT MAX(trade_date) FROM eod_bars")
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    return row[0] if isinstance(row[0], date) else date.fromisoformat(row[0])


def find_latest_file(max_lookback_days: int = 12) -> Optional[tuple[date, bytes, str]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    for d in prev_business_days(date.today(), max_lookback_days):
        url = build_url(d)
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200 and response.content:
                return d, response.content, "zip_bhav"
        except Exception:
            LOG.debug("ZIP bhavcopy fetch failed for %s", d, exc_info=True)

        url2 = SEC_BHAV.replace("{DDMMYYYY}", d.strftime("%d%m%Y"))
        try:
            response2 = session.get(url2, timeout=30)
            if response2.status_code == 200 and response2.content and len(response2.content) > 1000:
                return d, response2.content, "sec_bhav"
        except Exception:
            LOG.debug("sec_bhav fetch failed for %s", d, exc_info=True)
    return None


def _to_number(value: Optional[str]):
    value = (value or "").replace(",", "").strip()
    if not value:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def parse_bhav_zip(content: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_name = next((n for n in zf.namelist() if n.lower().endswith("bhav.csv")), None)
        if not csv_name:
            raise RuntimeError("CSV not found in downloaded ZIP")
        with zf.open(csv_name) as fh:
            data = fh.read().decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(data))
    rows = []
    for record in reader:
        series = (record.get("SERIES") or "").strip()
        if series and series != "EQ":
            continue
        ts = datetime.strptime(record.get("TIMESTAMP").strip(), "%d-%b-%Y").date()
        rows.append({
            "symbol": record.get("SYMBOL").strip(),
            "trade_date": ts.isoformat(),
            "open": _to_number(record.get("OPEN")),
            "high": _to_number(record.get("HIGH")),
            "low": _to_number(record.get("LOW")),
            "close": _to_number(record.get("CLOSE")),
            "prev_close": _to_number(record.get("PREVCLOSE")),
            "volume": _to_number(record.get("TOTTRDQTY")) or 0,
            "traded_value": _to_number(record.get("TOTTRDVAL")) or 0.0,
        })
    return rows


def parse_sec_bhav_csv(content: bytes) -> list[dict]:
    txt = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(txt))
    rows = []
    for record in reader:
        normalized = {(k or "").strip(): (v or "").strip() for k, v in record.items()}
        series = normalized.get("SERIES") or normalized.get("SERIES ") or normalized.get(" SERIES")
        if series and series != "EQ":
            continue
        symbol = normalized.get("SYMBOL")
        if not symbol:
            continue
        date_str = normalized.get("DATE1") or normalized.get(" DATE1")
        trade_date = datetime.strptime(date_str.strip(), "%d-%b-%Y").date().isoformat() if date_str else None
        rows.append({
            "symbol": symbol.strip(),
            "trade_date": trade_date,
            "open": _to_number(normalized.get("OPEN_PRICE") or normalized.get(" OPEN_PRICE")),
            "high": _to_number(normalized.get("HIGH_PRICE") or normalized.get(" HIGH_PRICE")),
            "low": _to_number(normalized.get("LOW_PRICE") or normalized.get(" LOW_PRICE")),
            "close": _to_number(normalized.get("CLOSE_PRICE") or normalized.get(" CLOSE_PRICE")),
            "prev_close": _to_number(normalized.get("PREV_CLOSE") or normalized.get(" PREV_CLOSE")),
            "volume": _to_number(normalized.get("TTL_TRD_QNTY") or normalized.get(" TTL_TRD_QNTY")) or 0,
            "traded_value": (_to_number(normalized.get("TURNOVER_LACS") or normalized.get(" TURNOVER_LACS")) or 0.0) * 100000,
        })
    return rows


def load_into_db(rows: list[dict], source: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    for row in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO eod_bars
            (symbol, trade_date, open, high, low, close, prev_close, volume, traded_value, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["symbol"],
                row["trade_date"],
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("prev_close"),
                row.get("volume", 0),
                row.get("traded_value", 0.0),
                source,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def refresh_latest_eod(max_lookback_days: int = 12) -> dict:
    found = find_latest_file(max_lookback_days=max_lookback_days)
    if not found:
        return {"updated": False, "reason": "No recent bhavcopy found"}

    trade_date, content, kind = found
    current_latest = latest_db_trade_date()
    if current_latest and current_latest >= trade_date:
        return {
            "updated": False,
            "reason": "Database already has this trade date",
            "trade_date": trade_date.isoformat(),
            "source_kind": kind,
        }

    rows = parse_bhav_zip(content) if kind == "zip_bhav" else parse_sec_bhav_csv(content)
    if not rows:
        return {"updated": False, "reason": "Downloaded file had no rows", "trade_date": trade_date.isoformat()}

    count = load_into_db(rows, source=f"nse_{kind}")
    LOG.info("Imported %s EOD rows for %s from %s", count, trade_date.isoformat(), kind)
    return {
        "updated": True,
        "trade_date": trade_date.isoformat(),
        "rows_imported": count,
        "source_kind": kind,
    }
