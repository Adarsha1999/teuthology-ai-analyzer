from __future__ import annotations

from pathlib import Path

_DOCS_PATH = Path(__file__).resolve().parent / "data" / "teuthology_readme_context.md"
_DOCS_URL = "https://docs.ceph.com/projects/teuthology/en/latest/README.html"


def teuthology_docs_context() -> str:
    if _DOCS_PATH.is_file():
        return _DOCS_PATH.read_text(encoding="utf-8").strip()
    return f"(Documentation file missing; see {_DOCS_URL})"


def teuthology_docs_url() -> str:
    return _DOCS_URL


def assistant_system_prompt() -> str:
    docs = teuthology_docs_context()
    return (
        "You are **Teuth Assistant**, a helpful chatbot for Ceph Teuthology integration testing.\n"
        "Answer questions using the official Teuthology documentation excerpt below.\n"
        "Rules:\n"
        "- Prefer facts from the documentation; do not invent commands or flags.\n"
        "- If the docs do not cover a question, say so clearly and suggest checking the upstream docs.\n"
        "- Be concise; use bullet lists for commands and parameters when helpful.\n"
        "- This app also analyzes Pulpito runs and teuthology.log via Ollama; you may mention that for log triage.\n"
        f"- Official docs: {teuthology_docs_url()}\n\n"
        "--- BEGIN TEUTHOLOGY DOCUMENTATION ---\n"
        f"{docs}\n"
        "--- END TEUTHOLOGY DOCUMENTATION ---"
    )
