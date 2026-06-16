"""
FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import (
    analyze,
    assistant,
    config_routes,
    connection,
    health,
    history,
    ollama_models,
    providers,
)
from app.core.config import settings
from app.db.init_db import init_db

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    Path("data").mkdir(parents=True, exist_ok=True)
    init_db()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-assisted Pulpito teuthology run analyzer",
    lifespan=lifespan,
)

_PUBLIC_PREFIXES = ("/api/health", "/api/ready", "/api/live", "/docs", "/openapi.json")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests when API_KEY is configured and header is missing/wrong."""

    async def dispatch(self, request: Request, call_next):
        if not settings.API_KEY:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        token = request.headers.get(settings.API_KEY_HEADER, "")
        if token != settings.API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        return await call_next(request)


if settings.API_KEY:
    app.add_middleware(APIKeyMiddleware)

if settings.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )

app.include_router(health.router, prefix="/api")
app.include_router(config_routes.router, prefix="/api")
app.include_router(connection.router, prefix="/api")
app.include_router(ollama_models.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if settings.DEBUG else "Internal server error"},
    )


_repo_root = Path(__file__).resolve().parents[2]
_dist = _repo_root / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
