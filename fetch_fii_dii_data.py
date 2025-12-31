#!/usr/bin/env python3
"""
Fetch FII/DII (Foreign and Domestic Institutional Investor) data from NSE.
This shows which stocks institutional investors are buying/selling.
"""

import requests
import csv
import io
from datetime import date, timedelta
from typing import Optional

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def fetch_fii_dii_data(target_date: date):
    """Fetch FII/DII participant-wise trading data"""
    
    print(f"📊 Fetching FII/DII data for {target_date.isoformat()}...\n")
    
    # FII/DII Derivatives Volume
    vol_url = f'https://archives.nseindia.com/content/nsccl/fao_participant_vol_{target_date.strftime("%d%m%Y")}.csv'
    
    # FII/DII Open Interest
    oi_url = f'https://archives.nseindia.com/content/nsccl/fao_participant_oi_{target_date.strftime("%d%m%Y")}.csv'
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    print("=" * 80)
    print("📈 FII/DII DERIVATIVES TRADING VOLUME")
    print("=" * 80)
    
    try:
        r = session.get(vol_url, timeout=30)
        if r.status_code == 200:
            parse_participant_data(r.content, "VOLUME")
        else:
            print(f"❌ Volume data not available (Status: {r.status_code})")
    except Exception as e:
        print(f"❌ Error fetching volume data: {e}")
    
    print("\n" + "=" * 80)
    print("📊 FII/DII OPEN INTEREST")
    print("=" * 80)
    
    try:
        r = session.get(oi_url, timeout=30)
        if r.status_code == 200:
            parse_participant_data(r.content, "OPEN INTEREST")
        else:
            print(f"❌ OI data not available (Status: {r.status_code})")
    except Exception as e:
        print(f"❌ Error fetching OI data: {e}")
    
    # Try to get bulk deals (shows large institutional trades)
    print("\n" + "=" * 80)
    print("💰 BULK DEALS (Large Institutional Trades)")
    print("=" * 80)
    
    bulk_url = f'https://archives.nseindia.com/content/equities/bulk_{target_date.strftime("%d%m%Y")}.csv'
    try:
        r = session.get(bulk_url, timeout=30)
        if r.status_code == 200:
            parse_bulk_deals(r.content)
        else:
            print(f"❌ Bulk deals data not available yet")
    except Exception as e:
        print(f"❌ Error fetching bulk deals: {e}")


