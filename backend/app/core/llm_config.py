"""
LLM provider catalog and runtime settings.

Defines the built-in provider catalog (Ollama, OpenAI, Gemini, Cursor,
Bob CLI) with sensible defaults that can be overridden via ``backend/.env``.
``get_settings()`` is the single entry-point for the rest of the app.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

LLMProvider = str

_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_BACKEND_ENV, override=False)


# ── Environment helpers ────────────────────────────────────────────────────────

def _env(key: str, default: Any) -> Any:
    """Read an environment variable with type coercion.

    The return type matches the type of ``default``:
    bool, int, float, or str.

    Args:
        key: Environment variable name.
        default: Default value (also determines type coercion).

    Returns:
        Coerced value from the environment, or ``default`` if unset.
    """
    val = os.environ.get(key)
    if val is None:
        return default
    if isinstance(default, bool):
        return val.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int(val)
    if isinstance(default, float):
        return float(val)
    return val


def _provider_models(spec: "ProviderSpec", resolved_model: str) -> list[str]:
    """Merge the built-in model list with the resolved env model.

    Ensures the active model (from e.g. ``CURSOR_MODEL``) is always
    present and listed first if not already in the catalog.

    Args:
        spec: Provider specification with built-in model list.
        resolved_model: Model name resolved from environment.

    Returns:
        Combined model list.
    """
    models = list(spec.models)
    name = resolved_model.strip()
    if name and name not in models:
        models.insert(0, name)
    return models


# ── Data models ────────────────────────────────────────────────────────────────

class ProviderSpec(BaseModel):
    """Static specification for an LLM provider.

    Combines built-in defaults with environment overrides.  Instances
    are created once in ``_builtin_providers()`` and resolved in
    ``get_settings()``.
    """

    kind: str
    label: str = ""
    icon: str = "🤖"
    tag: str = ""
    base_url: str = ""
    model: str = ""
    models: list[str] = Field(default_factory=list)
    api_key: str = ""
    api_key_env: str = ""
    team_id: str = ""
    instance_id: str = ""
    team_id_env: str = ""
    instance_id_env: str = ""
    extra_headers: dict[str, str] = Field(default_factory=dict)
    request_timeout: int = 600

    @property
    def requires_api_key(self) -> bool:
        """True if this provider kind needs an API key to operate."""
        return self.kind in ("openai", "gemini", "cursor", "bob_cli")

    @property
    def requires_base_url(self) -> bool:
        """True if this provider kind requires a base URL."""
        return self.kind == "ollama"


class LLMConnection(BaseModel):
    """Per-session LLM connection state stored in the DB + in-memory cache."""

    provider: str = "ollama"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    request_timeout: int = 600


class Settings(BaseModel):
    """Runtime settings assembled from environment variables.

    Created fresh by ``get_settings()`` on each call.  Holds the full
    provider catalog plus log-processing and external-service config.
    """

    # ── External services ──────────────────────────────────────────────
    pulpito_base: str = "https://pulpito.ceph.com"
    teuth_archive_base: str = "https://qa-proxy.ceph.com/teuthology"

    # ── LLM providers ──────────────────────────────────────────────────
    llm_default_provider: str = "ollama"
    llm_providers: dict[str, ProviderSpec] = Field(default_factory=dict)

    # ── Log processing ─────────────────────────────────────────────────
    max_log_bytes: int = 1_500_000
    max_local_log_bytes: int = 50_000_000
    max_digest_chars: int = 24_000
    log_fetch_workers: int = Field(default=4, ge=1, le=16)
    http_timeout_s: float = 120.0
    local_archive_root: str = ""

    def get_provider(self, provider_id: str) -> ProviderSpec:
        """Look up a provider by its catalog key.

        Args:
            provider_id: Key in ``llm_providers`` (e.g. ``"ollama"``).

        Returns:
            Matching ``ProviderSpec``.

        Raises:
            KeyError: If the provider is not in the catalog.
        """
        if provider_id not in self.llm_providers:
            raise KeyError(f"Unknown LLM provider '{provider_id}'")
        return self.llm_providers[provider_id]

    def provider_ids(self) -> list[str]:
        """Return all registered provider catalog keys."""
        return list(self.llm_providers.keys())

    @property
    def llm_request_timeout(self) -> int:
        """Default request timeout from the active default provider."""
        if self.llm_default_provider in self.llm_providers:
            return self.llm_providers[self.llm_default_provider].request_timeout
        return 600


# ── Built-in provider catalog ──────────────────────────────────────────────────

def _builtin_providers() -> dict[str, ProviderSpec]:
    """Return the built-in provider catalog.

    Each entry defines defaults for a single LLM provider.  Values can be
    overridden per-provider via environment variables (e.g. ``OLLAMA_MODEL``,
    ``GEMINI_API_KEY``).

    Returns:
        Dict mapping provider ID → ``ProviderSpec``.
    """
    return {
        "ollama": ProviderSpec(
            kind="ollama",
            label="Ollama",
            icon="🦙",
            tag="Local",
            base_url="http://127.0.0.1:11434",
            model="llama3.2:latest",
            models=["llama3.2:latest", "gemma4:latest"],
            request_timeout=600,
        ),
        "openai": ProviderSpec(
            kind="openai",
            label="OpenAI",
            icon="✦",
            tag="GPT",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            models=["gpt-4o", "gpt-4o-mini"],
            api_key_env="OPENAI_API_KEY",
            request_timeout=600,
        ),
        "gemini": ProviderSpec(
            kind="gemini",
            label="Gemini",
            icon="◇",
            tag="Google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-2.0-flash",
            models=["gemini-2.0-flash", "gemini-1.5-pro"],
            api_key_env="GEMINI_API_KEY",
            request_timeout=600,
        ),
        "cursor": ProviderSpec(
            kind="cursor",
            label="Cursor",
            icon="⌁",
            tag="SDK",
            model="composer-2",
            models=["composer-2", "claude-sonnet-4", "auto"],
            api_key_env="CURSOR_API_KEY",
            request_timeout=600,
        ),
        "bob": ProviderSpec(
            kind="bob_cli",
            label="IBM Bob",
            icon="🅑",
            tag="Shell",
            base_url="",
            model="bob-shell-local",
            models=["bob-shell-local"],
            api_key_env="BOBSHELL_API_KEY",
            request_timeout=600,
        ),
    }


# ── Settings factory ───────────────────────────────────────────────────────────

def get_settings() -> Settings:
    """Build runtime settings by merging built-in defaults with environment.

    Reads ``LLM_DEFAULT_PROVIDER``, per-provider env vars (``OLLAMA_MODEL``,
    ``GEMINI_API_KEY``, etc.), and global config vars (``PULPITO_BASE``,
    ``MAX_LOG_BYTES``, etc.).

    Returns:
        Fully resolved ``Settings`` instance.
    """
    default_provider = _env("LLM_DEFAULT_PROVIDER", "ollama")
    providers = _builtin_providers()
    if default_provider not in providers and providers:
        default_provider = next(iter(providers))

    resolved: dict[str, ProviderSpec] = {}
    for pid, spec in providers.items():
        env_prefix = pid.upper()
        team_id = spec.team_id
        if spec.team_id_env:
            team_id = _env(spec.team_id_env, team_id) or team_id
        instance_id = spec.instance_id
        if spec.instance_id_env:
            instance_id = _env(spec.instance_id_env, instance_id) or instance_id
        api_key = spec.api_key
        if spec.api_key_env:
            api_key = _env(spec.api_key_env, api_key) or api_key
        if spec.kind == "bob_cli" and not str(api_key).strip():
            api_key = _env("BOBSHELL_API_KEY", _env("BOB_API_KEY", api_key))
        resolved_model = _env(f"{env_prefix}_MODEL", spec.model) or spec.model
        resolved[pid] = ProviderSpec(
            kind=spec.kind,
            label=spec.label,
            icon=spec.icon,
            tag=spec.tag,
            base_url=_env(f"{env_prefix}_BASE_URL", spec.base_url),
            model=resolved_model,
            models=_provider_models(spec, resolved_model),
            api_key=str(api_key),
            api_key_env=spec.api_key_env,
            team_id=str(team_id),
            instance_id=str(instance_id),
            team_id_env=spec.team_id_env,
            instance_id_env=spec.instance_id_env,
            extra_headers=dict(spec.extra_headers),
            request_timeout=_env(f"{env_prefix}_REQUEST_TIMEOUT", spec.request_timeout),
        )

    return Settings(
        pulpito_base=_env("PULPITO_BASE", "https://pulpito.ceph.com"),
        teuth_archive_base=_env(
            "TEUTH_ARCHIVE_BASE",
            "https://qa-proxy.ceph.com/teuthology",
        ),
        llm_default_provider=default_provider,
        llm_providers=resolved,
        max_log_bytes=_env("MAX_LOG_BYTES", 1_500_000),
        max_local_log_bytes=_env("MAX_LOCAL_LOG_BYTES", 50_000_000),
        max_digest_chars=_env("MAX_DIGEST_CHARS", 24_000),
        log_fetch_workers=_env("LOG_FETCH_WORKERS", 4),
        http_timeout_s=_env("HTTP_TIMEOUT_S", 120.0),
        local_archive_root=_env("TEUTH_LOCAL_ARCHIVE_ROOT", ""),
    )
