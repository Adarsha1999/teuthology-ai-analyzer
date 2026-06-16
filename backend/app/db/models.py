"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppSession(Base):
    """Browser/API session: LLM connection binding."""

    __tablename__ = "app_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    llm_provider: Mapped[str] = mapped_column(String(32), default="")
    llm_model: Mapped[str] = mapped_column(String(128), default="")
    llm_base_url: Mapped[str] = mapped_column(String(512), default="")
    llm_api_key: Mapped[str] = mapped_column(Text, default="")
    llm_request_timeout: Mapped[int] = mapped_column(Integer, default=600)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    history: Mapped[list["RunHistory"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    analyses: Mapped[list["AnalysisCache"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class RunHistory(Base):
    __tablename__ = "run_history"
    __table_args__ = (UniqueConstraint("session_id", "run_name", name="uq_session_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("app_sessions.id"), index=True)
    run_name: Mapped[str] = mapped_column(String(512), index=True)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[AppSession] = relationship(back_populates="history")


class AnalysisCache(Base):
    __tablename__ = "analysis_cache"
    __table_args__ = (UniqueConstraint("session_id", "run_name", name="uq_session_analysis"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("app_sessions.id"), index=True)
    run_name: Mapped[str] = mapped_column(String(512), index=True)
    result_json: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped[AppSession] = relationship(back_populates="analyses")
