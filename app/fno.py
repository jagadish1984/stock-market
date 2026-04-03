from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional

import requests


LOG = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
}


@lru_cache(maxsize=1)
def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get("https://www.nseindia.com/option-chain", timeout=20)
    except Exception:
        LOG.debug("Initial NSE option-chain page warmup failed", exc_info=True)
    return session


@lru_cache(maxsize=1)
def get_fno_symbols() -> List[str]:
    session = _create_session()
    response = session.get("https://www.nseindia.com/api/master-quote?type=fno", timeout=30)
    response.raise_for_status()
    payload = response.json()
    return [symbol for symbol in payload if isinstance(symbol, str)]


@lru_cache(maxsize=256)
def get_contract_info(symbol: str) -> Dict:
    session = _create_session()
    response = session.get(
        f"https://www.nseindia.com/api/option-chain-contract-info?symbol={requests.utils.quote(symbol)}",
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


@lru_cache(maxsize=512)
def get_option_chain(symbol: str, expiry: Optional[str] = None, instrument_type: str = "Equity") -> Dict:
    session = _create_session()
    params = {
        "type": instrument_type,
        "symbol": symbol,
    }
    if expiry:
        params["expiry"] = expiry
    response = session.get(
        "https://www.nseindia.com/api/option-chain-v3",
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def nearest_strike(strikes: List[str], underlying_price: float) -> int | None:
    parsed = []
    for strike in strikes:
        try:
            parsed.append(int(float(strike)))
        except Exception:
            continue
    if not parsed:
        return None
    return min(parsed, key=lambda strike: abs(strike - underlying_price))
