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
from app.ingest import ingest_once
from app import analytics

from apscheduler.schedulers.background import BackgroundScheduler

LOG = logging.getLogger("uvicorn")


app = FastAPI(title="Local NSE Market Analytics")

# serve frontend static files
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.on_event("startup")
def startup_event():
    init_db()
    # run initial download/ingest once
    try:
        list_and_download_once()
        ingest_once()
    except Exception:
        LOG.exception("Startup download/ingest failed")

    scheduler = BackgroundScheduler(timezone=settings.TIMEZONE)
    scheduler.add_job(list_and_download_once, "interval", minutes=int(settings.SCHEDULE_MINUTES), id="downloader")
    scheduler.add_job(ingest_once, "interval", minutes=int(settings.SCHEDULE_MINUTES), id="ingest")
    scheduler.start()
    app.state.scheduler = scheduler


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
    return RedirectResponse(url="/frontend/index.html")


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


@app.get("/api/search")
def search_symbols(q: str, limit: int = 20, date: Optional[str] = None):
    """Search symbols by substring on latest available EOD date (or the provided date)."""
    target = date and datetime.fromisoformat(date).date() or None
    return JSONResponse(analytics.search_symbols(q, limit, target))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
