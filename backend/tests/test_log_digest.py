"""
Tests for backend/app/services/log_digest.py

Covers build_digest() — tail inclusion, keyword windows, failure anchoring,
budget fitting, and regression scenarios for cephfs/msgr/pytest edge cases.
"""
from app.services.log_digest import build_digest


# ── Basic digest behavior ─────────────────────────────────────────────────────

class TestBuildDigestBasic:
    def test_includes_tail(self) -> None:
        lines = [f"line {i}" for i in range(500)]
        lines[100] = "Traceback (most recent call last):"
        text = "\n".join(lines)
        d = build_digest(text, max_chars=50_000)
        assert "Traceback" in d
        assert "line 499" in d

    def test_empty_log(self) -> None:
        assert "empty" in build_digest("", 1000).lower()

    def test_uses_failure_reason_terms(self) -> None:
        lines = ["ok"] * 500 + ["running s3tests marker bucket_logging"] + ["ok"] * 100
        text = "\n".join(lines)
        d = build_digest(
            text,
            20_000,
            failure_reason="Command failed: tox -e s3tests -- bucket_logging",
        )
        assert "bucket_logging" in d or "s3tests" in d


# ── Keyword windows and budget fitting ────────────────────────────────────────

class TestBuildDigestBudget:
    def test_keeps_keyword_windows_when_over_budget(self) -> None:
        """Regression: old logic used text[-max_chars:] and dropped failure windows."""
        lines: list[str] = []
        for i in range(8000):
            lines.append(f"compressing teuthology.log.gz chunk {i}")
        lines[7500] = "FAILURES ======================================="
        lines[7501] = "_____ test_bucket_logging _________________________"
        lines[7502] = "E       AssertionError: expected bucket policy"
        lines.extend([f"archival cleanup line {i}" for i in range(7900, 8000)])
        text = "\n".join(lines)
        d = build_digest(text, max_chars=8_000)
        assert "FAILURES" in d or "AssertionError" in d
        assert "Focused failure window" in d or "Keyword windows" in d

    def test_includes_focused_window_and_command_evidence(self) -> None:
        lines = [f"noise line {i}" for i in range(600)]
        lines[320] = "Executing: tox -e py311 -- tests/smoke/test_rgw.py"
        lines[322] = "return code: 1"
        lines[340] = "ERROR task failed with status 1"
        text = "\n".join(lines)
        d = build_digest(text, 24_000, failure_reason="task failed status 1")
        assert "Focused failure window" in d
        assert "Command evidence near failure" in d
        assert "return code: 1" in d

    def test_truncation_keeps_failure_context_prefix(self) -> None:
        lines = [f"line {i}" for i in range(12000)]
        lines[11000] = "Traceback (most recent call last):"
        lines[11001] = "AssertionError: bucket check failed"
        text = "\n".join(lines)
        d = build_digest(text, 2_400, failure_reason="bucket check failed")
        assert "AssertionError: bucket check failed" in d or "Traceback" in d
        assert "Focused failure window" in d
        assert "line 11999" not in d or "AssertionError" in d


# ── Regression: anchor selection ──────────────────────────────────────────────

