"""
Chat API for Sovereign to communicate with Head of Council.
Supports streaming responses for real-time communication.

Changes vs original:
  - FIX: ChatMessage Pydantic model now accepts optional 'attachments' field.
  - FIX: _stream_response() accepts and injects file content into the prompt.
  - FIX: Non-streaming send_message() path also injects file content.
  - FIX: Persisted ChatMessage now stores attachment metadata for history reload.
"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Optional
from typing import Annotated

from fastapi import APIRouter, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.models.database import get_db, SessionLocal
from backend.models.entities import Agent, HeadOfCouncil, Task
from backend.models.entities.user import User
from backend.services.chat_service import ChatService
from backend.services.model_provider import ModelService
from backend.models.schemas.structured_input import StructuredInputCard
from backend.services.structured_input_service import render_external_text
from backend.api.routes.websocket import manager as ws_manager
from backend.models.entities.chat_message import ChatMessage as ChatMessageEntity

logger = logging.getLogger(__name__)
from backend.core.auth import get_current_active_user, get_voice_or_active_user
from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    message: str
    stream: bool = True
    # NEW: optional attachments forwarded from the frontend after file upload.
    # Each dict contains at minimum: name, type, size, url, extracted_text (optional).
    attachments: Optional[List[dict]] = Field(default=None)
    # NEW: structured input card answer (mirrors the WebSocket card_response frame).
    card_response: Optional[dict] = None
    # NEW (Jarvis upgrade): optional persona for the voice bridge. When set, it
    # is prepended to the prompt so the Head of Council speaks in character.
    voice_persona: Optional[str] = None
    # NEW (Jarvis upgrade): optional speaker id from the voice bridge's speaker
    # identification step, used to tag the resulting context.
    speaker_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    task_created: bool = False
    task_id: str = None


def _enrich_with_persona(message: str, persona: Optional[str]) -> str:
    """Prepend an optional persona instruction to the user message."""
    if not persona:
        return message
    return f"[Persona: {persona.strip()}]\n\n{message}"


def _build_turn_system_prompt(head, db, channel: str) -> str:
    """Resolve the Head of Council's system prompt for a chat turn.

    The prompt is ALWAYS derived server-side from the live Constitution via
    ``head.get_system_prompt``. The voice bridge's ``voice_persona`` payload is
    used ONLY to select the voice channel/adaptation (handled by the caller) and
    is NEVER trusted as the system prompt — this prevents a compromised or
    buggy bridge from injecting arbitrary behaviour into the Head.
    """
    return head.get_system_prompt(db=db, channel=channel)


def _build_enriched_message(
    message: str,
    attachments: Optional[List[dict]],
    persona: Optional[str] = None,
) -> str:
    """
    Append extracted file content to the user message.

    Uses build_file_context_for_ai() from file_processor so the same
    token-budgeted, consistently formatted context is produced for both
    the WebSocket and REST paths.

    Returns the original message unchanged if attachments is None/empty
    or file_processor is unavailable.
    """
    if persona:
        message = _enrich_with_persona(message, persona)

    if not attachments:
        return message

    try:
        from backend.services.file_processor import build_file_context_for_ai
        file_context = build_file_context_for_ai(attachments, max_total_chars=30_000)
    except Exception as exc:
        logger.warning(f"[chat.py] file_processor unavailable: {exc}")
        return message

    if not file_context:
        return message

    return f"{message}\n\n{file_context}" if message else file_context


# ═══════════════════════════════════════════════════════════
# Conversation endpoints
# ═══════════════════════════════════════════════════════════

@router.get(
    "/conversations",
    summary="List conversations",
    description="List all conversations for the current user.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def list_conversations(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """List all conversations for current user."""
    from backend.models.entities.chat_message import Conversation

    query = db.query(Conversation).filter(
        Conversation.user_id == str(current_user.get("user_id", "")),
        Conversation.is_deleted == "N",
    )

    if not include_archived:
        query = query.filter(Conversation.is_archived == "N")

    conversations = query.order_by(desc(Conversation.last_message_at)).all()

    return {
        "conversations": [c.to_dict() for c in conversations],
        "total": len(conversations),
    }


@router.post(
    "/conversations",
    summary="Create a conversation",
    description="Create a new conversation.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def create_conversation(
    title: Optional[str] = None,
    context: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Create a new conversation."""
    from backend.models.entities.chat_message import Conversation

    conversation = Conversation(
        user_id=str(current_user.get("user_id", "")),
        title=title or "New Conversation",
        context=context,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation.to_dict()


@router.get(
    "/conversations/{conversation_id}",
    summary="Get a conversation",
    description="Get a specific conversation with messages.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_conversation(
    conversation_id: str,
    include_messages: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get a specific conversation with messages."""
    from backend.models.entities.chat_message import Conversation

    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.get("user_id", "")),
        Conversation.is_deleted == "N",
    ).first()

    if not conversation:
        raise NotFoundError(error="Conversation not found", code="CONVERSATION_NOT_FOUND")

    return conversation.to_dict(include_messages=include_messages)


@router.post(
    "/conversations/{conversation_id}/archive",
    summary="Archive a conversation",
    description="Archive a conversation.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def archive_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Archive a conversation."""
    from backend.models.entities.chat_message import Conversation

    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.get("user_id", "")),
    ).first()

    if not conversation:
        raise NotFoundError(error="Conversation not found", code="CONVERSATION_NOT_FOUND")

    conversation.is_archived = "Y"
    db.commit()
    return {"success": True, "message": "Conversation archived"}


