from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_KEYWORD = re.compile(
    r"(traceback|assertionerror|\berror\b|\bfailed\b|critical|exception|task\s+failed|"
    r"command failed|commandfailederror|___\s*failed|failures in|=\s*FAILURES|"
    r"e\s+assertionerror|cephfs_test_runner|s3test|tox run|pytest|"
    r"runtimeerror:\s*test failure)",
    re.IGNORECASE,
)

# Keywords that introduce multi-line blocks (Python tracebacks, valgrind reports,
# exception chains). Give these a much larger post-match window so the actual
# exception message at the bottom of the block is not cut off.
_LONG_WINDOW_KW = re.compile(
    r"traceback|exception|assertionerror|task\s+failed|failures in",
    re.IGNORECASE,
)

# Post-test log archival noise — skip for keyword windows (still in raw tail if space).
_NOISE_LINE = re.compile(
    r"(gzip|compress(ing|ed)?\s+.*\.log|archive.*teuthology|scraping logs|"
    r"collecting logs|teuthology\.log\.gz|removing scratch)",
    re.IGNORECASE,
)

_POST_LINES_DEFAULT = 20
_POST_LINES_LONG = 60
_MAX_KEYWORD_WINDOWS = 40
_KEYWORD_SCAN_LINES = 12_000
_MIN_TAIL_LINES = 80
_MAX_TAIL_LINES = 350
_FOCUSED_PRE_LINES = 180
_FOCUSED_POST_LINES = 90
_MAX_FAILURE_TERMS = 8
_MAX_COMMAND_EVIDENCE = 12
_CMD_SCAN_PRE = 120
_CMD_SCAN_POST = 60

_FAILURE_HINT = re.compile(
    r"(traceback|assertionerror|exception|error|failed|failures in|command failed|"
    r"non-zero|exit status|return code|fatal)",
    re.IGNORECASE,
)
_COMMAND_LINE = re.compile(
    r"(?:^\s*\$\s+.+|(?:Executing|Running|CMD|command)\s*:\s*.+"
    r"|DEBUG:teuthology\.orchestra\.run\.[^:]+:>\s+.+)",
    re.IGNORECASE,
)
_RC_LINE = re.compile(
    r"(?:return code|exit status|exit code|rc)\s*[:=]?\s*(-?\d+)",
    re.IGNORECASE,
)


def build_digest(
    log_text: str,
    max_chars: int,
    *,
    failure_reason: str | None = None,
) -> str:
    if not log_text.strip():
        return "(empty log)"
    lines = log_text.splitlines()
    scan_start = 0
    if len(lines) > _KEYWORD_SCAN_LINES:
        scan_start = len(lines) - _KEYWORD_SCAN_LINES
        logger.info(
            "Digest: scanning last %d of %d lines for keywords",
            _KEYWORD_SCAN_LINES,
            len(lines),
        )

    windows: list[str] = []
    seen_ranges: set[tuple[int, int]] = set()
    anchor = _first_failure_line(lines, scan_start, failure_reason=failure_reason)
    anchor = _refine_anchor(lines, anchor)

    def add_window(i: int, post: int) -> None:
        lo = max(0, i - 4)
        hi = min(len(lines), i + post)
        key = (lo, hi)
        if key in seen_ranges:
            return
        seen_ranges.add(key)
        windows.append("\n".join(f"{j + 1:6d} | {lines[j]}" for j in range(lo, hi)))
        if len(windows) >= _MAX_KEYWORD_WINDOWS:
            return

    # Windows around terms from Pulpito failure line (e.g. bucket_logging, s3tests).
    for term in _terms_from_failure_reason(failure_reason):
        pat = re.compile(re.escape(term), re.IGNORECASE)
        for i in range(scan_start, len(lines)):
            if pat.search(lines[i]):
                add_window(i, _POST_LINES_DEFAULT)
                if len(windows) >= _MAX_KEYWORD_WINDOWS:
                    break
        if len(windows) >= _MAX_KEYWORD_WINDOWS:
            break

    for i in range(scan_start, len(lines)):
        line = lines[i]
        if _NOISE_LINE.search(line) and not _LONG_WINDOW_KW.search(line):
            continue
        if not _KEYWORD.search(line):
            continue
        post = _POST_LINES_LONG if _LONG_WINDOW_KW.search(line) else _POST_LINES_DEFAULT
        add_window(i, post)
        if len(windows) >= _MAX_KEYWORD_WINDOWS:
            break

    excerpt_blob = _extract_test_runner_excerpt(lines, anchor)
    focused_blob = ""
    if anchor is not None:
        lo, hi = _failure_block_bounds(lines, anchor)
        focused_blob = (
            f"=== Focused failure window (L{lo + 1}-L{hi}, anchor=L{anchor + 1}) ===\n"
            f"{_format_lines(lines, lo, hi)}\n\n"
        )

    cmd_blob = _extract_command_evidence(lines, anchor)

    windows_blob = ""
    if windows:
        header = "=== Keyword windows (failure-focused) ===\n"
        body = "\n\n".join(windows[-25:])
        windows_blob = header + body + "\n\n"

    # Fit tail into remaining budget (never drop windows in favor of cleanup tail).
    overhead = len("(…digest truncated…)\n")
    static_blob = excerpt_blob + focused_blob + cmd_blob + windows_blob
    tail_budget = max(0, max_chars - len(static_blob) - overhead)
    tail_lines = _MAX_TAIL_LINES
    tail = ""
    while tail_lines >= _MIN_TAIL_LINES:
        tail_start = max(0, len(lines) - tail_lines)
        candidate = "\n".join(
            f"{j + 1:6d} | {lines[j]}" for j in range(tail_start, len(lines))
        )
        header = f"=== Log tail (last {tail_lines} lines, numbered) ===\n"
        if len(header) + len(candidate) <= tail_budget:
            tail = header + candidate
            break
        tail_lines -= 50
    if not tail and tail_budget > 500:
        tail_start = max(0, len(lines) - _MIN_TAIL_LINES)
        candidate = "\n".join(
            f"{j + 1:6d} | {lines[j]}" for j in range(tail_start, len(lines))
        )
        tail = f"=== Log tail (last {_MIN_TAIL_LINES} lines, numbered) ===\n" + candidate[
            -(tail_budget - 80) :
        ]

    return _fit_digest_budget(
        max_chars,
        lines=lines,
        anchor=anchor,
        excerpt_blob=excerpt_blob,
        focused_blob=focused_blob,
        cmd_blob=cmd_blob,
        windows=windows,
        tail=tail,
    )


