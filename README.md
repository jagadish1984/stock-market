Local NSE Market Data Analytics Backend

This project provides a local backend (FastAPI) that downloads official NSE data files over SFTP, parses them, stores into SQLite, and exposes simple analytics APIs for a local UI.

Quick start
1. Copy `.env.example` to `.env` and fill SFTP credentials and product roots.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
uvicorn app.main:app --reload
```

Tests

Run unit tests with:

```bash
pytest -q
```

Frontend demo

Open `frontend/index.html` in your browser while the FastAPI server is running (it expects the backend at `http://127.0.0.1:8000`).

Where to plug in official NSE binary specs

See `app/parsers/binary_placeholder.py` and `app/README_ADDITIONAL.md` for guidance on implementing binary parsers once you have the official spec.

Production deployment
--------------------

Recommended quick production setup using Docker:

1. Build image:

```bash
docker build -t stock-market:latest .
```

2. Run with docker-compose (persists `data/`):

```bash
docker-compose up -d --build
```

Notes:
- The Docker image runs `gunicorn` with `uvicorn` workers. Tune `--workers` according to CPU.
- Mount or supply a secure `.env` (do NOT commit secrets). The `.env.example` provides names of variables required.
- For systemd deployments, see `systemd/stock-market.service` (adjust paths and envfile).

Security & production tips
- Run the service as a dedicated user and secure the `.env` file with appropriate filesystem permissions.
- Consider using a reverse proxy (nginx) for TLS termination, logging, and request buffering.
- Add log forwarding to a centralized log platform. Replace `app/logging_config.py` to output JSON if needed.

# stock-market