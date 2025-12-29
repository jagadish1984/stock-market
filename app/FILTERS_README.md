# Symbol Filtering for NSE Market Data

This module provides production-ready filtering logic for NSE market data ingestion.

## Features

1. **Instruments Master Management**: Load and maintain a master list of valid NSE symbols
2. **Multi-criteria Validation**: 
   - Regex pattern matching (uppercase alphanumeric + `&`, `.`, `-`)
   - Series validation (EQ, FUT, OPT, etc.)
   - Denylist filtering
   - Instruments master lookup
3. **Detailed Rejection Tracking**: Categorizes and counts rejection reasons
4. **Type-safe**: Full type hints throughout
5. **Configurable**: Environment-based configuration
6. **Well-tested**: Comprehensive test suite with 28 passing tests

## Quick Start

### 1. Configure Environment

Add to your `.env` file:

```bash
# Path to instruments master CSV
INSTRUMENTS_MASTER_PATH=data/instruments_master.csv

# Allowed series (comma-separated)
ALLOWED_SERIES=EQ

# Symbol denylist
SYMBOL_DENYLIST=AAA,BBB,CCC,TEST,DUMMY

# Enable/disable filtering
ENABLE_SYMBOL_FILTERING=true
```

### 2. Create Instruments Master File

Create a CSV file at `data/instruments_master.csv`:

```csv
symbol,isin,name,series,segment,status
RELIANCE,INE002A01018,Reliance Industries Limited,EQ,NSE,ACTIVE
TCS,INE467B01029,Tata Consultancy Services Limited,EQ,NSE,ACTIVE
INFY,INE009A01021,Infosys Limited,EQ,NSE,ACTIVE
SBIN,INE062A01020,State Bank of India,EQ,NSE,ACTIVE
HDFC,INE040A01034,HDFC Bank Limited,EQ,NSE,ACTIVE
```

### 3. Usage Example

```python
from app.filters import (
    load_instruments_master,
    filter_rows,
    is_valid_symbol,
)
from app.config import settings

# Load instruments master once at startup
instruments = load_instruments_master(
    settings.INSTRUMENTS_MASTER_PATH or "data/instruments_master.csv"
)

# Validate individual symbols
is_valid, reason = is_valid_symbol(
    "RELIANCE",
    instruments,
    allowed_series=settings.ALLOWED_SERIES,
    denylist=settings.SYMBOL_DENYLIST,
)

if is_valid:
    print(f"RELIANCE is valid")
else:
    print(f"RELIANCE rejected: {reason}")

# Filter a batch of market data rows
market_data = [
    {"symbol": "RELIANCE", "price": 2500, "volume": 1000000},
    {"symbol": "AAA", "price": 100, "volume": 500},  # in denylist
    {"symbol": None, "price": 50, "volume": 100},    # null
    {"symbol": "UNKNOWN", "price": 200, "volume": 0}, # not in master
]

accepted, stats = filter_rows(
    market_data,
    instruments,
    allowed_series=settings.ALLOWED_SERIES,
    denylist=settings.SYMBOL_DENYLIST,
)

print(f"Total: {stats.total_rows}")
print(f"Accepted: {stats.accepted_rows}")
print(f"Rejected: {stats.rejected_rows}")
print(f"Rejection breakdown: {stats.rejection_reasons}")
```

## Integration with Ingestion Pipeline

To integrate with your existing ingestion pipeline:

```python
from app.filters import load_instruments_master, filter_rows
from app.config import settings

# Load instruments once at startup
instruments_master = {}
if settings.ENABLE_SYMBOL_FILTERING and settings.INSTRUMENTS_MASTER_PATH:
    instruments_master = load_instruments_master(settings.INSTRUMENTS_MASTER_PATH)

def ingest_market_data(records):
    """Ingest market data with filtering."""
    
    if settings.ENABLE_SYMBOL_FILTERING and instruments_master:
        # Filter records
        accepted, stats = filter_rows(
            records,
            instruments_master,
            allowed_series=settings.ALLOWED_SERIES,
            denylist=settings.SYMBOL_DENYLIST,
        )
        
        # Process only accepted records
        for record in accepted:
            # Insert into database
            insert_into_db(record)
    else:
        # No filtering - process all
        for record in records:
            insert_into_db(record)
```

