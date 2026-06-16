"""
Tests for backend/app/providers/bob_cli_provider.py

Covers IBM Bob CLI health checks, subprocess invocation, input modes,
and the chat_llm dispatch path for the bob_cli provider kind.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.providers import bob_cli_provider
from app.services.llm_client import chat_llm
from app.core.llm_config import LLMConnection, ProviderSpec


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def bob_spec() -> ProviderSpec:
    return ProviderSpec(kind="bob_cli", label="IBM Bob")


@pytest.fixture
def bob_conn() -> LLMConnection:
    return LLMConnection(provider="bob", model="bob-shell-local", request_timeout=60)


# ── Health check ──────────────────────────────────────────────────────────────

class TestBobHealth:
    def test_missing_command(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-key")
        monkeypatch.setenv("IBM_BOB_ENABLED", "true")
        monkeypatch.delenv("IBM_BOB_COMMAND", raising=False)
        with patch("app.providers.bob_cli_provider.shutil.which", return_value=None):
            result = bob_cli_provider.detailed_health()
        assert result["healthy"] is False
        assert "not found" in (result["error"] or "").lower()

    def test_healthy_when_command_exists(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-key")
        with (
            patch("app.providers.bob_cli_provider.shutil.which", return_value="/usr/local/bin/bob"),
            patch(
                "app.providers.bob_cli_provider.subprocess.run",
                return_value=MagicMock(stdout=b"bobshell 1.0", stderr=b"", returncode=0),
            ),
        ):
            result = bob_cli_provider.detailed_health()
        assert result["healthy"] is True
        assert result["command"] == "/usr/local/bin/bob"


# ── Subprocess invocation ─────────────────────────────────────────────────────

class TestBobSubprocessInvocation:
    def test_prompt_file_uses_stdin_not_temp_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-key")
        monkeypatch.setenv("IBM_BOB_WORKDIR", str(tmp_path))
        monkeypatch.setenv("IBM_BOB_INPUT_MODE", "prompt_file")
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["input"] = kwargs.get("input")
            return MagicMock(stdout=b"analysis complete", stderr=b"", returncode=0)

        with (
            patch("app.providers.bob_cli_provider.shutil.which", return_value="/usr/local/bin/bob"),
            patch("app.providers.bob_cli_provider.subprocess.run", side_effect=fake_run),
        ):
            bob_cli_provider.chat_messages([{"role": "user", "content": "digest"}], timeout=30)

        assert captured["input"] == b"=== USER ===\ndigest"
        assert str(tmp_path) in " ".join(captured["cmd"]) or captured["cmd"][0] == "/usr/local/bin/bob"
        assert "/var/" not in " ".join(str(x) for x in captured["cmd"])
        assert "teuthology-ai-bob" not in " ".join(str(x) for x in captured["cmd"])

    def test_chat_messages_returns_json(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-key")
        with (
            patch("app.providers.bob_cli_provider.shutil.which", return_value="/usr/local/bin/bob"),
            patch(
                "app.providers.bob_cli_provider.subprocess.run",
                return_value=MagicMock(
                    stdout=b'{"summary":"ok","likely_root_cause":"x","evidence":[],"next_steps":[],"confidence":0.9}',
                    stderr=b"",
                    returncode=0,
                ),
            ),
        ):
            out = bob_cli_provider.chat_messages(
                [{"role": "user", "content": "analyze"}],
                timeout=30,
                json_format=True,
            )
        assert "summary" in out


# ── LLM dispatch ──────────────────────────────────────────────────────────────

class TestBobLLMDispatch:
    def test_chat_llm_dispatches_to_bob_cli(self, monkeypatch, bob_spec, bob_conn):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-key")
        with patch(
            "app.providers.bob_cli_provider.chat_messages",
            return_value='{"summary":"t","likely_root_cause":"","evidence":[],"next_steps":[],"confidence":1}',
        ):
            text = chat_llm(
                bob_conn,
                [{"role": "user", "content": "hi"}],
                timeout=60,
                settings=_make_bob_settings(bob_spec),
            )
        assert "summary" in text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bob_settings(spec: ProviderSpec):
    """Build a minimal Settings object with the bob provider configured."""
    return __import__("app.core.llm_config", fromlist=["Settings"]).Settings(
        llm_providers={"bob": spec}
    )
