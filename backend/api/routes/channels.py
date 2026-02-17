"""
API routes for Channel Management with IMAP support, health monitoring,
and comprehensive CRUD operations.

Endpoints:
  GET    /channels/                      — list all channels
  POST   /channels/                      — create channel
  GET    /channels/{id}                  — get channel detail
  PUT    /channels/{id}                  — update channel config
  DELETE /channels/{id}                  — delete channel
  POST   /channels/{id}/test             — test connection
  GET    /channels/{id}/qr               — poll WhatsApp QR code
  GET    /channels/{id}/messages         — list inbound messages
  POST   /channels/{id}/send             — send test message
  GET    /channels/{id}/health           — get health metrics
  POST   /channels/{id}/reset            — reset circuit breaker
"""

import secrets
from datetime import datetime
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.channels import ExternalChannel, ExternalMessage, ChannelType, ChannelStatus
from backend.services.channel_manager import (
    ChannelManager, WhatsAppAdapter, SlackAdapter, TelegramAdapter,
    DiscordAdapter, SignalAdapter, GoogleChatAdapter, TeamsAdapter,
    ZaloAdapter, MatrixAdapter, iMessageAdapter, EmailAdapter,
    circuit_breaker, rate_limiter, PLATFORM_RATE_LIMITS, imap_receiver,
    RichMediaContent, CircuitState, RateLimitConfig  # FIXED: Added missing imports
)
from backend.core.auth import get_current_active_user
from backend.core.config import settings

router = APIRouter(tags=["Channels"])


# ═══════════════════════════════════════════════════════════
# REQUEST / RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════

class ChannelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Channel type slug, e.g. 'whatsapp'")
    config: Dict[str, Any] = Field(default_factory=dict)
    default_agent_id: Optional[str] = None
    auto_create_tasks: bool = True
    require_approval: bool = False
    enable_imap: bool = False  # For email channels


class ChannelUpdateRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    default_agent_id: Optional[str] = None
    auto_create_tasks: Optional[bool] = None
    require_approval: Optional[bool] = None
    status: Optional[str] = None


