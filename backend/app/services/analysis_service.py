from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.llm_config import LLMConnection, get_settings
from app.models.schemas import (
    AnalysisOut,
    AnalyzeIn,
    AnalyzeLocalIn,
    AnalyzeOut,
    FailedJobOut,
    JobOut,
    RunMetricsOut,
)
from app.services.archive_client import fetch_teuthology_log, teuthology_log_url
from app.services.llm_client import analyze_failure
from app.services.llm_common import LLMError
from app.services.local_archive_client import (
    LocalArchiveError,
    LocalJobInfo,
    discover_run,
    read_job_log,
)
from app.services.log_digest import build_digest
from app.services.pulpito_client import (
    PulpitoError,
    fetch_job_failure_reason,
    fetch_run_jobs,
    parse_run_name,
    status_counts,
)
from app.services.session_service import SessionService


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.sessions = SessionService(db)

    def analyze_run(
        self,
        session_id: str,
        body: AnalyzeIn,
        conn: LLMConnection,
    ) -> AnalyzeOut:
        run_name = parse_run_name(body.run_url)
        settings = get_settings()
        timeout = httpx.Timeout(settings.http_timeout_s)
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=16)

        with httpx.Client(timeout=timeout, limits=limits) as client:
            jobs = fetch_run_jobs(client, settings, run_name)
            if not jobs:
                raise ValueError("No jobs found in Pulpito table.")

            counts = status_counts(jobs)
            total = len(jobs)
            passed = counts.get("pass", 0)
            failed_n = counts.get("fail", 0)
            metrics = RunMetricsOut(
                total=total,
                pass_count=passed,
                fail_count=failed_n,
                dead_count=counts.get("dead", 0),
                queued_count=counts.get("queued", 0),
                pass_rate=round(100 * passed / total) if total else 0,
            )

            self.sessions.push_history(
                session_id,
                run_name=run_name,
                pass_count=passed,
                fail_count=failed_n,
                total=total,
            )

            job_rows = [
                JobOut(
                    job_id=j.job_id,
                    description=j.description,
                    status=j.status,
                    machine=j.machine,
                    os_type=j.os_type,
                    os_version=j.os_version,
                )
                for j in jobs
            ]

            bad_status = {"fail", "dead"} if body.include_dead else {"fail"}
            failed_jobs = [j for j in jobs if j.status in bad_status][: body.max_failures]

            failed_analyses: list[FailedJobOut] = []
            logger.info(
                "Processing %d failed job(s) with %s / %s",
                len(failed_jobs),
                conn.provider,
                conn.model,
            )
            for job in sorted(failed_jobs, key=lambda j: int(j.job_id)):
                payload = self._fetch_payload_with_client(client, settings, run_name, job)
                logger.info("Starting LLM analysis for job %s", job.job_id)
                failed_analyses.append(
                    self._analyze_payload(conn, payload, show_digest=body.show_digest)
                )

        pulpito_url = f"{settings.pulpito_base.rstrip('/')}/{run_name}/"
        out = AnalyzeOut(
            run_name=run_name,
            pulpito_url=pulpito_url,
            metrics=metrics,
            jobs=job_rows,
            failed_analyses=failed_analyses,
        )
        self.sessions.save_analysis(
            session_id,
            run_name,
            out.model_dump(),
            body.model_dump(),
        )
        return out

    def _fetch_payload_with_client(self, client, settings, run_name, job):
        logger.info("Fetching logs for job %s", job.job_id)
        failure = (job.failure_reason or "").strip()
        if not failure:
            failure = fetch_job_failure_reason(client, settings, run_name, job.job_id) or ""
        log_text, resolved_run, truncated = fetch_teuthology_log(
            client, settings, run_name, job.job_id
        )
        logger.info(
            "Log fetched for job %s (%s bytes, truncated=%s)",
            job.job_id,
            len(log_text),
            truncated,
        )
        logger.info("Building digest for job %s", job.job_id)
        digest = build_digest(
            log_text,
            settings.max_digest_chars,
            failure_reason=failure or None,
        )
        logger.info("Digest ready for job %s (%s chars)", job.job_id, len(digest))
        log_url = teuthology_log_url(settings, resolved_run, job.job_id)
        return {
            "job": job,
            "failure_reason": failure or "",
            "log_truncated": truncated,
            "log_empty": not log_text.strip(),
            "digest": digest,
            "log_url": log_url,
        }

    # ── Local archive path ──────────────────────────────────────────────

    def analyze_local_run(
        self,
        session_id: str,
        body: AnalyzeLocalIn,
        conn: LLMConnection,
    ) -> AnalyzeOut:
        settings = get_settings()
        run_info = discover_run(
            body.run_path,
            allowed_root=settings.local_archive_root or None,
        )

        all_jobs = run_info.jobs
        if body.job_ids:
            allowed = set(body.job_ids)
            all_jobs = [j for j in all_jobs if j.job_id in allowed]

        counts: dict[str, int] = {}
        for j in all_jobs:
            counts[j.status] = counts.get(j.status, 0) + 1
        total = len(all_jobs)
        passed = counts.get("pass", 0)
        failed_n = counts.get("fail", 0)

        metrics = RunMetricsOut(
            total=total,
            pass_count=passed,
            fail_count=failed_n,
            dead_count=counts.get("dead", 0),
            queued_count=counts.get("queued", 0) + counts.get("waiting", 0),
            pass_rate=round(100 * passed / total) if total else 0,
        )

        self.sessions.push_history(
            session_id,
            run_name=run_info.run_name,
            pass_count=passed,
            fail_count=failed_n,
            total=total,
        )

        job_rows = [
            JobOut(
                job_id=j.job_id,
                description=j.description,
                status=j.status,
                machine=j.machine,
                os_type=j.os_type,
                os_version=j.os_version,
            )
            for j in all_jobs
        ]

        bad_status = {"fail", "dead"} if body.include_dead else {"fail"}
        failed_jobs = [j for j in all_jobs if j.status in bad_status][: body.max_failures]

        failed_analyses: list[FailedJobOut] = []
        logger.info(
            "Processing %d local failed job(s) with %s / %s",
            len(failed_jobs),
            conn.provider,
            conn.model,
        )

        use_tail = body.read_mode == "tail"
        max_bytes = settings.max_log_bytes if use_tail else settings.max_local_log_bytes

        for job in sorted(failed_jobs, key=lambda j: int(j.job_id)):
            payload = self._fetch_local_payload(settings, run_info, job, max_bytes=max_bytes)
            logger.info("Starting LLM analysis for local job %s", job.job_id)
            failed_analyses.append(
                self._analyze_payload(conn, payload, show_digest=body.show_digest)
            )

        out = AnalyzeOut(
            run_name=run_info.run_name,
            pulpito_url="",
            metrics=metrics,
            jobs=job_rows,
            failed_analyses=failed_analyses,
        )
        self.sessions.save_analysis(
            session_id,
            run_info.run_name,
            out.model_dump(),
            body.model_dump(),
        )
        return out

    def _fetch_local_payload(
        self,
        settings,
        run_info,
        job: LocalJobInfo,
        *,
        max_bytes: int,
    ) -> dict:
        logger.info("Reading local log for job %s at %s", job.job_id, job.job_path)
        failure = job.failure_reason or ""

        log_text, file_size, truncated = read_job_log(
            job.job_path,
            max_bytes=max_bytes,
        )
        logger.info(
            "Local log for job %s: %d bytes on disk, %d chars loaded, truncated=%s",
            job.job_id,
            file_size,
            len(log_text),
            truncated,
        )

        digest = build_digest(
            log_text,
            settings.max_digest_chars,
            failure_reason=failure or None,
        )
        logger.info("Digest ready for local job %s (%d chars)", job.job_id, len(digest))

        log_path = f"{job.job_path}/teuthology.log"

        return {
            "job": job,
            "failure_reason": failure,
            "log_truncated": truncated,
            "log_empty": not log_text.strip(),
            "digest": digest,
            "log_url": f"file://{log_path}",
            "log_source": "local",
            "log_size_bytes": file_size,
        }

    def _analyze_payload(
        self, conn: LLMConnection, payload: dict, *, show_digest: bool
    ) -> FailedJobOut:
        j = payload["job"]
        os_line = f"{j.os_type} {j.os_version}".strip()
        try:
            logger.info("LLM analysis for job %s", j.job_id)
            analysis = analyze_failure(
                conn,
                job_id=j.job_id,
                description=j.description,
                machine=j.machine,
                os_line=os_line,
                failure_reason=payload["failure_reason"],
                digest=payload["digest"],
            )
        except LLMError as e:
            analysis = {
                "summary": str(e),
                "likely_root_cause": "",
                "evidence": [],
                "next_steps": [],
                "confidence": 0.0,
            }

        return FailedJobOut(
            job=JobOut(
                job_id=j.job_id,
                description=j.description,
                status=j.status,
                machine=j.machine,
                os_type=j.os_type,
                os_version=j.os_version,
            ),
            failure_reason=payload["failure_reason"],
            log_url=payload["log_url"],
            log_empty=payload["log_empty"],
            log_truncated=payload["log_truncated"],
            log_source=payload.get("log_source", "http"),
            log_size_bytes=payload.get("log_size_bytes"),
            digest=payload["digest"] if show_digest else None,
            analysis=AnalysisOut(
                summary=analysis.get("summary", ""),
                likely_root_cause=analysis.get("likely_root_cause", ""),
                evidence=analysis.get("evidence") or [],
                next_steps=analysis.get("next_steps") or [],
                confidence=float(analysis.get("confidence") or 0),
            ),
        )


def map_pulpito_error(exc: PulpitoError) -> str:
    return str(exc)
