"""
Chat API for Sovereign to communicate with Head of Council.
Supports streaming responses for real-time communication.
"""
import json
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.models.database import get_db
from backend.models.entities import Agent, HeadOfCouncil, Task
from backend.models.entities.user import User  # Import User model
from backend.services.chat_service import ChatService
from backend.services.model_provider import ModelService
from backend.core.auth import get_current_active_user  # Import this at the top

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatMessage(BaseModel):
    message: str
    stream: bool = True

class ChatResponse(BaseModel):
    response: str
    agent_id: str
    task_created: bool = False
    task_id: str = None


@router.get("/conversations")
async def list_conversations(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all conversations for current user."""
    from backend.models.entities.chat_message import Conversation
    
    query = db.query(Conversation).filter(
        Conversation.user_id == str(current_user.id),
        Conversation.is_deleted == 'N'
    )
    
    if not include_archived:
        query = query.filter(Conversation.is_archived == 'N')
    
    conversations = query.order_by(desc(Conversation.last_message_at)).all()
    
    return {
        "conversations": [c.to_dict() for c in conversations],
        "total": len(conversations)
    }


@router.post("/conversations")
async def create_conversation(
    title: Optional[str] = None,
    context: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new conversation."""
    from backend.models.entities.chat_message import Conversation
    
    conversation = Conversation(
        user_id=str(current_user.id),
        title=title or "New Conversation",
        context=context
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
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific conversation with messages."""
    from backend.models.entities.chat_message import Conversation
    
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.id),
        Conversation.is_deleted == 'N'
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation.to_dict(include_messages=include_messages)


@router.post("/conversations/{conversation_id}/archive")
async def archive_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Archive a conversation."""
    from backend.models.entities.chat_message import Conversation
    
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.id)
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conversation.is_archived = 'Y'
    db.commit()
    
    return {"success": True, "message": "Conversation archived"}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Soft delete a conversation."""
    from backend.models.entities.chat_message import Conversation
    
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == str(current_user.id)
            ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conversation.is_deleted = 'Y'
    db.commit()
    
    return {"success": True, "message": "Conversation deleted"}


@router.get("/stats")
async def get_chat_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get chat statistics for current user."""
    from backend.models.entities.chat_message import ChatMessage, Conversation
    
    total_conversations = db.query(Conversation).filter(
        Conversation.user_id == str(current_user.id),
        Conversation.is_deleted == 'N'
    ).count()
    
    total_messages = db.query(ChatMessage).filter(
        ChatMessage.user_id == str(current_user.id),
        ChatMessage.is_deleted == 'N'
    ).count()
    
    # Messages today
    from datetime import datetime, timedelta
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    messages_today = db.query(ChatMessage).filter(
        ChatMessage.user_id == str(current_user.id),
        ChatMessage.created_at >= today_start,
        ChatMessage.is_deleted == 'N'
    ).count()
    
    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "storage_used_bytes": 0  # Placeholder - would calculate from attachments
    }