@router.delete(
    "/conversations/{conversation_id}",
    summary="Delete a conversation",
    description="Soft delete a conversation.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Soft delete a conversation."""
    from backend.models.entities.chat_message import Conversation

    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.get("user_id", "")),
    ).first()

    if not conversation:
        raise NotFoundError(error="Conversation not found", code="CONVERSATION_NOT_FOUND")

    conversation.is_deleted = "Y"
    db.commit()
    return {"success": True, "message": "Conversation deleted"}


@router.get(
    "/stats",
    summary="Get chat statistics",
    description="Get chat statistics for current user.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_chat_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get chat statistics for current user."""
    from backend.models.entities.chat_message import ChatMessage as ChatMsg, Conversation
    from datetime import datetime, timedelta

    total_conversations = db.query(Conversation).filter(
        Conversation.user_id == str(current_user.get("user_id", "")),
        Conversation.is_deleted == "N",
    ).count()

    total_messages = db.query(ChatMsg).filter(
        ChatMsg.user_id == str(current_user.get("user_id", "")),
        ChatMsg.is_deleted == "N",
    ).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = db.query(ChatMsg).filter(
        ChatMsg.user_id == str(current_user.get("user_id", "")),
        ChatMsg.created_at >= today_start,
        ChatMsg.is_deleted == "N",
    ).count()

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "storage_used_bytes": 0,
    }


# ═══════════════════════════════════════════════════════════
# Send message
# ═══════════════════════════════════════════════════════════

@router.post(
    "/send", response_class=StreamingResponse,
    summary="Send a message",
    description="Send a message to the Head of Council. Returns a streaming response for real-time updates.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        503: {"description": "Service Unavailable", "model": ErrorResponseExample},
    },
)
async def send_message(
    chat_msg: ChatMessage,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_voice_or_active_user),
):
    """
    Send message to Head of Council (00001).
    Returns streaming response for real-time updates.
    Attachments are enriched with extracted file content before reaching the AI.
    """
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

    if not head:
        raise ServiceUnavailableError(error="Head of Council not initialized", code="HEAD_OF_COUNCIL_NOT_INITIALIZED")

    if head.status.value != "active":
        raise ServiceUnavailableError(error=f"Head of Council is {head.status.value}", code="HEAD_OF_COUNCIL_IS")

    if chat_msg.stream:
        return StreamingResponse(
            # FIX: pass attachments so the streaming path can inject file content
            _stream_response(
                head.agentium_id,
                chat_msg,
                chat_msg.attachments,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # FIX: non-streaming path also enriches the message with file content.
    # voice_persona is no longer prepended to the user message — it is merged
    # into the system prompt by the streaming path for cross-channel consistency.
    enriched_message = _build_enriched_message(
        chat_msg.message, chat_msg.attachments
    )
    extra_metadata = {"card_response": chat_msg.card_response} if chat_msg.card_response else None
    response = await ChatService.process_message(head, enriched_message, db, extra_metadata=extra_metadata)
    return ChatResponse(
        response=response["content"],
        agent_id=head.agentium_id,
        task_created=response.get("task_created", False),
        task_id=response.get("task_id"),
    )


# ═══════════════════════════════════════════════════════════
# Structured Input Card
# ═══════════════════════════════════════════════════════════

@router.post(
    "/card",
    summary="Send a structured input card",
    description="Persist an agent-issued structured input card and broadcast it to the chat thread.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def send_structured_card(
    card: StructuredInputCard,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_active_user)],
):
    """Persist an agent-issued structured input card and broadcast it to the chat thread."""
    user_id = str(current_user.get("user_id", ""))
    msg = ChatService.send_structured_card(card, db, user_id)
    return {"status": "ok", "message": msg}


class PersonaResponse(BaseModel):
    persona: str
    source: str