class SendTestMessageRequest(BaseModel):
    recipient: str = Field(..., description="Recipient ID (phone, chat_id, email, etc.)")
    content: str = Field(..., min_length=1, max_length=4000)
    use_rich_media: bool = False


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _get_channel_or_404(channel_id: str, db: Session) -> ExternalChannel:
    channel = db.query(ExternalChannel).filter_by(id=channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    return channel


# ═══════════════════════════════════════════════════════════
# CRUD ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/channels/")
async def list_channels(
    status: Optional[str] = None,
    channel_type: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all configured channels with optional filters."""
    query = db.query(ExternalChannel).order_by(ExternalChannel.created_at.desc())
    
    if status:
        try:
            query = query.filter(ExternalChannel.status == ChannelStatus(status))
        except ValueError:
            pass
    
    if channel_type:
        try:
            query = query.filter(ExternalChannel.channel_type == ChannelType(channel_type))
        except ValueError:
            pass
    
    channels = query.all()
    return {
        "channels": [c.to_dict() for c in channels],
        "total": len(channels),
        "by_status": {
            s.value: db.query(ExternalChannel).filter(ExternalChannel.status == s).count()
            for s in ChannelStatus
        }
    }


@router.post("/channels/", status_code=status.HTTP_201_CREATED)
async def create_channel(
    request: ChannelCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create and register a new external channel.
    Generates a unique inbound webhook path automatically.
    """
    try:
        ctype = ChannelType(request.type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type '{request.type}'. Valid: {[t.value for t in ChannelType]}"
        )

    # Generate secure webhook path
    webhook_path = secrets.token_urlsafe(24)
    base_url = getattr(settings, 'BASE_URL', 'https://your-domain.com')
    webhook_url_display = f"{base_url}/webhooks/{ctype.value}/{webhook_path}"

    # Merge config
    config = dict(request.config)
    config['webhook_url_display'] = webhook_url_display

    # Create channel
    channel = ExternalChannel(
        name=request.name,
        channel_type=ctype,
        status=ChannelStatus.PENDING,
        config=config,
        default_agent_id=request.default_agent_id,
        auto_create_tasks=request.auto_create_tasks,
        require_approval=request.require_approval,
        webhook_path=webhook_path,
        created_by=current_user.get('username', 'system')
    )

    db.add(channel)
    db.commit()
    db.refresh(channel)

    # Initialize channel resources (IMAP, circuit breaker, etc.)
    background_tasks.add_task(ChannelManager.initialize_channel, db, channel)

    result = channel.to_dict()
    result['webhook_url'] = webhook_url_display
    result['setup_instructions'] = _get_setup_instructions(ctype, webhook_url_display)
    
    return result


def _get_setup_instructions(channel_type: ChannelType, webhook_url: str) -> Dict[str, str]:
    """Get platform-specific setup instructions."""
    instructions = {
        ChannelType.WHATSAPP: {
            "step_1": "Go to Meta for Developers → Your App → WhatsApp → Configuration",
            "step_2": f"Set webhook URL to: {webhook_url}",
            "step_3": "Set verify token to the value you provided",
            "step_4": "Subscribe to 'messages' webhook fields",
            "docs": "https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks"
        },
        ChannelType.SLACK: {
            "step_1": "Go to Slack API → Your App → Event Subscriptions",
            "step_2": f"Enable events and set Request URL to: {webhook_url}",
            "step_3": "Subscribe to 'message.channels' and 'app_mention' events",
            "step_4": "Add your Signing Secret to config for verification",
            "docs": "https://api.slack.com/events-api"
        },
        ChannelType.TELEGRAM: {
            "step_1": f"Send this to @BotFather or use API:",
            "step_2": f"POST https://api.telegram.org/bot<TOKEN>/setWebhook",
            "step_3": f"URL: {webhook_url}",
            "docs": "https://core.telegram.org/bots/webhooks"
        },
        ChannelType.DISCORD: {
            "step_1": "Go to Discord Developer Portal → Your App → General Information",
            "step_2": f"Set Interactions Endpoint URL to: {webhook_url}",
            "step_3": "Or use Gateway for MESSAGE_CREATE events",
            "docs": "https://discord.com/developers/docs/interactions/receiving-and-responding"
        },
        ChannelType.EMAIL: {
            "step_1": "Configure your email provider (SendGrid/Mailgun) to POST to:",
            "step_2": webhook_url,
            "step_3": "Enable IMAP in config for receiving, SMTP for sending",
            "docs": "https://sendgrid.com/docs/for-developers/parsing-email/setting-up-the-inbound-parse-webhook/"
        }
    }
    return instructions.get(channel_type, {"webhook_url": webhook_url})


@router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed info for a single channel including health metrics."""
    channel = _get_channel_or_404(channel_id, db)
    
    result = channel.to_dict()
    result['health'] = ChannelManager.get_channel_health(channel_id)
    result['rate_limit_status'] = rate_limiter.get_status(channel_id)
    
    return result


@router.put("/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    request: ChannelUpdateRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update channel configuration or routing rules."""
    channel = _get_channel_or_404(channel_id, db)

    if request.name is not None:
        channel.name = request.name
    
    if request.config is not None:
        # Preserve system-generated fields
        merged = dict(channel.config or {})
        merged.update(request.config)
        # Don't overwrite webhook_url_display
        if 'webhook_url_display' in channel.config:
            merged['webhook_url_display'] = channel.config['webhook_url_display']
        channel.config = merged
    
    if request.default_agent_id is not None:
        channel.default_agent_id = request.default_agent_id
    
    if request.auto_create_tasks is not None:
        channel.auto_create_tasks = request.auto_create_tasks
    
    if request.require_approval is not None:
        channel.require_approval = request.require_approval
    
    if request.status is not None:
        try:
            new_status = ChannelStatus(request.status)
            # If resetting from error, also reset circuit breaker
            if channel.status == ChannelStatus.ERROR and new_status == ChannelStatus.ACTIVE:
                circuit_breaker._metrics[channel_id].circuit_state = CircuitState.CLOSED
                circuit_breaker._metrics[channel_id].consecutive_failures = 0
            channel.status = new_status
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

    db.commit()
    db.refresh(channel)
    return channel.to_dict()


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently remove a channel and cleanup resources."""
    channel = _get_channel_or_404(channel_id, db)
    
    # Cleanup resources
    background_tasks.add_task(ChannelManager.shutdown_channel, channel_id)
    
    # Delete messages and channel
    db.query(ExternalMessage).filter_by(channel_id=channel_id).delete()
    db.delete(channel)
    db.commit()


@router.get("/channels/{channel_id}/messages")
async def list_channel_messages(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List recent inbound messages for a channel."""
    _get_channel_or_404(channel_id, db)
    
    query = db.query(ExternalMessage).filter_by(channel_id=channel_id)
    
    if status:
        query = query.filter(ExternalMessage.status == status)
    
    messages = (
        query.order_by(ExternalMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    return {
        "messages": [m.to_dict() for m in messages],
        "total": query.count(),
        "limit": limit,
        "offset": offset
    }


# ═══════════════════════════════════════════════════════════
# TEST CONNECTION
# ═══════════════════════════════════════════════════════════

@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Test that the channel credentials are valid.
    Updates channel status to ACTIVE on success, ERROR on failure.
    """
    channel = _get_channel_or_404(channel_id, db)
    cfg = channel.config or {}
    success = False
    error_msg = None
    test_details = {}

    try:
        ct = channel.channel_type

        if ct == ChannelType.WHATSAPP:
            # Test by getting phone number info
            import httpx
            access_token = cfg.get('access_token')
            phone_number_id = cfg.get('phone_number_id')
            
            if not access_token or not phone_number_id:
                raise ValueError("Missing access_token or phone_number_id")
            
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://graph.facebook.com/v17.0/{phone_number_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
            data = r.json()
            success = 'id' in data
            if success:
                test_details['phone_number'] = data.get('display_phone_number')
                test_details['verified'] = data.get('is_valid_number')

        elif ct == ChannelType.SLACK:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {cfg.get('bot_token', '')}"}
                )
            data = r.json()
            success = data.get('ok', False)
            if success:
                test_details['team'] = data.get('team')
                test_details['bot_user'] = data.get('user')

        elif ct == ChannelType.TELEGRAM:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.telegram.org/bot{cfg.get('bot_token', '')}/getMe"
                )
            data = r.json()
            success = data.get('ok', False)
            if success:
                test_details['bot_name'] = data['result'].get('username')
                test_details['can_join_groups'] = data['result'].get('can_join_groups')

        elif ct == ChannelType.DISCORD:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {cfg.get('bot_token', '')}"}
                )
            success = r.status_code == 200
            if success:
                data = r.json()
                test_details['bot_name'] = data.get('username')
                test_details['verified'] = data.get('verified')

        elif ct == ChannelType.MATRIX:
            import httpx
            homeserver = cfg.get('homeserver_url', 'https://matrix.org').rstrip('/')
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{homeserver}/_matrix/client/v3/account/whoami",
                    headers={"Authorization": f"Bearer {cfg.get('access_token', '')}"}
                )
            success = r.status_code == 200
            if success:
                data = r.json()
                test_details['user_id'] = data.get('user_id')
                test_details['device_id'] = data.get('device_id')

        elif ct == ChannelType.TEAMS:
            # Check if webhook or bot credentials provided
            if cfg.get('webhook_url'):
                # Test webhook with simple request
                import httpx
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        cfg['webhook_url'],
                        json={"text": "Test connection from Agentium"}
                    )
                success = r.status_code == 200
            elif cfg.get('client_id') and cfg.get('client_secret'):
                # Test bot token acquisition
                token = await TeamsAdapter._get_bot_token(cfg)
                success = bool(token)
                test_details['auth_method'] = 'bot_framework'
            else:
                raise ValueError("Missing webhook_url or Bot Framework credentials")

        elif ct == ChannelType.GOOGLE_CHAT:
            if cfg.get('webhook_url'):
                import httpx
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        cfg['webhook_url'],
                        json={"text": "Test connection"}
                    )
                success = r.status_code == 200
            elif cfg.get('service_account_json'):
                token = await GoogleChatAdapter._get_access_token(cfg['service_account_json'])
                success = bool(token)
                test_details['auth_method'] = 'service_account'
            else:
                raise ValueError("Missing webhook_url or service_account_json")

        elif ct == ChannelType.SIGNAL:
            # Check if signal-cli daemon is reachable
            import httpx  # FIXED: Added missing import
            try:
                async with httpx.AsyncClient() as client:  # FIXED: Added async with
                    r = await client.get(SignalAdapter._rpc_url(cfg))
                    success = r.status_code in (200, 405)  # 405 is expected for GET
            except:
                # Try subprocess as fallback
                success = bool(cfg.get('number'))

        elif ct == ChannelType.ZALO:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://openapi.zalo.me/v2.0/oa/getoa",
                    headers={"access_token": cfg.get('access_token', '')}
                )
            data = r.json()
            success = data.get('error') == 0
            if success:
                test_details['oa_name'] = data.get('data', {}).get('name')

        elif ct == ChannelType.IMESSAGE:
            success = iMessageAdapter.is_available()  # This is correct (not async)
            if not success:
                error_msg = "iMessage not available (requires macOS + Messages.app)"
            else:
                test_details['backend'] = cfg.get('backend', 'applescript')

        elif ct == ChannelType.EMAIL:
            # Test SMTP
            import asyncio
            import aiosmtplib
            try:
                smtp = aiosmtplib.SMTP(
                    hostname=cfg.get('smtp_host', ''),
                    port=int(cfg.get('smtp_port', 587))
                )
                await asyncio.wait_for(smtp.connect(), timeout=5)
                await smtp.starttls()
                await smtp.login(cfg.get('smtp_user', ''), cfg.get('smtp_pass', ''))
                await smtp.quit()
                success = True
                test_details['smtp'] = 'connected'
            except Exception as smtp_err:
                error_msg = f"SMTP: {str(smtp_err)}"
                success = False
            
            # Test IMAP if configured
            if cfg.get('imap_host') or cfg.get('enable_imap'):
                imap_ok = await EmailAdapter.verify_imap(cfg)
                test_details['imap'] = 'connected' if imap_ok else 'failed'

        else:
            success = True  # CUSTOM — assume OK

    except Exception as e:
        error_msg = str(e)
        success = False

    # Update channel status
    old_status = channel.status
    channel.status = ChannelStatus.ACTIVE if success else ChannelStatus.ERROR
    channel.error_message = error_msg
    channel.last_tested_at = datetime.utcnow()
    db.commit()

    return {
        "success": success,
        "channel_id": channel_id,
        "channel_type": channel.channel_type.value,
        "status": channel.status.value,
        "previous_status": old_status.value,
        "error": error_msg,
        "details": test_details,
        "tested_at": channel.last_tested_at.isoformat()
    }


# ═══════════════════════════════════════════════════════════
# SEND TEST MESSAGE
# ═══════════════════════════════════════════════════════════

@router.post("/channels/{channel_id}/send")
async def send_test_message(
    channel_id: str,
    request: SendTestMessageRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send a test message through the channel."""
    channel = _get_channel_or_404(channel_id, db)
    
    if channel.status != ChannelStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Channel is not active")
    
    try:
        rich_media = None
        if request.use_rich_media:
            rich_media = RichMediaContent(
                text=request.content,
                blocks=[{'type': 'text', 'content': request.content}],
                metadata={'header': 'Test Message from Agentium'}
            )
        
        success = await ChannelManager.send_response(
            message_id=f"test-{datetime.utcnow().timestamp()}",
            response_content=request.content,
            agent_id=current_user.get('id', 'system'),
            rich_media=rich_media,
            db=db
        )
        
        if success:
            channel.messages_sent += 1
            db.commit()
            return {"success": True, "message": "Test message sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# QR CODE POLLING (WhatsApp)
# ═══════════════════════════════════════════════════════════

@router.get("/channels/{channel_id}/qr")
async def get_channel_qr(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Poll for a WhatsApp QR code while pairing is in progress.
    Returns qr_code string when pending, or status='active' when connected.
    """
    channel = _get_channel_or_404(channel_id, db)

    if channel.channel_type != ChannelType.WHATSAPP:
        raise HTTPException(status_code=400, detail="QR polling only applies to WhatsApp channels")

    if channel.status == ChannelStatus.ACTIVE:
        return {"status": "active", "qr_code": None, "connected": True}

    # Check for QR in config (would be set by external WhatsApp library if using Baileys)
    qr_data = (channel.config or {}).get('qr_code_data')
    
    return {
        "status": channel.status.value,
        "qr_code": qr_data,
        "connected": False,
        "expires_at": (channel.config or {}).get('qr_expires_at')
    }


# ═══════════════════════════════════════════════════════════
# HEALTH & METRICS
# ═══════════════════════════════════════════════════════════

@router.get("/channels/{channel_id}/health")
async def get_channel_health(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive health metrics for a channel."""
    channel = _get_channel_or_404(channel_id, db)
    
    health = ChannelManager.get_channel_health(channel_id)
    
    # Add message statistics
    message_stats = db.query(ExternalMessage).filter_by(channel_id=channel_id)
    
    return {
        "channel_id": channel_id,
        "channel_name": channel.name,
        "channel_type": channel.channel_type.value,
        "status": channel.status.value,
        "health": health,
        "statistics": {
            "total_messages_received": channel.messages_received,
            "total_messages_sent": channel.messages_sent,
            "error_count": message_stats.filter(ExternalMessage.error_count > 0).count(),
            "last_message_at": channel.last_message_at.isoformat() if channel.last_message_at else None,
            "last_tested_at": channel.last_tested_at.isoformat() if hasattr(channel, 'last_tested_at') and channel.last_tested_at else None
        },
        "rate_limits": {
            "current_usage": rate_limiter.get_status(channel_id),
            "platform_limits": {
                "requests_per_minute": PLATFORM_RATE_LIMITS.get(channel.channel_type, RateLimitConfig()).requests_per_minute,
                "requests_per_hour": PLATFORM_RATE_LIMITS.get(channel.channel_type, RateLimitConfig()).requests_per_hour
            }
        }
    }


@router.post("/channels/{channel_id}/reset")
async def reset_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Reset circuit breaker and error state for a channel."""
    channel = _get_channel_or_404(channel_id, db)
    
    # Reset circuit breaker
    circuit_breaker._metrics[channel_id].circuit_state = CircuitState.CLOSED
    circuit_breaker._metrics[channel_id].consecutive_failures = 0
    circuit_breaker._metrics[channel_id].half_open_calls = 0
    
    # Reset channel status
    channel.status = ChannelStatus.PENDING
    channel.error_message = None
    db.commit()
    
    return {
        "success": True,
        "message": "Channel reset successfully. Please test connection.",
        "channel_id": channel_id,
        "new_status": ChannelStatus.PENDING.value
    }

