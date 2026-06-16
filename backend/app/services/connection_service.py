"""
Connection service — validation, SSRF protection, and config assembly.

Handles the connect/disconnect flow between the UI and LLM providers.
Validates base URLs against an allowlist to prevent SSRF, resolves API
keys, and builds the ``ProviderConfigOut`` list for ``GET /api/config``.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.core.llm_config import LLMConnection, get_settings
from app.models.schemas import ConnectionOut, ProviderConfigOut
from app.services.llm_client import (
    build_connection,
    resolve_api_key_for_connect,
    validate_connect,
    validate_cursor_api_key_live,
)

# ── SSRF protection ────────────────────────────────────────────────────────────

_SAFE_HOSTS = frozenset({
    "127.0.0.1", "localhost", "host.docker.internal",
    "api.openai.com",
    "generativelanguage.googleapis.com",
})


def _validate_base_url(url: str, provider: str) -> str | None:
    """Block base_url values that could reach internal or cloud-metadata services.

    Args:
        url: Raw base URL from the connect request.
        provider: Provider ID (for context in error messages).

    Returns:
        Error message string, or None if the URL is safe.
    """
    if not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return f"Invalid base URL: {url}"
    if parsed.scheme not in ("http", "https"):
        return f"base_url scheme must be http or https, got '{parsed.scheme}'"
    host = (parsed.hostname or "").lower()
    if not host:
        return "base_url has no hostname"
    if host in _SAFE_HOSTS:
        return None
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_link_local or addr.is_loopback:
            if host != "127.0.0.1":
                return (
                    f"base_url points to a private/link-local IP ({host}). "
                    "Only localhost is allowed."
                )
    except ValueError:
        pass
    if host in ("169.254.169.254", "metadata.google.internal"):
        return f"base_url blocked: cloud metadata endpoint ({host})"
    return None


# ── Connection status formatting ───────────────────────────────────────────────

def connection_out(conn: LLMConnection | None) -> dict:
    """Format a ``ConnectionOut`` dict for the frontend status endpoint.

    Args:
        conn: Active LLM connection, or None if disconnected.

    Returns:
        Serialised ``ConnectionOut`` as a dict.
    """
    if conn is None:
        return ConnectionOut(connected=False).model_dump()
    settings = get_settings()
    spec = settings.llm_providers.get(conn.provider)
    label = spec.label if spec else conn.provider
    icon = spec.icon if spec else "🤖"
    return ConnectionOut(
        connected=True,
        provider=conn.provider,
        label=label,
        icon=icon,
        model=conn.model,
    ).model_dump()


# ── Config assembly ────────────────────────────────────────────────────────────

def build_config_providers() -> list[ProviderConfigOut]:
    """Build the provider list returned by ``GET /api/config``.

    Reads the provider catalog from settings and maps each entry to
    a ``ProviderConfigOut`` schema suitable for the frontend.

    Returns:
        List of serialisable provider configuration objects.
    """
    settings = get_settings()
    providers: list[ProviderConfigOut] = []
    for pid, spec in settings.llm_providers.items():
        providers.append(
            ProviderConfigOut(
                provider=pid,
                kind=spec.kind,
                label=spec.label,
                icon=spec.icon,
                tag=spec.tag,
                base_url=spec.base_url,
                model=spec.model,
                models=list(spec.models),
                request_timeout=spec.request_timeout,
                has_api_key=bool(spec.api_key.strip()),
                requires_api_key=spec.requires_api_key,
                requires_base_url=spec.requires_base_url,
                api_key_env=spec.api_key_env,
            )
        )
    return providers


# ── Connect flow ───────────────────────────────────────────────────────────────

def connect_llm(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    request_timeout: int | None,
) -> tuple[LLMConnection | None, str | None]:
    """Validate and build an LLM connection from a connect request.

    Applies SSRF checks, provider/model validation, API key resolution,
    and optional live Cursor key verification.

    Args:
        provider: Provider catalog key (e.g. ``"ollama"``).
        model: Requested model name.
        base_url: Requested base URL.
        api_key: API key from the UI connect form.
        request_timeout: Optional timeout override.

    Returns:
        Tuple of (LLMConnection, None) on success, or (None, error_message)
        on validation failure.
    """
    settings = get_settings()
    spec = settings.llm_providers.get(provider)
    if spec is None:
        return None, f"Unknown provider '{provider}'"

    url_err = _validate_base_url(base_url, provider)
    if url_err:
        return None, url_err

    resolved_key = resolve_api_key_for_connect(body_api_key=api_key, spec=spec)
    err = validate_connect(
        provider,
        model=model,
        base_url=base_url,
        api_key=resolved_key,
        settings=settings,
    )
    if err:
        return None, err

    if spec.kind == "cursor" and api_key.strip():
        live_err = validate_cursor_api_key_live(resolved_key)
        if live_err:
            return None, live_err

    conn = build_connection(
        provider,
        model=model,
        base_url=base_url,
        api_key=resolved_key,
        request_timeout=request_timeout,
        settings=settings,
    )
    return conn, None