def _terms_from_failure_reason(failure_reason: str | None) -> list[str]:
    if not failure_reason:
        return []
    raw = re.split(r"[^\w:./-]+", failure_reason)
    terms: list[str] = []
    skip = frozenset({"failed", "status", "command", "error", "failure", "test"})
    for t in raw:
        t = t.strip().rstrip(":")
        if len(t) < 5 or t.lower() in skip:
            continue
        if t.endswith(":"):
            continue
        terms.append(t)
    # Prefer specific tokens (full test name) over generic substrings for anchoring.
    terms.sort(key=len, reverse=True)
    return terms[:_MAX_FAILURE_TERMS]


def _fit_digest_budget(
    max_chars: int,
    *,
    lines: list[str],
    anchor: int | None,
    excerpt_blob: str,
    focused_blob: str,
    cmd_blob: str,
    windows: list[str],
    tail: str,
) -> str:
    """Keep failure-focused sections; shrink or trim tail — never tail-only suffix truncation."""

    def pack(e_blob: str, f_blob: str, c_blob: str, w_blob: str, t_blob: str) -> str:
        return e_blob + f_blob + c_blob + w_blob + t_blob

    w_blob = ""
    if windows:
        w_blob = "=== Keyword windows (failure-focused) ===\n" + "\n\n".join(windows[-25:]) + "\n\n"

    text = pack(excerpt_blob, focused_blob, cmd_blob, w_blob, tail)
    if len(text) <= max_chars:
        return text

    # Drop keyword windows first (excerpt + focused + commands matter more).
    for n in range(len(windows), -1, -1):
        reduced_w = ""
        if n:
            reduced_w = (
                "=== Keyword windows (failure-focused) ===\n"
                + "\n\n".join(windows[-n:])
                + "\n\n"
            )
        trial = pack(excerpt_blob, focused_blob, cmd_blob, reduced_w, tail)
        if len(trial) <= max_chars:
            return trial
        w_blob = reduced_w

    # Shrink focused window around anchor (excerpt blob stays intact).
    if anchor is not None:
        for pre, post in ((120, 60), (60, 30), (30, 15)):
            lo = max(0, anchor - pre)
            hi = min(len(lines), anchor + post)
            f_blob = (
                f"=== Focused failure window (L{lo + 1}-L{hi}, anchor=L{anchor + 1}) ===\n"
                f"{_format_lines(lines, lo, hi)}\n\n"
            )
            trial = pack(excerpt_blob, f_blob, cmd_blob, w_blob, tail)
            if len(trial) <= max_chars:
                return trial
            focused_blob = f_blob

    # Trim log tail from the start (keep numbered lines nearest the failure).
    marker = "(…digest truncated…)\n"
    prefix = pack(excerpt_blob, focused_blob, cmd_blob, w_blob, "")
    budget = max_chars - len(marker)
    if budget <= 0:
        return marker + prefix[: max(0, max_chars - len(marker))]

    if len(prefix) >= budget:
        return marker + prefix[:budget]

    tail_room = budget - len(prefix)
    if tail and len(tail) > tail_room:
        # Keep the end of the tail section (closest to log end / recent activity).
        tail = "=== Log tail (trimmed) ===\n" + tail.split("\n", 1)[-1]
        tail = tail[-tail_room:]
    return marker + prefix + tail


