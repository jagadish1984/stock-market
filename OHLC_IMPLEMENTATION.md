# OHLC (Open, High, Low, Close) Implementation

## Summary

Added **Open, High, Low, and Close (OHLC)** values display for each stock across all views in the NSE market data dashboard.

## Changes Made

### 1. Database Schema Updates

**`app/db.py`**
- Updated `snapshots` table to include `open`, `high`, `low` columns
- These columns already existed in `eod_bars` table

**Migration:**
- Created `migrate_add_ohlc.py` to add columns to existing databases
- Run with: `python migrate_add_ohlc.py`

### 2. Analytics Module Updates

**`app/analytics.py`**
- Updated `_latest_snapshots_for_date()` to fetch open, high, low from snapshots
- Updated `_eod_for_date()` to fetch open, high, low from eod_bars
- Updated `top_gainers()` to include OHLC values in response
- Updated `top_losers()` to include OHLC values in response
- Updated `get_by_price_range()` to include OHLC values in response
- Updated `symbol_summary()` to fetch from both snapshots and eod_bars with OHLC

### 3. Frontend Display Updates

**`frontend/index.html`**
- Updated **Top Gainers** table to show: Symbol, LTP, Open, High, Low, Change %, Volume
- Updated **Top Losers** table to show: Symbol, LTP, Open, High, Low, Change %, Volume
- Updated **Price Range** tables (₹10-100, ₹100-1000, ₹1000+) to show OHLC values
- Updated **Search** results to show: Symbol, LTP, Open, High, Low, Prev Close, Volume, Value

### 4. Sample Data & Utilities

**Created files:**
- `data/sample_eod_with_ohlc.csv` - Sample EOD data with OHLC values for 10 stocks
- `import_sample_data.py` - Script to import sample OHLC data into database
- `migrate_add_ohlc.py` - Migration script to add OHLC columns to existing database

## API Response Example

### Before (without OHLC):
```json
{
  "symbol": "RELIANCE",
  "change_pct": 1.21,
  "last": 2540.25,
  "volume": 5000000
}
```

### After (with OHLC):
```json
{
  "symbol": "RELIANCE",
  "change_pct": 1.21,
  "last": 2540.25,
  "open": 2500.00,
  "high": 2550.50,
  "low": 2485.75,
  "prev_close": 2510.00,
  "volume": 5000000
}
```

## Frontend Display

The frontend now displays:

| Symbol | LTP | Open | High | Low | Change % | Volume |
|--------|-----|------|------|-----|----------|--------|
| SBIN | ₹562.50 | ₹550.00 | ₹565.75 | ₹548.25 | +1.35% | 1.00 Cr |
| RELIANCE | ₹2540.25 | ₹2500.00 | ₹2550.50 | ₹2485.75 | +1.21% | 50.00 L |
| ITC | ₹400.75 | ₹395.00 | ₹402.50 | ₹393.25 | +0.94% | 80.00 L |

## Setup Instructions

### For Existing Installations:

1. **Run the migration:**
```bash
python migrate_add_ohlc.py
```

2. **Import sample data (optional):**
```bash
python import_sample_data.py
```

3. **Restart the server:**
```bash
uvicorn app.main:app --reload
```

4. **View the updated dashboard:**
```
http://localhost:8000/frontend/index.html
```

### For New Installations:

The schema changes are already included in `init_db()`, so no migration is needed.

## Data Sources

OHLC values are populated from:
1. **EOD (End of Day) Bars** - `eod_bars` table (primary source)
2. **Snapshots** - `snapshots` table (if OHLC data is provided)

The system automatically:
- Fetches snapshots first if available for the date
- Falls back to EOD bars if no snapshots exist
- Shows `null` or `-` for OHLC values when not available

## Testing

All existing tests pass:
```bash
pytest tests/ -v
# 31 passed
```

API endpoints now return OHLC:
- `/api/top-gainers?limit=N`
- `/api/top-losers?limit=N`
- `/api/price-range?min_price=X&max_price=Y&limit=N`
- `/api/symbol/{symbol}`

## Benefits

✅ **Complete market data view** - Users can see intraday range (Open-High-Low-Close)
✅ **Better price context** - Understand if current price is near high/low
✅ **Volatility insight** - High-Low spread shows daily volatility
✅ **Professional display** - Similar to NSE, BSE, and other financial platforms
✅ **Backward compatible** - Handles missing OHLC data gracefully (shows null/-)

## Example Usage

The sample data includes 10 major stocks with realistic OHLC values:
- RELIANCE, TCS, INFY, SBIN, HDFC
- ICICIBANK, BHARTIARTL, WIPRO, HDFCBANK, ITC

View them at: **http://localhost:8000/frontend/index.html**

Check different price ranges:
- **₹10-100 tab** - No stocks (sample data is higher priced)
- **₹100-1000 tab** - Shows SBIN, ITC, etc.
- **₹1000+ tab** - Shows RELIANCE, TCS, INFY, etc.

All views now include Open, High, Low columns for complete market analysis!
