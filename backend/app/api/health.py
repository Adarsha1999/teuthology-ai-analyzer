"""Health check endpoints — liveness, readiness, and detailed status."""
from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.core.config import settings as app_settings
from app.core.llm_config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> dict:
    """Detailed health check including Ollama connectivity status.

    Returns:
        Dict with overall status, app version, and Ollama status.
    """
    settings = get_settings()
    ollama_status = "disabled"
    spec = settings.llm_providers.get("ollama")
    if spec and spec.base_url:
        try:
            r = httpx.get(f"{spec.base_url.rstrip('/')}/api/tags", timeout=3.0)
            ollama_status = "healthy" if r.status_code == 200 else "unreachable"
        except httpx.HTTPError:
            ollama_status = "unreachable"
    return {
        "status": "ok",
        "version": app_settings.APP_VERSION,
        "ollama": ollama_status,
    }


@router.get("/ready")
def readiness() -> dict[str, str]:
    """Kubernetes-style readiness probe."""
    return {"status": "ready"}


@router.get("/live")
def liveness() -> dict[str, str]:
    """Kubernetes-style liveness probe."""
    return {"status": "alive"}
