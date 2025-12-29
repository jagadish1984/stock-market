from __future__ import annotations
import math
import json
from typing import List, Dict, Optional
from datetime import date, datetime
from collections import defaultdict

from app.db import get_conn


def _latest_snapshots_for_date(target_date: date) -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    # get latest snapshot per symbol by ts
    cur.execute(
        "SELECT s.symbol, s.open, s.high, s.low, s.last, s.prev_close, s.change_pct, s.volume, s.traded_value FROM snapshots s WHERE date(s.ts)=?",
        (target_date.isoformat(),),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _eod_for_date(target_date: date) -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol, open, high, low, close as last, prev_close, volume, traded_value FROM eod_bars WHERE trade_date=?",
        (target_date.isoformat(),),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _latest_eod_date() -> Optional[date]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT MAX(trade_date) as d FROM eod_bars")
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return date.fromisoformat(row[0])
        except Exception:
            return None
    return None


def _build_unified(target_date: date) -> List[Dict]:
    snaps = _latest_snapshots_for_date(target_date)
    if snaps:
        return snaps
    eod = _eod_for_date(target_date)
    if eod:
        return eod
    latest = _latest_eod_date()
    if latest:
        return _eod_for_date(latest)
    return []


def top_gainers(target_date: date, limit: int = 20) -> List[Dict]:
    data = _build_unified(target_date)
    items = []
    for r in data:
        last = r.get("last")
        prev = r.get("prev_close")
        if last is None or prev in (None, 0):
            continue
        change_pct = (last - prev) / prev * 100
        items.append({
            "symbol": r.get("symbol"),
            "change_pct": change_pct,
            "last": last,
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "prev_close": prev,
            "volume": r.get("volume")
        })
    items.sort(key=lambda x: x["change_pct"], reverse=True)
    return items[:limit]


def top_losers(target_date: date, limit: int = 20) -> List[Dict]:
    data = _build_unified(target_date)
    items = []
    for r in data:
        last = r.get("last")
        prev = r.get("prev_close")
        if last is None or prev in (None, 0):
            continue
        change_pct = (last - prev) / prev * 100
        items.append({
            "symbol": r.get("symbol"),
            "change_pct": change_pct,
            "last": last,
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "prev_close": prev,
            "volume": r.get("volume")
        })
    items.sort(key=lambda x: x["change_pct"])  # ascending
    return items[:limit]


def most_active(target_date: date, limit: int = 20, by: str = "volume") -> List[Dict]:
    data = _build_unified(target_date)
    key = "volume" if by == "volume" else "traded_value"
    items = [ {"symbol": r.get("symbol"), key: r.get(key) or 0} for r in data ]
    items.sort(key=lambda x: x.get(key, 0), reverse=True)
    return items[:limit]


def most_bought_sold(target_date: date, limit: int = 20, mode: str = "real") -> List[Dict]:
    conn = get_conn()
    cur = conn.cursor()
    # check if trades with side exist for date
    cur.execute("SELECT COUNT(*) as c FROM trades WHERE trade_date=? AND side IS NOT NULL", (target_date.isoformat(),))
    has_side = cur.fetchone()[0] > 0
    results = []
    if mode == "real" and has_side:
        # compute net buy per symbol
        cur.execute(
            "SELECT symbol, SUM(CASE WHEN upper(side)='BUY' THEN qty ELSE 0 END) - SUM(CASE WHEN upper(side)='SELL' THEN qty ELSE 0 END) as net_buy FROM trades WHERE trade_date=? GROUP BY symbol ORDER BY net_buy DESC LIMIT ?",
            (target_date.isoformat(), limit),
        )
        rows = cur.fetchall()
        for r in rows:
            results.append({"symbol": r[0], "score": r[1]})
    else:
        # proxy using snapshots/eod
        from datetime import date as _date
        data = _build_unified(target_date)
        proxies = []
        for r in data:
            last = r.get("last")
            prev = r.get("prev_close")
            vol = r.get("volume") or 0
            if last is None or prev in (None, 0):
                continue
            change_pct = (last - prev) / prev * 100
            buy_score = max(change_pct, 0) * math.log1p(vol)
            sell_score = max(-change_pct, 0) * math.log1p(vol)
            proxies.append({"symbol": r.get("symbol"), "buy_score": buy_score, "sell_score": sell_score})
        # normalize buy and sell
        if proxies:
            max_buy = max(p["buy_score"] for p in proxies) or 1
            max_sell = max(p["sell_score"] for p in proxies) or 1
            buy_sorted = sorted(proxies, key=lambda x: x["buy_score"], reverse=True)[:limit]
            sell_sorted = sorted(proxies, key=lambda x: x["sell_score"], reverse=True)[:limit]
            results = {"buy": [{"symbol": p["symbol"], "score": p["buy_score"]/max_buy} for p in buy_sorted], "sell": [{"symbol": p["symbol"], "score": p["sell_score"]/max_sell} for p in sell_sorted]}
    conn.close()
    return results


def symbol_summary(symbol: str, target_date: Optional[date] = None) -> Dict:
    conn = get_conn()
    cur = conn.cursor()
    
    # Try snapshots first
    if target_date:
        cur.execute("SELECT * FROM snapshots WHERE symbol=? AND date(ts)=? ORDER BY ts DESC LIMIT 1", (symbol, target_date.isoformat()))
    else:
        cur.execute("SELECT * FROM snapshots WHERE symbol=? ORDER BY ts DESC LIMIT 1", (symbol,))
    row = cur.fetchone()
    
    # If no snapshot, try eod_bars
    if not row:
        if target_date:
            cur.execute("SELECT symbol, open, high, low, close as last, prev_close, volume, traded_value FROM eod_bars WHERE symbol=? AND trade_date=? ORDER BY trade_date DESC LIMIT 1", (symbol, target_date.isoformat()))
        else:
            cur.execute("SELECT symbol, open, high, low, close as last, prev_close, volume, traded_value FROM eod_bars WHERE symbol=? ORDER BY trade_date DESC LIMIT 1", (symbol,))
        row = cur.fetchone()
    
    conn.close()
    if not row:
        return {"symbol": symbol, "found": False}
    return dict(row)


def get_by_price_range(target_date: date, min_price: float, max_price: float, limit: int = 50) -> List[Dict]:
    """Get stocks within a price range, sorted by % change descending."""
    data = _build_unified(target_date)
    filtered = []
    for r in data:
        last = r.get("last")
        prev = r.get("prev_close")
        if last is None or prev in (None, 0):
            continue
        if min_price <= last <= max_price:
            change_pct = (last - prev) / prev * 100
            filtered.append({
                "symbol": r.get("symbol"),
                "last": last,
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "prev_close": prev,
                "change_pct": change_pct,
                "volume": r.get("volume"),
                "traded_value": r.get("traded_value")
            })
    filtered.sort(key=lambda x: x["change_pct"], reverse=True)
    return filtered[:limit]


def market_overview(target_date: date) -> Dict:
    """Get comprehensive market overview with multiple segments."""
    data = _build_unified(target_date)
    
    overview = {
        "total_stocks": len(data),
        "advancers": 0,
        "decliners": 0,
        "unchanged": 0,
        "segments": {
            "small_cap_10_100": {"count": 0, "avg_change": 0},
            "mid_cap_100_1000": {"count": 0, "avg_change": 0},
            "large_cap_1000_plus": {"count": 0, "avg_change": 0}
        }
    }
    
    segment_changes = {"small_cap_10_100": [], "mid_cap_100_1000": [], "large_cap_1000_plus": []}
    
    for r in data:
        last = r.get("last")
        prev = r.get("prev_close")
        if last is None or prev in (None, 0):
            continue
        
        change_pct = (last - prev) / prev * 100
        
        if change_pct > 0.1:
            overview["advancers"] += 1
        elif change_pct < -0.1:
            overview["decliners"] += 1
        else:
            overview["unchanged"] += 1
        
        # Categorize by price
        if 10 <= last <= 100:
            segment_changes["small_cap_10_100"].append(change_pct)
        elif 100 < last <= 1000:
            segment_changes["mid_cap_100_1000"].append(change_pct)
        elif last > 1000:
            segment_changes["large_cap_1000_plus"].append(change_pct)
    
    # Calculate averages
    for segment, changes in segment_changes.items():
        if changes:
            overview["segments"][segment]["count"] = len(changes)
            overview["segments"][segment]["avg_change"] = sum(changes) / len(changes)
    
    return overview


def search_symbols(query: str, limit: int = 20, target_date: Optional[date] = None) -> List[Dict]:
    """Search symbols by substring match on latest available EOD date.
    Returns rows with OHLC, last, prev_close, volume, traded_value.
    """
    if not query:
        return []
    q = query.strip().upper()
    conn = get_conn()
    cur = conn.cursor()
    date_str = None
    if target_date:
        date_str = target_date.isoformat()
    else:
        cur.execute("SELECT MAX(trade_date) FROM eod_bars")
        row = cur.fetchone()
        date_str = row and row[0]
    if not date_str:
        conn.close()
        return []
    cur.execute(
        """
        SELECT symbol, open, high, low, close as last, prev_close, volume, traded_value
        FROM eod_bars
        WHERE trade_date=? AND symbol LIKE ?
        ORDER BY symbol
        LIMIT ?
        """,
        (date_str, f"%{q}%", limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
