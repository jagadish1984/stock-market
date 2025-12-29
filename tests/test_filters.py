"""
Unit tests for symbol filtering and validation logic.
"""

import pytest
import tempfile
from pathlib import Path
from app.filters import (
    load_instruments_master,
    is_valid_symbol,
    filter_rows,
    get_instruments_set,
    FilterStats,
    DEFAULT_DENYLIST,
    DEFAULT_ALLOWED_SERIES,
    SYMBOL_PATTERN,
)


@pytest.fixture
def sample_instruments_csv(tmp_path: Path) -> Path:
    """Create a sample instruments master CSV file."""
    csv_file = tmp_path / "instruments.csv"
    csv_content = """symbol,isin,name,series,segment,status
RELIANCE,INE002A01018,Reliance Industries Limited,EQ,NSE,ACTIVE
TCS,INE467B01029,Tata Consultancy Services Limited,EQ,NSE,ACTIVE
INFY,INE009A01021,Infosys Limited,EQ,NSE,ACTIVE
AAA,INE000A00001,Test Company AAA,EQ,NSE,ACTIVE
SBIN,INE062A01020,State Bank of India,EQ,NSE,ACTIVE
FUT-INDEX,INE000F00001,Index Futures,FUT,NSE,ACTIVE
OPT-CALL,INE000O00001,Call Option,OPT,NSE,ACTIVE
"""
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def instruments_master(sample_instruments_csv: Path) -> dict:
    """Load sample instruments master."""
    return load_instruments_master(sample_instruments_csv)


class TestLoadInstrumentsMaster:
    """Tests for load_instruments_master function."""
    
    def test_load_valid_csv(self, sample_instruments_csv: Path):
        """Test loading a valid instruments CSV file."""
        instruments = load_instruments_master(sample_instruments_csv)
        
        assert len(instruments) == 7
        assert "RELIANCE" in instruments
        assert "TCS" in instruments
        assert "INFY" in instruments
        assert "FUT-INDEX" in instruments
        
        reliance = instruments["RELIANCE"]
        assert reliance["isin"] == "INE002A01018"
        assert reliance["name"] == "Reliance Industries Limited"
        assert reliance["series"] == "EQ"
        assert reliance["segment"] == "NSE"
    
    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_instruments_master(tmp_path / "nonexistent.csv")
    
    def test_missing_required_columns(self, tmp_path: Path):
        """Test loading CSV missing required columns raises ValueError."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("symbol,isin\nRELIANCE,INE002A01018\n")
        
        with pytest.raises(ValueError, match="Missing required columns"):
            load_instruments_master(csv_file)
    
    def test_empty_csv_file(self, tmp_path: Path):
        """Test loading an empty CSV file raises ValueError."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        
        with pytest.raises(ValueError, match="empty"):
            load_instruments_master(csv_file)
    
    def test_skip_rows_with_empty_symbol(self, tmp_path: Path):
        """Test that rows with empty symbols are skipped."""
        csv_file = tmp_path / "with_empty.csv"
        csv_file.write_text(
            "symbol,isin,name,series,segment,status\n"
            "RELIANCE,INE002A01018,Reliance,EQ,NSE,ACTIVE\n"
            ",INE999A00001,Empty Symbol,EQ,NSE,ACTIVE\n"
            "TCS,INE467B01029,TCS,EQ,NSE,ACTIVE\n"
        )
        
        instruments = load_instruments_master(csv_file)
        assert len(instruments) == 2
        assert "RELIANCE" in instruments
        assert "TCS" in instruments
    
    def test_case_normalization(self, tmp_path: Path):
        """Test that symbols are normalized to uppercase."""
        csv_file = tmp_path / "case_test.csv"
        csv_file.write_text(
            "symbol,isin,name,series,segment,status\n"
            "reliance,INE002A01018,Reliance,EQ,NSE,ACTIVE\n"
            "TcS,INE467B01029,TCS,eq,NSE,ACTIVE\n"
        )
        
        instruments = load_instruments_master(csv_file)
        assert "RELIANCE" in instruments
        assert "TCS" in instruments
        assert instruments["TCS"]["series"] == "EQ"


