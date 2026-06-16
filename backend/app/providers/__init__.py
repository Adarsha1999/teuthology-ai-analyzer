"""
LLM Provider package — Strategy + Factory pattern.

Architecture mirrors cephci-ai-assistant:

    ProviderFactory.get_provider(kind)
        → LLMProvider subclass (Ollama, OpenAI, Gemini, Cursor, BobCLI)
        → .chat(conn, messages, …) → str
"""
from app.providers.base import LLMProvider  # noqa: F401
from app.providers.factory import ProviderFactory  # noqa: F401
