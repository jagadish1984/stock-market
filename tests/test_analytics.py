from datetime import date
from app.analytics import top_gainers, top_losers, most_active, most_bought_sold, _build_option_watch_row
from app.db import get_conn


def seed_snapshots(conn):
    cur = conn.cursor()
    # symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file
    cur.execute("INSERT INTO snapshots (symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
                ("AAA", "2025-12-28 10:00:00", 110.0, 100.0, None, None, 1000, 110000.0, 1))
    cur.execute("INSERT INTO snapshots (symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
                ("BBB", "2025-12-28 10:00:00", 95.0, 100.0, None, None, 500, 47500.0, 1))
    cur.execute("INSERT INTO snapshots (symbol, ts, last, prev_close, change, change_pct, volume, traded_value, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
                ("CCC", "2025-12-28 10:00:00", 200.0, 180.0, None, None, 2000, 400000.0, 1))
    conn.commit()


def test_top_gainers_and_losers():
    conn = get_conn()
    seed_snapshots(conn)
    g = top_gainers(date(2025, 12, 28), limit=5)
    assert g[0]["symbol"] == "CCC"
    l = top_losers(date(2025, 12, 28), limit=5)
    assert l[0]["symbol"] == "BBB"


def test_most_active_and_pressure():
    conn = get_conn()
    seed_snapshots(conn)
    m = most_active(date(2025, 12, 28), limit=3, by="volume")
    assert m[0]["symbol"] == "CCC"
    pressure = most_bought_sold(date(2025, 12, 28), limit=3, mode="pressure")
    assert isinstance(pressure, dict)
    assert "buy" in pressure and "sell" in pressure


def test_build_option_watch_row_marks_bullish_setup():
    candidate = {
        "symbol": "RELIANCE",
        "price": 1348.0,
        "change_pct": 2.8,
        "traded_value": 3_000_000_000.0,
        "session_date": "2026-03-27",
    }
    chain_payload = {
        "records": {
            "timestamp": "27-Mar-2026 15:30:00",
            "data": [
                {
                    "strikePrice": 1350,
                    "CE": {
                        "lastPrice": 44.5,
                        "totalTradedVolume": 4800,
                        "openInterest": 2500,
                        "changeinOpenInterest": 600,
                        "buyPrice1": 44.0,
                        "sellPrice1": 44.8,
                    },
                    "PE": {
                        "lastPrice": 39.0,
                        "totalTradedVolume": 1200,
                        "openInterest": 1800,
                        "changeinOpenInterest": -200,
                        "buyPrice1": 38.8,
                        "sellPrice1": 39.6,
                    },
                }
            ],
        }
    }

    row = _build_option_watch_row(candidate, "30-Mar-2026", chain_payload)

    assert row is not None
    assert row["action"] == "Watch CE"
    assert row["tradability"] == "Liquid"
    assert row["atm_strike"] == 1350


def test_build_option_watch_row_marks_ignore_when_chain_is_mixed():
    candidate = {
        "symbol": "SBIN",
        "price": 820.0,
        "change_pct": 0.4,
        "traded_value": 1_500_000_000.0,
        "session_date": "2026-03-27",
    }
    chain_payload = {
        "records": {
            "timestamp": "27-Mar-2026 15:30:00",
            "data": [
                {
                    "strikePrice": 820,
                    "CE": {
                        "lastPrice": 5.0,
                        "totalTradedVolume": 80,
                        "openInterest": 120,
                        "changeinOpenInterest": 5,
                        "buyPrice1": 4.4,
                        "sellPrice1": 5.6,
                    },
                    "PE": {
                        "lastPrice": 4.8,
                        "totalTradedVolume": 75,
                        "openInterest": 100,
                        "changeinOpenInterest": 3,
                        "buyPrice1": 4.1,
                        "sellPrice1": 5.7,
                    },
                }
            ],
        }
    }

    row = _build_option_watch_row(candidate, "30-Mar-2026", chain_payload)

    assert row is not None
    assert row["action"] == "Ignore for now"