class TestSymbolPattern:
    """Tests for SYMBOL_PATTERN regex."""
    
    def test_valid_patterns(self):
        """Test symbols that should match the pattern."""
        valid_symbols = [
            "RELIANCE",
            "TCS",
            "M&M",
            "M&MFIN",
            "L&TFH",
            "3MINDIA",
            "500B1",
            "A",
            "ABCDEFGHIJ",
            "ABC-123",
            "ABC.COM",
            "ABB",
        ]
        for symbol in valid_symbols:
            assert SYMBOL_PATTERN.match(symbol), f"Should match: {symbol}"
    
    def test_invalid_patterns(self):
        """Test symbols that should NOT match the pattern."""
        invalid_symbols = [
            "reliance",  # lowercase
            "abc def",  # space
            "ABC@123",  # invalid char
            "ABC#DEF",  # invalid char
            "абсdefg",  # non-ASCII
            "ABCDEFGHIJKLMNOPQRSTU",  # >20 chars
            "",  # empty
            "ABC_123",  # underscore
        ]
        for symbol in invalid_symbols:
            assert not SYMBOL_PATTERN.match(symbol), f"Should not match: {symbol}"


class TestIsValidSymbol:
    """Tests for is_valid_symbol function."""
    
    def test_null_symbol(self, instruments_master):
        """Test that None and empty symbols are rejected."""
        is_valid, reason = is_valid_symbol(None, instruments_master)
        assert not is_valid
        assert reason == "null_or_empty"
        
        is_valid, reason = is_valid_symbol("", instruments_master)
        assert not is_valid
        assert reason == "null_or_empty"
        
        is_valid, reason = is_valid_symbol("   ", instruments_master)
        assert not is_valid
        assert reason == "null_or_empty"
    
    def test_invalid_format(self, instruments_master):
        """Test that symbols with invalid format are rejected."""
        is_valid, reason = is_valid_symbol("ABC DEF", instruments_master)  # space
        assert not is_valid
        assert reason == "invalid_format"
        
        is_valid, reason = is_valid_symbol("ABC@123", instruments_master)  # invalid char
        assert not is_valid
        assert reason == "invalid_format"
        
        # Symbol with >20 chars
        is_valid, reason = is_valid_symbol("ABCDEFGHIJKLMNOPQRSTU", instruments_master)
        assert not is_valid
        assert reason == "invalid_format"
    
    def test_not_in_instruments_master(self, instruments_master):
        """Test that symbols not in master are rejected."""
        is_valid, reason = is_valid_symbol("UNKNOWN", instruments_master)
        assert not is_valid
        assert reason == "not_in_instruments_master"
    
    def test_disallowed_series(self, instruments_master):
        """Test that symbols with non-EQ series are rejected by default."""
        is_valid, reason = is_valid_symbol("FUT-INDEX", instruments_master)
        assert not is_valid
        assert "disallowed_series" in reason
        assert "FUT" in reason
        
        is_valid, reason = is_valid_symbol("OPT-CALL", instruments_master)
        assert not is_valid
        assert "disallowed_series" in reason
        assert "OPT" in reason
    
    def test_allowed_series_custom(self, instruments_master):
        """Test that custom allowed_series is respected."""
        # FUT-INDEX has series=FUT - should be valid with custom config
        is_valid, reason = is_valid_symbol(
            "FUT-INDEX",
            instruments_master,
            allowed_series={"FUT", "EQ"},
        )
        assert is_valid
        assert reason == ""
        
        # Also test that even with custom series, check 3 (not in master) is enforced
        is_valid, reason = is_valid_symbol(
            "UNKNOWN-STOCK",
            instruments_master,
            allowed_series={"FUT", "EQ"},
        )
        assert not is_valid
        assert reason == "not_in_instruments_master"
    
    def test_in_denylist(self, instruments_master):
        """Test that symbols in denylist are rejected."""
        is_valid, reason = is_valid_symbol("AAA", instruments_master)
        assert not is_valid
        assert reason == "in_denylist"
    
    def test_custom_denylist(self, instruments_master):
        """Test that custom denylist is respected."""
        # RELIANCE is valid with default denylist
        is_valid, reason = is_valid_symbol("RELIANCE", instruments_master)
        assert is_valid
        
        # But rejected with custom denylist
        is_valid, reason = is_valid_symbol(
            "RELIANCE",
            instruments_master,
            denylist={"RELIANCE", "TCS"},
        )
        assert not is_valid
        assert reason == "in_denylist"
    
    def test_valid_symbol(self, instruments_master):
        """Test that valid symbols pass all checks."""
        is_valid, reason = is_valid_symbol("RELIANCE", instruments_master)
        assert is_valid
        assert reason == ""
        
        is_valid, reason = is_valid_symbol("TCS", instruments_master)
        assert is_valid
        assert reason == ""
        
        is_valid, reason = is_valid_symbol("INFY", instruments_master)
        assert is_valid
        assert reason == ""
    
    def test_case_insensitive_input(self, instruments_master):
        """Test that symbol input is case-insensitive (converted to uppercase)."""
        # lowercase 'reliance' gets converted to 'RELIANCE' by the function
        # and RELIANCE is in the master, so it should be valid
        is_valid, reason = is_valid_symbol("reliance", instruments_master)
        assert is_valid
        assert reason == ""
        
        # Mixed case also works
        is_valid, reason = is_valid_symbol("RelIance", instruments_master)
        assert is_valid
        assert reason == ""


