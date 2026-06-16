"""Provider health endpoints — per-provider health checks for the UI."""
from __future__ import annotations

from fastapi import APIRouter

from app.providers.bob_cli_provider import detailed_health

router = APIRouter(tags=["Providers"])


@router.get("/providers/bob/health")
def bob_health() -> dict:
    """Return detailed Bob Shell CLI health status.

    Checks: command on PATH, API key configured, workspace directory exists.
    """
    return detailed_health()
