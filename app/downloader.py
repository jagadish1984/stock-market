from __future__ import annotations
import os
import time
import hashlib
import logging
from typing import List
import paramiko

from app.config import settings
from app.db import get_conn, mark_file_downloaded, update_file_status

LOG = logging.getLogger(__name__)


def compute_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_sftp():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {}
    if settings.NSE_SFTP_PASSWORD:
        connect_kwargs["password"] = settings.NSE_SFTP_PASSWORD
    if settings.NSE_SFTP_PRIVATE_KEY_PATH:
        key_path = os.path.expanduser(settings.NSE_SFTP_PRIVATE_KEY_PATH)
        pkey = paramiko.RSAKey.from_private_key_file(key_path)
        connect_kwargs["pkey"] = pkey
    client.connect(settings.NSE_SFTP_HOST, port=settings.NSE_SFTP_PORT, username=settings.NSE_SFTP_USER, **connect_kwargs)
    sftp = client.open_sftp()
    return client, sftp


def list_and_download_once():
    products = [p.strip() for p in settings.NSE_PRODUCTS.split(",") if p.strip()]
    if not products:
        LOG.warning("No products configured in NSE_PRODUCTS")
        return

    if not settings.NSE_SFTP_HOST:
        LOG.info("NSE_SFTP_HOST not configured; skipping SFTP download")
        return

    try:
        client, sftp = _connect_sftp()
    except Exception as e:
        LOG.exception("SFTP connection failed: %s", e)
        return

    for product in products:
        remote_root = settings.NSE_SFTP_REMOTE_ROOT or "/"
        product_root = os.path.join(remote_root, product)
        try:
            entries = sftp.listdir_attr(product_root)
        except IOError:
            LOG.exception("Cannot list %s", product_root)
            continue

        local_dir = os.path.join(os.getcwd(), "data", "downloads", product)
        os.makedirs(local_dir, exist_ok=True)

        for entry in entries:
            filename = entry.filename
            remote_path = os.path.join(product_root, filename)
            local_path = os.path.join(local_dir, filename)
            # decide whether to download (we simply check for local file existence and size)
            need_download = True
            if os.path.exists(local_path) and os.path.getsize(local_path) == entry.st_size:
                need_download = False
            if not need_download:
                continue

            # retry with simple backoff
            backoff = 1
            for attempt in range(5):
                try:
                    LOG.info("Downloading %s -> %s", remote_path, local_path)
                    sftp.get(remote_path, local_path)
                    checksum = compute_checksum(local_path)
                    fid = mark_file_downloaded(product, product_root, filename, entry.st_size, checksum)
                    LOG.info("Downloaded %s (file_id=%s)", filename, fid)
                    break
                except Exception as e:
                    LOG.exception("Download failed for %s (attempt %s): %s", remote_path, attempt + 1, e)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)
            else:
                LOG.error("Failed to download %s after retries", remote_path)
                # Optionally record failure in files_processed
                try:
                    fid = mark_file_downloaded(product, product_root, filename, entry.st_size, "")
                    update_file_status(fid, "download_failed", None, "download failed after retries")
                except Exception:
                    pass

    try:
        sftp.close()
        client.close()
    except Exception:
        pass
