from __future__ import annotations

from app.core.llm_config import LLMConnection
from app.services.llm_client import chat_llm
from app.services.teuth_docs import assistant_system_prompt


def chat_with_assistant(
    conn: LLMConnection,
    *,
    messages: list[dict[str, str]],
) -> str:
    """Run one assistant turn; messages are prior user/assistant turns (no system)."""
    system = assistant_system_prompt()
    ollama_messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for msg in messages[-20:]:
        role = msg.get("role", "").strip()
        content = msg.get("content", "").strip()
        if role in ("user", "assistant") and content:
            ollama_messages.append({"role": role, "content": content})
    if not any(m["role"] == "user" for m in ollama_messages):
        raise ValueError("At least one user message is required")
    return chat_llm(conn, ollama_messages, timeout=float(conn.request_timeout))