class TestBuildDigestAnchorRegression:
    def test_anchors_on_pytest_assertion_not_debug_mention(self) -> None:
        """Regression: first test-name mention in DEBUG output is not the failure."""
        lines = [f"noise {i}" for i in range(9100)]
        lines[8961] = "DEBUG: running test_cephfs_mirror_cancel_mirroring_and_readd setup"
        lines[9018] = "FAILURES ======================================="
        lines[9019] = "_____ test_cephfs_mirror_cancel_mirroring_and_readd _____"
        lines[9020] = "E       AssertionError: metrics not found in output"
        lines.extend([f"teardown noise {i}" for i in range(9021, 9100)])
        text = "\n".join(lines)
        d = build_digest(
            text,
            24_000,
            failure_reason=(
                "Test failure: test_cephfs_mirror_cancel_mirroring_and_readd "
                "(tasks.cephfs.test_mirroring.TestMirroring.test_cephfs_mirror_cancel_mirroring_and_readd)"
            ),
        )
        assert "metrics not found" in d
        assert "Focused failure window" in d

    def test_cephfs_test_runner_not_job_summary(self) -> None:
        """Regression: Pulpito failure_reason YAML at log end must not win anchoring."""
        lines = [f"noise {i}" for i in range(5342)]
        lines[2109] = (
            "INFO:tasks.cephfs_test_runner:test_journal_smoke "
            "(tasks.cephfs.test_journal_repair.TestJournalRepair.test_journal_smoke) ... ERROR"
        )
        lines[2947] = "INFO:tasks.cephfs_test_runner:ERROR: test_journal_smoke (tasks.cephfs.test_journal_repair.TestJournalRepair.test_journal_smoke)"
        lines[2974] = "INFO:tasks.cephfs_test_runner:teuthology.exceptions.CommandFailedError: Command failed (workunit test suites/cephfs_journal_tool_smoke.sh)"
        lines[2979] = "INFO:tasks.cephfs_test_runner:FAILED (errors=1)"
        lines[5340] = "failure_reason: 'Test failure: test_journal_smoke (tasks.cephfs.test_journal_repair.TestJournalRepair.test_journal_smoke)'"
        lines[5341] = "status: fail"
        text = "\n".join(lines)
        d = build_digest(
            text,
            24_000,
            failure_reason=(
                "Test failure: test_journal_smoke "
                "(tasks.cephfs.test_journal_repair.TestJournalRepair.test_journal_smoke)"
            ),
        )
        assert "CommandFailedError" in d or "cephfs_journal_tool_smoke" in d
        assert "Focused failure window" in d
        assert "ntpq: command not found" not in d or "CommandFailedError" in d

    def test_recover_header_command_failed_not_msgr_noise(self) -> None:
        """Regression: anchor must not be duplicate ERROR: with 180 lines of msgr before traceback."""
        lines = [f"msgr noise {i}" for i in range(1500)]
        for i in range(1538, 1565):
            lines.append(f"2026 INFO:teuthology.orchestra.run.trial033.stderr:ceph connection {i}")
        lines.append("2026 INFO:tasks.cephfs_test_runner:======================================")
        lines.append(
            "2026 INFO:tasks.cephfs_test_runner:ERROR: test_recover_header "
            "(tasks.cephfs.test_journal_repair.TestJournalRepair.test_recover_header)"
        )
        lines.append("2026 INFO:tasks.cephfs_test_runner:Traceback (most recent call last):")
        lines.append(
            "2026 INFO:tasks.cephfs_test_runner:  File test_journal_repair.py, line 561, in test_recover_header"
        )
        lines.append("2026 INFO:tasks.cephfs_test_runner:    self.fs.set_max_mds(0)")
        lines.append("2026 INFO:tasks.cephfs_test_runner:    self.run_ceph_cmd(\"fs\", \"set\", self.name, var, *a)")
        lines.append(
            "2026 INFO:tasks.cephfs_test_runner:teuthology.exceptions.CommandFailedError: "
            "Command failed on trial033 with status 22: 'ceph fs set cephfs max_mds 0 --yes-i-really-mean-it'"
        )
        lines.append("2026 INFO:tasks.cephfs_test_runner:FAILED (errors=1)")
        lines.append(
            "2026 INFO:tasks.cephfs_test_runner:ERROR: test_recover_header "
            "(tasks.cephfs.test_journal_repair.TestJournalRepair.test_recover_header)"
        )
        text = "\n".join(lines)
        d = build_digest(
            text,
            24_000,
            failure_reason=(
                "Test failure: test_recover_header "
                "(tasks.cephfs.test_journal_repair.TestJournalRepair.test_recover_header)"
            ),
        )
        assert "Test failure excerpt" in d
        assert "set_max_mds(0)" in d
        assert "status 22" in d
        assert "max_mds 0" in d
        idx_noise = d.find("ceph connection 1538")
        idx_fail = d.find("set_max_mds(0)")
        assert idx_fail >= 0
        if idx_noise >= 0:
            assert idx_fail < idx_noise or "msgr noise 0" not in d[:idx_fail]
