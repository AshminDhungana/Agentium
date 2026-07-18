"""Tool: request_user_clarification — ask the Sovereign a structured question."""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from backend.models.entities.user import User
from backend.models.schemas.structured_input import (
    StructuredInputCard, CardQuestion, CardOption,
)
from backend.services.chat_service import ChatService


def _resolve_sovereign_user_id(db: Session) -> str:
    user = db.query(User).filter_by(is_admin=True, is_active=True).first()
    return str(user.id) if user else ""


def request_user_clarification(
    title: Optional[str] = None,
    questions: Optional[List[Dict[str, Any]]] = None,
    expires_at: Optional[str] = None,
    db: Optional[Session] = None,
    agent_id: Optional[str] = None,
) -> str:
    """Post a structured input card to the Sovereign and continue.

    Fire-and-forget: the answer is recorded later via the card_response path and
    appears in chat history. Returns a short status string for the LLM.
    """
    if db is None:
        return "error: no database session available"
    if not questions:
        return "error: 'questions' is required to ask the Sovereign"
    try:
        card = StructuredInputCard(
            card_id=f"card-{uuid4()}",
            card_group_id=None,
            title=title,
            questions=[CardQuestion(**q) for q in questions],
            expires_at=expires_at,
        )
    except Exception as exc:  # noqa: BLE001
        return f"error: invalid card payload: {exc}"

    user_id = _resolve_sovereign_user_id(db)
    if not user_id:
        return "error: no sovereign user found"
    try:
        result = ChatService.send_structured_card(card, db, user_id)
    except Exception as exc:  # noqa: BLE001
        return f"error: failed to send card: {exc}"
    return f"ok: clarification card {result.get('card_id')} sent to the Sovereign"
