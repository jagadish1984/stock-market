#!/usr/bin/env python3
"""
Migration script to add open, high, low columns to snapshots table.

Run with:
    python migrate_add_ohlc.py
"""

from app.db import get_conn

def migrate():
    """Add open, high, low columns to snapshots table if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()
    
    # Check if columns already exist
    cur.execute("PRAGMA table_info(snapshots)")
    columns = [row[1] for row in cur.fetchall()]
    
    columns_to_add = []
    if 'open' not in columns:
        columns_to_add.append('open')
    if 'high' not in columns:
        columns_to_add.append('high')
    if 'low' not in columns:
        columns_to_add.append('low')
    
    if not columns_to_add:
        print("✅ All OHLC columns already exist in snapshots table")
        conn.close()
        return
    
    # Add missing columns
    for col in columns_to_add:
        cur.execute(f"ALTER TABLE snapshots ADD COLUMN {col} REAL")
        print(f"✅ Added column: {col}")
    
    conn.commit()
    conn.close()
    print(f"\n✅ Migration complete! Added {len(columns_to_add)} columns to snapshots table")

if __name__ == "__main__":
    migrate()
