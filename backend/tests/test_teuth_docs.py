"""
Tests for backend/app/services/teuth_docs.py

Validates that embedded teuthology documentation context and system prompts
contain the expected reference material.
"""
from app.services.teuth_docs import (
    assistant_system_prompt,
    teuthology_docs_context,
    teuthology_docs_url,
)


# ── Documentation context ────────────────────────────────────────────────────

class TestTeuthDocs:
    def test_context_not_empty(self) -> None:
        ctx = teuthology_docs_context()
        assert "teuthology-suite" in ctx
        assert "Paramiko" in ctx or "SSH" in ctx

    def test_system_prompt_includes_docs(self) -> None:
        prompt = assistant_system_prompt()
        assert teuthology_docs_url() in prompt
        assert "Teuth Assistant" in prompt
        assert "teuthology-suite" in prompt
