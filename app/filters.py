"""
Symbol filtering and validation logic for NSE market data ingestion.

This module provides functionality to:
1. Load and maintain an instruments master (valid NSE symbols)
2. Validate symbols against multiple criteria
3. Filter market data rows with detailed rejection tracking
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

LOG = logging.getLogger(__name__)

# Default denylist for placeholder/test symbols
DEFAULT_DENYLIST: Set[str] = {"AAA", "BBB", "CCC", "TEST", "DUMMY"}

# Default allowed series for equities
DEFAULT_ALLOWED_SERIES: Set[str] = {"EQ"}

# Symbol validation regex: uppercase alphanumeric + & . - only, 1-20 chars
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&\.\-]{1,20}$")


@dataclass
class FilterStats:
    """Statistics from filtering operation."""
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    rejection_reasons: Dict[str, int]  # reason -> count


def load_instruments_master(
    path: str | Path,
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> Dict[str, Dict[str, str]]:
    """
    Load instruments master from a CSV file.
    
    Expected columns: symbol, isin, name, series, segment, [status (optional)]
    
    Args:
        path: Path to the instruments master file
        delimiter: CSV delimiter (default: comma)
        encoding: File encoding (default: utf-8)
    
    Returns:
        Dictionary mapping symbol -> {isin, name, series, segment, status}
    
    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If required columns are missing
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Instruments master file not found: {path}")
    
    instruments: Dict[str, Dict[str, str]] = {}
    
    try:
        import csv
        with open(path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            
            if reader.fieldnames is None:
                raise ValueError("CSV file is empty")
            
            # Normalize column names
            fieldnames = [fn.strip().lower() if fn else "" for fn in reader.fieldnames]
            required_cols = {"symbol", "isin", "name", "series", "segment"}
            if not required_cols.issubset(set(fieldnames)):
                missing = required_cols - set(fieldnames)
                raise ValueError(f"Missing required columns: {missing}")
            
            for row_idx, row in enumerate(reader, start=2):  # start=2 because 1 is header
                # Normalize keys to lowercase
                normalized_row = {k.strip().lower(): v for k, v in row.items() if k}
                symbol = normalized_row.get("symbol", "").strip().upper()
                
                if not symbol:
                    LOG.warning(f"Row {row_idx}: empty symbol, skipping")
                    continue
                
                instruments[symbol] = {
                    "isin": normalized_row.get("isin", "").strip(),
                    "name": normalized_row.get("name", "").strip(),
                    "series": normalized_row.get("series", "").strip().upper(),
                    "segment": normalized_row.get("segment", "").strip(),
                    "status": normalized_row.get("status", "").strip().upper(),
                }
        
        LOG.info(f"Loaded {len(instruments)} instruments from {path}")
    except Exception as e:
        LOG.error(f"Error loading instruments master from {path}: {e}")
        raise
    
    return instruments


def is_valid_symbol(
    symbol: str | None,
    instruments_master: Dict[str, Dict[str, str]],
    *,
    allowed_series: Set[str] | None = None,
    denylist: Set[str] | None = None,
) -> Tuple[bool, str]:
    """
    Validate a symbol against multiple criteria.
    
    Validation rules (in order):
    1. Symbol is not None/empty
    2. Symbol matches regex ^[A-Z0-9&.-]{1,20}$ (uppercase only)
    3. Symbol exists in instruments master
    4. Symbol's series is in allowed_series (default: {"EQ"})
    5. Symbol is not in denylist (default: {"AAA", "BBB", "CCC", "TEST", "DUMMY"})
    
    Args:
        symbol: The symbol to validate
        instruments_master: Dictionary of {symbol: {isin, name, series, ...}}
        allowed_series: Set of allowed series (default: {"EQ"})
        denylist: Set of symbols to reject (default: DEFAULT_DENYLIST)
    
    Returns:
        Tuple of (is_valid, rejection_reason)
        If valid: (True, "")
        If invalid: (False, reason_string)
    """
    if allowed_series is None:
        allowed_series = DEFAULT_ALLOWED_SERIES
    if denylist is None:
        denylist = DEFAULT_DENYLIST
    
    # Check 1: Not null/empty
    if not symbol or not str(symbol).strip():
        return False, "null_or_empty"
    
    symbol = str(symbol).strip().upper()
    
    # Check 2: Regex pattern match
    if not SYMBOL_PATTERN.match(symbol):
        return False, "invalid_format"
    
    # Check 3: Exists in instruments master
    if symbol not in instruments_master:
        return False, "not_in_instruments_master"
    
    # Check 4: Series validation
    instrument = instruments_master[symbol]
    series = instrument.get("series", "").upper()
    if series not in allowed_series:
        return False, f"disallowed_series_{series}"
    
    # Check 5: Not in denylist
    if symbol in denylist:
        return False, "in_denylist"
    
    return True, ""


def filter_rows(
    rows: List[Dict],
    instruments_master: Dict[str, Dict[str, str]],
    *,
    symbol_key: str = "symbol",
    allowed_series: Set[str] | None = None,
    denylist: Set[str] | None = None,
) -> Tuple[List[Dict], FilterStats]:
    """
    Filter market data rows based on symbol validation.
    
    Args:
        rows: List of market data records (dicts)
        instruments_master: Dictionary of {symbol: {isin, name, series, ...}}
        symbol_key: Key in each row containing the symbol (default: "symbol")
        allowed_series: Set of allowed series (default: {"EQ"})
        denylist: Set of symbols to reject (default: DEFAULT_DENYLIST)
    
    Returns:
        Tuple of (accepted_rows, FilterStats)
        where FilterStats contains counts and rejection breakdown
    """
    if allowed_series is None:
        allowed_series = DEFAULT_ALLOWED_SERIES
    if denylist is None:
        denylist = DEFAULT_DENYLIST
    
    accepted: List[Dict] = []
    rejection_counts: Dict[str, int] = defaultdict(int)
    
    for row in rows:
        symbol = row.get(symbol_key)
        is_valid, reason = is_valid_symbol(
            symbol,
            instruments_master,
            allowed_series=allowed_series,
            denylist=denylist,
        )
        
        if is_valid:
            accepted.append(row)
        else:
            rejection_counts[reason] += 1
    
    total = len(rows)
    accepted_count = len(accepted)
    rejected_count = total - accepted_count
    
    stats = FilterStats(
        total_rows=total,
        accepted_rows=accepted_count,
        rejected_rows=rejected_count,
        rejection_reasons=dict(rejection_counts),
    )
    
    # Log statistics
    log_filter_stats(stats)
    
    return accepted, stats


def log_filter_stats(stats: FilterStats) -> None:
    """Log filtering statistics with detailed breakdown."""
    LOG.info(
        f"Filtering complete: total={stats.total_rows}, "
        f"accepted={stats.accepted_rows}, rejected={stats.rejected_rows}"
    )
    
    if stats.rejected_rows > 0:
        LOG.info("Rejection reasons:")
        # Sort by count (descending) for better visibility
        sorted_reasons = sorted(
            stats.rejection_reasons.items(), key=lambda x: x[1], reverse=True
        )
        for reason, count in sorted_reasons:
            pct = (count / stats.total_rows * 100) if stats.total_rows > 0 else 0
            LOG.info(f"  {reason}: {count} ({pct:.1f}%)")


def get_instruments_set(instruments_master: Dict[str, Dict[str, str]]) -> Set[str]:
    """
    Convert instruments master dict to a simple set of symbols.
    Useful for quick membership checks.
    """
    return set(instruments_master.keys())
