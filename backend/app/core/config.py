"""Application settings loaded from backend/.env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "Teuthology AI Analyzer"
    APP_VERSION: str = "0.3.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    ENABLE_CORS: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ALLOW_METHODS: str = "GET,POST,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Content-Type,Authorization,X-API-Key"

    # PostgreSQL default; SQLite kept for dev/test via DATABASE_URL override
    DATABASE_URL: str = "postgresql://teuth:teuth123@localhost:5432/teuthology_ai"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    API_KEY_HEADER: str = "X-API-Key"
    API_KEY: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def cors_methods_list(self) -> list[str]:
        return [m.strip() for m in self.CORS_ALLOW_METHODS.split(",") if m.strip()]

    @property
    def cors_headers_list(self) -> list[str]:
        return [h.strip() for h in self.CORS_ALLOW_HEADERS.split(",") if h.strip()]


settings = AppSettings()
