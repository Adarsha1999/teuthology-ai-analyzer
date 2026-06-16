"""
LLM client — thin dispatch layer over the provider factory.

All provider-specific logic lives in ``app.providers.*``.  This module
provides the public API consumed by ``analysis_service`` and ``assistant``:

    chat_llm(conn, messages, …) → str
    analyze_failure(conn, …) → dict

It also houses connection validation and API-key resolution helpers
used by ``connection_service``.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.core.llm_config import LLMConnection, ProviderSpec, Settings, get_settings
from app.providers.factory import ProviderFactory
from app.services.llm_common import LLMError, build_analysis_prompt, parse_analysis_response

logger = logging.getLogger(__name__)


# ── API key helpers ────────────────────────────────────────────────────────────

def env_api_key(spec: ProviderSpec) -> str:
    """Read the API key from provider-specific environment variables.

    Checks ``spec.api_key_env`` first, then falls back to well-known
    env vars for Cursor and Bob CLI.

    Args:
        spec: Provider specification with ``api_key_env`` hint.

    Returns:
        API key string (may be empty if nothing is set).
    """
    if spec.api_key_env:
        val = os.environ.get(spec.api_key_env, "").strip()
        if val:
            return val
    if spec.kind == "cursor":
        return os.environ.get("CURSOR_API_KEY", "").strip()
    if spec.kind == "bob_cli":
        return (
            os.environ.get("BOBSHELL_API_KEY", "").strip()
            or os.environ.get("BOB_API_KEY", "").strip()
        )
    return ""


def resolve_api_key(conn: LLMConnection, spec: ProviderSpec) -> str:
    """Resolve API key with priority: session paste > env var > config default.

    Args:
        conn: Per-session connection with optional user-pasted key.
        spec: Provider specification with defaults.

    Returns:
        Best available API key string (may be empty).
    """
    pasted = conn.api_key.strip()
    if pasted:
        return pasted
    env_key = env_api_key(spec)
    if env_key:
        return env_key
    return spec.api_key.strip()


def resolve_api_key_for_connect(
    *,
    body_api_key: str,
    spec: ProviderSpec,
) -> str:
    """Resolve API key during the connect flow (UI body > env > config).

    Args:
        body_api_key: Key pasted in the connect form.
        spec: Provider specification.

    Returns:
        Resolved API key string.
    """
    return body_api_key.strip() or env_api_key(spec) or spec.api_key.strip()


def validate_api_key(spec: ProviderSpec, api_key: str) -> str | None:
    """Return an error message if the key is missing for key-based providers.

    Args:
        spec: Provider specification with ``requires_api_key``.
        api_key: Candidate API key to check.

    Returns:
        Error message string, or None if valid.
    """
    if not spec.requires_api_key:
        return None
    key = api_key.strip() or env_api_key(spec) or spec.api_key.strip()
    if not key:
        env_hint = f" or export {spec.api_key_env}" if spec.api_key_env else ""
        if spec.kind == "bob_cli":
            return (
                f"{spec.label} API key is required. Create an Inference-scope key at "
                "https://bob.ibm.com/docs/ide/account/api-keys and set "
                "BOBSHELL_API_KEY in backend/.env. Install Bob Shell: "
                "https://bob.ibm.com/docs/shell/getting-started/install-and-setup"
            )
        return f"{spec.label} API key is required. Set it in .env{env_hint}."
    return None


# ── Connection validation ──────────────────────────────────────────────────────

def validate_connect(
    provider_id: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    settings: Settings | None = None,
) -> str | None:
    """Validate a connect request before persisting the session.

    Checks provider existence, model name, base URL, and API key.

    Args:
        provider_id: Provider catalog key (e.g. ``"ollama"``).
        model: Requested model name.
        base_url: Requested base URL.
        api_key: Resolved API key.
        settings: Optional pre-loaded settings (avoids re-read).

    Returns:
        Error message string, or None if all checks pass.
    """
    settings = settings or get_settings()
    if provider_id not in settings.llm_providers:
        return f"Unknown provider '{provider_id}'"
    spec = settings.get_provider(provider_id)
    if not model.strip():
        return "Model name is required"
    if model.strip() not in spec.models:
        return (
            f"Unknown model '{model}' for {provider_id}. "
            f"Choose from: {', '.join(spec.models)}"
        )
    if spec.requires_base_url and not (base_url.strip() or spec.base_url.strip()):
        return "Base URL is required"
    return validate_api_key(spec, api_key)


def build_connection(
    provider_id: str,
    *,
    model: str,
    base_url: str = "",
    api_key: str = "",
    request_timeout: int | None = None,
    settings: Settings | None = None,
) -> LLMConnection:
    """Build an ``LLMConnection`` with resolved defaults from provider config.

    Args:
        provider_id: Provider catalog key.
        model: Requested model (falls back to spec default).
        base_url: Requested base URL (falls back to spec default).
        api_key: Resolved API key.
        request_timeout: Optional timeout override.
        settings: Optional pre-loaded settings.

    Returns:
        Populated LLMConnection instance.
    """
    settings = settings or get_settings()
    spec = settings.get_provider(provider_id)
    resolved_key = api_key.strip() or env_api_key(spec) or spec.api_key.strip()
    return LLMConnection(
        provider=provider_id,
        base_url=base_url.strip() or spec.base_url.strip(),
        model=model.strip() or spec.model,
        api_key=resolved_key,
        request_timeout=request_timeout or spec.request_timeout,
    )


def validate_cursor_api_key_live(api_key: str) -> str | None:
    """Call Cursor API to verify the key; return an error message or None.

    Delegates to ``CursorProvider.validate_api_key_live()``.

    Args:
        api_key: API key to validate.

    Returns:
        Error message string, or None if the key is valid.
    """
    from app.providers.cursor_provider import CursorProvider
    return CursorProvider.validate_api_key_live(api_key)


# ── Model discovery ────────────────────────────────────────────────────────────

def list_installed_models(base_url: str, *, timeout: float = 5.0) -> list[str]:
    """Return model names from Ollama ``GET /api/tags``, or ``[]`` if unreachable.

    Args:
        base_url: Ollama server URL (e.g. ``http://127.0.0.1:11434``).
        timeout: HTTP timeout in seconds.

    Returns:
        List of model name strings.
    """
    base = base_url.strip().rstrip("/")
    if not base:
        return []
    try:
        r = httpx.get(f"{base}/api/tags", timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    data = r.json()
    names: list[str] = []
    for entry in data.get("models") or []:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def merge_model_lists(*lists: list[str]) -> list[str]:
    """De-duplicate and merge multiple model name lists preserving order.

    Args:
        *lists: Variable number of model-name lists.

    Returns:
        Merged list with duplicates removed.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for name in lst:
            if name and name not in seen:
                seen.add(name)
                merged.append(name)
    return merged


# ── Core dispatch ──────────────────────────────────────────────────────────────

def chat_llm(
    conn: LLMConnection,
    messages: list[dict[str, str]],
    *,
    timeout: float,
    json_format: bool = False,
    settings: Settings | None = None,
) -> str:
    """Dispatch a chat request to the appropriate provider via the factory.

    Resolves the provider ``kind`` from the connection's provider ID, looks
    up (or creates) the provider instance via ``ProviderFactory``, and
    delegates to its ``chat()`` method.

    Args:
        conn: Per-session LLM connection.
        messages: OpenAI-format message list.
        timeout: Request timeout in seconds.
        json_format: If True, request JSON-only output.
        settings: Optional pre-loaded settings.

    Returns:
        Raw model response text.

    Raises:
        LLMError: If the provider kind is unknown or the request fails.
    """
    settings = settings or get_settings()
    spec = settings.get_provider(conn.provider)
    provider = ProviderFactory.get_provider(spec.kind)
    return provider.chat(conn, messages, timeout=timeout, json_format=json_format)


def analyze_failure(
    conn: LLMConnection,
    *,
    job_id: str,
    description: str,
    machine: str,
    os_line: str,
    failure_reason: str | None,
    digest: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Analyze a single job failure using the connected LLM.

    Builds the analysis prompt, dispatches to the provider, and parses
    the structured JSON response.

    Args:
        conn: Per-session LLM connection.
        job_id: Teuthology job identifier.
        description: Job description string.
        machine: Machine hostname.
        os_line: OS type and version string.
        failure_reason: Pulpito failure reason (may be None).
        digest: Pre-built log digest text.
        settings: Optional pre-loaded settings.

    Returns:
        Parsed analysis dict with keys: summary, likely_root_cause,
        evidence, next_steps, confidence.
    """
    system, user = build_analysis_prompt(
        job_id=job_id,
        description=description,
        machine=machine,
        os_line=os_line,
        failure_reason=failure_reason,
        digest=digest,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    content = chat_llm(
        conn,
        messages,
        timeout=float(conn.request_timeout),
        json_format=True,
        settings=settings,
    )
    return parse_analysis_response(content)
