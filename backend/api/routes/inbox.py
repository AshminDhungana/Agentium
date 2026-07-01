from fastapi import APIRouter, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from pydantic import BaseModel

from backend.models.database import get_db
from backend.models.entities.chat_message import Conversation, ChatMessage
from backend.models.entities.user import User
from backend.models.entities.channels import ExternalChannel
from backend.core.auth import get_current_active_user
from backend.services.channel_manager import ChannelManager

router = APIRouter(prefix="/inbox", tags=["Unified Inbox"])

def _user_id(current_user) -> str:
    """Extract user id whether current_user is an ORM object or a dict."""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id", ""))
    return str(current_user.id)

class ReplyRequest(BaseModel):
    content: str
    message_type: str = "text"
    attachments: Optional[list] = None

@router.get("/conversations")
async def list_unified_conversations(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List conversations for the unified inbox viewing."""
    query = db.query(Conversation).filter(
        Conversation.user_id == _user_id(current_user),
        Conversation.is_deleted == 'N'
    )
    
    # We can add more advanced filters if we track status on the conversation 
    # but for now we'll just return all active ones ordered by latest
    conversations = query.order_by(desc(Conversation.last_message_at)).all()
    
    # Optional filtering by channel could be done by inspecting the latest message
    # if `Conversation` itself doesn't explicitly store `channel`.
    # For now, we return all and frontend can filter or we can implement advanced joins.
    
    return {
        "conversations": [c.to_dict(include_messages=True) for c in conversations],
        "total": len(conversations)
    }

@router.get("/conversations/{conversation_id}")
async def get_unified_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific conversation to view in the inbox."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == _user_id(current_user),
        Conversation.is_deleted == 'N'
    ).first()
    
    if not conversation:
        raise NotFoundError(error="Conversation not found", code="CONVERSATION_NOT_FOUND")
        
    return conversation.to_dict(include_messages=True)

@router.post("/conversations/{conversation_id}/reply")
async def reply_to_conversation(
    conversation_id: str,
    request: ReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Send a reply to an external channel from the unified inbox."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == _user_id(current_user),
        Conversation.is_deleted == 'N'
    ).first()
    
    if not conversation:
        raise NotFoundError(error="Conversation not found", code="CONVERSATION_NOT_FOUND")
        
    # We need to find the external channel ID to send the reply.
    # We can inspect the messages in this conversation to find one that came from an external channel.
    latest_external_msg = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.external_message_id.isnot(None)
    ).order_by(desc(ChatMessage.created_at)).first()
    
    if not latest_external_msg:
        raise BadRequestError(error="This conversation has no external channel messages to reply to.", code="THIS_CONVERSATION_HAS_NO_EXTERNAL")
        
    from backend.models.entities.channels import ExternalMessage
    orig_msg = db.query(ExternalMessage).filter_by(id=latest_external_msg.external_message_id).first()
    
    if not orig_msg:
        raise NotFoundError(error="Original external message not found", code="ORIGINAL_EXTERNAL_MESSAGE_NOT_FOUND")
        
    channel = db.query(ExternalChannel).filter_by(id=orig_msg.channel_id).first()
    if not channel:
        raise NotFoundError(error="External channel not found", code="EXTERNAL_CHANNEL_NOT_FOUND")

    # Use ChannelManager to send the message back to the sender
    success = await ChannelManager.send_response(
        message_id=orig_msg.id,
        response_content=request.content,
        agent_id=_user_id(current_user),
        rich_media=None, # Expand later if attachments are supported from frontend
        db=db
    )
    
    if not success:
        raise InternalServerError(error="Failed to send reply to external channel", code="FAILED_TO_SEND_REPLY_TO")
        
    # If successful, record the reply as a ChatMessage in the conversation
    sys_msg = ChatMessage.create_system_message(
        content=request.content,
        conversation_id=conversation_id,
        error=False
    )
    # Give it an indicator that this was sent by the admin
    sys_msg.role = "system"
    sys_msg.metadata = {"sent_by_admin": True, "channel_routed": channel.channel_type.value}
    
    db.add(sys_msg)
    
    import datetime
    conversation.last_message_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(sys_msg)
    
    # Broadcast to update UI
    try:
        from backend.api.routes.websocket import manager as ws_manager
        import asyncio
        asyncio.create_task(
            ws_manager.broadcast({
                "type": "message_created",
                "message": sys_msg.to_dict()
            })
        )
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
        
    return {"success": True, "message": sys_msg.to_dict()}