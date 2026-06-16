"""
Ollama provider — local LLM inference, model discovery, and health checks.

All Ollama logic lives here: chat completions via ``/api/chat``, model
listing via ``/api/tags`` with sizes and recommended-use tags, and
health probes.  No separate service module.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.llm_config import LLMConnection, ProviderSpec, get_settings
from app.providers.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider for local model inference.

    Uses the ``/api/chat`` endpoint (not the OpenAI-compatible ``/v1``).
    Supports ``format: "json"`` for structured output.
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
        """Send a chat request to the Ollama ``/api/chat`` endpoint.

        Args:
            conn: Session connection with ``base_url`` and ``model``.
            messages: Chat messages (system / user / assistant).
            timeout: HTTP timeout in seconds.
            json_format: Request JSON-only output via ``format: "json"``.

        Returns:
            Model response text.

        Raises:
            LLMError: If base_url or model is missing, or the request fails.
        """
        base = conn.base_url.strip().rstrip("/")
        model = conn.model.strip()
        if not base:
            raise LLMError("Ollama base URL is required")
        if not model:
            raise LLMError("Ollama model name is required")

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if json_format:
            payload["format"] = "json"

        logger.info(
            "Ollama chat: model=%s messages=%d timeout=%ss",
            model, len(messages), int(timeout),
        )
        try:
            r = httpx.post(f"{base}/api/chat", json=payload, timeout=timeout)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Ollama HTTP {e.response.status_code}: {e.response.text[:500]}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Could not reach Ollama at {base}: {e}") from e

        data = r.json()
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise LLMError(f"Unexpected Ollama response shape: {repr(data)[:800]}")
        return content

    def health_check(self) -> bool:
        """Ping Ollama ``GET /api/tags`` to verify the server is reachable.

        Returns:
            True if Ollama responds successfully, False otherwise.
        """
        base = self.spec.base_url.strip().rstrip("/")
        if not base:
            return False
        try:
            r = httpx.get(f"{base}/api/tags", timeout=5.0)
            return r.is_success
        except httpx.HTTPError:
            return False


# ── Model discovery (used by API routes) ───────────────────────────────────────

def recommend_tags(name: str) -> list[str]:
    """Suggest recommended-use tags for a model based on its name.

    Args:
        name: Ollama model name (e.g. ``"qwen2.5-coder:7b"``).

    Returns:
        De-duplicated list of tag strings.
    """
    n = name.lower()
    tags: list[str] = []
    if any(k in n for k in ("qwen", "coder", "code")):
        tags += ["code_analysis", "script_tracing", "failure_analysis"]
    if "deepseek" in n:
        tags += ["code_analysis", "script_tracing"]
    if "llama" in n and "coder" not in n:
        tags += ["chat", "summarization", "general_reasoning"]
    if "gemma" in n:
        tags += ["fast_chat", "quick_summary", "failure_analysis"]
    if "mistral" in n:
        tags += ["chat", "summarization"]
    if not tags:
        tags = ["general_reasoning"]
    return list(dict.fromkeys(tags))


def human_size(size_bytes: int) -> str:
    """Format byte count as a human-readable string (KB / MB / GB).

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string (e.g. ``"4.7 GB"``).
    """
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.0f} MB"
    return f"{size_bytes / 1_000:.0f} KB"


def ollama_health() -> dict:
    """Check Ollama server reachability via ``GET /api/tags``.

    Returns:
        Dict with ``healthy``, ``base_url``, and ``error`` keys.
    """
    settings = get_settings()
    spec = settings.llm_providers.get("ollama")
    base = (spec.base_url if spec else "http://127.0.0.1:11434").rstrip("/")
    try:
        r = httpx.get(f"{base}/api/tags", timeout=5.0)
        r.raise_for_status()
        return {"healthy": True, "base_url": base, "error": None}
    except httpx.ConnectError:
        return {
            "healthy": False,
            "base_url": base,
            "error": f"Unable to connect to Ollama at {base}. Run: ollama serve",
        }
    except Exception as exc:
        return {"healthy": False, "base_url": base, "error": str(exc)}


def list_ollama_models(*, selected_model: str = "") -> dict:
    """Fetch installed Ollama models with sizes and recommended-use tags.

    Args:
        selected_model: Currently selected model name (for UI tracking).

    Returns:
        Dict with ``models`` list, ``default_model``, ``selected_model``,
        ``healthy`` flag, and ``base_url``.
    """
    settings = get_settings()
    spec = settings.llm_providers.get("ollama")
    base = (spec.base_url if spec else "http://127.0.0.1:11434").rstrip("/")
    default_model = spec.model if spec else "llama3.2:latest"

    try:
        r = httpx.get(f"{base}/api/tags", timeout=10.0)
        r.raise_for_status()
        raw = r.json()
    except httpx.HTTPError:
        return {
            "models": [],
            "default_model": default_model,
            "selected_model": selected_model or default_model,
            "healthy": False,
            "base_url": base,
        }

    models: list[dict] = []
    for entry in raw.get("models") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        size_bytes = entry.get("size") or 0
        models.append(
            {
                "name": name.strip(),
                "size": human_size(size_bytes) if size_bytes else None,
                "modified_at": entry.get("modified_at"),
                "recommended_for": recommend_tags(name),
            }
        )

    return {
        "models": models,
        "default_model": default_model,
        "selected_model": selected_model or default_model,
        "healthy": True,
        "base_url": base,
    }