class TestFilterRows:
    """Tests for filter_rows function."""
    
    def test_filter_all_valid_rows(self, instruments_master):
        """Test filtering when all rows are valid."""
        rows = [
            {"symbol": "RELIANCE", "price": 2500},
            {"symbol": "TCS", "price": 3500},
            {"symbol": "INFY", "price": 1500},
        ]
        
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert len(accepted) == 3
        assert stats.total_rows == 3
        assert stats.accepted_rows == 3
        assert stats.rejected_rows == 0
        assert len(stats.rejection_reasons) == 0
    
    def test_filter_all_invalid_rows(self, instruments_master):
        """Test filtering when all rows are invalid."""
        rows = [
            {"symbol": None, "price": 100},
            {"symbol": "", "price": 200},
            {"symbol": "UNKNOWN", "price": 300},
        ]
        
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert len(accepted) == 0
        assert stats.total_rows == 3
        assert stats.accepted_rows == 0
        assert stats.rejected_rows == 3
    
    def test_filter_mixed_rows(self, instruments_master):
        """Test filtering with mix of valid and invalid rows."""
        rows = [
            {"symbol": "RELIANCE", "price": 2500},
            {"symbol": "AAA", "price": 100},  # in denylist
            {"symbol": "TCS", "price": 3500},
            {"symbol": None, "price": 50},  # null
            {"symbol": "INFY", "price": 1500},
            {"symbol": "UNKNOWN", "price": 200},  # not in master
        ]
        
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert len(accepted) == 3
        assert stats.total_rows == 6
        assert stats.accepted_rows == 3
        assert stats.rejected_rows == 3
        assert "in_denylist" in stats.rejection_reasons
        assert "null_or_empty" in stats.rejection_reasons
        assert "not_in_instruments_master" in stats.rejection_reasons
    
    def test_filter_with_series_validation(self, instruments_master):
        """Test filtering with series validation."""
        rows = [
            {"symbol": "RELIANCE", "price": 2500},  # EQ - valid
            {"symbol": "FUT-INDEX", "price": 3500},  # FUT - invalid
        ]
        
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert len(accepted) == 1
        assert stats.rejected_rows == 1
        # Check that the rejection reason contains "disallowed_series"
        assert any("disallowed_series" in str(k) for k in stats.rejection_reasons.keys())
    
    def test_filter_custom_symbol_key(self, instruments_master):
        """Test filtering with custom symbol key."""
        rows = [
            {"ticker": "RELIANCE", "price": 2500},
            {"ticker": "TCS", "price": 3500},
        ]
        
        accepted, stats = filter_rows(
            rows,
            instruments_master,
            symbol_key="ticker",
        )
        
        assert len(accepted) == 2
        assert stats.accepted_rows == 2
    
    def test_filter_rejection_counts(self, instruments_master):
        """Test that rejection reasons are counted correctly."""
        rows = [
            {"symbol": None},  # null_or_empty x2
            {"symbol": ""},
            {"symbol": "ABC DEF"},  # invalid_format x1 (space)
            {"symbol": "ABC@123"},  # invalid_format x1 (special char)
            {"symbol": "UNKNOWN"},  # not_in_instruments_master x1
        ]
        
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert stats.rejection_reasons["null_or_empty"] == 2
        assert stats.rejection_reasons["invalid_format"] == 2
        assert stats.rejection_reasons["not_in_instruments_master"] == 1
    
    def test_filter_empty_rows(self, instruments_master):
        """Test filtering empty row list."""
        rows = []
        accepted, stats = filter_rows(rows, instruments_master)
        
        assert len(accepted) == 0
        assert stats.total_rows == 0
        assert stats.accepted_rows == 0
        assert stats.rejected_rows == 0


