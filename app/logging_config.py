from __future__ import annotations
import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Setup basic console logging for production.

    Keep this lightweight; replace with structured logging (python-json-logger)
    if you need JSON logs for ingestion by log aggregators.
    """
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    # remove default handlers to avoid duplicate logs in some environments
    root.handlers = []
    root.addHandler(handler)
