from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, resolve_app_session
from app.models.schemas import HistoryEntry

router = APIRouter(tags=["History"])


@router.get("/history", response_model=list[HistoryEntry])
def list_history(
    db: DbSession,
    session: tuple = Depends(resolve_app_session),
) -> list[HistoryEntry]:
    svc, sid = session
    return svc.list_history(sid)
