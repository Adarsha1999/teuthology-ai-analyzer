"""
Tests for backend/app/services/pulpito_client.py — parse_run_name()

Covers URL stripping, trailing path segments, plain names, and
empty-input error handling.
"""
import pytest

from app.services.pulpito_client import parse_run_name


# ── Parametrized extraction ───────────────────────────────────────────────────

class TestParseRunName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://pulpito.ceph.com/foo-bar-baz/", "foo-bar-baz"),
            ("foo-bar-baz", "foo-bar-baz"),
            ("https://pulpito.ceph.com/foo-bar-baz/165644", "foo-bar-baz"),
        ],
    )
    def test_extracts_run_name(self, raw: str, expected: str) -> None:
        assert parse_run_name(raw) == expected

    def test_empty_input_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_run_name("   ")
