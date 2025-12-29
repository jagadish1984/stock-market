#!/usr/bin/env python3
"""
Demo script showing how to use the symbol filtering module.

Run with:
    python demo_filtering.py
"""

from app.filters import (
    load_instruments_master,
    filter_rows,
    is_valid_symbol,
)

def main():
    print("=" * 70)
    print("NSE Market Data Symbol Filtering Demo")
    print("=" * 70)
    
    # 1. Load instruments master
    print("\n1. Loading instruments master...")
    instruments = load_instruments_master("data/instruments_master_sample.csv")
    print(f"   Loaded {len(instruments)} instruments")
    print(f"   Sample symbols: {list(instruments.keys())[:5]}")
    
    # 2. Validate individual symbols
    print("\n2. Validating individual symbols...")
    test_symbols = [
        "RELIANCE",    # Valid
        "AAA",         # In denylist
        "UNKNOWN",     # Not in master
        None,          # Null
        "ABC@123",     # Invalid format
    ]
    
    for symbol in test_symbols:
        is_valid, reason = is_valid_symbol(symbol, instruments)
        status = "✓ VALID" if is_valid else f"✗ REJECTED ({reason})"
        print(f"   {str(symbol):15s} → {status}")
    
    # 3. Filter a batch of market data
    print("\n3. Filtering batch of market data...")
    market_data = [
        {"symbol": "RELIANCE", "price": 2500.50, "volume": 1000000},
        {"symbol": "TCS", "price": 3500.00, "volume": 500000},
        {"symbol": "INFY", "price": 1500.75, "volume": 750000},
        {"symbol": "AAA", "price": 100.00, "volume": 500},      # denylist
        {"symbol": "BBB", "price": 200.00, "volume": 300},      # denylist
        {"symbol": None, "price": 50.00, "volume": 100},        # null
        {"symbol": "UNKNOWN", "price": 200.00, "volume": 0},    # not in master
        {"symbol": "ABC DEF", "price": 150.00, "volume": 50},   # invalid format
    ]
    
    accepted, stats = filter_rows(market_data, instruments)
    
    print(f"\n   Input rows:     {stats.total_rows}")
    print(f"   Accepted rows:  {stats.accepted_rows}")
    print(f"   Rejected rows:  {stats.rejected_rows}")
    
    if stats.rejected_rows > 0:
        print("\n   Rejection breakdown:")
        for reason, count in sorted(stats.rejection_reasons.items(), 
                                    key=lambda x: x[1], reverse=True):
            pct = (count / stats.total_rows * 100)
            print(f"     • {reason:30s}: {count:2d} ({pct:5.1f}%)")
    
    print("\n   Accepted data:")
    for row in accepted:
        print(f"     • {row['symbol']:10s} @ ₹{row['price']:8.2f}  "
              f"vol={row['volume']:,}")
    
    # 4. Custom configuration example
    print("\n4. Custom configuration (allowing multiple series)...")
    
    # Create test data with mixed series (for demo purposes)
    custom_instruments = {
        "RELIANCE": {"series": "EQ", "isin": "INE002A01018", "name": "Reliance", "segment": "NSE", "status": "ACTIVE"},
        "NIFTY-FUT": {"series": "FUT", "isin": "INE000F00001", "name": "Nifty Futures", "segment": "NSE", "status": "ACTIVE"},
        "NIFTY-OPT": {"series": "OPT", "isin": "INE000O00001", "name": "Nifty Options", "segment": "NSE", "status": "ACTIVE"},
    }
    
    test_data = [
        {"symbol": "RELIANCE", "type": "equity"},
        {"symbol": "NIFTY-FUT", "type": "futures"},
        {"symbol": "NIFTY-OPT", "type": "options"},
    ]
    
    # Default: only EQ
    accepted_eq, stats_eq = filter_rows(
        test_data, 
        custom_instruments,
        allowed_series={"EQ"}
    )
    print(f"   With allowed_series=['EQ']: {stats_eq.accepted_rows}/{stats_eq.total_rows} accepted")
    
    # Custom: EQ + FUT + OPT
    accepted_all, stats_all = filter_rows(
        test_data, 
        custom_instruments,
        allowed_series={"EQ", "FUT", "OPT"}
    )
    print(f"   With allowed_series=['EQ', 'FUT', 'OPT']: {stats_all.accepted_rows}/{stats_all.total_rows} accepted")
    
    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
