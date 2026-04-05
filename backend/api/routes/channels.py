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
  GET    /channels/{id}/logs             — paginated log with status/sender/date filters [15.3]
  PATCH  /channels/{id}/settings         — update per-channel settings [15.3]
  POST   /channels/{id}/send             — send test message
  GET    /channels/{id}/health           — get health metrics (now includes error_count_24h) [15.3]
  POST   /channels/{id}/reset            — reset circuit breaker
"""

import secrets
import os
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, subqueryload  # FIX: added subqueryload

from backend.models.database import get_db
from backend.models.entities.channels import ExternalChannel, ExternalMessage, ChannelType, ChannelStatus
from backend.services.channel_manager import (
    ChannelManager, WhatsAppAdapter, SlackAdapter, TelegramAdapter,
    DiscordAdapter, SignalAdapter, GoogleChatAdapter, TeamsAdapter,
    ZaloAdapter, MatrixAdapter, iMessageAdapter, EmailAdapter,
    circuit_breaker, rate_limiter, PLATFORM_RATE_LIMITS, imap_receiver,
    RichMediaContent, CircuitState, RateLimitConfig  # FIXED: Added missing imports
)
from backend.services.channels.whatsapp_unified import UnifiedWhatsAppAdapter, WhatsAppProvider
from backend.core.auth import get_current_active_user
from backend.core.config import settings
from backend.models.entities.channels import ChannelMetrics, CircuitBreakerState

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


# ─── Phase 15.3: per-channel settings schema ─────────────────────────────────

class ChannelSettingsRequest(BaseModel):
    """
    Update per-channel operational settings without touching credentials.
    All fields are optional — only provided fields are applied.
    """
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=10_000)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=200_000)
    auto_create_tasks: Optional[bool] = None
    require_approval: Optional[bool] = None
    default_agent_id: Optional[str] = None
    content_filters: Optional[List[str]] = Field(
        None,
        description="List of blocked keyword substrings; messages matching any are dropped"
    )


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
def list_channels(
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

    # Fix #7: single GROUP BY instead of one COUNT query per status (was N+1)
    status_counts = (
        db.query(ExternalChannel.status, func.count(ExternalChannel.id))
        .group_by(ExternalChannel.status)
        .all()
    )
    by_status = {s.value: 0 for s in ChannelStatus}
    for status_val, count in status_counts:
        by_status[status_val.value] = count

    return {
        "channels": [c.to_dict() for c in channels],
        "total": len(channels),
        "by_status": by_status,
    }


@router.post("/channels/", status_code=status.HTTP_201_CREATED)
def create_channel(
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

    # ── Resolve env:// sentinels for web_bridge ──────────────────────────────
    if config.get('provider') == 'web_bridge':
        if config.get('bridge_url', '').startswith('env://'):
            config['bridge_url'] = os.environ.get('WHATSAPP_BRIDGE_URL', 'ws://whatsapp-bridge:3001')
        if config.get('bridge_token', '').startswith('env://'):
            config['bridge_token'] = os.environ.get('WHATSAPP_BRIDGE_TOKEN', '')

    # Generate agentium_id for the channel (e.g. CH0001, CH0002, ...)
    channel_count = db.query(ExternalChannel).count()
    agentium_id = f"CH{channel_count + 1:04d}"

    # Create channel
    channel = ExternalChannel(
        agentium_id=agentium_id,
        name=request.name,
        channel_type=ctype,
        status=ChannelStatus.PENDING,
        config=config,
        default_agent_id=request.default_agent_id,
        auto_create_tasks=request.auto_create_tasks,
        require_approval=request.require_approval,
        webhook_path=webhook_path,
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
            "cloud_api": {
                "step_1": "Go to Meta for Developers → Your App → WhatsApp → Configuration",
                "step_2": f"Set webhook URL to: {webhook_url}",
                "step_3": "Set verify token to the value you provided in config",
                "step_4": "Subscribe to 'messages' webhook fields",
                "docs": "https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks",
            },
            "web_bridge": {
                "step_1": "Deploy the Node.js Baileys bridge service",
                "step_2": "Set bridge_url and bridge_token in channel config",
                "step_3": f"Point the bridge's outbound webhook to: {webhook_url}",
                "step_4": "Call GET /channels/{id}/qr to scan the QR code with WhatsApp",
                "docs": "https://github.com/WhiskeySockets/Baileys",
            },
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


@router.get("/channels/metrics")
def get_all_channels_metrics(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get metrics for all channels (for dashboard widget)."""
    channels = db.query(ExternalChannel).all()
    
    new_metrics_objs: list = []
    for channel in channels:
        metrics = db.query(ChannelMetrics).filter_by(channel_id=channel.id).first()
        if not metrics:
            metrics = ChannelMetrics(channel_id=channel.id)
            db.add(metrics)
            new_metrics_objs.append(metrics)

    if new_metrics_objs:
        db.flush()
        db.commit()

    results = []
    for channel in channels:
        metrics = db.query(ChannelMetrics).filter_by(channel_id=channel.id).first()
        results.append({
            "channel_id": channel.id,
            "channel_name": channel.name,
            "channel_type": channel.channel_type.value,
            "status": channel.status.value,
            "metrics": metrics.to_dict(),
            "health_status": _calculate_health_status(metrics)
        })
    
    return {
        "channels": results,
        "summary": {
            "total": len(results),
            "healthy": sum(1 for r in results if r["health_status"] == "healthy"),
            "warning": sum(1 for r in results if r["health_status"] == "warning"),
            "critical": sum(1 for r in results if r["health_status"] == "critical"),
            "circuit_open": sum(1 for r in results if r["metrics"]["circuit_breaker_state"] == "open")
        }
    }

