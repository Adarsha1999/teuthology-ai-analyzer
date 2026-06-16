"""
AI Provider Factory — creates, caches, and manages LLM provider instances.

Mirrors the cephci-ai-assistant ``ProviderFactory`` pattern:
eager registration for always-available providers, lazy import for
optional dependencies, singleton caching per provider kind.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.llm_config import ProviderSpec, get_settings
from app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating and managing LLM provider instances.

    Providers are registered by ``kind`` (transport type) and instantiated
    lazily on first request.  Instances are cached for the process lifetime.
    """

    # ── Registry ───────────────────────────────────────────────────────────

    _providers: dict[str, type[LLMProvider]] = {}
    _instances: dict[str, LLMProvider] = {}

    DISPLAY_LABELS: dict[str, str] = {
        "ollama":  "Ollama (Local)",
        "openai":  "ChatGPT (OpenAI)",
        "gemini":  "Gemini (Google)",
        "cursor":  "Cursor Agent (SDK)",
        "bob_cli": "IBM Bob (Shell)",
    }

    # ── Registration ───────────────────────────────────────────────────────

    @classmethod
    def _ensure_all_providers_registered(cls) -> None:
        """Eagerly register built-in providers, gracefully skip missing deps.

        Called once before any provider lookup to populate ``_providers``.
        """
        if "ollama" not in cls._providers:
            try:
                from app.providers.ollama_provider import OllamaProvider
                cls._providers["ollama"] = OllamaProvider
            except Exception as e:
                logger.warning("Ollama provider unavailable: %s", e)

        if "openai" not in cls._providers:
            try:
                from app.providers.openai_provider import OpenAIProvider
                cls._providers["openai"] = OpenAIProvider
            except Exception as e:
                logger.warning("OpenAI provider unavailable: %s", e)

        if "gemini" not in cls._providers:
            try:
                from app.providers.gemini_provider import GeminiProvider
                cls._providers["gemini"] = GeminiProvider
            except Exception as e:
                logger.warning("Gemini provider unavailable: %s", e)

        if "cursor" not in cls._providers:
            try:
                from app.providers.cursor_provider import CursorProvider
                cls._providers["cursor"] = CursorProvider
            except Exception as e:
                logger.warning("Cursor provider unavailable: %s", e)

        if "bob_cli" not in cls._providers:
            try:
                from app.providers.bob_cli_provider import BobCLIProvider
                cls._providers["bob_cli"] = BobCLIProvider
            except Exception as e:
                logger.warning("Bob CLI provider unavailable: %s", e)

    @classmethod
    def register_provider(cls, kind: str, provider_class: type[LLMProvider]) -> None:
        """Register a custom provider class.

        Args:
            kind: Unique transport identifier (e.g. ``"ollama"``).
            provider_class: Subclass of ``LLMProvider``.
        """
        cls._providers[kind] = provider_class
        logger.info("Registered provider: %s", kind)

    # ── Lookup ─────────────────────────────────────────────────────────────

    @classmethod
    def get_provider(cls, kind: str) -> LLMProvider:
        """Get or create a cached provider instance by kind.

        Args:
            kind: Provider transport type (``"ollama"``, ``"openai"``, etc.).

        Returns:
            Cached ``LLMProvider`` instance.

        Raises:
            ValueError: If the kind is not registered.
        """
        cls._ensure_all_providers_registered()

        if kind in cls._instances:
            return cls._instances[kind]

        if kind not in cls._providers:
            available = ", ".join(sorted(cls._providers.keys()))
            raise ValueError(
                f"Provider kind '{kind}' not found. Available: {available}"
            )

        provider_class = cls._providers[kind]
        spec = cls._get_provider_spec(kind)
        try:
            instance = provider_class(spec)
            cls._instances[kind] = instance
            logger.info("Created provider instance: %s", kind)
            return instance
        except Exception as e:
            logger.error("Failed to create provider '%s': %s", kind, e)
            raise

    @classmethod
    def get_all_providers(cls) -> dict[str, LLMProvider]:
        """Get all available provider instances.

        Returns:
            Dict mapping kind → provider instance (skipping failures).
        """
        cls._ensure_all_providers_registered()
        providers: dict[str, LLMProvider] = {}
        for kind in cls._providers:
            try:
                providers[kind] = cls.get_provider(kind)
            except Exception as e:
                logger.warning("Failed to initialize provider '%s': %s", kind, e)
        return providers

    @classmethod
    def list_available_providers(cls) -> list[str]:
        """List registered provider kinds in display order.

        Returns:
            Ordered list of kind strings.
        """
        cls._ensure_all_providers_registered()
        ordered = ["ollama", "openai", "gemini", "cursor", "bob_cli"]
        return [k for k in ordered if k in cls._providers] + [
            k for k in cls._providers if k not in ordered
        ]

    @classmethod
    def health_check_all(cls) -> dict[str, bool]:
        """Run health checks for all registered providers.

        Returns:
            Dict mapping kind → healthy boolean.
        """
        cls._ensure_all_providers_registered()
        results: dict[str, bool] = {}
        for kind in cls._providers:
            try:
                provider = cls.get_provider(kind)
                results[kind] = provider.health_check()
            except Exception as e:
                logger.warning("Health check failed for '%s': %s", kind, e)
                results[kind] = False
        return results

    # ── Cache management ───────────────────────────────────────────────────

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached provider instances (useful for testing)."""
        cls._instances.clear()
        logger.info("Cleared provider cache")

    # ── Private helpers ────────────────────────────────────────────────────

    @classmethod
    def _get_provider_spec(cls, kind: str) -> ProviderSpec:
        """Look up the ``ProviderSpec`` for a kind from app settings.

        Falls back to a minimal default spec if the kind is not in the
        provider catalog (e.g. custom-registered providers).

        Args:
            kind: Provider transport type.

        Returns:
            ProviderSpec from settings, or a bare-minimum default.
        """
        settings = get_settings()
        for _pid, spec in settings.llm_providers.items():
            if spec.kind == kind:
                return spec
        return ProviderSpec(kind=kind, label=cls.DISPLAY_LABELS.get(kind, kind))
