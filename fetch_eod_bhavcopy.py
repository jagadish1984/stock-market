#!/usr/bin/env python3
from __future__ import annotations

import sys

from app.eod_refresh import refresh_latest_eod


def main():
    result = refresh_latest_eod(max_lookback_days=12)
    if result.get("updated"):
        print(f"Downloaded NSE EOD for {result['trade_date']} ({result['source_kind']})")
        print(f"Imported {result['rows_imported']} EOD rows into eod_bars")
        return
    print(result.get("reason", "No update performed"))
    if result.get("trade_date"):
        print(f"Latest available trade date checked: {result['trade_date']}")
    sys.exit(1)

if __name__ == "__main__":
    main()
