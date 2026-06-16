"""OpenAI provider — ChatGPT and OpenAI-compatible APIs."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.llm_config import LLMConnection, ProviderSpec
from app.providers.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI provider using the ``/chat/completions`` endpoint.

    Also serves as the base for any OpenAI-compatible API (e.g. Azure,
    Together, etc.) by pointing ``base_url`` at the target host.
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
        """Send a chat-completion request to OpenAI (or compatible API).

        Args:
            conn: Session connection with model, base_url, and API key.
            messages: OpenAI-format message list.
            timeout: HTTP timeout in seconds.
            json_format: If True, request ``response_format: json_object``.

        Returns:
            Model response text.

        Raises:
            LLMError: On missing credentials, HTTP errors, or empty responses.
        """
        api_key = self._require_api_key(conn)
        base = conn.base_url.strip().rstrip("/") or self.spec.base_url.strip().rstrip("/")
        model = conn.model.strip()
        if not base:
            raise LLMError("OpenAI base URL is required (set in .env)")
        if not model:
            raise LLMError("OpenAI model name is required")

        payload: dict[str, Any] = {"model": model, "messages": messages}
        if json_format:
            payload["response_format"] = {"type": "json_object"}

        headers = self._build_headers(api_key)
        try:
            r = httpx.post(
                f"{base}/chat/completions",
                json=payload, headers=headers, timeout=timeout,
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI HTTP {e.response.status_code}: {e.response.text[:500]}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Could not reach OpenAI at {base}: {e}") from e

        return self._extract_content(r.json())

    def health_check(self) -> bool:
        """Verify OpenAI API key by listing models.

        Returns:
            True if the key is valid and the API responds, False otherwise.
        """
        api_key = self._resolve_api_key(
            LLMConnection(provider="openai", api_key="")
        )
        if not api_key:
            return False
        base = self.spec.base_url.strip().rstrip("/")
        try:
            r = httpx.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0,
            )
            return r.is_success
        except httpx.HTTPError:
            return False

    # ── Private helpers ────────────────────────────────────────────────────

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Build HTTP headers for the OpenAI-compatible request.

        Args:
            api_key: Resolved API key.

        Returns:
            Header dict with Authorization and Content-Type.
        """
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        """Extract the assistant message text from an OpenAI response.

        Args:
            data: Parsed JSON response body.

        Returns:
            Text content string.

        Raises:
            LLMError: If the response is missing choices or content.
        """
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"Unexpected OpenAI response: {repr(data)[:800]}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMError(f"Unexpected OpenAI response shape: {repr(data)[:800]}")
        return content