class TestGetInstrumentsSet:
    """Tests for get_instruments_set function."""
    
    def test_get_instruments_set(self, instruments_master):
        """Test converting instruments dict to set."""
        symbols_set = get_instruments_set(instruments_master)
        
        assert isinstance(symbols_set, set)
        assert "RELIANCE" in symbols_set
        assert "TCS" in symbols_set
        assert "INFY" in symbols_set
        assert len(symbols_set) == 7


class TestFilterStatsDataclass:
    """Tests for FilterStats dataclass."""
    
    def test_filter_stats_creation(self):
        """Test creating FilterStats objects."""
        stats = FilterStats(
            total_rows=100,
            accepted_rows=85,
            rejected_rows=15,
            rejection_reasons={"null_or_empty": 10, "invalid_format": 5},
        )
        
        assert stats.total_rows == 100
        assert stats.accepted_rows == 85
        assert stats.rejected_rows == 15
        assert len(stats.rejection_reasons) == 2


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_end_to_end_filtering(self, sample_instruments_csv: Path):
        """Test complete filtering pipeline."""
        # 1. Load instruments
        instruments = load_instruments_master(sample_instruments_csv)
        
        # 2. Filter rows
        rows = [
            {"symbol": "RELIANCE", "price": 2500},
            {"symbol": "AAA", "price": 100},
            {"symbol": None, "price": 50},
            {"symbol": "UNKNOWN", "price": 200},
        ]
        
        accepted, stats = filter_rows(rows, instruments)
        
        # 3. Verify results
        assert len(accepted) == 1
        assert accepted[0]["symbol"] == "RELIANCE"
        assert stats.total_rows == 4
        assert stats.accepted_rows == 1
        assert stats.rejected_rows == 3
    
    def test_filtering_with_custom_config(self, sample_instruments_csv: Path):
        """Test filtering with custom allowed_series and denylist."""
        instruments = load_instruments_master(sample_instruments_csv)
        
        rows = [
            {"symbol": "RELIANCE", "price": 2500},  # EQ - valid
            {"symbol": "FUT-INDEX", "price": 3500},  # FUT - valid with custom config
            {"symbol": "OPT-CALL", "price": 1000},  # OPT - valid with custom config
        ]
        
        # With custom config allowing FUT and OPT
        accepted, stats = filter_rows(
            rows,
            instruments,
            allowed_series={"EQ", "FUT", "OPT"},
        )
        
        assert len(accepted) == 3
        assert stats.accepted_rows == 3
        assert stats.rejected_rows == 0
