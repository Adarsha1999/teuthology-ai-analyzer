"""
Tests for API key validation and resolution in backend/app/services/llm_client.py

Covers env_api_key, resolve_api_key, resolve_api_key_for_connect, and
validate_api_key for Bob CLI (key-based provider). Ollama is keyless so
only Bob needs key resolution tests.
"""
from app.core.llm_config import LLMConnection, ProviderSpec
from app.services.llm_client import (
    env_api_key,
    resolve_api_key,
    resolve_api_key_for_connect,
    validate_api_key,
)


# ── Ollama — no key required ─────────────────────────────────────────────────

class TestOllamaNoKeyRequired:
    def test_ollama_does_not_require_api_key(self):
        spec = ProviderSpec(kind="ollama", label="Ollama")
        assert validate_api_key(spec, "") is None

    def test_env_api_key_returns_empty_for_ollama(self, monkeypatch):
        spec = ProviderSpec(kind="ollama", label="Ollama")
        assert env_api_key(spec) == ""


# ── Bob — validation and resolution ──────────────────────────────────────────

class TestBobApiKeyValidation:
    def test_missing_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("BOBSHELL_API_KEY", raising=False)
        monkeypatch.delenv("BOB_API_KEY", raising=False)
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob", api_key_env="BOBSHELL_API_KEY")
        assert validate_api_key(spec, "") is not None

    def test_resolves_from_env(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "test-bob-key")
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob")
        conn = LLMConnection(provider="bob", api_key="")
        assert resolve_api_key(conn, spec) == "test-bob-key"


class TestBobResolveApiKeyForConnect:
    def test_uses_env_when_body_empty(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "bob_connect_key")
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob", api_key_env="BOBSHELL_API_KEY")
        assert resolve_api_key_for_connect(body_api_key="", spec=spec) == "bob_connect_key"

    def test_prefers_body_over_env(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "bob_env_key")
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob", api_key_env="BOBSHELL_API_KEY")
        assert resolve_api_key_for_connect(body_api_key="bob_pasted", spec=spec) == "bob_pasted"


# ── resolve_api_key priority ─────────────────────────────────────────────────

class TestResolveApiKeyPriority:
    def test_session_paste_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "from_env")
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob")
        conn = LLMConnection(provider="bob", api_key="from_session")
        assert resolve_api_key(conn, spec) == "from_session"

    def test_env_wins_when_session_empty(self, monkeypatch):
        monkeypatch.setenv("BOBSHELL_API_KEY", "from_env")
        spec = ProviderSpec(kind="bob_cli", label="IBM Bob")
        conn = LLMConnection(provider="bob", api_key="")
        assert resolve_api_key(conn, spec) == "from_env"
