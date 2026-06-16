"""
Tests for backend/app/services/local_archive_client.py

Covers job discovery (discover_run), log reading (read_job_log),
security enforcement (allowed_root), metadata extraction, and edge cases.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.local_archive_client import (
    LocalArchiveError,
    LocalJobInfo,
    discover_run,
    read_job_log,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def archive_root(tmp_path: Path) -> Path:
    """Return a root directory that discover_run will accept as allowed_root."""
    root = tmp_path / "archive"
    root.mkdir()
    return root


@pytest.fixture()
def run_dir(archive_root: Path) -> Path:
    """Create a minimal teuthology archive layout under the allowed root."""
    run = archive_root / "my-run-2026-06-09"
    run.mkdir()
    return run


# ── discover_run — job enumeration ────────────────────────────────────────────

class TestDiscoverRunJobEnumeration:
    def test_discovers_jobs_with_statuses(self, run_dir: Path, archive_root: Path):
        _make_job(run_dir, "100", status="pass", failure_reason=None)
        _make_job(run_dir, "101", status="fail")
        _make_job(run_dir, "102", status="dead", failure_reason="OSD crashed")

        info = discover_run(run_dir, allowed_root=str(archive_root))
        assert info.run_name == run_dir.name
        assert len(info.jobs) == 3
        assert [j.job_id for j in info.jobs] == ["100", "101", "102"]
        assert {j.job_id: j.status for j in info.jobs} == {
            "100": "pass", "101": "fail", "102": "dead",
        }

    def test_ignores_non_numeric_dirs(self, run_dir: Path, archive_root: Path):
        _make_job(run_dir, "50", status="pass", failure_reason=None)
        (run_dir / "logs").mkdir()
        (run_dir / "results.log").touch()

        info = discover_run(run_dir, allowed_root=str(archive_root))
        assert len(info.jobs) == 1
        assert info.jobs[0].job_id == "50"


# ── discover_run — metadata extraction ────────────────────────────────────────

class TestDiscoverRunMetadata:
    def test_failure_reason_extraction(self, run_dir: Path, archive_root: Path):
        _make_job(run_dir, "10", status="fail", failure_reason="cmd exit 1")

        info = discover_run(run_dir, allowed_root=str(archive_root))
        assert info.jobs[0].failure_reason == "cmd exit 1"

    def test_no_failure_reason_for_passing_job(self, run_dir: Path, archive_root: Path):
        _make_job(run_dir, "20", status="pass", failure_reason=None)

        info = discover_run(run_dir, allowed_root=str(archive_root))
        assert info.jobs[0].failure_reason is None

    def test_info_yaml_used_as_fallback(self, run_dir: Path, archive_root: Path):
        jd = run_dir / "400"
        jd.mkdir()
        (jd / "info.yaml").write_text(
            "description: mirror test\nmachine_type: smithi\nos_type: ubuntu\nos_version: '22.04'\n"
        )
        (jd / "teuthology.log").write_text("log\n")

        info = discover_run(run_dir, allowed_root=str(archive_root))
        j = info.jobs[0]
        assert j.description == "mirror test"
        assert j.machine == "smithi"
        assert j.os_type == "ubuntu"
        assert j.os_version == "22.04"

    def test_job_without_summary_but_with_log(self, run_dir: Path, archive_root: Path):
        jd = run_dir / "300"
        jd.mkdir()
        (jd / "teuthology.log").write_text("some log content\n")

        info = discover_run(run_dir, allowed_root=str(archive_root))
        assert len(info.jobs) == 1
        assert info.jobs[0].status == "unknown"


# ── discover_run — security / path enforcement ────────────────────────────────

class TestDiscoverRunSecurity:
    def test_error_when_no_allowed_root(self, tmp_path: Path):
        run = tmp_path / "run1"
        run.mkdir()
        _make_job(run, "1", status="pass", failure_reason=None)
        with pytest.raises(LocalArchiveError, match="TEUTH_LOCAL_ARCHIVE_ROOT"):
            discover_run(run)

    def test_allowed_root_enforcement(self, tmp_path: Path):
        outside = tmp_path / "outside"
        outside.mkdir()
        run = outside / "run1"
        run.mkdir()
        _make_job(run, "1", status="pass", failure_reason=None)

        allowed = tmp_path / "safe"
        allowed.mkdir()

        with pytest.raises(LocalArchiveError, match="outside the allowed root"):
            discover_run(run, allowed_root=str(allowed))

    def test_allowed_root_passes_for_valid_path(self, tmp_path: Path):
        safe = tmp_path / "safe"
        safe.mkdir()
        run = safe / "run1"
        run.mkdir()
        _make_job(run, "1", status="pass", failure_reason=None)

        info = discover_run(run, allowed_root=str(safe))
        assert len(info.jobs) == 1


# ── discover_run — error handling ─────────────────────────────────────────────

class TestDiscoverRunErrors:
    def test_error_on_missing_path(self, tmp_path: Path):
        with pytest.raises(LocalArchiveError, match="does not exist"):
            discover_run(tmp_path / "nonexistent", allowed_root=str(tmp_path))

    def test_error_on_no_jobs(self, run_dir: Path, archive_root: Path):
        with pytest.raises(LocalArchiveError, match="No numeric job"):
            discover_run(run_dir, allowed_root=str(archive_root))


# ── read_job_log ──────────────────────────────────────────────────────────────

class TestReadJobLog:
    def test_reads_full_log(self, run_dir: Path):
        _make_job(run_dir, "500", log_lines=100)
        jd = run_dir / "500"
        text, size, truncated = read_job_log(jd)
        assert not truncated
        assert size > 0
        assert "line 0" in text
        assert "line 99" in text

    def test_tail_mode(self, run_dir: Path):
        _make_job(run_dir, "501", log_lines=2000)
        jd = run_dir / "501"

        full_text, full_size, _ = read_job_log(jd)

        text, size, truncated = read_job_log(jd, max_bytes=1024)
        assert truncated
        assert size == full_size
        assert len(text.encode("utf-8")) <= 1024
        assert "line 1999" in text

    def test_missing_log(self, run_dir: Path):
        jd = run_dir / "502"
        jd.mkdir()
        text, size, truncated = read_job_log(jd)
        assert text == ""
        assert size == 0
        assert not truncated

    def test_custom_log_name(self, run_dir: Path):
        jd = run_dir / "504"
        jd.mkdir()
        (jd / "ansible.log").write_text("ansible output here\n")
        text, size, truncated = read_job_log(jd, log_name="ansible.log")
        assert "ansible output" in text
        assert size > 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_job(
    run: Path,
    job_id: str,
    *,
    status: str = "fail",
    description: str = "fs basic test",
    failure_reason: str | None = "assertion error in test_foo",
    log_lines: int = 200,
) -> Path:
    """Create a job directory with summary.yaml and teuthology.log."""
    jd = run / job_id
    jd.mkdir(parents=True, exist_ok=True)

    summary = {"status": status, "description": description}
    if failure_reason:
        summary["failure_reason"] = failure_reason

    (jd / "summary.yaml").write_text(
        "\n".join(f"{k}: {v}" for k, v in summary.items()) + "\n"
    )

    lines = [f"2026-06-09T12:00:{i:02d}.000 INFO line {i}\n" for i in range(log_lines)]
    if status == "fail" and failure_reason:
        mid = log_lines // 2
        lines[mid] = f"2026-06-09T12:00:{mid:02d}.000 ERROR {failure_reason}\n"
    (jd / "teuthology.log").write_text("".join(lines))

    return jd
