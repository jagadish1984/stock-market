#!/usr/bin/env python3
"""
Fetch live stock data from NSE using nsepython library
and populate the database with real market data.
"""

from nsepython import *
from app.db import get_conn
from datetime import date, datetime
import time

def fetch_and_store_nse_data():
    """Fetch live NSE data and store in database"""
    
    print("🔄 Fetching live NSE data...")
    
    # List of popular NSE stocks to fetch
    symbols = [
        # Large Cap
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
        'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK',
        'LT', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'BAJFINANCE',
        
        # Mid/Small Cap - Under 100
        'YESBANK', 'SUZLON', 'TATASTEEL', 'ZEEL', 'SBICARD',
        'VEDL', 'IRCTC', 'COALINDIA', 'SAIL', 'NMDC',
        
        # Additional popular stocks
        'WIPRO', 'ONGC', 'NTPC', 'POWERGRID', 'ULTRACEMCO',
        'TATAMOTORS', 'SUNPHARMA', 'TITAN', 'NESTLEIND', 'TECHM'
    ]
    
    conn = get_conn()
    cur = conn.cursor()
    today = date.today()
    
    success_count = 0
    error_count = 0
    
    for symbol in symbols:
        try:
            print(f"  Fetching {symbol}...", end=' ')
            
            # Try nse_get_advances_declines which gives market-wide data
            try:
                quote = nse_eq(symbol)
            except:
                quote = None
            
            if quote and isinstance(quote, dict):
                # Try to extract price data
                last_price = None
                prev_close = None
                open_price = None
                high = None
                low = None
                volume = 0
                traded_value = 0
                
                # Check for data in different structures
                if 'priceInfo' in quote:
                    price_info = quote['priceInfo']
                    last_price = float(price_info.get('lastPrice', 0))
                    prev_close = float(price_info.get('previousClose', last_price))
                    open_price = float(price_info.get('open', last_price))
                    high_low = price_info.get('intraDayHighLow', {})
                    high = float(high_low.get('max', last_price))
                    low = float(high_low.get('min', last_price))
                elif 'data' in quote and isinstance(quote['data'], list) and len(quote['data']) > 0:
                    data = quote['data'][0]
                    last_price = float(data.get('CH_CLOSING_PRICE', 0))
                    prev_close = float(data.get('CH_PREVIOUS_CLS_PRICE', last_price))
                    open_price = float(data.get('CH_OPENING_PRICE', last_price))
                    high = float(data.get('CH_TRADE_HIGH_PRICE', last_price))
                    low = float(data.get('CH_TRADE_LOW_PRICE', last_price))
                    volume = int(data.get('CH_TOT_TRADED_QTY', 0))
                    traded_value = float(data.get('CH_TOT_TRADED_VAL', 0))
                
                if last_price and last_price > 0:
                    cur.execute('''
                        INSERT OR REPLACE INTO eod_bars 
                        (symbol, trade_date, open, high, low, close, prev_close, volume, traded_value, source_file)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (symbol, today.isoformat(), open_price, high, low, last_price, 
                          prev_close, volume, traded_value, 'nsepython'))
                    
                    print(f"✅ ₹{last_price:.2f}")
                    success_count += 1
                else:
                    print(f"⚠️  No price data")
                    error_count += 1
            else:
                print(f"⚠️  No data")
                error_count += 1
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            error_count += 1
            continue
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"✅ Successfully fetched: {success_count} stocks")
    print(f"❌ Errors: {error_count} stocks")
    print(f"{'='*60}")
    print(f"\n💡 Data saved to database for {today.isoformat()}")
    print(f"🌐 Restart the server to see the latest data!")

if __name__ == '__main__':
    fetch_and_store_nse_data()
