#!/usr/bin/env python3
"""
Download latest available NSE Equity Bhavcopy (official EOD file)
from NSE archives and load it into the eod_bars table.

URL pattern:
  https://archives.nseindia.com/content/historical/EQUITIES/YYYY/MM/CMDDMMMYYYYbhav.csv.zip

This script tries recent past dates (up to 10 business days back)
until it finds a file.
"""
from __future__ import annotations
import csv
import io
import sys
import zipfile
import requests
from datetime import date, timedelta, datetime
from typing import Optional

from app.db import get_conn

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
        if d.weekday() < 5:  # Monday=0..Friday=4
            tried += 1
            yield d


def build_url(d: date) -> str:
    DD = d.strftime("%d")
    MMM = d.strftime("%b").upper()
    YYYY = d.strftime("%Y")
    return BASE.replace("{YYYY}", YYYY).replace("{MMM}", MMM).replace("{DD}", DD)


def find_latest_file(max_lookback_days: int = 12) -> Optional[tuple[date, bytes, str]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    for d in prev_business_days(date.today(), max_lookback_days):
        url = build_url(d)
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200 and r.content:
                return d, r.content, "zip_bhav"
        except Exception:
            pass
        # Try newer sec_bhavdata_full format (CSV, not zipped)
        url2 = SEC_BHAV.replace("{DDMMYYYY}", d.strftime("%d%m%Y"))
        try:
            r2 = session.get(url2, timeout=30)
            if r2.status_code == 200 and r2.content and len(r2.content) > 1000:
                return d, r2.content, "sec_bhav"
        except Exception:
            pass
    return None


def parse_bhav_zip(content: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        # Find CSV inside
        csv_name = None
        for n in zf.namelist():
            if n.lower().endswith("bhav.csv"):
                csv_name = n
                break
        if not csv_name:
            raise RuntimeError("CSV not found in downloaded ZIP")
        with zf.open(csv_name) as fh:
            data = fh.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(data))
            out: list[dict] = []
            for r in reader:
                # Expected columns: SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN
                series = (r.get("SERIES") or "").strip()
                if series and series != "EQ":
                    continue
                try:
                    ts = datetime.strptime(r.get("TIMESTAMP").strip(), "%d-%b-%Y").date()
                except Exception:
                    # some files have TIMESTAMP like 28-DEC-2025
                    ts = datetime.strptime(r.get("TIMESTAMP").strip(), "%d-%b-%Y").date()
                def f(x):
                    x = (x or "").replace(",", "").strip()
                    if not x:
                        return None
                    try:
                        if "." in x:
                            return float(x)
                        return int(x)
                    except Exception:
                        try:
                            return float(x)
                        except Exception:
                            return None
                out.append({
                    "symbol": r.get("SYMBOL").strip(),
                    "trade_date": ts.isoformat(),
                    "open": f(r.get("OPEN")),
                    "high": f(r.get("HIGH")),
                    "low": f(r.get("LOW")),
                    "close": f(r.get("CLOSE")),
                    "prev_close": f(r.get("PREVCLOSE")),
                    "volume": f(r.get("TOTTRDQTY")) or 0,
                    "traded_value": f(r.get("TOTTRDVAL")) or 0.0,
                })
            return out


def parse_sec_bhav_csv(content: bytes) -> list[dict]:
    txt = content.decode("utf-8", errors="replace")
    # Some files have trailing commas and spaces in header; normalize by stripping keys/values
    stream = io.StringIO(txt)
    reader = csv.DictReader(stream)
    out: list[dict] = []
    for r in reader:
        # Normalize keys and values by stripping
        rr = { (k or "").strip(): (v or "").strip() for k,v in r.items() }
        series = rr.get("SERIES") or rr.get("SERIES ") or rr.get(" SERIES")
        if series and series != "EQ":
            continue
        sym = rr.get("SYMBOL")
        if not sym:
            continue
        # Date field
        date_str = rr.get("DATE1") or rr.get(" DATE1")
        ts = None
        if date_str:
            ts = datetime.strptime(date_str.strip(), "%d-%b-%Y").date().isoformat()
        def f(x):
            x = (x or "").replace(",", "").strip()
            if not x:
                return None
            try:
                if "." in x:
                    return float(x)
                return int(x)
            except Exception:
                try:
                    return float(x)
                except Exception:
                    return None
        out.append({
            "symbol": sym.strip(),
            "trade_date": ts,
            "open": f(rr.get("OPEN_PRICE") or rr.get(" OPEN_PRICE")),
            "high": f(rr.get("HIGH_PRICE") or rr.get(" HIGH_PRICE")),
            "low": f(rr.get("LOW_PRICE") or rr.get(" LOW_PRICE")),
            "close": f(rr.get("CLOSE_PRICE") or rr.get(" CLOSE_PRICE")),
            "prev_close": f(rr.get("PREV_CLOSE") or rr.get(" PREV_CLOSE")),
            "volume": f(rr.get("TTL_TRD_QNTY") or rr.get(" TTL_TRD_QNTY")) or 0,
            # TURNOVER_LACS is in Lakhs; convert to absolute value in rupees if desired; we'll keep as lakhs*1e5
            "traded_value": (f(rr.get("TURNOVER_LACS") or rr.get(" TURNOVER_LACS")) or 0.0) * 100000,
        })
    return out


def load_into_db(rows: list[dict], source: str):
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    for r in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO eod_bars
            (symbol, trade_date, open, high, low, close, prev_close, volume, traded_value, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["symbol"],
                r["trade_date"],
                r.get("open"),
                r.get("high"),
                r.get("low"),
                r.get("close"),
                r.get("prev_close"),
                r.get("volume", 0),
                r.get("traded_value", 0.0),
                source,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def main():
    found = find_latest_file(max_lookback_days=12)
    if not found:
        print("❌ Could not find recent bhavcopy in the last 12 business days")
        sys.exit(1)
    d, content, kind = found
    print(f"📦 Downloaded NSE EOD for {d.isoformat()} ({kind})")
    if kind == "zip_bhav":
        rows = parse_bhav_zip(content)
    else:
        rows = parse_sec_bhav_csv(content)
    if not rows:
        print("⚠️ No rows parsed from bhavcopy")
        sys.exit(2)
    count = load_into_db(rows, source="bhavcopy_archive")
    print(f"✅ Imported {count} EOD rows into eod_bars")

if __name__ == "__main__":
    main()