@router.get(
    "/persona",
    response_model=PersonaResponse,
    summary="Get the Head of Council persona",
    description="Return the Head of Council's effective system prompt so the voice "
                "bridge can speak in the same persona as the text chat.",
)
async def get_persona(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_voice_or_active_user),
    channel: str = "text",
):
    """
    Return the Head of Council's effective persona (system prompt).

    The voice bridge calls this so its spoken replies match the chat persona
    exactly — both are driven by the same Constitution-derived Head system
    prompt, which keeps behavior consistent across channels. Pass
    `?channel=voice` to get the spoken-style-adapted persona.
    """
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    if not head:
        return PersonaResponse(persona="", source="none")
    prompt = head.get_system_prompt(db=db, channel=channel)
    return PersonaResponse(persona=prompt or "", source="constitution")


async def _stream_response(
    agent_id: str,
    chat_msg: "ChatMessage",
    attachments: Optional[List[dict]] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream response from Head of Council.

    FIX: Accepts optional attachments and enriches the message with
    extracted file content before calling stream_generate().

    FIX: A `_done_sent` flag prevents the finally block from emitting a
    second 'done' event when an early-return error path has already
    terminated the stream.
    """
    db: Session = SessionLocal()
    broadcast_payload: Optional[dict] = None
    _done_sent = False

    try:
        head = db.query(HeadOfCouncil).filter_by(agentium_id=agent_id).first()
        if not head:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Head of Council not found'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            _done_sent = True
            return

        config    = head.get_model_config(db)
        config_id = config.id if config else None
        model_name = config.default_model if config else "default"

        # FALLBACK: if Head has no model_config_id fall back to the system default
        if not config_id:
            try:
                from backend.models.entities import UserModelConfig
                from backend.models.entities.user_config import ConnectionStatus
                _default = (
                    db.query(UserModelConfig)
                    .filter(UserModelConfig.is_default == True)
                    .filter(UserModelConfig.status == ConnectionStatus.ACTIVE)
                    .first()
                )
                if _default:
                    config_id  = str(_default.id)
                    model_name = _default.default_model
            except Exception as _fb_err:
                logger.error(f"[chat.py] Config fallback failed: {_fb_err}")

        provider = await ModelService.get_provider("sovereign", config_id)
        if not provider:
            error_msg = (
                "⚠️ **Model Configuration Required**\n\n"
                "No AI model provider is configured. "
                "Go to **Settings → Model Configuration** and add a provider."
            )
            yield f"data: {json.dumps({'type': 'content', 'content': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            _done_sent = True
            return

        channel = "voice" if chat_msg.voice_persona else "text"
        # Resolve the system prompt server-side from the live Constitution.
        # We deliberately do NOT use ``chat_msg.voice_persona`` as the prompt:
        # it is bridge-supplied and must never be trusted as the Head's system
        # prompt (see _build_turn_system_prompt). Voice adaptation is applied
        # via the channel flag above.
        system_prompt = _build_turn_system_prompt(head, db, channel)
        context = await ChatService.get_system_context(db)
        full_prompt = f"{system_prompt}\n\nCurrent System State:\n{context}"

        # ── Governance & Delegation Protocol (Issue 8.1) ─────────────────────
        # Prompt-only guardrail: the Head delegates execution to Lead/Task agents
        # and must never call execution tools inline during a chat turn.
        full_prompt += (
            "\n\nGOVERNANCE & DELEGATION PROTOCOL — you are the Head of Council. "
            "Your role is control and delegation only; you are NOT an execution worker. "
            "For ANY work that requires execution (shell commands, file read/write, "
            "browsing, git) emit a create_task / dispatch_task / delegate / spawn_agent "
            "decision so Lead/Task agents perform it in the background. "
            "You MUST NOT call execution tools (execute_command, read_file, write_file, "
            "browser, git) directly during this chat turn. "
            "Governance tools (create_task, cast_vote, propose_amendment, spawn_agent) "
            "are allowed."
        )

        from backend.services.prompt_template_manager import prompt_template_manager
        full_prompt += prompt_template_manager.DEEP_THINK_HINT

        # FIX: Enrich message with extracted file content before streaming.
        # This is the missing step that caused the AI to ignore all attachments.
        enriched_message = _build_enriched_message(chat_msg.message, attachments)

        full_response: list[str] = []
        async for chunk in provider.stream_generate(full_prompt, enriched_message):
            full_response.append(chunk)
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        full_text = "".join(full_response)
        # Use original message (without file content) for task analysis
        # to avoid false-positive task creation from extracted PDF keywords.
        task_info = await ChatService.analyze_for_task(head, chat_msg.message, full_text, db)

        # ── 2–3 line response policy enforcement ─────────────────────────────
        if not task_info.get("created", False):
            original_length = len(full_text)
            non_empty_lines = [ln for ln in full_text.split("\n") if ln.strip()]
            if len(non_empty_lines) > 3:
                full_text = "\n".join(non_empty_lines[:3])
                logger.debug(
                    f"[chat.py] Response truncated for 2-3 line policy: "
                    f"{original_length} chars → {len(full_text)} chars"
                )
        # ── end enforcement ───────────────────────────────────────────────────

        message_id = str(uuid.uuid4())

        yield f"data: {json.dumps({'type': 'complete', 'content': '', 'message_id': message_id, 'metadata': {'agent_id': agent_id, 'model': model_name, 'task_created': task_info['created'], 'task_id': task_info.get('task_id'), 'card': None}})}\n\n"

        await ChatService.log_interaction(agent_id, chat_msg.message, full_text, config_id, db)

        sovereign_user = db.query(User).filter_by(is_admin=True, is_active=True).first()

        # ── Persist both turns to ChatMessage ────────────────────────────────
        if sovereign_user:
            try:
                from backend.models.entities.chat_message import ChatMessage as ChatMsg
                user_str_id = str(sovereign_user.id)

                # Store original message text + attachment metadata (not extracted content)
                # The frontend uses attachment metadata (url, name, type) to render previews.
                # We strip extracted_text from stored attachments to keep the DB lean.
                stored_attachments = None
                if attachments:
                    stored_attachments = [
                        {k: v for k, v in att.items() if k != "extracted_text"}
                        for att in attachments
                    ]

                db.add(ChatMsg(
                    id=str(uuid.uuid4()),
                    user_id=user_str_id,
                    role="sovereign",
                    content=chat_msg.message,
                    attachments=stored_attachments,
                    message_metadata={"source": "chat"},
                ))
                db.add(ChatMsg(
                    id=message_id,
                    user_id=user_str_id,
                    role="head_of_council",
                    content=full_text,
                    message_metadata={
                        "agent_id": agent_id,
                        "model": model_name,
                        "task_created": task_info.get("created", False),
                        "task_id": task_info.get("task_id"),
                    },
                ))
                db.commit()
            except Exception as _persist_err:
                logger.error(f"[chat.py] ChatMessage persist failed (non-fatal): {_persist_err}")
                try:
                    db.rollback()
                except Exception:
                    pass
        # ─────────────────────────────────────────────────────────────────────

        if sovereign_user:
            broadcast_payload = {
                "user_id": sovereign_user.id,
                "content": full_text,
            }

    except Exception as exc:
        logger.error(f"[chat.py] Streaming error: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'An unexpected error occurred during processing.'})}\n\n"

    finally:
        db.close()
        if not _done_sent:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # Broadcast AFTER db is fully closed — uses its OWN session internally
    if broadcast_payload:
        try:
            import asyncio
            from backend.services.channel_manager import ChannelManager

            async def _do_broadcast():
                broadcast_db: Session = SessionLocal()
                try:
                    await ChannelManager.broadcast_to_channels(
                        user_id=broadcast_payload["user_id"],
                        content=broadcast_payload["content"],
                        db=broadcast_db,
                    )
                finally:
                    broadcast_db.close()

            asyncio.create_task(_do_broadcast())
        except Exception as exc:
            logger.error(f"[chat.py] Broadcast task error: {exc}")


# ═══════════════════════════════════════════════════════════
# History
# ═══════════════════════════════════════════════════════════

@router.get(
    "/history",
    summary="Get chat history",
    description="Get chat history for the current user. Returns messages from the ChatMessage table ordered chronologically.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_chat_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Get chat history for the current user.

    Returns messages from the ChatMessage table ordered chronologically.
    Attachment metadata (without extracted_text) is included so the frontend
    can render file previews in history view.
    """
    try:
        from backend.models.entities.chat_message import ChatMessage as ChatMsg
    except ImportError as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("Failed to import ChatMessage model: %s", exc)
        raise InternalServerError(error="Chat history unavailable — model import error", code="CHAT_HISTORY_UNAVAILABLE_MODEL_IMPORT")

    try:
        messages = (
            db.query(ChatMsg)
            .filter(
                ChatMsg.user_id == str(current_user.get("user_id", "")),
                ChatMsg.is_deleted != True,   # noqa: E712
            )
            .order_by(desc(ChatMsg.created_at))
            .limit(limit)
            .all()
        )
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("get_chat_history query failed for user %s: %s", current_user.get("user_id"), exc)
        raise InternalServerError(error="Failed to retrieve chat history", code="FAILED_TO_RETRIEVE_CHAT_HISTORY")

    # Return in chronological order
    messages = list(reversed(messages))

    return {
        "messages": [
            {
                "id":          msg.id,
                "role":        msg.role,
                "content":     msg.content,
                "created_at":  msg.created_at.isoformat(),
                "metadata":    msg.message_metadata or {},
                "attachments": msg.attachments or [],
            }
            for msg in messages
        ],
        "total":    len(messages),
        "has_more": len(messages) == limit,
    }