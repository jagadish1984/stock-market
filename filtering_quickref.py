"""
Quick reference for NSE symbol filtering.

See app/FILTERS_README.md for full documentation.
"""

# =============================================================================
# QUICK START
# =============================================================================

from app.filters import load_instruments_master, filter_rows, is_valid_symbol
from app.config import settings

# 1. Load instruments master (do this once at startup)
instruments = load_instruments_master("data/instruments_master_sample.csv")

# 2. Validate a single symbol
is_valid, reason = is_valid_symbol("RELIANCE", instruments)
if not is_valid:
    print(f"Rejected: {reason}")

# 3. Filter a batch of rows
rows = [
    {"symbol": "RELIANCE", "price": 2500},
    {"symbol": "AAA", "price": 100},  # rejected
]
accepted, stats = filter_rows(rows, instruments)
print(f"Accepted {stats.accepted_rows} of {stats.total_rows} rows")


# =============================================================================
# VALIDATION RULES (in order)
# =============================================================================

# 1. Not null/empty
# 2. Regex: ^[A-Z0-9&.\-]{1,20}$ (uppercase, 1-20 chars)
# 3. Exists in instruments master
# 4. Series in allowed list (default: EQ)
# 5. Not in denylist (default: AAA, BBB, CCC, TEST, DUMMY)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variables (.env):
# INSTRUMENTS_MASTER_PATH=data/instruments_master.csv
# ALLOWED_SERIES=EQ
# SYMBOL_DENYLIST=AAA,BBB,CCC,TEST,DUMMY
# ENABLE_SYMBOL_FILTERING=true

# Access in code:
# settings.INSTRUMENTS_MASTER_PATH
# settings.ALLOWED_SERIES          # Set[str]
# settings.SYMBOL_DENYLIST         # Set[str]
# settings.ENABLE_SYMBOL_FILTERING # bool


# =============================================================================
# CUSTOM CONFIGURATION
# =============================================================================

# Override defaults per-call
accepted, stats = filter_rows(
    rows,
    instruments,
    allowed_series={"EQ", "FUT", "OPT"},  # Allow multiple series
    denylist={"TEST", "DUMMY"},            # Custom denylist
    symbol_key="ticker",                   # Use different key
)


# =============================================================================
# REJECTION REASONS
# =============================================================================

# - null_or_empty: Symbol is None or ""
# - invalid_format: Doesn't match regex
# - not_in_instruments_master: Symbol not found
# - disallowed_series_<SERIES>: Wrong series
# - in_denylist: In configured denylist


# =============================================================================
# FILTER STATISTICS
# =============================================================================

accepted, stats = filter_rows(rows, instruments)

# stats.total_rows: int
# stats.accepted_rows: int
# stats.rejected_rows: int
# stats.rejection_reasons: Dict[str, int]

# Example:
# {
#   "not_in_instruments_master": 150,
#   "in_denylist": 75,
#   "null_or_empty": 20
# }


# =============================================================================
# INSTRUMENTS MASTER CSV FORMAT
# =============================================================================

# Required columns: symbol, isin, name, series, segment, status
# Example:
#
# symbol,isin,name,series,segment,status
# RELIANCE,INE002A01018,Reliance Industries Limited,EQ,NSE,ACTIVE
# TCS,INE467B01029,Tata Consultancy Services Limited,EQ,NSE,ACTIVE


# =============================================================================
# INTEGRATION WITH INGESTION
# =============================================================================

# Load once at module/startup level
instruments_master = {}
if settings.ENABLE_SYMBOL_FILTERING and settings.INSTRUMENTS_MASTER_PATH:
    instruments_master = load_instruments_master(settings.INSTRUMENTS_MASTER_PATH)

def ingest_market_data(records):
    """Ingest with filtering."""
    if settings.ENABLE_SYMBOL_FILTERING and instruments_master:
        records, stats = filter_rows(
            records,
            instruments_master,
            allowed_series=settings.ALLOWED_SERIES,
            denylist=settings.SYMBOL_DENYLIST,
        )
    
    # Process only accepted records
    for record in records:
        insert_into_db(record)


# =============================================================================
# TESTING
# =============================================================================

# Run tests:
# pytest tests/test_filters.py -v

# Run demo:
# python demo_filtering.py
