"""Initialize the database — run Alembic migrations with SQLite fallback."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def init_db() -> None:
    if settings.DATABASE_URL.startswith("sqlite"):
        _init_sqlite_dev()
    else:
        _run_alembic()


def _run_alembic() -> None:
    from alembic import command
    from alembic.config import Config

    alembic_ini = _BACKEND_DIR / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied (alembic upgrade head)")


def _init_sqlite_dev() -> None:
    """Dev/test: use create_all for SQLite since Alembic expects a real DB."""
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(bind=engine)
    logger.info("SQLite dev database schema ready (create_all)")
