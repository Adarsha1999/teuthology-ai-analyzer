"""
IBM Bob Shell provider — subprocess-based LLM inference via the ``bob`` CLI.

Handles subprocess invocation with three input modes (stdin, argument,
prompt_file), ANSI/chrome stripping, folder-trust detection, detailed
health checks, and environment sandboxing.

All Bob CLI logic lives here — no separate service module.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.llm_config import LLMConnection, ProviderSpec, get_settings
from app.providers.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]

# ── Trust detection phrases ────────────────────────────────────────────────────

_TRUST_PHRASES = (
    "do you trust this folder",
    "trust this folder",
    "trusting a folder allows bob",
    "trust folder",
    "folder trust",
)

# ── Output cleaning patterns ──────────────────────────────────────────────────

_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_BOX_DRAWING = re.compile(r"[╔╦╗╠╬╣╚╩╝═║┌┬┐├┼┤└┴┘─│╭╮╯╰▶◀►◄]")
_CHROME_LINE = re.compile(
    r"^\s*(\[?✓\]?|✗|\bTask\b|\bTool\b|\bCompleted\b|\bRunning\b|\bDone\b|[-─═]+)\s*$",
    re.IGNORECASE,
)


class FolderTrustError(LLMError):
    """Bob Shell blocked the run until the workspace folder is trusted."""


# ── Settings ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BobCLISettings:
    """Resolved Bob CLI configuration from environment variables."""

    command: str
    workdir: str
    timeout: int
    input_mode: str
    extra_args: list[str]
    api_key: str

    @property
    def enabled(self) -> bool:
        """True if Bob is explicitly enabled or an API key is set."""
        flag = os.environ.get("IBM_BOB_ENABLED", "").lower() in ("1", "true", "yes")
        return flag or bool(self.api_key.strip())


def load_bob_settings() -> BobCLISettings:
    """Load Bob CLI settings from environment variables and provider config.

    Returns:
        Populated ``BobCLISettings`` with resolved command, workdir, timeout,
        input mode, extra args, and API key.
    """
    settings = get_settings()
    spec = settings.llm_providers.get("bob")
    api_key = (
        os.environ.get("BOBSHELL_API_KEY", "").strip()
        or os.environ.get("BOB_API_KEY", "").strip()
        or (spec.api_key.strip() if spec else "")
    )
    workdir = os.environ.get("IBM_BOB_WORKDIR", "").strip() or str(_REPO_ROOT)
    raw_extra = os.environ.get("IBM_BOB_EXTRA_ARGS", "").strip()
    extra = raw_extra.split() if raw_extra else ["--auth-method", "api-key"]
    if "--auth-method" not in " ".join(extra):
        extra = ["--auth-method", "api-key", *extra]
    return BobCLISettings(
        command=os.environ.get("IBM_BOB_COMMAND", "bob"),
        workdir=workdir,
        timeout=int(
            os.environ.get(
                "IBM_BOB_TIMEOUT_SECONDS",
                str(spec.request_timeout if spec else 600),
            )
        ),
        input_mode=os.environ.get("IBM_BOB_INPUT_MODE", "stdin").lower(),
        extra_args=extra,
        api_key=api_key,
    )


# ── Provider class ─────────────────────────────────────────────────────────────

class BobCLIProvider(LLMProvider):
    """IBM Bob Shell provider for CLI-based LLM inference.

    Runs the ``bob`` command as a subprocess.  Configuration is loaded
    from ``IBM_BOB_*`` / ``BOBSHELL_*`` environment variables.
    """

    def __init__(self, spec: ProviderSpec) -> None:
        super().__init__(spec)

    def chat(
        self,
        conn: LLMConnection,
        messages: list[dict[str, str]],
        *,
        timeout: float,
        json_format: bool = False,
    ) -> str:
        """Invoke Bob Shell with a chat-style message list.

        Args:
            conn: Session connection (unused — Bob reads config from env).
            messages: Chat messages formatted into a Bob-compatible prompt.
            timeout: Subprocess timeout in seconds.
            json_format: If True, append JSON output instructions.

        Returns:
            Cleaned Bob Shell output text.

        Raises:
            LLMError: If Bob is disabled, API key is missing, or subprocess fails.
        """
        del conn
        return chat_messages(messages, timeout=timeout, json_format=json_format)

    def health_check(self) -> bool:
        """Check if the Bob CLI is configured, installed, and accessible.

        Returns:
            True if Bob is healthy, False otherwise.
        """
        health = detailed_health()
        return bool(health.get("healthy"))


# ── Public functions (used by API routes + tests) ──────────────────────────────

def clean_terminal_output(raw: str) -> str:
    """Strip ANSI codes and Bob Shell UI chrome from subprocess output.

    Args:
        raw: Raw subprocess stdout/stderr text.

    Returns:
        Cleaned text with chrome stripped.
    """
    text = _ANSI_ESCAPE.sub("", raw)
    text = _BOX_DRAWING.sub("", text)
    lines = [ln for ln in text.splitlines() if not _CHROME_LINE.match(ln)]
    return "\n".join(lines).strip()


def detailed_health() -> dict:
    """Return detailed health status for the Bob CLI provider.

    Checks: command on PATH, API key configured, workspace directory
    exists, and optionally fetches ``--version`` output.

    Returns:
        Dict with provider, configured, healthy, command, workdir,
        model_label, version, and error keys.
    """
    cfg = load_bob_settings()
    base: dict[str, Any] = {
        "provider": "bob",
        "configured": False,
        "healthy": False,
        "command": None,
        "workdir": cfg.workdir,
        "model_label": "Bob Shell (IBM)",
        "version": None,
        "error": None,
    }
    if not cfg.enabled:
        base["error"] = (
            "IBM Bob CLI is disabled. Set BOBSHELL_API_KEY in backend/.env "
            "or IBM_BOB_ENABLED=true."
        )
        return base
    if not cfg.api_key.strip():
        base["error"] = "BOBSHELL_API_KEY or BOB_API_KEY is not set."
        return base
    resolved = shutil.which(cfg.command)
    if not resolved:
        base["error"] = (
            f"`{cfg.command}` not found in PATH. Install: "
            "curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash"
        )
        return base
    if not Path(cfg.workdir).is_dir():
        base["error"] = f"IBM_BOB_WORKDIR does not exist: {cfg.workdir}"
        base["configured"] = True
        return base
    version: str | None = None
    try:
        proc = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            timeout=15,
            cwd=cfg.workdir,
            env=_safe_env(cfg),
            check=False,
        )
        combined = clean_terminal_output(
            (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
        )
        if combined:
            version = combined[:200]
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Bob --version check failed: %s", exc)
    base.update(
        configured=True,
        healthy=True,
        command=resolved,
        version=version,
    )
    return base


def chat_messages(
    messages: list[dict[str, str]],
    *,
    timeout: float | None = None,
    json_format: bool = False,
) -> str:
    """Run Bob Shell with a chat-style message list; return stdout text.

    Args:
        messages: Chat messages to send.
        timeout: Subprocess timeout in seconds (defaults to config).
        json_format: If True, append JSON output instructions.

    Returns:
        Cleaned Bob Shell output text.

    Raises:
        LLMError: If Bob is disabled, API key is missing, or output is empty.
    """
    cfg = load_bob_settings()
    if not cfg.enabled:
        raise LLMError(
            "IBM Bob CLI is disabled. Set BOBSHELL_API_KEY in backend/.env "
            "(see https://bob.ibm.com/docs/shell/getting-started/install-and-setup)."
        )
    if not cfg.api_key.strip():
        raise LLMError(
            "BOBSHELL_API_KEY is required for Bob Shell. Create an Inference-scope key "
            "at https://bob.ibm.com/docs/ide/account/api-keys"
        )
    prompt = _messages_to_prompt(messages, json_format=json_format)
    limit = int(timeout if timeout is not None else cfg.timeout)
    logger.info(
        "Bob Shell: cmd=%s workdir=%s prompt_len=%d timeout=%ds",
        cfg.command,
        cfg.workdir,
        len(prompt),
        limit,
    )
    raw = _invoke(prompt, cfg, timeout=limit)
    cleaned = clean_terminal_output(raw)
    if not cleaned:
        raise LLMError("Bob Shell returned empty output.")
    return cleaned


# ── Private helpers ────────────────────────────────────────────────────────────

def _messages_to_prompt(messages: list[dict[str, str]], *, json_format: bool) -> str:
    """Flatten chat messages into a Bob-compatible prompt string."""
    parts: list[str] = []
    for msg in messages:
        role = (msg.get("role") or "user").strip().upper()
        content = (msg.get("content") or "").strip()
        if content:
            parts.append(f"=== {role} ===\n{content}")
    if json_format:
        parts.append(
            "\n=== OUTPUT FORMAT ===\n"
            "Respond with a single JSON object only (no markdown fences). "
            "Keys: summary, likely_root_cause, evidence (array of strings), "
            "next_steps (array of strings), confidence (number 0-1)."
        )
    return "\n\n".join(parts)


def _prompt_spool_dir(cfg: BobCLISettings) -> Path:
    """Directory inside IBM_BOB_WORKDIR for large prompts (Bob cannot read system /tmp)."""
    d = Path(cfg.workdir) / ".bob" / "teuthology-prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _invoke(prompt: str, cfg: BobCLISettings, *, timeout: int) -> str:
    """Dispatch to the configured input mode handler."""
    mode = cfg.input_mode
    if mode == "argument":
        return _invoke_argument(prompt, cfg, timeout=timeout)
    if mode == "prompt_file":
        return _invoke_prompt_file(prompt, cfg, timeout=timeout)
    return _invoke_stdin(prompt, cfg, timeout=timeout)


def _resolve_command(command: str) -> str:
    """Resolve the bob command path, raising LLMError if not found."""
    resolved = shutil.which(command)
    if not resolved:
        raise LLMError(
            f"IBM Bob command `{command}` not found in PATH. "
            "Install Bob Shell: curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash"
        )
    return resolved


def _invoke_stdin(prompt: str, cfg: BobCLISettings, *, timeout: int) -> str:
    """Send prompt via stdin to bob subprocess."""
    resolved = _resolve_command(cfg.command)
    cmd = [resolved, *cfg.extra_args]
    try:
        proc = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            cwd=cfg.workdir,
            env=_safe_env(cfg),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"Bob Shell timed out after {timeout}s.") from exc
    return _process_output(proc.returncode, proc.stdout, proc.stderr, cfg)


def _invoke_argument(prompt: str, cfg: BobCLISettings, *, timeout: int) -> str:
    """Pass prompt as a positional argument to bob subprocess."""
    resolved = _resolve_command(cfg.command)
    cmd = [resolved, *cfg.extra_args, prompt]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=cfg.workdir,
            env=_safe_env(cfg),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"Bob Shell timed out after {timeout}s.") from exc
    return _process_output(proc.returncode, proc.stdout, proc.stderr, cfg)


def _invoke_prompt_file(prompt: str, cfg: BobCLISettings, *, timeout: int) -> str:
    """Spool prompt under workdir; deliver on stdin (never pass /tmp path as positional)."""
    resolved = _resolve_command(cfg.command)
    prompt_file = _prompt_spool_dir(cfg) / f"prompt-{uuid.uuid4().hex}.txt"
    try:
        prompt_file.write_text(prompt, encoding="utf-8")
        prompt_file.chmod(0o600)
        logger.debug("Bob prompt spool: %s", prompt_file)
        cmd = [resolved, *cfg.extra_args]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                cwd=cfg.workdir,
                env=_safe_env(cfg),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"Bob Shell timed out after {timeout}s.") from exc
        return _process_output(proc.returncode, proc.stdout, proc.stderr, cfg)
    finally:
        try:
            prompt_file.unlink(missing_ok=True)
        except OSError:
            pass


def _process_output(
    returncode: int, stdout: bytes, stderr: bytes, cfg: BobCLISettings
) -> str:
    """Check subprocess output for trust errors, workspace issues, and warnings."""
    stdout_s = stdout.decode("utf-8", errors="replace")
    stderr_s = stderr.decode("utf-8", errors="replace")
    combined_lower = (stdout_s + stderr_s).lower()
    if any(phrase in combined_lower for phrase in _TRUST_PHRASES):
        raise FolderTrustError(
            f"Bob Shell requires folder trust. In a terminal: cd {cfg.workdir!r} && "
            f"{cfg.command} --accept-license --trust --auth-method api-key"
        )
    if "outside my allowed workspace" in combined_lower or (
        "encountered an issue accessing the file" in combined_lower
        and "teuthology-ai-bob" in combined_lower
    ):
        raise LLMError(
            "Bob Shell could not read the prompt file (workspace restriction). "
            "Restart the API after upgrading bob_cli (prompts are sent on stdin)."
        )
    if returncode != 0:
        logger.warning(
            "Bob Shell exit %d stderr=%s", returncode, stderr_s[:500]
        )
    return stdout_s.strip() or stderr_s.strip()


def _safe_env(cfg: BobCLISettings) -> dict[str, str]:
    """Build minimal sandboxed env for bob: PATH, home, and Bob API key only."""
    keep = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP")
    env: dict[str, str] = {}
    for key in keep:
        if key in os.environ:
            env[key] = os.environ[key]
    env["BOBSHELL_API_KEY"] = cfg.api_key
    env["IBM_BOB_ENABLED"] = "true"
    return env
