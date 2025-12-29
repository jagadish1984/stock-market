import os
import importlib
import pytest
import sys
from pathlib import Path

# ensure repository root is on sys.path so `app` package is importable during tests
REPO_ROOT = str(Path(__file__).resolve().parents[1])
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture(autouse=True)
def temp_env(tmp_path, monkeypatch):
    # set a temporary sqlite DB for tests
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("NSE_PRODUCTS", "CM_EOD")
    # reload app.config to pick up env changes
    import app.config as cfg
    importlib.reload(cfg)
    # initialize DB via reloaded app.db so it picks up the new DATABASE_URL
    import app.db as adb
    importlib.reload(adb)
    adb.init_db()
    # reload analytics to reference fresh DB module
    import app.analytics as aanalytics
    importlib.reload(aanalytics)
    return {"db_path": str(db)}
