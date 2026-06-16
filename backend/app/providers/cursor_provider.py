"""Cursor SDK provider — uses ``cursor-sdk`` to run prompts via Cursor Agent."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.llm_config import LLMConnection, ProviderSpec
from app.providers.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_CURSOR_AUTH_HELP = (
    "Cursor authentication failed. Check:\n"
    "1. Create a **user** API key at https://cursor.com/dashboard/integrations "
    "(not Admin API keys under Settings → Advanced)\n"
    "2. export CURSOR_API_KEY='crsr_...' in the **same terminal** that runs uvicorn, "
    "or set CURSOR_API_KEY in .env\n"
    "3. Restart the API server after exporting, then Disconnect → Connect in the UI"
)


class CursorProvider(LLMProvider):
    """Cursor SDK provider for running prompts via the Cursor Agent.

    Requires the optional ``cursor-sdk`` package
    (``pip install -e ".[cursor]"``).
    """

    def __init__(self, spec: ProviderSpec) -> None:
        super().__init__(spec)

    def chat(
        self,
        conn: LLMConnection,
        messages: list[dict[str, str]],
        *,
        timeout: float,
        json_format: bool = False,
    ) -> str:
        """Run a prompt through the Cursor Agent SDK.

        Args:
            conn: Session connection with model and API key.
            messages: Chat messages converted into a single prompt string.
            timeout: Ignored (Cursor SDK manages its own timeout).
            json_format: If True, append a JSON-only instruction.

        Returns:
            Agent response text.

        Raises:
            LLMError: On missing SDK, auth failure, or empty response.
        """
        del timeout
        api_key = self._require_api_key(conn)
        model = conn.model.strip()
        if not model:
            raise LLMError("Cursor model name is required")

        try:
            from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
        except ImportError as e:
            raise LLMError(
                'cursor-sdk is not installed. Run: pip install -e ".[cursor]"'
            ) from e

        prompt = self._messages_to_prompt(messages, json_format=json_format)
        options = AgentOptions(
            model=model,
            api_key=api_key or None,
            local=LocalAgentOptions(cwd=str(_PROJECT_ROOT)),
        )
        try:
            result = Agent.prompt(prompt, options)
        except Exception as e:
            raise self._map_exception(e) from e
        return self._extract_result(result)

    def health_check(self) -> bool:
        """Check if cursor-sdk is importable and API key is configured.

        Returns:
            True if SDK is available and a key is set, False otherwise.
        """
        try:
            import cursor_sdk  # noqa: F401
        except ImportError:
            return False
        key = self._resolve_api_key(
            LLMConnection(provider="cursor", api_key="")
        )
        return bool(key)

    @staticmethod
    def validate_api_key_live(api_key: str) -> str | None:
        """Call Cursor API to verify the key; return an error message or None.

        Args:
            api_key: API key to validate.

        Returns:
            Error message string, or None if valid.
        """
        key = api_key.strip()
        if not key:
            return (
                "Cursor API key is required. export CURSOR_API_KEY=crsr_... "
                "or set CURSOR_API_KEY in .env"
            )
        try:
            from cursor_sdk._client import _default_client
        except ImportError:
            return 'cursor-sdk is not installed. Run: pip install -e ".[cursor]"'
        try:
            _default_client().me(api_key=key)
        except Exception as e:
            lower = str(e).lower()
            if "unauthenticated" in lower or "401" in lower or "authentication" in type(e).__name__.lower():
                return f"Cursor rejected this API key ({e}).\n\n{_CURSOR_AUTH_HELP}"
            return f"Cursor API check failed: {e}"
        return None

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _messages_to_prompt(
        messages: list[dict[str, str]], *, json_format: bool
    ) -> str:
        """Flatten chat messages into a single prompt string.

        Args:
            messages: OpenAI-format message list.
            json_format: Append JSON-only instruction if True.

        Returns:
            Concatenated prompt text.
        """
        system_parts: list[str] = []
        dialog: list[str] = []
        for msg in messages:
            role = msg.get("role", "").strip()
            content = msg.get("content", "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                dialog.append(f"User:\n{content}")
            elif role == "assistant":
                dialog.append(f"Assistant:\n{content}")
        chunks: list[str] = []
        if system_parts:
            chunks.append("\n\n".join(system_parts))
        if dialog:
            chunks.append("\n\n".join(dialog))
        prompt = "\n\n".join(chunks)
        if json_format:
            prompt += (
                "\n\nRespond with a single JSON object only. "
                "No markdown fences or extra commentary."
            )
        return prompt

    @staticmethod
    def _coerce_result_text(raw: Any) -> str:
        """Coerce various SDK result shapes into a plain string.

        Args:
            raw: The ``result`` attribute from ``Agent.prompt()``.

        Returns:
            Extracted text content.
        """
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            for key in ("text", "content", "message", "output", "response"):
                val = raw.get(key)
                if isinstance(val, str):
                    return val
            return json.dumps(raw)
        return str(raw)

    @classmethod
    def _extract_result(cls, result: Any) -> str:
        """Extract usable text from a Cursor Agent result object.

        Args:
            result: Result object from ``Agent.prompt()``.

        Returns:
            Non-empty response text.

        Raises:
            LLMError: If the agent failed or returned empty output.
        """
        status = getattr(result, "status", None)
        raw = getattr(result, "result", None)
        text = cls._coerce_result_text(raw)
        status_s = str(status).lower() if status is not None else ""

        if status_s in ("error", "failed", "cancelled", "canceled") and not text.strip():
            raise LLMError(
                f"Cursor agent failed (status={status}). "
                "Log triage works best with Ollama; Cursor is a coding agent."
            )
        if not text.strip():
            if status_s and status_s not in ("completed", "success", "succeeded", "done"):
                raise LLMError(
                    f"Cursor returned no output (status={status}). "
                    f"{_CURSOR_AUTH_HELP if 'auth' in status_s else ''}"
                )
            raise LLMError("Cursor returned empty output.")
        return text.strip()

    @staticmethod
    def _map_exception(exc: Exception) -> LLMError:
        """Map cursor-sdk exceptions to descriptive LLMError messages.

        Args:
            exc: Original exception from the SDK.

        Returns:
            Wrapped LLMError with user-friendly guidance.
        """
        msg = str(exc)
        lower = msg.lower()
        if "configurationerror" in type(exc).__name__.lower() or "api_key" in lower:
            return LLMError(f"{msg}\n\n{_CURSOR_AUTH_HELP}")
        if "unauthenticated" in lower or "401" in lower or "403" in lower:
            return LLMError(f"{msg}\n\n{_CURSOR_AUTH_HELP}")
        if "cursor-sdk" in lower or "cursor_sdk" in lower or "no module" in lower:
            return LLMError('cursor-sdk is not installed. Run: pip install -e ".[cursor]"')
        return LLMError(f"Cursor error: {msg}")
