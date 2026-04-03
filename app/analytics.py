from __future__ import annotations
import math
import json
from pathlib import Path
from typing import Any, List, Dict, Optional
from datetime import date, datetime
from collections import defaultdict

from app.db import get_conn
from app.bulk_deals import get_bulk_block_deals
from app.fii_dii import get_fii_dii_data
from app.fno import get_contract_info, get_fno_symbols, get_option_chain


RESEARCH_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "fundamentals_watchlist.json"


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
            return row[0] if isinstance(row[0], date) else date.fromisoformat(row[0])
        except Exception:
            return None
    return None


def _latest_complete_eod_date(min_symbols: int = 500) -> Optional[date]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trade_date, COUNT(DISTINCT symbol) AS symbol_count
        FROM eod_bars
        GROUP BY trade_date
        ORDER BY trade_date DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return None

    def _coerce_date(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except Exception:
            return None

    for row in rows:
        if row["symbol_count"] >= min_symbols:
            parsed = _coerce_date(row["trade_date"])
            if parsed:
                return parsed

    best_row = max(rows, key=lambda item: item["symbol_count"])
    return _coerce_date(best_row["trade_date"])


def _build_unified(target_date: date) -> List[Dict]:
    snaps = _latest_snapshots_for_date(target_date)
    if snaps:
        return snaps
    eod = _eod_for_date(target_date)
    if eod:
        return eod
    latest = _latest_complete_eod_date() or _latest_eod_date()
    if latest:
        return _eod_for_date(latest)
    return []


def _resolved_market_date(target_date: Optional[date] = None) -> Optional[date]:
    if target_date:
        if _latest_snapshots_for_date(target_date):
            return target_date
        day_rows = _eod_for_date(target_date)
        if len(day_rows) >= 500:
            return target_date
    return _latest_complete_eod_date() or _latest_eod_date()


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
    resolved_date = _resolved_market_date(target_date)
    date_str = resolved_date.isoformat() if resolved_date else None
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


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_research_watchlist() -> List[Dict]:
    if not RESEARCH_DATA_PATH.exists():
        return []
    try:
        payload = json.loads(RESEARCH_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    stocks = payload.get("stocks", [])
    return stocks if isinstance(stocks, list) else []


def _unified_by_symbol(target_date: date) -> Dict[str, Dict]:
    return {
        row.get("symbol"): row
        for row in _build_unified(target_date)
        if row.get("symbol")
    }


def latest_available_date(target_date: Optional[date] = None) -> Optional[str]:
    effective = _resolved_market_date(target_date)
    return effective.isoformat() if effective else None


def _option_spread_pct(leg: Optional[Dict]) -> Optional[float]:
    if not leg:
        return None
    buy_price = _safe_float(leg.get("buyPrice1"))
    sell_price = _safe_float(leg.get("sellPrice1"))
    last_price = _safe_float(leg.get("lastPrice"))
    if buy_price is None or sell_price is None or last_price in (None, 0):
        return None
    spread = sell_price - buy_price
    if spread < 0:
        return None
    return spread / max(last_price, 1.0) * 100


def _atm_option_row(chain_payload: Dict, spot_price: float) -> Optional[Dict]:
    records = chain_payload.get("records") or {}
    rows = records.get("data") or []
    best_row = None
    best_distance = None
    for row in rows:
        strike = _safe_float(row.get("strikePrice"))
        if strike is None:
            continue
        distance = abs(strike - spot_price)
        if best_distance is None or distance < best_distance:
            best_row = row
            best_distance = distance
    return best_row


def _build_option_watch_row(candidate: Dict, expiry: str, chain_payload: Dict) -> Optional[Dict]:
    spot_price = _safe_float(candidate.get("price"))
    if spot_price is None:
        return None

    atm_row = _atm_option_row(chain_payload, spot_price)
    if not atm_row:
        return None

    ce = atm_row.get("CE") or {}
    pe = atm_row.get("PE") or {}
    if not ce or not pe:
        return None

    ce_ltp = _safe_float(ce.get("lastPrice")) or 0.0
    pe_ltp = _safe_float(pe.get("lastPrice")) or 0.0
    ce_volume = _safe_float(ce.get("totalTradedVolume")) or 0.0
    pe_volume = _safe_float(pe.get("totalTradedVolume")) or 0.0
    ce_oi = _safe_float(ce.get("openInterest")) or 0.0
    pe_oi = _safe_float(pe.get("openInterest")) or 0.0
    ce_coi = _safe_float(ce.get("changeinOpenInterest")) or 0.0
    pe_coi = _safe_float(pe.get("changeinOpenInterest")) or 0.0
    ce_spread_pct = _option_spread_pct(ce)
    pe_spread_pct = _option_spread_pct(pe)
    change_pct = _safe_float(candidate.get("change_pct")) or 0.0
    traded_value = _safe_float(candidate.get("traded_value")) or 0.0
    atm_strike = _safe_float(atm_row.get("strikePrice"))
    timestamp = ((chain_payload.get("records") or {}).get("timestamp")) or candidate.get("session_date")

    ce_liquid = ce_volume >= 1000 and ce_oi >= 500 and (ce_spread_pct is None or ce_spread_pct <= 8)
    pe_liquid = pe_volume >= 1000 and pe_oi >= 500 and (pe_spread_pct is None or pe_spread_pct <= 8)

    bullish_score = 0.0
    bearish_score = 0.0
    if change_pct >= 1.0:
        bullish_score += min(change_pct, 12.0)
    if change_pct <= -1.0:
        bearish_score += min(abs(change_pct), 12.0)
    if ce_volume > pe_volume * 1.15:
        bullish_score += 2.5
    if pe_volume > ce_volume * 1.15:
        bearish_score += 2.5
    if ce_coi > 0:
        bullish_score += 2.0
    if pe_coi > 0:
        bearish_score += 2.0
    if ce_liquid and ce_ltp >= 10:
        bullish_score += 2.0
    if pe_liquid and pe_ltp >= 10:
        bearish_score += 2.0
    if traded_value >= 1_000_000_000:
        bullish_score += 1.0
        bearish_score += 1.0

    if bullish_score >= bearish_score + 2 and bullish_score >= 6 and ce_liquid and ce_coi > 0:
        action = "Watch CE"
        option_type = "CE"
        selected_leg = ce
        selected_score = bullish_score
        why = "Spot closed strong, CE volume/OI support the move, and the CE spread looks tradable."
    elif bearish_score >= bullish_score + 2 and bearish_score >= 6 and pe_liquid and pe_coi > 0:
        action = "Watch PE"
        option_type = "PE"
        selected_leg = pe
        selected_score = bearish_score
        why = "Spot closed weak, PE volume/OI support the move, and the PE spread looks tradable."
    else:
        action = "Ignore for now"
        option_type = None
        selected_leg = ce if ce_volume >= pe_volume else pe
        selected_score = max(bullish_score, bearish_score)
        why = "The option chain is mixed or not liquid enough, so this underlying is better skipped for now."

    selected_spread_pct = _option_spread_pct(selected_leg)
    tradability = "Liquid" if (ce_liquid or pe_liquid) else "Weak"
    if action == "Ignore for now" and (ce_liquid or pe_liquid):
        tradability = "Mixed"

    return {
        "symbol": candidate["symbol"],
        "session_date": candidate.get("session_date"),
        "chain_timestamp": timestamp,
        "action": action,
        "spot_price": spot_price,
        "change_pct": change_pct,
        "traded_value": traded_value,
        "nearest_expiry": expiry,
        "atm_strike": int(atm_strike) if atm_strike is not None else None,
        "ce_contract": f'{candidate["symbol"]} {expiry} CE {int(atm_strike)}' if atm_strike is not None else None,
        "pe_contract": f'{candidate["symbol"]} {expiry} PE {int(atm_strike)}' if atm_strike is not None else None,
        "ce_last_price": ce_ltp,
        "pe_last_price": pe_ltp,
        "ce_volume": int(ce_volume),
        "pe_volume": int(pe_volume),
        "ce_open_interest": int(ce_oi),
        "pe_open_interest": int(pe_oi),
        "ce_change_oi": int(ce_coi),
        "pe_change_oi": int(pe_coi),
        "ce_spread_pct": ce_spread_pct,
        "pe_spread_pct": pe_spread_pct,
        "selected_option_type": option_type,
        "selected_option_price": _safe_float(selected_leg.get("lastPrice")),
        "selected_spread_pct": selected_spread_pct,
        "score": round(selected_score, 2),
        "tradability": tradability,
        "why": why,
    }


def data_sources() -> Dict:
    return {
        "official_nse_market_data": {
            "status": "configured_in_code",
            "description": "Core price and activity views are built from NSE-oriented feeds used by this repo.",
            "inputs": [
                "NSE SFTP downloader for official files when credentials are configured",
                "NSE bhavcopy archives for end-of-day equity bars",
                "NSE archive CSVs for participant-wise and bulk/block-deal information",
            ],
        },
        "inferred_layers": {
            "status": "derived",
            "description": "Tomorrow bias and CE/PE watchlists are directional models built from yesterday's market activity and institutional flow, not guaranteed buy calls.",
        },
        "research_layers": {
            "status": "manual_reference",
            "description": "Screener/Tijori-style fundamentals are not fetched live in this repo. They are loaded from a local research file so you can maintain your own trusted inputs.",
            "path": str(RESEARCH_DATA_PATH),
        },
        "warning": "Use this dashboard as a research assistant, not as a promise of future returns.",
    }


def market_brief(target_date: date) -> Dict:
    resolved_date = _resolved_market_date(target_date) or target_date
    overview = market_overview(resolved_date)
    gainers = top_gainers(resolved_date, limit=5)
    losers = top_losers(resolved_date, limit=5)
    active = most_active(resolved_date, limit=5, by="value")
    fii_dii = get_fii_dii_data(target_date) or {}
    bulk = get_bulk_block_deals(target_date) or {}

    fii_net = ((fii_dii.get("fii") or {}).get("net")) or 0
    dii_net = ((fii_dii.get("dii") or {}).get("net")) or 0
    breadth = overview["advancers"] - overview["decliners"]

    if breadth > 0 and fii_net >= 0:
        mood = "Constructive"
    elif breadth < 0 and fii_net < 0:
        mood = "Risk-off"
    else:
        mood = "Mixed"

    return {
        "date": resolved_date.isoformat(),
        "market_mood": mood,
        "overview": overview,
        "leaders": {
            "gainers": gainers,
            "losers": losers,
            "active_by_value": active,
        },
        "institutional_summary": {
            "fii": fii_dii.get("fii"),
            "dii": fii_dii.get("dii"),
            "bulk_deal_summary": bulk.get("summary", {}),
        },
        "notes": [
            "Breadth is based on advancing versus declining symbols in the latest available dataset.",
            "Institutional flow defaults to yesterday because NSE participant files usually publish with a lag.",
        ],
    }


def long_term_candidates(target_date: date, limit: int = 12) -> List[Dict]:
    latest = _unified_by_symbol(target_date)
    research_rows = _load_research_watchlist()
    candidates = []

    for row in research_rows:
        symbol = row.get("symbol")
        market = latest.get(symbol, {})
        last = market.get("last")
        prev_close = market.get("prev_close")
        change_pct = None
        if last not in (None, 0) and prev_close not in (None, 0):
            change_pct = (last - prev_close) / prev_close * 100

        pe = _safe_float(row.get("pe"))
        roce = _safe_float(row.get("roce"))
        debt_to_equity = _safe_float(row.get("debt_to_equity"))
        sales_cagr_3y = _safe_float(row.get("sales_cagr_3y"))
        profit_cagr_3y = _safe_float(row.get("profit_cagr_3y"))
        institutional_score = _safe_float(row.get("institutional_score")) or 0

        score = 0
        reasons = []

        if profit_cagr_3y is not None and profit_cagr_3y >= 12:
            score += 3
            reasons.append("Profit growth is healthy on the 3Y view.")
        if sales_cagr_3y is not None and sales_cagr_3y >= 10:
            score += 2
            reasons.append("Sales growth remains supportive.")
        if roce is not None and roce >= 15:
            score += 2
            reasons.append("ROCE is above the quality threshold.")
        if debt_to_equity is not None and debt_to_equity <= 0.6:
            score += 2
            reasons.append("Leverage is under control.")
        if pe is not None and pe <= 35:
            score += 2
            reasons.append("Valuation is not stretched versus the watchlist rule.")
        if change_pct is not None and change_pct > -3:
            score += 1
        if institutional_score > 0:
            score += 1
            reasons.append("Institutional conviction is positive in the research sheet.")

        if score >= 10:
            label = "High priority"
        elif score >= 7:
            label = "Watch closely"
        else:
            label = "Needs more review"

        candidates.append({
            "symbol": symbol,
            "company_name": row.get("company_name"),
            "sector": row.get("sector"),
            "theme": row.get("theme"),
            "price": last,
            "change_pct": change_pct,
            "pe": pe,
            "roce": roce,
            "debt_to_equity": debt_to_equity,
            "sales_cagr_3y": sales_cagr_3y,
            "profit_cagr_3y": profit_cagr_3y,
            "valuation_view": row.get("valuation_view"),
            "holding_view": row.get("holding_view"),
            "score": score,
            "priority": label,
            "notes": row.get("notes"),
            "reasons": reasons[:3],
        })

    candidates.sort(key=lambda item: (item["score"], item.get("profit_cagr_3y") or -999), reverse=True)
    return candidates[:limit]


def options_watch(target_date: date, limit: int = 12) -> Dict:
    resolved_date = _resolved_market_date(target_date) or target_date
    latest = _unified_by_symbol(resolved_date)

    try:
        fno_symbols = set(get_fno_symbols())
    except Exception:
        fno_symbols = set()

    candidates = []
    for symbol in fno_symbols:
        market = latest.get(symbol)
        if not market:
            continue
        prev_close = market.get("prev_close")
        last = market.get("last")
        if prev_close in (None, 0) or last is None:
            continue
        change_pct = (last - prev_close) / prev_close * 100
        traded_value = _safe_float(market.get("traded_value")) or 0.0
        if traded_value <= 0:
            continue
        candidates.append({
            "symbol": symbol,
            "price": last,
            "change_pct": change_pct,
            "traded_value": traded_value,
            "session_date": resolved_date.isoformat(),
        })

    candidates.sort(key=lambda row: (row["traded_value"], abs(row["change_pct"])), reverse=True)

    rows = []
    for candidate in candidates[: max(limit * 4, 24)]:
        symbol = candidate["symbol"]
        try:
            contract_info = get_contract_info(symbol)
        except Exception:
            continue
        expiry_dates = contract_info.get("expiryDates") or []
        if not expiry_dates:
            continue

        expiry = expiry_dates[0]
        try:
            chain_payload = get_option_chain(symbol, expiry=expiry, instrument_type="Equity")
        except Exception:
            continue
        row = _build_option_watch_row(candidate, expiry, chain_payload)
        if not row:
            continue
        rows.append(row)
        if len(rows) >= max(limit * 2, 12):
            break

    priority = {"Watch CE": 0, "Watch PE": 1, "Ignore for now": 2}
    rows.sort(key=lambda row: (priority.get(row["action"], 99), -row["score"], -(row.get("traded_value") or 0)))

    return {
        "date": resolved_date.isoformat(),
        "warning": "This view uses official NSE option-chain data for real F&O symbols. It is a research watchlist only, not a guaranteed buy call.",
        "rows": rows[:limit],
    }
