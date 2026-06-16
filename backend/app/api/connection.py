"""Connection endpoints — connect, disconnect, and query LLM provider status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import DbSession, resolve_app_session
from app.core.llm_config import get_settings
from app.models.schemas import ConnectIn
from app.services.connection_service import connect_llm

router = APIRouter(tags=["Connection"])


@router.get("/connection")
def get_connection_status(
    db: DbSession,
    response: Response,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    """Return the current LLM connection status for this session."""
    svc, sid = session
    return svc.connection_status(sid)


@router.post("/connect")
def connect_agent(
    body: ConnectIn,
    db: DbSession,
    response: Response,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    """Validate and connect to an LLM provider for this session.

    Applies SSRF checks, model/key validation, and optional live key
    verification for Cursor.  Stores the connection in the session.
    """
    svc, sid = session
    spec = get_settings().llm_providers.get(body.provider.strip())
    if spec is None:
        raise HTTPException(400, f"Unknown provider '{body.provider}'")

    conn, err = connect_llm(
        provider=body.provider.strip(),
        model=body.model.strip() or spec.model,
        base_url=body.base_url.strip() or spec.base_url,
        api_key=body.api_key,
        request_timeout=body.request_timeout or None,
    )
    if err:
        if "rejected" in err.lower() or "authentication" in err.lower():
            raise HTTPException(401, err)
        raise HTTPException(400, err)
    svc.set_llm_connection(sid, conn)
    return svc.connection_status(sid)


@router.post("/disconnect")
def disconnect_agent(
    db: DbSession,
    response: Response,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    """Disconnect the LLM for this session."""
    svc, sid = session
    svc.clear_llm_connection(sid)
    return svc.connection_status(sid)
