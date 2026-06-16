"""
Base LLM provider interface.

Every concrete provider (Ollama, OpenAI, Gemini, Cursor, Bob CLI) implements
this ABC.  The factory instantiates providers and caches them by ``kind``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.llm_config import LLMConnection, ProviderSpec
from app.services.llm_common import LLMError  # noqa: F401 — re-exported for convenience


class LLMProvider(ABC):
    """Base class for LLM providers.

    Args:
        spec: Static provider configuration loaded from env / builtin catalog.
    """

    def __init__(self, spec: ProviderSpec) -> None:
        self.spec = spec
        self.name = spec.kind

    @abstractmethod
    def chat(
        self,
        conn: LLMConnection,
        messages: list[dict[str, str]],
        *,
        timeout: float,
        json_format: bool = False,
    ) -> str:
        """Send a chat-completion request and return the model's text reply.

        Args:
            conn: Per-session connection (model, base_url, api_key overrides).
            messages: OpenAI-style message list (role + content).
            timeout: Request timeout in seconds.
            json_format: If True, instruct the model to reply with JSON only.

        Returns:
            Raw text content from the model.

        Raises:
            LLMError: On transport, auth, or empty-response errors.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Check whether the provider is reachable and healthy.

        Returns:
            True if the provider can serve requests, False otherwise.
        """

    def get_display_name(self) -> str:
        """Human-readable name shown in the UI."""
        return self.spec.label or self.name

    def get_model_name(self) -> str | None:
        """Default model name from provider config."""
        return self.spec.model or None

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _resolve_api_key(self, conn: LLMConnection) -> str:
        """Resolve API key: session paste > env var > config default.

        Args:
            conn: Per-session connection with optional user-pasted key.

        Returns:
            Best available API key string (may be empty).
        """
        import os

        pasted = conn.api_key.strip()
        if pasted:
            return pasted
        if self.spec.api_key_env:
            env_val = os.environ.get(self.spec.api_key_env, "").strip()
            if env_val:
                return env_val
        if self.spec.kind == "cursor":
            val = os.environ.get("CURSOR_API_KEY", "").strip()
            if val:
                return val
        if self.spec.kind == "bob_cli":
            val = (
                os.environ.get("BOBSHELL_API_KEY", "").strip()
                or os.environ.get("BOB_API_KEY", "").strip()
            )
            if val:
                return val
        return self.spec.api_key.strip()

    def _require_api_key(self, conn: LLMConnection) -> str:
        """Like ``_resolve_api_key`` but raises if the key is empty.

        Returns:
            Non-empty API key.

        Raises:
            LLMError: If no key can be resolved.
        """
        key = self._resolve_api_key(conn)
        if key:
            return key
        env_hint = f" or export {self.spec.api_key_env}" if self.spec.api_key_env else ""
        raise LLMError(
            f"{self.spec.label} API key is required. Set it in .env{env_hint}."
        )
