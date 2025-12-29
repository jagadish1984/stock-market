from datetime import date
from app.analytics import top_gainers, top_losers, most_active, most_bought_sold
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