@router.post("/send", response_class=StreamingResponse)
async def send_message(
    chat_msg: ChatMessage,
    db: Session = Depends(get_db)
):
    """
    Send message to Head of Council (00001).
    Returns streaming response for real-time updates.
    """
    # Get Head of Council
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    
    if not head:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Head of Council not initialized"
        )
    
    if head.status.value != "active":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Head of Council is {head.status.value}"
        )
    
    # Check if we should stream
    if chat_msg.stream:
        return StreamingResponse(
            _stream_response(head.agentium_id, chat_msg.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Non-streaming response
        response = await ChatService.process_message(head, chat_msg.message, db)
        return ChatResponse(
            response=response["content"],
            agent_id=head.agentium_id,
            task_created=response.get("task_created", False),
            task_id=response.get("task_id")
        )


async def _stream_response(
    agent_id: str, 
    message: str
) -> AsyncGenerator[str, None]:
    """
    Stream response from Head of Council.
    Format: SSE (Server-Sent Events)
    """
    from backend.models.database import SessionLocal
    from sqlalchemy.exc import DetachedInstanceError
    
    # Create a fresh session for the streaming context
    db = SessionLocal()
    try:
        # Re-fetch head with new session
        head = db.query(HeadOfCouncil).filter_by(agentium_id=agent_id).first()
        if not head:
            yield f"data: {json.dumps({'type': 'error', 'content': 'System Error: Head of Council agent not found.'})}\n\n"
            return

        # Send initial "thinking" event
        yield f"data: {json.dumps({'type': 'status', 'content': 'Head of Council is deliberating...'})}\n\n"
        
        # Safe config retrieval with error handling
        try:
            config = head.get_model_config(db)
            if not config:
                raise ValueError("No active model configuration found")
            
            # Eagerly extract ALL scalar values we need before any async work.
            # This prevents DetachedInstanceError: once we await anything the
            # session may expire/close and lazy-attribute access will fail.
            config_id = str(config.id)
            model_name = str(config.default_model)

            # Expunge the ORM object so SQLAlchemy stops tracking it.
            # We have everything we need as plain Python scalars above.
            try:
                db.expunge(config)
            except Exception:
                pass  # Already detached or not in session — safe to ignore

            # Also pre-fetch head's scalar values for the same reason
            head_agentium_id = str(head.agentium_id)

            # Verify provider availability
            provider = await ModelService.get_provider("sovereign", config_id)
            if not provider:
                raise ValueError("Could not initialize AI provider")
                
        except (ValueError, DetachedInstanceError, AttributeError) as e:
            # FRIENDLY ERROR MESSAGE
            error_msg = (
                "System Operational Warning: \n\n"
                "The Head of Council cannot be reached because no AI Model is currently connected. \n\n"
                "Please go to the 'Models' page and connect a provider (e.g., OpenAI, Anthropic, or Local) "
                "to initialize the system."
            )
            yield f"data: {json.dumps({'type': 'content', 'content': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        
        # Build system prompt from ethos
        system_prompt = head.get_system_prompt()
        
        # Add context about available agents
        context = await ChatService.get_system_context(db)
        full_prompt = f"""{system_prompt}

Current System State:
{context}

You are speaking directly to the Sovereign. Address them respectfully and provide clear, actionable responses."""

        # Stream the response
        full_response = []
        
        # Using the provider (which might use async http clients)
        async for chunk in provider.stream_generate(full_prompt, message):
            full_response.append(chunk)
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
        
        # Check if this should create a task
        full_text = "".join(full_response)
        task_info = await ChatService.analyze_for_task(head, message, full_text, db)
        
        # Send completion event with metadata
        yield f"""data: {json.dumps({
            'type': 'complete',
            'content': '',
            'metadata': {
                'agent_id': head_agentium_id,
                'model': model_name,
                'task_created': task_info['created'],
                'task_id': task_info.get('task_id')
            }
        })}\n\n"""
        
        # --- UNIFIED INBOX BROADCAST ---
        # Broadcast streaming response to user's external channels
        from backend.models.entities.user import User
        from backend.services.channel_manager import ChannelManager
        
        # We need the user so we can broadcast to their channels.
        # Find an active admin user (in multi-user this comes from the connection/auth context)
        sovereign_user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        if sovereign_user:
            import asyncio
            asyncio.create_task(
                ChannelManager.broadcast_to_channels(
                    user_id=sovereign_user.id,
                    content=full_text,
                    db=db,
                    is_silent=True
                )
            )
        # -------------------------------
        
        # Log the interaction
        await ChatService.log_interaction(
            head_agentium_id,
            message,
            full_text,
            config_id,
            db
        )
        
    except Exception as e:
        print(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'An unexpected error occurred during processing.'})}\n\n"
    finally:
        db.close()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get chat history with Head of Council."""
    from backend.models.entities.audit import AuditLog
    
    logs = db.query(AuditLog).filter(
        AuditLog.actor_id == "00001",
        AuditLog.action == "chat_response"
    ).order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    return {
        "messages": [
            {
                "id": log.id,
                "role": "head_of_council",
                "content": json.loads(log.after_state).get("response") if log.after_state else "",
                "timestamp": log.created_at.isoformat(),
                "metadata": {
                    "prompt": json.loads(log.before_state).get("prompt") if log.before_state else ""
                }
            }
            for log in reversed(logs)
        ]
    }