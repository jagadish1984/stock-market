"""NSE participant-wise derivatives data helpers."""
import requests
import csv
import io
from datetime import date, timedelta
from typing import Optional, Dict, List
import logging

LOG = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def _fetch_participant_csv(target_date: date, report_type: str) -> Optional[List[Dict]]:
    report_map = {
        "volume": f"https://archives.nseindia.com/content/nsccl/fao_participant_vol_{target_date.strftime('%d%m%Y')}.csv",
        "oi": f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{target_date.strftime('%d%m%Y')}.csv",
    }
    url = report_map[report_type]
    session = requests.Session()
    session.headers.update(HEADERS)

    response = session.get(url, timeout=30)
    if response.status_code != 200:
        LOG.warning("Participant %s data not available for %s", report_type, target_date)
        return None

    lines = response.text.strip().split("\n")
    for i, line in enumerate(lines):
        if "Client Type" in line:
            csv_data = "\n".join(lines[i:])
            reader = csv.DictReader(io.StringIO(csv_data))
            return [{k.strip(): v.strip() for k, v in row.items()} for row in reader]
    return None


def _to_int(value: str) -> int:
    return int((value or "0").replace(",", "").strip() or "0")


def _build_participant_summary(row: Dict) -> Dict:
    future_index_long = _to_int(row.get("Future Index Long", "0"))
    future_index_short = _to_int(row.get("Future Index Short", "0"))
    future_stock_long = _to_int(row.get("Future Stock Long", "0"))
    future_stock_short = _to_int(row.get("Future Stock Short", "0"))
    option_index_call_long = _to_int(row.get("Option Index Call Long", "0"))
    option_index_put_long = _to_int(row.get("Option Index Put Long", "0"))
    option_index_call_short = _to_int(row.get("Option Index Call Short", "0"))
    option_index_put_short = _to_int(row.get("Option Index Put Short", "0"))
    option_stock_call_long = _to_int(row.get("Option Stock Call Long", "0"))
    option_stock_put_long = _to_int(row.get("Option Stock Put Long", "0"))
    option_stock_call_short = _to_int(row.get("Option Stock Call Short", "0"))
    option_stock_put_short = _to_int(row.get("Option Stock Put Short", "0"))
    total_long = _to_int(row.get("Total Long Contracts", "0"))
    total_short = _to_int(row.get("Total Short Contracts", "0"))
    net = total_long - total_short
    stock_fno_focus = future_stock_long + option_stock_call_long + option_stock_put_long

    return {
        "client_type": row.get("Client Type", ""),
        "future_index_long": future_index_long,
        "future_index_short": future_index_short,
        "future_stock_long": future_stock_long,
        "future_stock_short": future_stock_short,
        "option_index_call_long": option_index_call_long,
        "option_index_put_long": option_index_put_long,
        "option_index_call_short": option_index_call_short,
        "option_index_put_short": option_index_put_short,
        "option_stock_call_long": option_stock_call_long,
        "option_stock_put_long": option_stock_put_long,
        "option_stock_call_short": option_stock_call_short,
        "option_stock_put_short": option_stock_put_short,
        "total_long": total_long,
        "total_short": total_short,
        "net": net,
        "sentiment": "bullish" if net > 0 else "bearish" if net < 0 else "neutral",
        "stock_fno_focus": stock_fno_focus,
    }


def get_fii_dii_data(target_date: Optional[date] = None) -> Dict:
    """Fetch FII/DII participant-wise trading data from NSE"""
    
    if target_date is None:
        # Default to yesterday (data has 1-day lag)
        target_date = date.today() - timedelta(days=1)
    
    try:
        rows = _fetch_participant_csv(target_date, "volume")
        if not rows:
            return None
        result = {"date": target_date.isoformat(), "fii": None, "dii": None}
        for row in rows:
            ct = row.get("Client Type", "")
            summary = _build_participant_summary(row)
            if ct == "FII":
                result["fii"] = {
                    "long": summary["total_long"],
                    "short": summary["total_short"],
                    "net": summary["net"],
                    "sentiment": summary["sentiment"],
                }
            elif ct == "DII":
                result["dii"] = {
                    "long": summary["total_long"],
                    "short": summary["total_short"],
                    "net": summary["net"],
                    "sentiment": summary["sentiment"],
                }
        return result
        
    except Exception as e:
        LOG.error(f"Error fetching FII/DII data: {e}")
        return None


def get_fno_participant_activity(target_date: Optional[date] = None) -> Dict:
    """Return official NSE participant-wise F&O activity for the last session."""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    try:
        volume_rows = _fetch_participant_csv(target_date, "volume")
        oi_rows = _fetch_participant_csv(target_date, "oi")
        if not volume_rows:
            return {"date": target_date.isoformat(), "rows": [], "warning": "Participant-wise F&O data is not available for this session yet."}

        oi_by_client = {row.get("Client Type", ""): row for row in (oi_rows or [])}
        participants = []
        for row in volume_rows:
            client_type = row.get("Client Type", "")
            if client_type in {"TOTAL", ""}:
                continue
            summary = _build_participant_summary(row)
            oi_summary = _build_participant_summary(oi_by_client.get(client_type, {})) if client_type in oi_by_client else None
            summary["open_interest_long"] = oi_summary["total_long"] if oi_summary else 0
            summary["open_interest_short"] = oi_summary["total_short"] if oi_summary else 0
            summary["open_interest_net"] = oi_summary["net"] if oi_summary else 0
            participants.append(summary)

        participants.sort(key=lambda item: item["stock_fno_focus"], reverse=True)
        return {
            "date": target_date.isoformat(),
            "warning": "This is official NSE participant-category data for derivatives. It shows client categories like FII, DII, Pro, and Client, not individual investor names per stock.",
            "rows": participants,
        }
    except Exception as exc:
        LOG.error("Error fetching F&O participant activity: %s", exc)
        return {"date": target_date.isoformat(), "rows": [], "warning": "Unable to load F&O participant activity right now."}
