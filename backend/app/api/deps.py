"""
FastAPI dependency injection — database session and app session resolution.

Provides ``DbSession`` (type alias for injected SQLAlchemy sessions) and
``resolve_app_session`` (cookie-based session lookup used by most endpoints).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.session_service import COOKIE_NAME, SessionService

DbSession = Annotated[Session, Depends(get_db)]


def resolve_app_session(
    db: DbSession,
    response: Response,
    teuth_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> tuple[SessionService, str]:
    """Resolve (or create) the browser's app session from the session cookie.

    Sets the ``teuth_session`` cookie on the response if absent or changed.

    Args:
        db: Injected SQLAlchemy session.
        response: FastAPI response for setting cookies.
        teuth_session: Cookie value (may be None on first visit).

    Returns:
        Tuple of (SessionService instance, session_id string).
    """
    svc = SessionService(db)
    row = svc.get_or_create(teuth_session)
    if not teuth_session or teuth_session != row.id:
        response.set_cookie(
            key=COOKIE_NAME,
            value=row.id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
        )
    return svc, row.id
