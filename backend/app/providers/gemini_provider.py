"""Google Gemini provider — GenerateContent REST API."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.llm_config import LLMConnection, ProviderSpec
from app.providers.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini provider using the ``models/{model}:generateContent`` endpoint.

    Converts OpenAI-style messages to Gemini's ``contents`` / ``systemInstruction``
    format before sending.
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
        """Send a generateContent request to Gemini.

        Args:
            conn: Session connection with model and API key.
            messages: OpenAI-format messages (system / user / assistant).
            timeout: HTTP timeout in seconds.
            json_format: If True, append a JSON-only instruction to the system prompt.

        Returns:
            Model response text.

        Raises:
            LLMError: On missing credentials, HTTP errors, or empty responses.
        """
        api_key = self._require_api_key(conn)
        base = conn.base_url.strip().rstrip("/") or self.spec.base_url.strip().rstrip("/")
        model = conn.model.strip()
        if not base:
            raise LLMError("Gemini base URL is required")
        if not model:
            raise LLMError("Gemini model name is required")

        system_instruction, contents = self._convert_messages(messages)
        if json_format:
            hint = "Respond with a single JSON object only. No markdown fences."
            system_instruction = f"{system_instruction}\n\n{hint}" if system_instruction else hint

        payload: dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{base}/models/{model}:generateContent"
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Gemini HTTP {e.response.status_code}: {e.response.text[:500]}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Could not reach Gemini at {base}: {e}") from e

        return self._extract_content(r.json())

    def health_check(self) -> bool:
        """Verify Gemini API key by listing models.

        Returns:
            True if the key is accepted and models are returned, False otherwise.
        """
        api_key = self._resolve_api_key(
            LLMConnection(provider="gemini", api_key="")
        )
        if not api_key:
            return False
        base = self.spec.base_url.strip().rstrip("/")
        try:
            r = httpx.get(
                f"{base}/models",
                headers={"x-goog-api-key": api_key},
                timeout=5.0,
            )
            return r.is_success
        except httpx.HTTPError:
            return False

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI-format messages to Gemini's contents format.

        Args:
            messages: List of ``{role, content}`` dicts.

        Returns:
            Tuple of (system_instruction text or None, contents list).
        """
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "").strip()
            text = msg.get("content", "").strip()
            if not text:
                continue
            if role == "system":
                system_parts.append(text)
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": text}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": text}]})
        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return system_instruction, contents

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        """Extract text from Gemini generateContent response.

        Args:
            data: Parsed JSON response body.

        Returns:
            Concatenated text from all candidate parts.

        Raises:
            LLMError: If no candidates or empty content.
        """
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError(f"Unexpected Gemini response: {repr(data)[:800]}")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if isinstance(p.get("text"), str)]
        content = "\n".join(t for t in texts if t.strip()).strip()
        if not content:
            raise LLMError(f"Gemini returned empty content: {repr(data)[:800]}")
        return content
