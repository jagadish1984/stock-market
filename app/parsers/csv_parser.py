from __future__ import annotations
from typing import List, Dict
import csv
from datetime import datetime

from app.parsers.base import BaseParser


class CSVParser(BaseParser):
    def parse_file(self, path: str) -> List[Dict]:
        results: List[Dict] = []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            for row in reader:
                # normalize keys to lowercase
                r = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                rec: Dict = {}
                # basic mapping heuristics
                rec["symbol"] = r.get("symbol") or r.get("scrip") or r.get("ticker")
                date_raw = r.get("date") or r.get("trade_date")
                if date_raw:
                    try:
                        rec["trade_date"] = datetime.fromisoformat(date_raw).date()
                    except Exception:
                        rec["trade_date"] = date_raw
                # numeric fields
                def fnum(k):
                    v = r.get(k)
                    if v in (None, ""):
                        return None
                    try:
                        if "." in v or "e" in v.lower():
                            return float(v.replace(",", ""))
                        return int(v.replace(",", ""))
                    except Exception:
                        try:
                            return float(v.replace(",", ""))
                        except Exception:
                            return None

                rec["open"] = fnum("open")
                rec["high"] = fnum("high")
                rec["low"] = fnum("low")
                rec["close"] = fnum("close") or fnum("last")
                rec["last"] = fnum("last") or rec.get("close")
                rec["prev_close"] = fnum("prev_close") or fnum("previousclose") or fnum("prevclose")
                rec["volume"] = fnum("volume") or fnum("vol")
                rec["traded_value"] = fnum("traded_value") or fnum("value") or fnum("turnover")
                rec["buy_qty"] = fnum("buy_qty") or fnum("buyqty")
                rec["sell_qty"] = fnum("sell_qty") or fnum("sellqty")
                rec["oi"] = fnum("oi")
                results.append(rec)
        return results
