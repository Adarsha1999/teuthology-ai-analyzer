"""Initial schema — app_sessions, run_history, analysis_cache.

Revision ID: 001
Revises: None
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("llm_provider", sa.String(32), server_default="", nullable=False),
        sa.Column("llm_model", sa.String(128), server_default="", nullable=False),
        sa.Column("llm_base_url", sa.String(512), server_default="", nullable=False),
        sa.Column("llm_api_key", sa.Text, server_default="", nullable=False),
        sa.Column("llm_request_timeout", sa.Integer, server_default="600", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "run_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(32), sa.ForeignKey("app_sessions.id"), nullable=False),
        sa.Column("run_name", sa.String(512), nullable=False),
        sa.Column("pass_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("fail_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("total", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "run_name", name="uq_session_run"),
    )
    op.create_index("ix_run_history_session_id", "run_history", ["session_id"])
    op.create_index("ix_run_history_run_name", "run_history", ["run_name"])

    op.create_table(
        "analysis_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(32), sa.ForeignKey("app_sessions.id"), nullable=False),
        sa.Column("run_name", sa.String(512), nullable=False),
        sa.Column("result_json", sa.Text, nullable=False),
        sa.Column("options_json", sa.Text, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "run_name", name="uq_session_analysis"),
    )
    op.create_index("ix_analysis_cache_session_id", "analysis_cache", ["session_id"])
    op.create_index("ix_analysis_cache_run_name", "analysis_cache", ["run_name"])


def downgrade() -> None:
    op.drop_table("analysis_cache")
    op.drop_table("run_history")
    op.drop_table("app_sessions")
