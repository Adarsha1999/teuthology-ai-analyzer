"""Read teuthology job logs and metadata from a local archive directory.

Expected layout (standard teuthology archive on teuth-teuthology host):

    {run_path}/
    ├── 2203/
    │   ├── teuthology.log
    │   ├── summary.yaml
    │   ├── info.yaml
    │   ├── config.yaml
    │   ├── ansible.log
    │   ├── remote/
    │   └── ...
    ├── 2204/
    ├── results.log
    └── scrape.log
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class LocalArchiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalJobInfo:
    """Metadata for one job discovered from the local archive."""

    job_id: str
    job_path: str
    status: str
    description: str
    failure_reason: str | None
    machine: str
    os_type: str
    os_version: str


@dataclass
class LocalRunInfo:
    """Metadata for the entire run directory."""

    run_name: str
    run_path: str
    jobs: list[LocalJobInfo] = field(default_factory=list)


def discover_run(
    run_path: str | Path,
    *,
    allowed_root: str | None = None,
) -> LocalRunInfo:
    """Discover job directories under a teuthology run archive path.

    Args:
        run_path: Absolute path to the run directory.
        allowed_root: If set, ``run_path`` must be under this root (security).
    """
    rp = Path(run_path).resolve()
    if not rp.is_dir():
        raise LocalArchiveError(f"Run path does not exist or is not a directory: {rp}")

    if allowed_root:
        root = Path(allowed_root).resolve()
        if not rp.is_relative_to(root):
            raise LocalArchiveError(
                f"Run path {rp} is outside the allowed root {root}"
            )
    else:
        raise LocalArchiveError(
            "Local archive analysis requires TEUTH_LOCAL_ARCHIVE_ROOT to be set "
            "in backend/.env (security: restricts which filesystem paths can be read)"
        )

    run_name = rp.name

    job_dirs = sorted(
        (d for d in rp.iterdir() if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    if not job_dirs:
        raise LocalArchiveError(f"No numeric job directories found under {rp}")

    jobs: list[LocalJobInfo] = []
    for jd in job_dirs:
        info = _read_job_info(jd)
        if info is not None:
            jobs.append(info)

    logger.info(
        "Discovered %d job(s) under %s (%d dirs scanned)",
        len(jobs),
        rp,
        len(job_dirs),
    )
    return LocalRunInfo(run_name=run_name, run_path=str(rp), jobs=jobs)


def read_job_log(
    job_path: str | Path,
    *,
    max_bytes: int = 0,
    log_name: str = "teuthology.log",
) -> tuple[str, int, bool]:
    """Read a job log file from disk.

    Args:
        job_path: Path to the job directory.
        max_bytes: If > 0, read only the last N bytes (tail mode). 0 = full file.
        log_name: Which log file to read.

    Returns:
        (text, file_size_bytes, truncated)
    """
    log_file = Path(job_path) / log_name
    if not log_file.is_file():
        return "", 0, False

    file_size = log_file.stat().st_size

    if max_bytes > 0 and file_size > max_bytes:
        with open(log_file, "rb") as f:
            f.seek(file_size - max_bytes)
            raw = f.read(max_bytes)
        return raw.decode("utf-8", errors="replace"), file_size, True

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return text, file_size, False


def _read_job_info(job_dir: Path) -> LocalJobInfo | None:
    """Extract job metadata from summary.yaml / info.yaml in the job directory."""
    summary = _load_yaml(job_dir / "summary.yaml")
    info = _load_yaml(job_dir / "info.yaml")

    has_log = (job_dir / "teuthology.log").is_file()
    if summary is None and info is None and not has_log:
        logger.debug("Skipping %s — no summary.yaml, info.yaml, or teuthology.log", job_dir)
        return None

    merged = {}
    if info:
        merged.update(info)
    if summary:
        merged.update(summary)

    status = str(merged.get("status", "unknown")).strip().lower()
    if status == "0":
        status = "pass"
    elif status and status not in ("pass", "fail", "dead", "running", "queued", "waiting"):
        status = "fail" if "fail" in status else "unknown"

    description = str(merged.get("description", "")).strip()
    failure_reason = merged.get("failure_reason")
    if isinstance(failure_reason, str):
        failure_reason = failure_reason.strip() or None
    else:
        failure_reason = None

    machine = str(merged.get("machine_type", "")).strip()
    os_type = str(merged.get("os_type", "")).strip()
    os_version = str(merged.get("os_version", "")).strip()

    return LocalJobInfo(
        job_id=job_dir.name,
        job_path=str(job_dir),
        status=status,
        description=description,
        failure_reason=failure_reason,
        machine=machine,
        os_type=os_type,
        os_version=os_version,
    )


def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return None
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", path, e)
        return None