@router.get("/channels/{channel_id}")
def get_channel(
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
def update_channel(
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
        merged = dict(channel.config or {})
        merged.update(request.config)
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
def delete_channel(
    channel_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently remove a channel and cleanup resources."""
    channel = _get_channel_or_404(channel_id, db)
    
    background_tasks.add_task(ChannelManager.shutdown_channel, channel_id, db)
    
    db.query(ExternalMessage).filter_by(channel_id=channel_id).delete()
    db.delete(channel)
    db.commit()


@router.get("/channels/{channel_id}/messages")
def list_channel_messages(
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
    channel = await run_in_threadpool(_get_channel_or_404, channel_id, db)
    cfg = channel.config or {}
    success = False
    error_msg = None
    test_details = {}

    try:
        ct = channel.channel_type

        if ct == ChannelType.WHATSAPP:
            provider = cfg.get("provider", "cloud_api")
            test_details["provider"] = provider

            if provider == "web_bridge":
                adapter = UnifiedWhatsAppAdapter(channel)
                status = await adapter.get_status()
                success = status.get("connected", False)

                if not success:
                    error_msg = (
                        "Bridge not connected. "
                        "Ensure the Node.js Baileys bridge is running and the "
                        "bridge_url / bridge_token are correct."
                    )
                else:
                    test_details["authenticated"] = status.get("authenticated", False)
                    test_details["bridge_url"] = cfg.get("bridge_url")
                    test_details["qr_available"] = status.get("qr_code") is not None
            else:
                import httpx
                access_token = cfg.get("access_token")
                phone_number_id = cfg.get("phone_number_id")

                if not access_token or not phone_number_id:
                    raise ValueError(
                        "Missing access_token or phone_number_id for Cloud API provider"
                    )

                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        f"https://graph.facebook.com/v18.0/{phone_number_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                data = r.json()
                success = "id" in data
                if success:
                    test_details["phone_number"] = data.get("display_phone_number")
                    test_details["verified"] = data.get("is_valid_number")
                else:
                    error_msg = data.get("error", {}).get(
                        "message", "Cloud API validation failed"
                    )

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
            if cfg.get('webhook_url'):
                import httpx
                async with httpx.AsyncClient() as client:
                    r = await client.post(
                        cfg['webhook_url'],
                        json={"text": "Test connection from Agentium"}
                    )
                success = r.status_code == 200
            elif cfg.get('client_id') and cfg.get('client_secret'):
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
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(SignalAdapter._rpc_url(cfg))
                    success = r.status_code in (200, 405)
            except:
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
            success = iMessageAdapter.is_available()
            if not success:
                error_msg = "iMessage not available (requires macOS + Messages.app)"
            else:
                test_details['backend'] = cfg.get('backend', 'applescript')

        elif ct == ChannelType.EMAIL:
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
            
            if cfg.get('imap_host') or cfg.get('enable_imap'):
                imap_ok = await EmailAdapter.verify_imap(cfg)
                test_details['imap'] = 'connected' if imap_ok else 'failed'

        else:
            success = True  # CUSTOM — assume OK

    except Exception as e:
        error_msg = str(e)
        success = False

    def _update_status():
        old_stat = channel.status
        channel.status = ChannelStatus.ACTIVE if success else ChannelStatus.ERROR
        channel.error_message = error_msg
        channel.last_tested_at = datetime.utcnow()
        db.commit()
        return old_stat
    
    old_status = await run_in_threadpool(_update_status)

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
    channel = await run_in_threadpool(_get_channel_or_404, channel_id, db)
    
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
            def _commit_msg():
                channel.messages_sent += 1
                db.commit()
            await run_in_threadpool(_commit_msg)
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

    - For ``web_bridge`` provider: delegates to :class:`UnifiedWhatsAppAdapter`
      which holds live bridge state (QR string, expiry, auth status).
    - For ``cloud_api`` provider: returns status='active' once connected; QR is
      not applicable.
    - Returns ``status='active'`` immediately if the channel is already active.
    """
    channel = await run_in_threadpool(_get_channel_or_404, channel_id, db)

    if channel.channel_type != ChannelType.WHATSAPP:
        raise HTTPException(status_code=400, detail="QR polling only applies to WhatsApp channels")

    if channel.status == ChannelStatus.ACTIVE:
        return {"status": "active", "qr_code": None, "connected": True}

    provider = (channel.config or {}).get("provider", "cloud_api")

    if provider != "web_bridge":
        return {
            "status": channel.status.value,
            "provider": "cloud_api",
            "qr_code": None,
            "connected": channel.status == ChannelStatus.ACTIVE,
            "message": "QR codes are only used for the web_bridge provider.",
        }

    adapter = UnifiedWhatsAppAdapter(channel)
    bridge_status = await adapter.get_status()

    return {
        "status": channel.status.value,
        "provider": "web_bridge",
        "qr_code": bridge_status.get("qr_code"),
        "qr_expires_at": bridge_status.get("qr_expires_at"),
        "connected": bridge_status.get("connected", False),
        "authenticated": bridge_status.get("authenticated", False),
    }


# ═══════════════════════════════════════════════════════════
# WHATSAPP PROVIDER-SPECIFIC ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/channels/{channel_id}/whatsapp/status")
async def get_whatsapp_detailed_status(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed WhatsApp connection status including provider-specific fields.
    Works for both ``cloud_api`` and ``web_bridge`` providers.
    """
    channel = await run_in_threadpool(_get_channel_or_404, channel_id, db)

    if channel.channel_type != ChannelType.WHATSAPP:
        raise HTTPException(status_code=400, detail="Not a WhatsApp channel")

    adapter = UnifiedWhatsAppAdapter(channel)
    provider_status = await adapter.get_status()

    return {
        "channel_id": channel_id,
        "name": channel.name,
        "provider": channel.config.get("provider", "cloud_api"),
        "channel_status": channel.status.value,
        "connection": provider_status,
        "config_present": {
            "cloud_api": {
                "phone_number_id": bool(channel.config.get("phone_number_id")),
                "access_token": bool(channel.config.get("access_token")),
                "app_secret": bool(channel.config.get("app_secret")),
            },
            "web_bridge": {
                "bridge_url": bool(channel.config.get("bridge_url")),
                "bridge_token": bool(channel.config.get("bridge_token")),
            },
        },
    }


@router.post("/channels/{channel_id}/whatsapp/switch-provider")
async def switch_whatsapp_provider(
    channel_id: str,
    new_provider: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Switch a WhatsApp channel between ``cloud_api`` and ``web_bridge`` providers.
    """
    channel = await run_in_threadpool(_get_channel_or_404, channel_id, db)

    if channel.channel_type != ChannelType.WHATSAPP:
        raise HTTPException(status_code=400, detail="Not a WhatsApp channel")

    if new_provider not in ("cloud_api", "web_bridge"):
        raise HTTPException(
            status_code=400,
            detail="provider must be 'cloud_api' or 'web_bridge'",
        )

    old_provider = (channel.config or {}).get("provider", "cloud_api")

    if old_provider == new_provider:
        return {
            "success": False,
            "message": f"Already using {new_provider}",
            "provider": new_provider,
        }

    try:
        old_adapter = UnifiedWhatsAppAdapter(channel)
        await old_adapter.shutdown()
    except Exception:
        pass

    def _update_channel():
        merged_config = dict(channel.config or {})
        merged_config["provider"] = new_provider
        channel.config = merged_config
        channel.status = ChannelStatus.PENDING
        channel.error_message = None
        db.commit()
    await run_in_threadpool(_update_channel)

    new_adapter = UnifiedWhatsAppAdapter(channel)
    await new_adapter.initialize()

    return {
        "success": True,
        "message": f"Switched from {old_provider} to {new_provider}",
        "channel_id": channel_id,
        "provider": new_provider,
        "setup_required": new_provider == "cloud_api",
        "qr_required": new_provider == "web_bridge",
    }


# ═══════════════════════════════════════════════════════════
# HEALTH & METRICS
# ═══════════════════════════════════════════════════════════

@router.get("/channels/{channel_id}/health")
def get_channel_health(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive health metrics for a channel.

    Phase 15.3 additions:
    - statistics.error_count_24h  — errors in the last 24 hours
    - rate_limits.utilization_pct — current usage as % of hourly platform limit
    """
    channel = _get_channel_or_404(channel_id, db)
    
    health = ChannelManager.get_channel_health(channel_id)
    
    message_stats = db.query(ExternalMessage).filter_by(channel_id=channel_id)

    # ── Phase 15.3: 24-hour error window ──────────────────────────────────────
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    error_count_24h = (
        message_stats
        .filter(ExternalMessage.created_at >= cutoff_24h)
        .filter(ExternalMessage.error_count > 0)
        .count()
    )

    # ── Rate limit utilization ────────────────────────────────────────────────
    rate_status = rate_limiter.get_status(channel_id)
    platform_limits = PLATFORM_RATE_LIMITS.get(channel.channel_type, RateLimitConfig())
    hourly_limit = platform_limits.requests_per_hour or 1
    hourly_used = rate_status.get("requests_this_hour", 0) if isinstance(rate_status, dict) else 0
    utilization_pct = round(min(hourly_used / hourly_limit * 100, 100), 1)

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
            "error_count_24h": error_count_24h,
            "last_message_at": channel.last_message_at.isoformat() if channel.last_message_at else None,
            "last_tested_at": channel.last_tested_at.isoformat() if hasattr(channel, 'last_tested_at') and channel.last_tested_at else None,
        },
        "rate_limits": {
            "current_usage": rate_status,
            "utilization_pct": utilization_pct,
            "platform_limits": {
                "requests_per_minute": platform_limits.requests_per_minute,
                "requests_per_hour": platform_limits.requests_per_hour,
            },
        },
    }


# ─── Phase 15.3: per-channel logs endpoint ────────────────────────────────────

@router.get("/channels/{channel_id}/logs")
def get_channel_logs(
    channel_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by message status: received, processing, responded, failed"),
    sender_id: Optional[str] = Query(None, description="Partial match on sender_id or sender_name"),
    date_from: Optional[str] = Query(None, description="ISO datetime lower bound, e.g. 2024-01-01T00:00:00"),
    date_to: Optional[str] = Query(None, description="ISO datetime upper bound"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Paginated ExternalMessage history for a single channel.

    Phase 15.3: Supports filtering by status, sender_id (partial), and date range.
    """
    _get_channel_or_404(channel_id, db)

    query = db.query(ExternalMessage).filter_by(channel_id=channel_id)

    if status:
        query = query.filter(ExternalMessage.status == status)

    if sender_id:
        from sqlalchemy import or_
        term = f"%{sender_id}%"
        query = query.filter(
            or_(
                ExternalMessage.sender_id.ilike(term),
                ExternalMessage.sender_name.ilike(term),
            )
        )

    if date_from:
        try:
            query = query.filter(ExternalMessage.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass

    if date_to:
        try:
            query = query.filter(ExternalMessage.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    total = query.count()
    messages = (
        query.order_by(ExternalMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "messages": [m.to_dict() for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ─── Phase 15.3: per-channel settings PATCH ───────────────────────────────────

@router.patch("/channels/{channel_id}/settings")
def update_channel_settings(
    channel_id: str,
    request: ChannelSettingsRequest,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update per-channel operational settings.

    Phase 15.3: rate limits, auto-create-tasks flag, default agent assignment,
    and content filter keyword list. Credentials and webhook paths are
    intentionally excluded — use PUT /channels/{id} for those.
    """
    channel = _get_channel_or_404(channel_id, db)

    # Routing fields live on the model directly
    if request.auto_create_tasks is not None:
        channel.auto_create_tasks = request.auto_create_tasks
    if request.require_approval is not None:
        channel.require_approval = request.require_approval
    if request.default_agent_id is not None:
        channel.default_agent_id = request.default_agent_id

    # Rate limits and content filters are stored inside config so they survive
    # without a schema migration; existing credential keys are preserved.
    config = dict(channel.config or {})
    if request.rate_limit_per_minute is not None:
        config["rate_limit_per_minute"] = request.rate_limit_per_minute
    if request.rate_limit_per_hour is not None:
        config["rate_limit_per_hour"] = request.rate_limit_per_hour
    if request.content_filters is not None:
        config["content_filters"] = request.content_filters
    channel.config = config

    db.commit()
    db.refresh(channel)
    return channel.to_dict()


@router.post("/channels/{channel_id}/reset")
def reset_channel(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Reset circuit breaker and error state for a channel."""
    channel = _get_channel_or_404(channel_id, db)
    
    circuit_breaker._metrics[channel_id].circuit_state = CircuitState.CLOSED
    circuit_breaker._metrics[channel_id].consecutive_failures = 0
    circuit_breaker._metrics[channel_id].half_open_calls = 0
    
    channel.status = ChannelStatus.PENDING
    channel.error_message = None
    db.commit()
    
    return {
        "success": True,
        "message": "Channel reset successfully. Please test connection.",
        "channel_id": channel_id,
        "new_status": ChannelStatus.PENDING.value
    }

# ═══════════════════════════════════════════════════════════
# METRICS ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/channels/{channel_id}/metrics")
def get_channel_metrics(
    channel_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed health metrics for a specific channel."""
    channel = _get_channel_or_404(channel_id, db)
    
    metrics = db.query(ChannelMetrics).filter_by(channel_id=channel_id).first()
    if not metrics:
        metrics = ChannelMetrics(channel_id=channel_id)
        db.add(metrics)
        db.commit()
        db.refresh(metrics)
    
    return {
        "channel_id": channel_id,
        "channel_name": channel.name,
        "channel_type": channel.channel_type.value,
        "status": channel.status.value,
        "metrics": metrics.to_dict(),
        "health_status": _calculate_health_status(metrics)
    }

def _calculate_health_status(metrics: ChannelMetrics) -> str:
    """Calculate overall health status based on metrics."""
    if metrics.circuit_breaker_state == CircuitBreakerState.OPEN:
        return "critical"
    if metrics.consecutive_failures >= 3:
        return "warning"
    if metrics.success_rate < 90 and metrics.total_requests > 10:
        return "warning"
    if metrics.rate_limit_hits > 5:
        return "warning"
    return "healthy"

# ═══════════════════════════════════════════════════════════
# CROSS-CHANNEL MESSAGE LOG
# ═══════════════════════════════════════════════════════════

@router.get("/channels/messages/log")
def get_message_log(
    # Filters
    channel_id: Optional[str] = Query(None, description="Filter by channel ID"),
    channel_type: Optional[str] = Query(None, description="Filter by channel type (whatsapp, slack, etc.)"),
    agent_id: Optional[str] = Query(None, description="Filter by assigned agent ID"),
    status: Optional[str] = Query(None, description="Filter by status: received, processing, responded, failed"),
    success: Optional[bool] = Query(None, description="True=success only, False=failures only"),
    date_from: Optional[str] = Query(None, description="ISO date string, e.g. 2024-01-01T00:00:00"),
    date_to: Optional[str] = Query(None, description="ISO date string, e.g. 2024-12-31T23:59:59"),
    search: Optional[str] = Query(None, description="Full-text search in message content or sender"),
    # Pagination
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cross-channel message log with rich filtering.
    Returns messages across all channels with audit context.
    """
    from sqlalchemy import or_

    query = db.query(ExternalMessage)

    # Channel filter
    if channel_id:
        query = query.filter(ExternalMessage.channel_id == channel_id)

    # Channel type filter — join to ExternalChannel
    if channel_type:
        try:
            ct = ChannelType(channel_type)
            query = query.join(ExternalChannel, ExternalMessage.channel_id == ExternalChannel.id)
            query = query.filter(ExternalChannel.channel_type == ct)
        except ValueError:
            pass

    # Agent filter
    if agent_id:
        query = query.filter(ExternalMessage.assigned_agent_id == agent_id)

    # Status filter
    if status:
        query = query.filter(ExternalMessage.status == status)

    # Success/failure shorthand
    if success is True:
        query = query.filter(ExternalMessage.status == "responded")
    elif success is False:
        query = query.filter(
            or_(
                ExternalMessage.status == "failed",
                ExternalMessage.error_count > 0
            )
        )

    # Date range
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(ExternalMessage.created_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(ExternalMessage.created_at <= dt_to)
        except ValueError:
            pass

    # Full-text search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                ExternalMessage.content.ilike(search_term),
                ExternalMessage.sender_id.ilike(search_term),
                ExternalMessage.sender_name.ilike(search_term),
            )
        )

    total = query.count()

    # FIX: count failed messages using the already-filtered query rather than
    # a secondary full-table scan of ExternalChannel. filter() returns a new
    # query object without mutating the original, so `query` is still usable
    # for the pagination fetch below.
    failed_total = query.filter(ExternalMessage.status == "failed").count()

    # FIX: use subqueryload to resolve channel metadata in a single extra
    # SQL query (one IN-clause for all distinct channel_ids) instead of the
    # previous Python-level loop that issued up to N individual SELECTs.
    # subqueryload is safe here even when channel_type already added an
    # explicit JOIN, because it runs as a separate query, not a join.
    messages = (
        query
        .options(subqueryload(ExternalMessage.channel))
        .order_by(ExternalMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for msg in messages:
        ch = msg.channel  # populated by subqueryload — no extra DB hit
        msg_dict = msg.to_dict()
        msg_dict["channel_name"] = ch.name if ch else "Unknown"
        msg_dict["channel_type"] = ch.channel_type.value if ch else "unknown"
        result.append(msg_dict)

    return {
        "messages": result,
        "total": total,
        "limit": limit,
        "offset": offset,
        "stats": {
            "total_in_filter": total,
            "has_more": (offset + limit) < total,
            # FIX: exposed so the frontend can show an accurate failed-message
            # count across the full dataset rather than just the current page.
            "failed_total": failed_total,
        }
    }


# ═══════════════════════════════════════════════════════════
# REPLAY FAILED MESSAGE
# ═══════════════════════════════════════════════════════════

@router.post("/channels/messages/{message_id}/replay")
async def replay_message(
    message_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Replay a failed or errored message through the channel pipeline.
    Re-queues it for processing as if it were just received.
    """
    message = db.query(ExternalMessage).filter_by(id=message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

    channel = db.query(ExternalChannel).filter_by(id=message.channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Parent channel not found")

    if channel.status != ChannelStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot replay: channel is {channel.status.value}. Activate the channel first."
        )

    # Reset message error state
    message.status = "received"
    message.error_count = 0
    message.last_error = None
    db.commit()

    # Re-process through ChannelManager
    try:
        await ChannelManager._create_task_for_message(message, channel, db)
        message.status = "processing"
        db.commit()
        return {
            "success": True,
            "message_id": message_id,
            "new_status": "processing",
            "detail": "Message re-queued for processing."
        }
    except Exception as e:
        message.error_count += 1
        message.last_error = str(e)
        message.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


# ═══════════════════════════════════════════════════════════
# BULK REPLAY FAILED MESSAGES
# ═══════════════════════════════════════════════════════════

class BulkReplayRequest(BaseModel):
    channel_id: Optional[str] = None  # If None, replay across all channels
    limit: int = Field(50, ge=1, le=200, description="Max messages to replay")


@router.post("/channels/messages/replay-failed")
async def replay_failed_messages(
    request: BulkReplayRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Replay all failed messages, optionally scoped to a single channel.
    Runs in the background and returns immediately with a count.
    """
    query = db.query(ExternalMessage).filter(
        ExternalMessage.status == "failed"
    )
    if request.channel_id:
        query = query.filter(ExternalMessage.channel_id == request.channel_id)

    failed_messages = query.order_by(ExternalMessage.created_at.desc()).limit(request.limit).all()
    message_ids = [m.id for m in failed_messages]

    async def _replay_batch(ids: list):
        for mid in ids:
            try:
                with get_db_context() as batch_db:
                    msg = batch_db.query(ExternalMessage).filter_by(id=mid).first()
                    if not msg:
                        continue
                    ch = batch_db.query(ExternalChannel).filter_by(id=msg.channel_id).first()
                    if not ch or ch.status != ChannelStatus.ACTIVE:
                        continue
                    msg.status = "received"
                    msg.error_count = 0
                    msg.last_error = None
                    batch_db.commit()
                    await ChannelManager._create_task_for_message(msg, ch, batch_db)
                    msg.status = "processing"
                    batch_db.commit()
            except Exception as e:
                print(f"[ReplayBatch] Failed to replay {mid}: {e}")

    background_tasks.add_task(_replay_batch, message_ids)

    return {
        "success": True,
        "queued": len(message_ids),
        "detail": f"Replaying {len(message_ids)} failed message(s) in background."
    }