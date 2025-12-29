from __future__ import annotations
from typing import List, Dict


class BaseParser:
    """Parsers should implement parse_file and return list[dict] with standardized fields.

    Standard fields (as available):
    symbol, trade_date, trade_time(optional), open, high, low, close, last, prev_close,
    volume, traded_value, buy_qty(optional), sell_qty(optional), oi(optional), delivery_qty(optional), delivery_pct(optional)
    """

    def parse_file(self, path: str) -> List[Dict]:
        raise NotImplementedError()
