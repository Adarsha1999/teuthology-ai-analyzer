"""
Tests for backend/app/services/llm_common.py

Covers failure_mode_hint() for known failure patterns and graceful fallback,
and _parse_json_content() for plain JSON and fenced-block extraction.
"""
from app.services.llm_common import failure_mode_hint as _failure_mode_hint
from app.services.llm_common import _parse_json_content


# ── Failure mode hints ────────────────────────────────────────────────────────

class TestFailureModeHint:
    def test_cram_failure_hint(self) -> None:
        h = _failure_mode_hint(
            "cram -v /path/*.t", "orch:cephadm/rbd_iscsi suite"
        )
        assert "cram" in h.lower()
        assert "digest" in h.lower()

    def test_workunit_hint(self) -> None:
        h = _failure_mode_hint("timeout", "tasks.workunit rbd test")
        assert "workunit" in h.lower() or "client" in h.lower()

    def test_empty_hint_when_unrecognized(self) -> None:
        assert _failure_mode_hint("", "generic teuth pass") == ""


# ── JSON content parsing ──────────────────────────────────────────────────────

class TestParseJsonContent:
    def test_plain_json(self) -> None:
        assert _parse_json_content('{"summary":"a","confidence":0.5}') == {
            "summary": "a",
            "confidence": 0.5,
        }

    def test_fenced_json_block(self) -> None:
        raw = """```json
{"summary": "x"}
```"""
        assert _parse_json_content(raw) == {"summary": "x"}
