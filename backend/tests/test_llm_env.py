"""
Tests for backend/app/core/llm_config.py — provider settings from environment.

Validates that Ollama provider config (base_url, model) is correctly
loaded from environment variables via get_settings().
"""
from __future__ import annotations

from app.core.llm_config import get_settings


# ── Provider config from environment ──────────────────────────────────────────

class TestOllamaConfigFromEnv:
    def test_ollama_base_url_and_model_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.100:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "gemma4:latest")
        settings = get_settings()
        ollama = settings.llm_providers["ollama"]
        assert ollama.base_url == "http://192.168.1.100:11434"
        assert ollama.model == "gemma4:latest"
        assert "gemma4:latest" in ollama.models

    def test_ollama_is_default_provider(self) -> None:
        settings = get_settings()
        assert settings.llm_default_provider == "ollama"
        assert "ollama" in settings.llm_providers
