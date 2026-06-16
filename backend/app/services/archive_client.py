from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

from app.core.llm_config import Settings
from app.services.pulpito_client import run_variants_for_archive

_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-\d+/(\d+)", re.IGNORECASE)


def teuthology_log_url(settings: Settings, run_name: str, job_id: str) -> str:
    return f"{settings.teuth_archive_base.rstrip('/')}/{run_name}/{job_id}/teuthology.log"


def fetch_teuthology_log(
    client: httpx.Client,
    settings: Settings,
    run_name: str,
    job_id: str,
) -> tuple[str, str, bool]:
    """Return (text, resolved_run_name, truncated). Empty text if not found."""
    last_err: str | None = None
    for variant in run_variants_for_archive(run_name):
        url = teuthology_log_url(settings, variant, job_id)
        try:
            text, truncated = _fetch_log_tail(client, url, settings.max_log_bytes)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                last_err = "404"
                continue
            raise
        except httpx.RequestError as e:
            last_err = str(e)
            continue
        if text or not last_err:
            return text, variant, truncated
    return "", run_name, False


def _fetch_log_tail(
    client: httpx.Client, url: str, max_bytes: int
) -> tuple[str, bool]:
    """Fetch the last *max_bytes* of a log file using HTTP Range requests.

    Teuthology logs are written sequentially; failures always appear at the end.
    Fetching from the tail ensures the digest sees the actual failure rather than
    the setup/install preamble that fills the first megabytes of large logs.

    Falls back to streaming from the start when the server does not honour Range
    (returns 200 instead of 206).
    """
    # Accept-Encoding: gzip makes nginx ignore Range and return the full log (~10GB+).
    r = client.get(
        url,
        headers={
            "Range": f"bytes=-{max_bytes}",
            "Accept-Encoding": "identity",
        },
        follow_redirects=True,
    )

    if r.status_code == 206:
        # Partial content — we got the tail of the file.
        # Determine whether the response starts at byte 0 (whole file fits) or
        # somewhere further in (genuinely truncated from the front).
        cr = r.headers.get("content-range", "")
        m = _CONTENT_RANGE.match(cr)
        truncated = bool(m and int(m.group(1)) > 0)
        return r.content.decode("utf-8", errors="replace"), truncated

    if r.status_code == 200:
        # Server ignored Range — stream and keep only the last max_bytes (avoid
        # loading multi‑GB teuthology.log files entirely into memory).
        tail = bytearray()
        total = 0
        for chunk in r.iter_bytes(chunk_size=256 * 1024):
            if not chunk:
                continue
            tail.extend(chunk)
            total += len(chunk)
            if len(tail) > max_bytes:
                del tail[: len(tail) - max_bytes]
        truncated = total > max_bytes
        logger.info(
            "Archive returned 200 (no Range); kept last %d of %d bytes",
            len(tail),
            total,
        )
        return tail.decode("utf-8", errors="replace"), truncated

    r.raise_for_status()
    return "", False  # unreachable
