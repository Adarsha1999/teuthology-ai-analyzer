"""
Session service — manages browser sessions, LLM connections, run history, and analysis cache.

Each browser tab gets an ``AppSession`` row (keyed by a cookie).  The session
binds an LLM provider + model + base_url.  API keys are kept in an in-process
``_key_cache`` dict (never written to the database) for security.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.llm_config import LLMConnection
from app.db.models import AnalysisCache, AppSession, RunHistory
from app.models.schemas import AnalyzeOut, ConnectionOut, HistoryEntry
from app.services.connection_service import connection_out


COOKIE_NAME = "teuth_session"


class SessionService:
    """Per-request service wrapping all session-scoped DB operations."""

    _key_cache: dict[str, str] = {}

    def __init__(self, db: Session) -> None:
        """Initialize with a SQLAlchemy database session.

        Args:
            db: Active SQLAlchemy ``Session`` instance.
        """
        self.db = db

    # ── Session lifecycle ──────────────────────────────────────────────────

    def new_session_id(self) -> str:
        """Generate a new random session identifier.

        Returns:
            32-character hex UUID string.
        """
        return uuid.uuid4().hex

    def get_or_create(self, session_id: str | None) -> AppSession:
        """Fetch an existing session or create a new one.

        Args:
            session_id: Cookie value (may be None for first visit).

        Returns:
            Existing or newly created ``AppSession`` row.
        """
        if session_id:
            row = self.db.get(AppSession, session_id)
            if row:
                return row
        row = AppSession(id=self.new_session_id())
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    # ── LLM connection ─────────────────────────────────────────────────────

    def get_llm_connection(self, session_id: str) -> LLMConnection | None:
        """Load the LLM connection for a session from DB + in-memory key cache.

        Args:
            session_id: Session identifier.

        Returns:
            ``LLMConnection`` if a provider is set, or None.
        """
        row = self.db.get(AppSession, session_id)
        if row is None or not row.llm_provider:
            return None
        cached_key = self._key_cache.get(session_id, "")
        return LLMConnection(
            provider=row.llm_provider,
            base_url=row.llm_base_url or "",
            model=row.llm_model or "",
            api_key=cached_key,
            request_timeout=row.llm_request_timeout or 600,
        )

    def set_llm_connection(self, session_id: str, conn: LLMConnection) -> AppSession:
        """Persist an LLM connection for a session.

        The API key is stored only in the in-memory ``_key_cache``;
        the DB column is cleared for security.

        Args:
            session_id: Session identifier.
            conn: LLM connection to persist.

        Returns:
            Updated ``AppSession`` row.
        """
        row = self.get_or_create(session_id)
        row.llm_provider = conn.provider
        row.llm_base_url = conn.base_url
        row.llm_model = conn.model
        row.llm_api_key = ""
        row.llm_request_timeout = conn.request_timeout
        self.db.commit()
        self.db.refresh(row)
        self._key_cache[session_id] = conn.api_key
        return row

    def clear_llm_connection(self, session_id: str) -> None:
        """Disconnect the LLM for a session.

        Args:
            session_id: Session identifier.
        """
        row = self.db.get(AppSession, session_id)
        if row is None:
            return
        row.llm_provider = ""
        row.llm_model = ""
        row.llm_base_url = ""
        row.llm_api_key = ""
        self.db.commit()
        self._key_cache.pop(session_id, None)

    def connection_status(self, session_id: str) -> dict:
        """Return serialised connection status for the frontend.

        Args:
            session_id: Session identifier.

        Returns:
            ``ConnectionOut``-shaped dict.
        """
        conn = self.get_llm_connection(session_id)
        return connection_out(conn)

    # ── Run history ────────────────────────────────────────────────────────

    def list_history(self, session_id: str) -> list[HistoryEntry]:
        """Return recent run history entries for a session (newest first).

        Args:
            session_id: Session identifier.

        Returns:
            List of ``HistoryEntry`` objects (max 12).
        """
        rows = self.db.scalars(
            select(RunHistory)
            .where(RunHistory.session_id == session_id)
            .order_by(RunHistory.id.desc())
            .limit(12)
        ).all()
        out: list[HistoryEntry] = []
        for h in rows:
            out.append(
                HistoryEntry(
                    id=h.id,
                    run_name=h.run_name,
                    pass_count=h.pass_count,
                    fail_count=h.fail_count,
                    total=h.total,
                    analyzed=self.has_analysis(session_id, h.run_name),
                )
            )
        return out

    def push_history(
        self,
        session_id: str,
        *,
        run_name: str,
        pass_count: int,
        fail_count: int,
        total: int,
    ) -> None:
        """Upsert a run history entry.

        Args:
            session_id: Session identifier.
            run_name: Teuthology run name.
            pass_count: Number of passing jobs.
            fail_count: Number of failing jobs.
            total: Total number of jobs.
        """
        existing = self.db.scalar(
            select(RunHistory).where(
                RunHistory.session_id == session_id,
                RunHistory.run_name == run_name,
            )
        )
        if existing:
            existing.pass_count = pass_count
            existing.fail_count = fail_count
            existing.total = total
        else:
            self.db.add(
                RunHistory(
                    session_id=session_id,
                    run_name=run_name,
                    pass_count=pass_count,
                    fail_count=fail_count,
                    total=total,
                )
            )
        self.db.commit()

    # ── Analysis cache ─────────────────────────────────────────────────────

    def save_analysis(self, session_id: str, run_name: str, result: dict, options: dict) -> None:
        """Upsert an analysis result for a run.

        Args:
            session_id: Session identifier.
            run_name: Teuthology run name.
            result: Serialised ``AnalyzeOut`` dict.
            options: Original analysis options.
        """
        row = self.db.scalar(
            select(AnalysisCache).where(
                AnalysisCache.session_id == session_id,
                AnalysisCache.run_name == run_name,
            )
        )
        payload_result = json.dumps(result)
        payload_opts = json.dumps(options)
        if row:
            row.result_json = payload_result
            row.options_json = payload_opts
        else:
            self.db.add(
                AnalysisCache(
                    session_id=session_id,
                    run_name=run_name,
                    result_json=payload_result,
                    options_json=payload_opts,
                )
            )
        self.db.commit()

    def get_analysis(self, session_id: str, run_name: str) -> AnalyzeOut | None:
        """Retrieve a cached analysis result.

        Args:
            session_id: Session identifier.
            run_name: Teuthology run name.

        Returns:
            Validated ``AnalyzeOut``, or None if not cached.
        """
        row = self.db.scalar(
            select(AnalysisCache).where(
                AnalysisCache.session_id == session_id,
                AnalysisCache.run_name == run_name,
            )
        )
        if row is None:
            return None
        data = json.loads(row.result_json)
        return AnalyzeOut.model_validate(data)

    def has_analysis(self, session_id: str, run_name: str) -> bool:
        """Check whether a cached analysis exists for a run.

        Args:
            session_id: Session identifier.
            run_name: Teuthology run name.

        Returns:
            True if an analysis is cached.
        """
        row = self.db.scalar(
            select(AnalysisCache.id).where(
                AnalysisCache.session_id == session_id,
                AnalysisCache.run_name == run_name,
            )
        )
        return row is not None
