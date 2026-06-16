"""
Tests for backend/app/services/pulpito_client.py — parse_jobs_table()

Validates HTML table parsing against the fixture run_table_snippet.html,
ensuring job IDs, statuses, and failure reasons are extracted correctly.
"""
from pathlib import Path

from app.services.pulpito_client import parse_jobs_table

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "run_table_snippet.html"


# ── HTML table parsing ────────────────────────────────────────────────────────

class TestParseJobsTable:
    def test_extracts_jobs_from_fixture(self) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8")
        jobs = parse_jobs_table(html)
        assert len(jobs) == 2
        assert jobs[0].job_id == "165644"
        assert jobs[0].status == "fail"
        assert "tox" in (jobs[0].failure_reason or "")
        assert jobs[1].job_id == "165645"
        assert jobs[1].status == "pass"
        assert jobs[1].failure_reason is None
