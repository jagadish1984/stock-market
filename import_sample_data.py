#!/usr/bin/env python3
"""
Script to import sample OHLC data into the database for testing.

Run with:
    python import_sample_data.py
"""

import csv
from datetime import date
from app.db import get_conn, init_db

def import_sample_data():
    """Import sample EOD data with OHLC values."""
    init_db()
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Read sample data
    with open('data/sample_eod_with_ohlc.csv', 'r') as f:
        reader = csv.DictReader(f)
        today = date.today()
        
        for row in reader:
            cur.execute(
                """INSERT INTO eod_bars 
                   (symbol, trade_date, open, high, low, close, prev_close, volume, traded_value, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row['symbol'],
                    today.isoformat(),
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    float(row['prev_close']),
                    int(row['volume']),
                    float(row['traded_value']),
                    None
                )
            )
    
    conn.commit()
    rows_added = cur.rowcount
    conn.close()
    
    print(f"✅ Successfully imported {rows_added} rows of sample OHLC data")
    print(f"📅 Data date: {today.isoformat()}")
    print(f"🔍 View at: http://localhost:8000/frontend/index.html")

if __name__ == "__main__":
    import_sample_data()