# Pytest, cephfs test-runner, and teuthology task failures (not Pulpito job YAML).
_TEUTH_FAILURE = re.compile(
    r"(=+\s*FAILURES\b|^\s*E\s+AssertionError|AssertionError:"
    r"|cephfs_test_runner:ERROR:\s|cephfs_test_runner:[^\n]*\.\.\.\s+ERROR\b"
    r"|FAILED\s*\(errors=|CommandFailedError:"
    r"|RuntimeError:\s*Test failure)",
    re.IGNORECASE,
)

# Teuthology writes job metadata at the end of teuthology.log — not the failure itself.
_JOB_SUMMARY = re.compile(
    r"^(failure_reason|status|duration|flavor|owner|sentry_event|updated|scheduled)\s*:",
    re.IGNORECASE,
)


def _failure_line_score(line: str, line_no: int, total_lines: int) -> int:
    score = 0
    if _TEUTH_FAILURE.search(line):
        score += 200
    if "cephfs_test_runner" in line:
        score += 600
    if re.search(r"ERROR:\s+test_", line, re.I) or re.search(r"\.\.\.\s+ERROR\b", line):
        score += 500
    if "AssertionError" in line:
        score += 400
    if re.search(r"CommandFailedError:.*\bstatus\s+\d+", line, re.I):
        score += 900
    elif "CommandFailedError:" in line:
        score += 650
    if "Traceback" in line and "cephfs_test_runner" in line:
        score += 350
    if "run_tasks:Exception was not quenched" in line or "Unwinding manager" in line:
        score -= 700
    if "scraping logs" in line.lower() or "collecting logs" in line.lower():
        score -= 400
    if line_no >= total_lines - 200:
        score -= 250
    return score


def _is_job_summary_line(line: str) -> bool:
    stripped = line.strip()
    if _JOB_SUMMARY.match(stripped):
        return True
    # Pulpito dumps multi-line YAML; single-quoted failure_reason without timestamp prefix.
    if stripped.startswith("failure_reason:") and "Test failure:" in stripped:
        return True
    return False


def _score_failure_proximity(lines: list[str], anchor: int) -> int:
    score = 0
    for j in range(anchor, min(len(lines), anchor + 300)):
        ln = lines[j]
        if _TEUTH_FAILURE.search(ln):
            score += 1000 - (j - anchor)
        if "Traceback" in ln and "cephfs_test_runner" in ln:
            score += 500 - (j - anchor)
        if "CommandFailedError" in ln:
            score += 300 - (j - anchor)
    return score


def _anchor_from_term_matches(lines: list[str], matches: list[int]) -> int:
    if not matches:
        raise ValueError("matches must be non-empty")
    scored = [( _score_failure_proximity(lines, i), i) for i in matches]
    scored.sort(reverse=True)
    if scored[0][0] > 0:
        return scored[0][1]
    return matches[-1]


def _first_failure_line(
    lines: list[str], scan_start: int, *, failure_reason: str | None
) -> int | None:
    tail_scan = max(scan_start, len(lines) - 4000)
    best_idx: int | None = None
    best_score = 0
    for i in range(len(lines) - 1, tail_scan - 1, -1):
        if _is_job_summary_line(lines[i]):
            continue
        if not _TEUTH_FAILURE.search(lines[i]):
            continue
        score = _failure_line_score(lines[i], i, len(lines))
        if score > best_score:
            best_score = score
            best_idx = i
    if best_idx is not None:
        return best_idx

    terms = _terms_from_failure_reason(failure_reason)
    if terms:
        for term in terms:
            pat = re.compile(re.escape(term), re.IGNORECASE)
            matches = [
                i
                for i in range(scan_start, len(lines))
                if pat.search(lines[i]) and not _is_job_summary_line(lines[i])
            ]
            if not matches:
                continue
            anchor = _anchor_from_term_matches(lines, matches)
            for j in range(anchor, min(len(lines), anchor + 250)):
                if _TEUTH_FAILURE.search(lines[j]):
                    return j
            return anchor

    for i in range(scan_start, len(lines)):
        line = lines[i]
        if _NOISE_LINE.search(line) or _is_job_summary_line(line):
            continue
        if _FAILURE_HINT.search(line):
            return i
    return None


