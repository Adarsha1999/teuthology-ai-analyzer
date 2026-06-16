from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession, resolve_app_session
from app.models.schemas import AssistantChatIn, AssistantChatOut
from app.services.assistant import chat_with_assistant
from app.services.llm_common import LLMError
from app.services.teuth_docs import teuthology_docs_url

router = APIRouter(tags=["Assistant"])


@router.post("/assistant/chat", response_model=AssistantChatOut)
def assistant_chat(
    body: AssistantChatIn,
    db: DbSession,
    session: tuple = Depends(resolve_app_session),
) -> AssistantChatOut:
    from app.services.session_service import SessionService

    svc, sid = session
    sessions = SessionService(db)
    conn = sessions.get_llm_connection(sid)
    if conn is None:
        raise HTTPException(
            401,
            "Connect a model first (pick a provider in the top bar).",
        )
    try:
        reply = chat_with_assistant(
            conn,
            messages=[m.model_dump() for m in body.messages],
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return AssistantChatOut(reply=reply, docs_url=teuthology_docs_url())
