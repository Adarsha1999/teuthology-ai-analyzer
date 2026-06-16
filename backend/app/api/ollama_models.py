"""Ollama model discovery and health endpoints for the frontend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import DbSession, resolve_app_session
from app.providers.ollama_provider import list_ollama_models, ollama_health

router = APIRouter()


@router.get("/ollama/health")
def get_ollama_health() -> dict:
    """Check Ollama server reachability."""
    return ollama_health()


@router.get("/ollama/models")
def get_ollama_models(
    db: DbSession,
    response: Response,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    """List installed Ollama models with sizes and recommended-use tags."""
    svc, sid = session
    conn = svc.get_llm_connection(sid)
    selected = conn.model if conn and conn.provider == "ollama" else ""
    return list_ollama_models(selected_model=selected)
