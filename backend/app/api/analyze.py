"""
Analyze endpoints — submit analysis as background task, poll for result.

POST /analyze       → 202 + task_id (analysis runs in background)
POST /analyze-local → 202 + task_id
GET  /analyze/status/{task_id} → result or 202 if still running
GET  /history/{run_name}/analysis → cached result
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession, resolve_app_session
from app.models.schemas import AnalyzeIn, AnalyzeLocalIn, AnalyzeOut
from app.services.analysis_service import AnalysisService, map_pulpito_error
from app.services.local_archive_client import LocalArchiveError
from app.services.pulpito_client import PulpitoError, parse_run_name
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Analyze"])

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="analyze")
_tasks: dict[str, Future[Any]] = {}

MAX_PENDING_TASKS = 20


def _prune_done_tasks() -> None:
    """Remove completed futures to prevent unbounded memory growth."""
    done = [tid for tid, f in _tasks.items() if f.done()]
    for tid in done[-max(0, len(done) - MAX_PENDING_TASKS):]:
        pass
    if len(_tasks) > MAX_PENDING_TASKS * 2:
        for tid in done:
            _tasks.pop(tid, None)


def _run_analysis(db_factory, session_id: str, body: AnalyzeIn, conn) -> AnalyzeOut:
    """Execute in thread pool — isolated DB session."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        service = AnalysisService(db)
        return service.analyze_run(session_id, body, conn)
    finally:
        db.close()


def _run_local_analysis(db_factory, session_id: str, body: AnalyzeLocalIn, conn) -> AnalyzeOut:
    """Execute in thread pool — isolated DB session."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        service = AnalysisService(db)
        return service.analyze_local_run(session_id, body, conn)
    finally:
        db.close()


@router.post("/analyze", status_code=202)
def analyze_run(
    body: AnalyzeIn,
    db: DbSession,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    svc, sid = session
    conn = SessionService(db).get_llm_connection(sid)
    if conn is None:
        raise HTTPException(401, "No LLM connected. Pick a model in the top bar.")

    _prune_done_tasks()
    task_id = uuid.uuid4().hex
    future = _executor.submit(_run_analysis, None, sid, body, conn)
    _tasks[task_id] = future
    logger.info("Analysis task %s submitted for %s", task_id, body.run_url)
    return {"task_id": task_id, "status": "running"}


@router.post("/analyze-local", status_code=202)
def analyze_local_run(
    body: AnalyzeLocalIn,
    db: DbSession,
    session: tuple = Depends(resolve_app_session),
) -> dict:
    svc, sid = session
    conn = SessionService(db).get_llm_connection(sid)
    if conn is None:
        raise HTTPException(401, "No LLM connected. Pick a model in the top bar.")

    _prune_done_tasks()
    task_id = uuid.uuid4().hex
    future = _executor.submit(_run_local_analysis, None, sid, body, conn)
    _tasks[task_id] = future
    logger.info("Local analysis task %s submitted for %s", task_id, body.run_path)
    return {"task_id": task_id, "status": "running"}


@router.get("/analyze/status/{task_id}")
def get_analysis_status(task_id: str):
    future = _tasks.get(task_id)
    if future is None:
        raise HTTPException(404, "Unknown task_id. It may have expired.")

    if not future.done():
        return {"task_id": task_id, "status": "running"}

    exc = future.exception()
    if exc is not None:
        _tasks.pop(task_id, None)
        if isinstance(exc, ValueError):
            raise HTTPException(400, str(exc)) from exc
        if isinstance(exc, PulpitoError):
            raise HTTPException(502, map_pulpito_error(exc)) from exc
        if isinstance(exc, LocalArchiveError):
            raise HTTPException(400, str(exc)) from exc
        logger.error("Analysis task %s failed: %s", task_id, exc, exc_info=exc)
        raise HTTPException(502, f"Analysis failed: {exc}") from exc

    result = future.result()
    _tasks.pop(task_id, None)
    return {"task_id": task_id, "status": "complete", "result": result}


@router.get("/history/{run_name:path}/analysis", response_model=AnalyzeOut)
def get_cached_analysis(
    run_name: str,
    db: DbSession,
    session: tuple = Depends(resolve_app_session),
) -> AnalyzeOut:
    svc, sid = session
    try:
        key = parse_run_name(run_name)
    except ValueError:
        key = run_name.strip().strip("/")
    cached = svc.get_analysis(sid, key)
    if cached is None:
        raise HTTPException(404, "No saved analysis for this run. Click Analyze run first.")
    return cached
