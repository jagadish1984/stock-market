from __future__ import annotations
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.logging_config import setup_logging

# configure logging early
setup_logging()
from datetime import date, datetime
from typing import Optional
import uvicorn

from app.config import settings
from app.db import init_db
from app.downloader import list_and_download_once
from app.eod_refresh import refresh_latest_eod
from app.ingest import ingest_once
from app import analytics
from app.fii_dii import get_fii_dii_data, get_fno_participant_activity
from app.bulk_deals import get_bulk_block_deals

from apscheduler.schedulers.background import BackgroundScheduler

LOG = logging.getLogger("uvicorn")


app = FastAPI(title="Local NSE Market Analytics")

# serve frontend static files
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.on_event("startup")
def startup_event():
    init_db()
    try:
        result = refresh_latest_eod()
        if result.get("updated"):
            LOG.info("Latest NSE EOD refreshed for %s with %s rows", result["trade_date"], result["rows_imported"])
        else:
            LOG.info("Latest NSE EOD refresh skipped: %s", result.get("reason"))
    except Exception:
        LOG.exception("Latest NSE EOD refresh failed")
    # run initial download/ingest once
    try:
        list_and_download_once()
        ingest_once()
    except Exception:
        LOG.exception("Startup download/ingest failed")

    scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)
    scheduler.add_job(refresh_latest_eod, "interval", minutes=int(settings.EOD_REFRESH_MINUTES), id="eod_refresh")
    scheduler.add_job(list_and_download_once, "interval", minutes=int(settings.SCHEDULE_MINUTES), id="downloader")
    scheduler.add_job(ingest_once, "interval", minutes=int(settings.SCHEDULE_MINUTES), id="ingest")
    scheduler.start()
    app.state.scheduler = scheduler


@app.post("/api/refresh-latest-data")
def refresh_latest_data():
    """Fetch latest available NSE EOD into the local database before the dashboard reads from it."""
    try:
        result = refresh_latest_eod()
        return JSONResponse(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Latest data refresh failed: {exc}")


@app.get("/api/health")
def health():
    """Health check endpoint for monitoring and load balancers."""
    from app.db import get_conn
    health_status = {"status": "healthy", "timezone": settings.TIMEZONE}
    
    # Check DB connectivity
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM files_processed")
        file_count = cur.fetchone()[0]
        conn.close()
        health_status["database"] = "connected"
        health_status["files_processed"] = file_count
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check scheduler status
    if hasattr(app.state, "scheduler") and app.state.scheduler.running:
        health_status["scheduler"] = "running"
    else:
        health_status["scheduler"] = "stopped"
    
    return health_status


@app.get("/api/ready")
def readiness():
    """Readiness probe for orchestrators (k8s, Cloud Run)."""
    from app.db import get_conn
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        return {"ready": True}
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")


@app.get("/")
def root():
    return RedirectResponse(url="/frontend/dashboard.html")


@app.get("/api/top-gainers")
def get_top_gainers(limit: int = 20, date: Optional[str] = None):
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.top_gainers(target, limit))


@app.get("/api/top-losers")
def get_top_losers(limit: int = 20, date: Optional[str] = None):
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.top_losers(target, limit))


@app.get("/api/most-active")
def get_most_active(limit: int = 20, date: Optional[str] = None, by: str = "volume"):
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.most_active(target, limit, by))


@app.get("/api/most-bought")
def get_most_bought(limit: int = 20, date: Optional[str] = None, mode: str = "real"):
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.most_bought_sold(target, limit, mode=mode)["buy"] if mode != "real" else analytics.most_bought_sold(target, limit, mode=mode))


@app.get("/api/most-sold")
def get_most_sold(limit: int = 20, date: Optional[str] = None, mode: str = "real"):
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    if mode != "real":
        return JSONResponse(analytics.most_bought_sold(target, limit, mode=mode)["sell"])
    return JSONResponse(analytics.most_bought_sold(target, limit, mode=mode))


@app.get("/api/symbol/{symbol}")
def get_symbol(symbol: str, date: Optional[str] = None):
    target = date and datetime.fromisoformat(date).date() or None
    res = analytics.symbol_summary(symbol, target)
    if not res.get("found", True):
        raise HTTPException(status_code=404, detail="Symbol not found")
    return res


@app.get("/api/price-range")
def get_price_range(min_price: float = 10, max_price: float = 100, limit: int = 50, date: Optional[str] = None):
    """Get stocks within a price range."""
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.get_by_price_range(target, min_price, max_price, limit))


@app.get("/api/market-overview")
def get_market_overview(date: Optional[str] = None):
    """Get comprehensive market overview with segments."""
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.market_overview(target))


@app.get("/api/market-brief")
def get_market_brief(date: Optional[str] = None):
    """Get a higher-level market brief for the dashboard home view."""
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.market_brief(target))


@app.get("/api/search")
def search_symbols(q: str, limit: int = 20, date: Optional[str] = None):
    """Search symbols by substring on latest available EOD date (or the provided date)."""
    target = date and datetime.fromisoformat(date).date() or None
    return JSONResponse(analytics.search_symbols(q, limit, target))


@app.get("/api/fii-dii")
def get_institutional_data(date: Optional[str] = None):
    """Get FII/DII institutional investor data for the given date."""
    from datetime import timedelta
    target = date and datetime.fromisoformat(date).date() or (datetime.utcnow().date() - timedelta(days=1))
    data = get_fii_dii_data(target)
    if data:
        return JSONResponse(data)
    return JSONResponse({"error": "Data not available for the specified date"}, status_code=404)


@app.get("/api/fno-participants")
def get_fno_participants(date: Optional[str] = None):
    """Get official NSE participant-category F&O activity for the last session."""
    from datetime import timedelta
    target = date and datetime.fromisoformat(date).date() or (datetime.utcnow().date() - timedelta(days=1))
    return JSONResponse(get_fno_participant_activity(target))


@app.get("/api/bulk-deals")
def get_bulk_deals_data(date: Optional[str] = None):
    """Get bulk/block deals showing which stocks FII/DII are trading."""
    from datetime import timedelta
    target = date and datetime.fromisoformat(date).date() or (datetime.utcnow().date() - timedelta(days=1))
    data = get_bulk_block_deals(target)
    return JSONResponse(data)


@app.get("/api/long-term-candidates")
def get_long_term_candidates(limit: int = 12, date: Optional[str] = None):
    """Get 3-5 year investment candidates using local research inputs plus market context."""
    target = date and datetime.fromisoformat(date).date() or datetime.utcnow().date()
    return JSONResponse(analytics.long_term_candidates(target, limit))


@app.get("/api/options-watch")
def get_options_watch(limit: int = 12, date: Optional[str] = None):
    """Get directional CE/PE watchlist based on market activity and yesterday-style institutional flow."""
    from datetime import timedelta
    target = date and datetime.fromisoformat(date).date() or (datetime.utcnow().date() - timedelta(days=1))
    return JSONResponse(analytics.options_watch(target, limit))


@app.get("/api/data-sources")
def get_data_sources():
    """Explain which parts of the app come from NSE-oriented feeds versus local research inputs."""
    return JSONResponse(analytics.data_sources())


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
