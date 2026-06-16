"""
Shared LLM utilities — error class, prompt builder, and response parser.

Used by ``llm_client.analyze_failure()`` and provider implementations.
Decoupled from any specific provider or transport.
"""
from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


class LLMError(RuntimeError):
    """Raised when an LLM request fails (transport, auth, or content error)."""


# Backwards compatibility for imports expecting OllamaError
OllamaError = LLMError


# ── Prompt construction ────────────────────────────────────────────────────────

def build_analysis_prompt(
    *,
    job_id: str,
    description: str,
    machine: str,
    os_line: str,
    failure_reason: str | None,
    digest: str,
) -> tuple[str, str]:
    """Build the (system, user) message pair for failure triage.

    The system message defines the LLM's role and expected JSON schema.
    The user message contains job metadata, failure context, and log digest.

    Args:
        job_id: Teuthology job identifier.
        description: Job description text.
        machine: Machine hostname.
        os_line: OS type and version string.
        failure_reason: Pulpito failure line (may be None).
        digest: Pre-built log digest text.

    Returns:
        Tuple of (system_message, user_message) strings.
    """
    system = (
        "You triage Ceph Teuthology job failures. "
        "The **Pulpito failure line** and **log digest** are the sole basis for a concrete root cause. "
        "Put matching lines or paraphrases from the digest in `evidence`. "
        "If the digest is empty or uninformative, say so and lower confidence. "
        "Respond with a single JSON object with keys: "
        "summary (string), likely_root_cause (string), evidence (array of strings), "
        "next_steps (array of strings), confidence (number 0-1)."
    )
    hint = failure_mode_hint(failure_reason, description)
    user_parts: list[str] = [
        f"Job ID: {job_id}\n",
        f"Description: {description}\n",
        f"Machine: {machine}\n",
        f"OS: {os_line}\n\n",
        f"Pulpito failure reason:\n{failure_reason or '(none)'}\n",
    ]
    if hint:
        user_parts.append("\n" + hint)
    user_parts.append(f"\n=== Log digest (primary) ===\n{digest}\n")
    return system, "".join(user_parts)


def failure_mode_hint(failure_reason: str | None, description: str) -> str:
    """Generate heuristic anchors to help the model focus on the right failure type.

    Scans the failure reason and description for known patterns (cram, workunit,
    pytest, valgrind, etc.) and returns short guidance strings.

    Args:
        failure_reason: Pulpito failure line (may be None).
        description: Job description text.

    Returns:
        Hint block string, or empty string if no patterns match.
    """
    u = f"{failure_reason or ''} {description}".lower()
    parts: list[str] = []
    if "cram" in u:
        parts.append(
            "Pulpito mentions `cram` (`.t` shell tests). Treat the root cause as whatever the **cram test log** in the digest shows "
            "(diff/exit code), not unrelated Ceph core / OSD / Seastore issues unless the same error lines appear in the digest."
        )
    if "workunit" in u or "tasks.workunit" in u:
        parts.append("Workunit-style client test: anchor on workunit / client host output in the digest.")
    if "apt" in u or "apt-get" in u or "no space left" in u or "dpkg" in u:
        parts.append("Package or disk/mirror issues: consider host space, apt mirrors, and install steps; do not default to unrelated OSD bugs.")
    if "ansible" in u or "playbook" in u:
        parts.append("Ansible: focus on remote command and playbook errors in the digest, not random historical tracker bugs.")
    if "pytest" in u or "nose" in u or "unittest" in u:
        parts.append("Python test harness: the failure is usually the traceback or assertion in the digest.")
    if "s3test" in u or "tox" in u or "bucket_logging" in u:
        parts.append(
            "S3/tox harness: look for tox/pytest FAILED lines and s3test assertion output in the digest, "
            "not post-run log compression or archival."
        )
    if "valgrind" in u:
        parts.append(
            "Valgrind validater: look for `valgrind error:` lines (Leak_*, Invalid read/write) in the digest. "
            "The valgrind exception in `valgrind_post` is the terminating error — identify which allocation/call site it points to."
        )
    if "coredump" in u or "crimson" in u or "seastore" in u:
        parts.append(
            "Crimson/SeaStore OSD job: look for coredump warnings (`Found coredumps`) and OSD crash tracebacks in the digest. "
            "The OSD crash is usually the root cause; cluster degradation and timeout errors are downstream symptoms."
        )
    if not parts:
        return ""
    return "=== Heuristic hints (from job text only; still verify in digest) ===\n" + "\n".join(f"- {p}\n" for p in parts)


# ── Response parsing ───────────────────────────────────────────────────────────

def parse_analysis_response(content: str) -> dict[str, Any]:
    """Parse an LLM analysis response into a structured dict.

    Tries JSON first (plain or markdown-fenced), falls back to a
    prose wrapper with low confidence.

    Args:
        content: Raw model response text.

    Returns:
        Dict with keys: summary, likely_root_cause, evidence,
        next_steps, confidence.
    """
    parsed = _parse_json_content(content)
    if parsed is not None:
        return parsed
    return _fallback_prose_dict(content)


def _parse_json_content(content: str) -> dict[str, Any] | None:
    """Attempt to parse JSON from raw content, stripping markdown fences.

    Args:
        content: Raw text that may contain JSON.

    Returns:
        Parsed dict, or None if parsing fails.
    """
    s = content.strip()
    m = _JSON_FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _fallback_prose_dict(text: str) -> dict[str, Any]:
    """Wrap raw prose in the expected analysis schema with zero confidence.

    Args:
        text: Raw model text that couldn't be parsed as JSON.

    Returns:
        Analysis dict with the text as summary and confidence 0.0.
    """
    return {
        "summary": text[:2000],
        "likely_root_cause": "(model did not return valid JSON)",
        "evidence": [],
        "next_steps": ["Retry with a model that follows JSON format, or inspect raw digest."],
        "confidence": 0.0,
    }