def parse_participant_data(content: bytes, data_type: str):
    """Parse FII/DII participant-wise data"""
    txt = content.decode('utf-8', errors='replace')
    
    # Parse CSV - skip first line (title)
    lines = txt.strip().split('\n')
    if len(lines) < 3:
        print("Insufficient data")
        return
    
    # Find header line (has "Client Type")
    header_idx = 0
    for i, line in enumerate(lines):
        if 'Client Type' in line:
            header_idx = i
            break
    
    csv_data = '\n'.join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_data))
    
    print(f"\n{data_type} - Participant-wise Activity:\n")
    
    fii_row = None
    dii_row = None
    client_row = None
    total_row = None
    
    for row in reader:
        client_type = row.get('Client Type', '').strip()
        if client_type == 'FII':
            fii_row = row
        elif client_type == 'DII':
            dii_row = row
        elif client_type == 'Client':
            client_row = row
        elif client_type == 'TOTAL':
            total_row = row
    
    # Display FII data
    if fii_row:
        print("🌍 FOREIGN INSTITUTIONAL INVESTORS (FII):")
        print(f"   Index Futures: Long {fii_row.get('Future Index Long', '0'):>12} | Short {fii_row.get('Future Index Short', '0'):>12}")
        print(f"   Stock Futures: Long {fii_row.get('Future Stock Long', '0'):>12} | Short {fii_row.get('Future Stock Short', '0'):>12}")
        
        idx_call_long = int(fii_row.get('Option Index Call Long', '0').replace(',', ''))
        idx_put_long = int(fii_row.get('Option Index Put Long', '0').replace(',', ''))
        idx_call_short = int(fii_row.get('Option Index Call Short', '0').replace(',', ''))
        idx_put_short = int(fii_row.get('Option Index Put Short', '0').replace(',', ''))
        
        total_long = int(fii_row.get('Total Long Contracts', '0').replace(',', ''))
        total_short = int(fii_row.get('Total Short Contracts', '0').replace(',', ''))
        net_position = total_long - total_short
        
        print(f"   Index Options: Call {idx_call_long:>15,} | Put {idx_put_long:>15,}")
        print(f"   Total Contracts: Long {total_long:>12,} | Short {total_short:>12,}")
        print(f"   Net Position: {net_position:>+15,} {'📈 BULLISH' if net_position > 0 else '📉 BEARISH'}")
    
    # Display DII data
    if dii_row:
        print("\n🏛️  DOMESTIC INSTITUTIONAL INVESTORS (DII):")
        print(f"   Index Futures: Long {dii_row.get('Future Index Long', '0'):>12} | Short {dii_row.get('Future Index Short', '0'):>12}")
        print(f"   Stock Futures: Long {dii_row.get('Future Stock Long', '0'):>12} | Short {dii_row.get('Future Stock Short', '0'):>12}")
        
        total_long = int(dii_row.get('Total Long Contracts', '0').replace(',', ''))
        total_short = int(dii_row.get('Total Short Contracts', '0').replace(',', ''))
        net_position = total_long - total_short
        
        print(f"   Total Contracts: Long {total_long:>12,} | Short {total_short:>12,}")
        print(f"   Net Position: {net_position:>+15,} {'📈 BULLISH' if net_position > 0 else '📉 BEARISH'}")


def parse_bulk_deals(content: bytes):
    """Parse bulk deals data to show large institutional trades"""
    txt = content.decode('utf-8', errors='replace')
    
    lines = txt.strip().split('\n')
    
    # Find CSV start
    data_start = 0
    for i, line in enumerate(lines):
        if 'Symbol' in line or 'SYMBOL' in line:
            data_start = i
            break
    
    if data_start == 0:
        print("No bulk deals data found")
        return
    
    csv_data = '\n'.join(lines[data_start:])
    reader = csv.DictReader(io.StringIO(csv_data))
    
    print("\nLARGE TRADES (Bulk Deals):\n")
    
    count = 0
    for row in reader:
        row = {k.strip(): v.strip() for k, v in row.items() if k}
        
        symbol = row.get('Symbol') or row.get('SYMBOL', '')
        if not symbol:
            continue
        
        client = row.get('Client Name') or row.get('CLIENT NAME', '')
        quantity = row.get('Quantity') or row.get('QUANTITY', '')
        trade_type = row.get('Buy/Sell') or row.get('BUY/SELL', '')
        
        print(f"📌 {symbol:15} | {trade_type:4} | Qty: {quantity:>15} | {client}")
        count += 1
    
    if count == 0:
        print("No bulk deals recorded for this date")
    else:
        print(f"\n✅ Total bulk deals: {count}")


def main():
    # Try Dec 30 first (Dec 31 data not available yet)
    target_date = date(2025, 12, 30)
    
    print(f"\n🔍 FII/DII ACTIVITY ANALYSIS - {target_date.strftime('%B %d, %Y')}")
    print("=" * 80)
    print("\nNOTE: This shows institutional investor activity in derivatives.")
    print("For stock-specific cash market activity, bulk deals are most relevant.\n")
    
    fetch_fii_dii_data(target_date)
    
    print("\n" + "=" * 80)
    print("📝 INTERPRETATION:")
    print("=" * 80)
    print("""
• FII/DII Volume: Total contracts traded in derivatives market
• Open Interest: Outstanding derivative positions (bullish if increasing)
• Bulk Deals: Large cash market transactions (>0.5% of total shares)
  - Look for repeated buyers/sellers to identify institutional activity
  - Multiple buys = Accumulation (bullish)
  - Multiple sells = Distribution (bearish)
    """)


if __name__ == "__main__":
    main()