## Validation Rules

Symbols are validated against the following criteria (in order):

1. **Not Null/Empty**: Symbol must not be None or empty string
2. **Format**: Must match regex `^[A-Z0-9&.\-]{1,20}$` (uppercase only, 1-20 characters)
3. **Instruments Master**: Symbol must exist in the instruments master
4. **Series**: Symbol's series must be in `allowed_series` (default: `{"EQ"}`)
5. **Denylist**: Symbol must not be in the denylist (default: `{"AAA", "BBB", "CCC", "TEST", "DUMMY"}`)

## API Reference

### `load_instruments_master(path, *, delimiter=',', encoding='utf-8')`

Load instruments master from a CSV file.

**Parameters:**
- `path`: Path to CSV file
- `delimiter`: CSV delimiter (default: `,`)
- `encoding`: File encoding (default: `utf-8`)

**Returns:** Dict mapping symbol → {isin, name, series, segment, status}

**Raises:**
- `FileNotFoundError`: If file doesn't exist
- `ValueError`: If required columns are missing

---

### `is_valid_symbol(symbol, instruments_master, *, allowed_series=None, denylist=None)`

Validate a single symbol against all criteria.

**Parameters:**
- `symbol`: The symbol to validate
- `instruments_master`: Dictionary from `load_instruments_master()`
- `allowed_series`: Set of allowed series (default: `{"EQ"}`)
- `denylist`: Set of denied symbols (default: `{"AAA", "BBB", "CCC", "TEST", "DUMMY"}`)

**Returns:** Tuple of `(is_valid: bool, rejection_reason: str)`

---

### `filter_rows(rows, instruments_master, *, symbol_key='symbol', allowed_series=None, denylist=None)`

Filter a list of market data rows.

**Parameters:**
- `rows`: List of dictionaries containing market data
- `instruments_master`: Dictionary from `load_instruments_master()`
- `symbol_key`: Key in each row containing the symbol (default: `'symbol'`)
- `allowed_series`: Set of allowed series (default: `{"EQ"}`)
- `denylist`: Set of denied symbols

**Returns:** Tuple of `(accepted_rows: List[Dict], stats: FilterStats)`

---

### `FilterStats` (dataclass)

Statistics from filtering operation.

**Fields:**
- `total_rows: int` - Total number of input rows
- `accepted_rows: int` - Number of accepted rows
- `rejected_rows: int` - Number of rejected rows
- `rejection_reasons: Dict[str, int]` - Mapping of reason → count

## Testing

Run the comprehensive test suite:

```bash
pytest tests/test_filters.py -v
```

Test coverage includes:
- Instruments master loading (various formats and edge cases)
- Symbol pattern validation
- Individual symbol validation
- Batch filtering
- Custom configuration
- Integration scenarios

## Performance Considerations

- **Load Once**: Load instruments master once at startup, not per-request
- **Memory**: Instruments master is kept in memory as a dict for O(1) lookups
- **Batch Processing**: `filter_rows()` is optimized for batch operations
- **Logging**: Detailed logging with counts and percentages

## Common Rejection Reasons

- `null_or_empty`: Symbol is None or empty string
- `invalid_format`: Symbol doesn't match the regex pattern
- `not_in_instruments_master`: Symbol not found in master
- `disallowed_series_<SERIES>`: Symbol's series not allowed
- `in_denylist`: Symbol is in the configured denylist

## Example Output

```
2025-12-28 INFO Filtering complete: total=10000, accepted=9750, rejected=250
2025-12-28 INFO Rejection reasons:
2025-12-28 INFO   not_in_instruments_master: 150 (1.5%)
2025-12-28 INFO   in_denylist: 75 (0.8%)
2025-12-28 INFO   null_or_empty: 20 (0.2%)
2025-12-28 INFO   invalid_format: 5 (0.1%)
```
