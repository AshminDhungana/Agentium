"""
Chat API for Sovereign to communicate with Head of Council.
Supports streaming responses for real-time communication.

"""
import json
import uuid
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.models.database import get_db, SessionLocal
from backend.models.entities import Agent, HeadOfCouncil, Task
from backend.models.entities.user import User
from backend.services.chat_service import ChatService
from backend.services.model_provider import ModelService
from backend.core.auth import get_current_active_user

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    message: str
    stream: bool = True


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    task_created: bool = False
    task_id: str = None


# ═══════════════════════════════════════════════════════════
# Conversation endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/conversations")
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


@router.post("/conversations")
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


@router.get("/conversations/{conversation_id}")
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
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation.to_dict(include_messages=include_messages)


@router.post("/conversations/{conversation_id}/archive")
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
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.is_archived = "Y"
    db.commit()
    return {"success": True, "message": "Conversation archived"}


@router.delete("/conversations/{conversation_id}")
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
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.is_deleted = "Y"
    db.commit()
    return {"success": True, "message": "Conversation deleted"}


@router.get("/stats")
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

@router.post("/send", response_class=StreamingResponse)
async def send_message(
    chat_msg: ChatMessage,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Send message to Head of Council (00001).
    Returns streaming response for real-time updates.
    """
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

    if not head:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Head of Council not initialized",
        )

    if head.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Head of Council is {head.status.value}",
        )

    if chat_msg.stream:
        return StreamingResponse(
            _stream_response(head.agentium_id, chat_msg.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    response = await ChatService.process_message(head, chat_msg.message, db)
    return ChatResponse(
        response=response["content"],
        agent_id=head.agentium_id,
        task_created=response.get("task_created", False),
        task_id=response.get("task_id"),
    )


async def _stream_response(
    agent_id: str,
    message: str,
) -> AsyncGenerator[str, None]:
    """
    Stream response from Head of Council.

    FIX #5: The session is opened here, used for the entire stream, then
    closed.  The ChannelManager broadcast task captures only *primitive*
    data before the session closes — it does NOT receive the db handle.

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

        # FALLBACK: mirror process_message — if Head has no model_config_id
        # (fresh deploy / unassigned agent) fall back to the system default
        # so streaming doesn't silently fail with no provider.
        if not config_id:
            try:
                from backend.models.entities import UserModelConfig
                _default = (
                    db.query(UserModelConfig)
                    .filter(UserModelConfig.is_default == True)
                    .filter(UserModelConfig.status == "active")
                    .first()
                )
                if _default:
                    config_id  = str(_default.id)
                    model_name = _default.default_model
            except Exception as _fb_err:
                print(f"[chat.py] Config fallback failed: {_fb_err}")

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

        system_prompt = head.get_system_prompt()
        context       = await ChatService.get_system_context(db)
        full_prompt   = (
            f"{system_prompt}\n\nCurrent System State:\n{context}\n\n"
            "You are speaking directly to the Sovereign. "
            "Address them respectfully and provide clear, actionable responses."
        )

        # Append the same deep_think hint that build_system_prompt() injects
        # for task agents — keeps streaming and non-streaming paths consistent.
        from backend.services.prompt_template_manager import prompt_template_manager
        full_prompt += prompt_template_manager.DEEP_THINK_HINT

        full_response: list[str] = []
        async for chunk in provider.stream_generate(full_prompt, message):
            full_response.append(chunk)
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        full_text = "".join(full_response)
        task_info = await ChatService.analyze_for_task(head, message, full_text, db)

        # ── 2–3 line response policy enforcement (Gap 3) ─────────────────────
        # Only apply to plain chat turns, not task-confirmation responses.
        if not task_info.get("created", False):
            original_length = len(full_text)
            non_empty_lines = [ln for ln in full_text.split("\n") if ln.strip()]
            if len(non_empty_lines) > 3:
                full_text = "\n".join(non_empty_lines[:3])
                print(
                    f"[chat.py] Response truncated for 2-3 line policy: "
                    f"{original_length} chars → {len(full_text)} chars"
                )
        # ── end enforcement ───────────────────────────────────────────────────

        message_id = str(uuid.uuid4())

        yield f"data: {json.dumps({'type': 'complete', 'content': '', 'message_id': message_id, 'metadata': {'agent_id': agent_id, 'model': model_name, 'task_created': task_info['created'], 'task_id': task_info.get('task_id')}})}\n\n"

        await ChatService.log_interaction(agent_id, message, full_text, config_id, db)

        sovereign_user = db.query(User).filter_by(is_admin=True, is_active=True).first()

        # ── Persist both turns to ChatMessage so history survives navigation ──
        if sovereign_user:
            try:
                from backend.models.entities.chat_message import ChatMessage as ChatMsg
                user_str_id = str(sovereign_user.id)

                db.add(ChatMsg(
                    id=str(uuid.uuid4()),
                    user_id=user_str_id,
                    role="sovereign",
                    content=message,
                    metadata={"source": "chat"},
                ))
                db.add(ChatMsg(
                    id=message_id,
                    user_id=user_str_id,
                    role="head_of_council",
                    content=full_text,
                    metadata={
                        "agent_id": agent_id,
                        "model": model_name,
                        "task_created": task_info.get("created", False),
                        "task_id": task_info.get("task_id"),
                    },
                ))
                db.commit()
            except Exception as _persist_err:
                # Non-fatal — message already delivered to client
                print(f"[chat.py] ChatMessage persist failed (non-fatal): {_persist_err}")
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
        print(f"[chat.py] Streaming error: {exc}")
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
                        is_silent=True,
                    )
                finally:
                    broadcast_db.close()

            asyncio.create_task(_do_broadcast())
        except Exception as exc:
            print(f"[chat.py] Broadcast task error: {exc}")


# ═══════════════════════════════════════════════════════════
# History
# ═══════════════════════════════════════════════════════════

@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Get chat history for the current user.

    FIX #3: Returns messages from the ChatMessage table (both sovereign and
    head_of_council roles) ordered chronologically.  This single source of
    truth prevents the frontend from merging API results with localStorage
    and creating duplicate messages on reload.

    FIX (500): The ChatMessage import is performed at the top of the try
    block so an ImportError produces a clear 500 log rather than an opaque
    SQLAlchemy failure.  The is_deleted filter uses isnot(True) so it
    works correctly whether the column is a Boolean or a "Y"/"N" string.
    """
    try:
        from backend.models.entities.chat_message import ChatMessage as ChatMsg
    except ImportError as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("Failed to import ChatMessage model: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat history unavailable — model import error",
        )

    try:
        # Use isnot(True) / != True so the filter works for both Boolean
        # columns (False) and "Y"/"N" string columns ("N" != True).
        messages = (
            db.query(ChatMsg)
            .filter(
                ChatMsg.user_id == str(current_user.get("user_id", "")),
                ChatMsg.is_deleted != True,   # noqa: E712 — intentional ORM expression
            )
            .order_by(desc(ChatMsg.created_at))
            .limit(limit)
            .all()
        )
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("get_chat_history query failed for user %s: %s", current_user.get("user_id"), exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history",
        )

    # Return in chronological order
    messages = list(reversed(messages))

    return {
        "messages": [
            {
                "id":          msg.id,
                "role":        msg.role,
                "content":     msg.content,
                "created_at":  msg.created_at.isoformat(),
                "metadata":    msg.metadata or {},
                "attachments": msg.attachments or [],
            }
            for msg in messages
        ],
        "total":    len(messages),
        "has_more": len(messages) == limit,
    }