def _refine_anchor(lines: list[str], anchor: int | None) -> int | None:
    """Prefer CommandFailedError / traceback over duplicate pytest ERROR banners."""
    if anchor is None:
        return None
    search_lo = max(0, anchor - 120)
    cmd_idx: int | None = None
    for i in range(anchor, search_lo - 1, -1):
        if _is_job_summary_line(lines[i]):
            continue
        if re.search(r"CommandFailedError:.*\bstatus\s+\d+", lines[i], re.I):
            return i
        if "CommandFailedError:" in lines[i] and cmd_idx is None:
            cmd_idx = i
    if cmd_idx is not None:
        return cmd_idx
    for i in range(anchor, search_lo - 1, -1):
        if "Traceback (most recent call last)" in lines[i]:
            return i
    return anchor


def _failure_block_bounds(lines: list[str], anchor: int) -> tuple[int, int]:
    """Bounds for the cephfs/pytest failure block, not a fixed line count before anchor."""
    lo = max(0, anchor - _FOCUSED_PRE_LINES)
    hi = min(len(lines), anchor + _FOCUSED_POST_LINES)
    for i in range(anchor, max(0, anchor - 120) - 1, -1):
        if re.search(r"ERROR:\s+test_", lines[i], re.I) and "cephfs_test_runner" in lines[i]:
            lo = max(0, i - 2)
            break
        if "======" in lines[i] and "cephfs_test_runner" in lines[i]:
            lo = max(0, i - 1)
            break
    for i in range(anchor, min(len(lines), anchor + 80)):
        if "FAILED (errors=" in lines[i] or "FAILED (failures=" in lines[i]:
            hi = min(len(lines), i + 8)
            break
        if re.search(r"Ran \d+ tests? in ", lines[i]) and "cephfs_test_runner" in lines[i]:
            hi = min(len(lines), i + 12)
    # Do not let the window start hundreds of lines before the failure block.
    block_lo = lo
    for i in range(anchor, max(0, anchor - 120) - 1, -1):
        if "Traceback (most recent call last)" in lines[i]:
            block_lo = max(0, i - 3)
            break
    if block_lo > lo:
        lo = block_lo
    max_span = 220
    if hi - lo > max_span:
        lo = hi - max_span
    return lo, hi


def _extract_test_runner_excerpt(lines: list[str], anchor: int | None) -> str:
    """Compact traceback + CommandFailedError block (always high priority for LLM)."""
    if anchor is None:
        return ""
    lo, hi = _failure_block_bounds(lines, anchor)
    # Tighten to runner lines with failure content when the block is large.
    picked: list[str] = []
    for j in range(lo, hi):
        line = lines[j]
        if "cephfs_test_runner" not in line:
            continue
        if re.search(
            r"ERROR:\s+test_|Traceback|CommandFailedError|FAILED \(|set_max_mds|"
            r"run_ceph_cmd|status \d+|line \d+",
            line,
            re.I,
        ):
            picked.append(f"{j + 1:6d} | {line}")
    if len(picked) < 8:
        picked = [f"{j + 1:6d} | {lines[j]}" for j in range(lo, hi) if "cephfs_test_runner" in lines[j]]
    if not picked:
        return ""
    body = "\n".join(picked[:80])
    return f"=== Test failure excerpt (cephfs_test_runner) ===\n{body}\n\n"


def _format_lines(lines: list[str], lo: int, hi: int) -> str:
    return "\n".join(f"{j + 1:6d} | {lines[j]}" for j in range(lo, hi))


def _extract_command_evidence(lines: list[str], anchor: int | None) -> str:
    if anchor is None:
        return ""
    lo = max(0, anchor - _CMD_SCAN_PRE)
    hi = min(len(lines), anchor + _CMD_SCAN_POST)
    evidence: list[str] = []
    for i in range(lo, hi):
        line = lines[i]
        if not _COMMAND_LINE.search(line):
            continue
        chunk = [f"L{i + 1}: {line.strip()}"]
        for j in range(i + 1, min(hi, i + 6)):
            nxt = lines[j].strip()
            rc = _RC_LINE.search(nxt)
            if rc:
                chunk.append(f"L{j + 1}: {nxt}")
                break
            if _FAILURE_HINT.search(nxt):
                chunk.append(f"L{j + 1}: {nxt[:220]}")
                break
        evidence.append(" | ".join(chunk))
        if len(evidence) >= _MAX_COMMAND_EVIDENCE:
            break
    if not evidence:
        return ""
    body = "\n".join(f"- {row}" for row in evidence)
    return f"=== Command evidence near failure ===\n{body}\n\n"
