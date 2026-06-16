"""
Tests for backend/app/services/connection_service.py

Covers connect_llm() for the primary Ollama provider path (connect,
model validation, base_url SSRF checks), connection_out() formatting,
and build_config_providers() assembly.
"""
from __future__ import annotations

from app.services.connection_service import (
    _validate_base_url,
    build_config_providers,
    connect_llm,
    connection_out,
)
from app.core.llm_config import LLMConnection


# ── Ollama connect (primary path) ─────────────────────────────────────────────

class TestOllamaConnect:
    """connect_llm() with the default Ollama provider."""

    def test_connects_with_valid_model(self):
        conn, err = connect_llm(
            provider="ollama",
            model="llama3.2:latest",
            base_url="http://127.0.0.1:11434",
            api_key="",
            request_timeout=600,
        )
        assert err is None
        assert conn is not None
        assert conn.provider == "ollama"
        assert conn.model == "llama3.2:latest"
        assert conn.base_url == "http://127.0.0.1:11434"

    def test_rejects_unknown_model(self):
        conn, err = connect_llm(
            provider="ollama",
            model="nonexistent-model",
            base_url="http://127.0.0.1:11434",
            api_key="",
            request_timeout=600,
        )
        assert conn is None
        assert err is not None
        assert "unknown model" in err.lower()

    def test_rejects_empty_model(self):
        conn, err = connect_llm(
            provider="ollama",
            model="",
            base_url="http://127.0.0.1:11434",
            api_key="",
            request_timeout=600,
        )
        assert conn is None
        assert "model" in (err or "").lower()

    def test_rejects_unknown_provider(self):
        conn, err = connect_llm(
            provider="nonexistent",
            model="some-model",
            base_url="",
            api_key="",
            request_timeout=600,
        )
        assert conn is None
        assert "unknown provider" in (err or "").lower()


# ── SSRF base_url validation ──────────────────────────────────────────────────

class TestBaseUrlValidation:
    """_validate_base_url() blocks dangerous URLs while allowing safe ones."""

    def test_allows_localhost(self):
        assert _validate_base_url("http://127.0.0.1:11434", "ollama") is None

    def test_allows_empty_url(self):
        assert _validate_base_url("", "ollama") is None

    def test_blocks_cloud_metadata(self):
        err = _validate_base_url("http://169.254.169.254/latest/meta-data", "ollama")
        assert err is not None
        assert "169.254.169.254" in err

    def test_blocks_private_ip(self):
        err = _validate_base_url("http://10.0.0.1:8080", "ollama")
        assert err is not None
        assert "private" in err.lower()

    def test_blocks_non_http_scheme(self):
        err = _validate_base_url("ftp://127.0.0.1:11434", "ollama")
        assert err is not None
        assert "scheme" in err.lower()


# ── Connection status formatting ──────────────────────────────────────────────

class TestConnectionOut:
    """connection_out() builds the frontend-facing status dict."""

    def test_disconnected_status(self):
        result = connection_out(None)
        assert result["connected"] is False

    def test_connected_ollama_status(self):
        conn = LLMConnection(
            provider="ollama",
            model="llama3.2:latest",
            base_url="http://127.0.0.1:11434",
        )
        result = connection_out(conn)
        assert result["connected"] is True
        assert result["provider"] == "ollama"
        assert result["model"] == "llama3.2:latest"
        assert result["label"] == "Ollama"


# ── Config assembly ───────────────────────────────────────────────────────────

class TestBuildConfigProviders:
    """build_config_providers() returns all registered providers."""

    def test_includes_ollama_as_first_provider(self):
        providers = build_config_providers()
        assert len(providers) > 0
        ollama = next((p for p in providers if p.provider == "ollama"), None)
        assert ollama is not None
        assert ollama.kind == "ollama"
        assert ollama.requires_base_url is True
        assert ollama.requires_api_key is False

    def test_all_providers_have_required_fields(self):
        providers = build_config_providers()
        for p in providers:
            assert p.provider
            assert p.kind
            assert p.label
            assert p.model
            assert len(p.models) > 0
