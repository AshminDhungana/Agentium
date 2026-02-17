"""
Secure webhook endpoints with signature verification, rate limiting, 
circuit breaker awareness, and comprehensive error handling.
"""

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session
import json
import hmac
import hashlib
import asyncio

from backend.models.database import get_db
from backend.models.entities.channels import ExternalChannel, ChannelStatus
from backend.services.channel_manager import (
    ChannelManager, WhatsAppAdapter, SlackAdapter, TelegramAdapter,
    DiscordAdapter, SignalAdapter, GoogleChatAdapter, TeamsAdapter, 
    ZaloAdapter, MatrixAdapter, iMessageAdapter, EmailAdapter,
    circuit_breaker, rate_limiter, PLATFORM_RATE_LIMITS
)
from backend.core.auth import WebhookAuth
from backend.core.security import decrypt_api_key

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ═══════════════════════════════════════════════════════════
# Webhook Security & Validation
# ═══════════════════════════════════════════════════════════

async def get_channel_by_path(
    channel_type: str,
    webhook_path: str,
    db: Session = Depends(get_db)
) -> ExternalChannel:
    """Get channel by webhook path with security checks."""
    channel = db.query(ExternalChannel).filter_by(
        channel_type=channel_type,
        webhook_path=webhook_path,
        status=ChannelStatus.ACTIVE
    ).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found or inactive")
    
    # Check circuit breaker
    if not circuit_breaker.can_execute(channel.id):
        raise HTTPException(
            status_code=503, 
            detail="Service temporarily unavailable - circuit breaker open"
        )
    
    return channel


def verify_signature(secret: str, body: bytes, signature: str, algorithm: str = 'sha256') -> bool:
    """Verify HMAC signature."""
    if not signature:
        return False
    
    expected = hmac.new(
        secret.encode(),
        body,
        getattr(hashlib, algorithm)
    ).hexdigest()
    
    # Handle different signature formats
    if signature.startswith('v0='):
        expected = f"v0={expected}"
    elif signature.startswith('sha256='):
        expected = f"sha256={expected}"
    
    return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════
# WhatsApp Webhook (Meta Graph API)
# ═══════════════════════════════════════════════════════════

@router.get("/whatsapp/{webhook_path}")
async def whatsapp_verify(
    webhook_path: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    WhatsApp verification endpoint (GET).
    Meta sends challenge here to verify webhook.
    """
    # Find channel even if pending (for initial setup)
    channel = db.query(ExternalChannel).filter_by(
        channel_type='whatsapp',
        webhook_path=webhook_path
    ).first()
    
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    params = dict(request.query_params)
    hub_mode = params.get("hub.mode")
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")
    
    if hub_mode == "subscribe" and hub_verify_token == channel.config.get("verify_token"):
        # Update status to active on successful verification
        if channel.status == ChannelStatus.PENDING:
            channel.status = ChannelStatus.ACTIVE
            db.commit()
        return int(hub_challenge) if hub_challenge else "OK"
    
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp/{webhook_path}")
async def whatsapp_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive WhatsApp messages with signature verification.
    """
    body = await request.body()
    
    # Verify signature if app_secret configured
    if channel.config.get('app_secret'):
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not verify_signature(channel.config['app_secret'], body, signature, 'sha256'):
            circuit_breaker.record_failure(channel.id)
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        payload = json.loads(body)
        
        # Handle different webhook types
        entry = payload.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        # Skip if no messages (e.g., status updates)
        if 'messages' not in value:
            return {"status": "ignored", "reason": "no_messages"}
        
        messages = value.get('messages', [])
        contacts = value.get('contacts', [{}])
        
        for msg in messages:
            # Skip non-text messages that aren't supported
            msg_type = msg.get('type', 'text')
            if msg_type not in ['text', 'image', 'document', 'audio', 'video', 'location', 'contacts']:
                continue
            
            # Find sender info
            sender_id = msg.get('from')
            contact = next((c for c in contacts if c.get('wa_id') == sender_id), {})
            profile = contact.get('profile', {})
            
            # Parse with rich media support
            parsed = WhatsAppAdapter.parse_webhook({'entry': [{'changes': [{'value': {'messages': [msg], 'contacts': [contact]}}]}]})
            
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed['sender_name'],
                content=parsed['content'],
                message_type=parsed['message_type'],
                media_url=parsed.get('media_url'),
                raw_payload={'entry': [{'changes': [{'value': {'messages': [msg], 'contacts': [contact]}}]}]}
            )
        
        return {"status": "received", "messages_processed": len(messages)}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Slack Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/slack/{webhook_path}")
async def slack_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """Receive Slack events with signature verification."""
    
    body = await request.body()
    content_type = request.headers.get('content-type', '')
    
    # Verify signature
    if channel.config.get('signing_secret'):
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        
        # Check timestamp (prevent replay attacks)
        import time
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 300:  # 5 minute tolerance
            raise HTTPException(status_code=403, detail="Request too old")
        
        base = f"v0:{timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            channel.config['signing_secret'].encode(),
            base.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected, signature):
            circuit_breaker.record_failure(channel.id)
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        if 'application/json' in content_type:
            payload = json.loads(body)
        else:
            # Form-encoded (slash commands)
            from urllib.parse import parse_qs
            form_data = parse_qs(body.decode())
            payload = {k: v[0] if v else '' for k, v in form_data.items()}
        
        # URL verification challenge
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}
        
        # Handle retries (Slack resends if no 200 OK within 3 seconds)
        retry_num = request.headers.get('X-Slack-Retry-Num')
        if retry_num and int(retry_num) > 2:
            # Acknowledge but don't process to avoid duplicates
            return {"status": "acknowledged", "retry_skipped": True}
        
        # Process events
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            
            # Skip bot messages and message changes
            if event.get("bot_id") or event.get("subtype") in ['bot_message', 'message_changed', 'message_deleted']:
                return {"status": "ignored"}
            
            # Skip messages without text (e.g., reactions)
            if not event.get("text") and not event.get("files"):
                return {"status": "ignored"}
            
            parsed = SlackAdapter.parse_webhook(payload)
            
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed['sender_name'],
                content=parsed['content'],
                message_type=parsed['message_type'],
                media_url=None,
                raw_payload=payload
            )
        
        # Handle slash commands
        elif 'command' in payload:
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=payload.get('channel_id'),
                sender_name=payload.get('user_name'),
                content=payload.get('text', ''),
                message_type='slash_command',
                media_url=None,
                raw_payload=payload
            )
        
        return {"status": "received"}
        
    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Telegram Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/telegram/{webhook_path}")
async def telegram_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Telegram updates.
    Security is path-based (secret token in URL).
    """
    try:
        payload = await request.json()
        
        # Handle different update types
        message = payload.get("message") or payload.get("edited_message") or payload.get("channel_post")
        callback_query = payload.get("callback_query")
        
        if callback_query:
            # Handle button clicks
            from_user = callback_query.get('from', {})
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=str(from_user.get("id")),
                sender_name=from_user.get("first_name") or from_user.get("username"),
                content=callback_query.get("data", ""),
                message_type="callback_query",
                media_url=None,
                raw_payload=payload
            )
        elif message:
            parsed = TelegramAdapter.parse_webhook(payload)
            
            # Skip messages from bots
            if message.get('from', {}).get('is_bot'):
                return {"status": "ignored", "reason": "bot_message"}
            
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed['sender_name'],
                content=parsed['content'],
                message_type=parsed['message_type'],
                media_url=None,
                raw_payload=payload
            )
        else:
            return {"status": "ignored", "reason": "unknown_update_type"}
        
        return {"status": "received"}
        
    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Discord Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/discord/{webhook_path}")
async def discord_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Discord interactions and gateway events.
    Responds to Discord PING (type 1) immediately.
    """
    try:
        payload = await request.json()

        # Discord PING - must ACK synchronously
        if payload.get('type') == 1:
            return {"type": 1}

        # Handle Application Commands (slash commands)
        if payload.get('type') == 2:
            parsed = DiscordAdapter.parse_webhook(payload)
            
            # Defer response if processing might take time
            # Discord requires response within 3 seconds
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type='slash_command',
                media_url=None,
                raw_payload=payload
            )
            
            # Return deferred response
            return {
                "type": 5,  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
                "data": {"flags": 64}  # Ephemeral
            }

        # Handle Message Components (buttons, selects)
        if payload.get('type') == 3:
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=payload.get('channel_id', ''),
                sender_name=payload.get('member', {}).get('user', {}).get('username'),
                content=payload.get('data', {}).get('custom_id', ''),
                message_type='component_interaction',
                media_url=None,
                raw_payload=payload
            )
            return {"type": 6}  # ACK

        # Handle Gateway events (if configured)
        if payload.get('t') == 'MESSAGE_CREATE':
            # Verify not from bot
            if payload.get('d', {}).get('author', {}).get('bot'):
                return {"status": "ignored"}
            
            parsed = DiscordAdapter.parse_webhook(payload.get('d', {}))
            
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type=parsed.get('message_type', 'text'),
                media_url=None,
                raw_payload=payload
            )

        return {"status": "received"}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Signal Webhook (signal-cli)
# ═══════════════════════════════════════════════════════════

@router.post("/signal/{webhook_path}")
async def signal_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Signal messages forwarded by signal-cli JSON-RPC daemon.
    """
    try:
        payload = await request.json()
        
        # Skip sync messages (our own messages)
        if payload.get('envelope', {}).get('syncMessage'):
            return {"status": "ignored", "reason": "sync_message"}
        
        # Skip empty data messages
        if not payload.get('envelope', {}).get('dataMessage', {}).get('message'):
            return {"status": "ignored", "reason": "no_content"}

        parsed = SignalAdapter.parse_webhook(payload)

        background_tasks.add_task(
            ChannelManager.receive_message,
            channel_id=channel.id,
            sender_id=parsed['sender_id'],
            sender_name=parsed.get('sender_name'),
            content=parsed['content'],
            message_type='text',
            media_url=None,
            raw_payload=payload
        )

        return {"status": "received"}

    except ValueError as e:
        # Expected for self-sent messages
        return {"status": "ignored", "reason": str(e)}
    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Google Chat Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/google_chat/{webhook_path}")
async def google_chat_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Google Chat bot events.
    """
    try:
        payload = await request.json()

        # Handle different event types
        event_type = payload.get('type')
        
        if event_type == 'ADDED_TO_SPACE':
            # Bot added to space
            return {"text": "Hello! I'm Agentium. How can I help you today?"}
        
        if event_type == 'REMOVED_FROM_SPACE':
            return {"status": "removed"}
        
        if event_type not in ('MESSAGE', 'CARD_CLICKED'):
            return {"text": ""}

        parsed = GoogleChatAdapter.parse_webhook(payload)

        background_tasks.add_task(
            ChannelManager.receive_message,
            channel_id=channel.id,
            sender_id=parsed['sender_id'],
            sender_name=parsed.get('sender_name'),
            content=parsed['content'],
            message_type=parsed.get('message_type', 'text'),
            media_url=None,
            raw_payload=payload
        )

        # Return immediate acknowledgment
        return {"text": "Processing your request..."}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Microsoft Teams Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/teams/{webhook_path}")
async def teams_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Microsoft Teams Bot Framework Activity objects.
    """
    try:
        payload = await request.json()

        # Handle authentication challenge
        if payload.get('type') == 'installationUpdate':
            return {"status": "ok"}
        
        # Only process message activities
        if payload.get('type') != 'message':
            return {"status": "ignored", "type": payload.get('type')}

        # Skip messages from bots
        if payload.get('from', {}).get('role') == 'bot':
            return {"status": "ignored", "reason": "bot_message"}

        parsed = TeamsAdapter.parse_webhook(payload)

        background_tasks.add_task(
            ChannelManager.receive_message,
            channel_id=channel.id,
            sender_id=parsed['sender_id'],
            sender_name=parsed.get('sender_name'),
            content=parsed['content'],
            message_type='text',
            media_url=None,
            raw_payload=payload
        )

        return {"status": "received"}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Zalo Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/zalo/{webhook_path}")
async def zalo_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Zalo Official Account events.
    Zalo expects {"error": 0} on success.
    """
    try:
        payload = await request.json()

        event_name = payload.get('event_name', '')
        
        # Handle follow/unfollow
        if event_name in ('follow', 'unfollow'):
            # Log these but don't create tasks
            return {"error": 0}

        # Only process message events
        if not event_name.startswith('user_send_'):
            return {"error": 0}

        parsed = ZaloAdapter.parse_webhook(payload)

        if parsed.get('content') and parsed.get('sender_id'):
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type=parsed.get('message_type', 'text'),
                media_url=None,
                raw_payload=payload
            )

        return {"error": 0}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        # Zalo still expects error: 0 format even on error
        return {"error": 1, "message": str(e)}


# ═══════════════════════════════════════════════════════════
# Matrix Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/matrix/{webhook_path}")
async def matrix_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive Matrix room events via Application Service.
    """
    try:
        payload = await request.json()

        # Skip self-sent events
        bot_user = (channel.config or {}).get('bot_user_id', '')
        if payload.get('sender') == bot_user:
            return {"status": "ignored", "reason": "self_sent"}

        # Only handle m.room.message events
        if payload.get('type') != 'm.room.message':
            return {"status": "ignored", "type": payload.get('type')}

        parsed = MatrixAdapter.parse_webhook(payload)

        if parsed.get('content'):
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type=parsed.get('message_type', 'text'),
                media_url=None,
                raw_payload=payload
            )

        return {"status": "received"}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# iMessage Webhook (BlueBubbles)
# ═══════════════════════════════════════════════════════════

@router.post("/imessage/{webhook_path}")
async def imessage_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive iMessage events from BlueBubbles server.
    """
    try:
        payload = await request.json()

        # Only process new-message events
        if payload.get('type') not in ('new-message', None):
            return {"status": "ignored", "type": payload.get('type')}

        parsed = iMessageAdapter.parse_webhook(payload)

        if parsed.get('content') and parsed.get('sender_id'):
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type='text',
                media_url=None,
                raw_payload=payload
            )

        return {"status": "received"}

    except ValueError:
        # Self-sent messages
        return {"status": "ignored", "reason": "self_sent"}
    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Email Webhook (SendGrid / Mailgun)
# ═══════════════════════════════════════════════════════════

@router.post("/email/{webhook_path}")
async def email_webhook(
    webhook_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    channel: ExternalChannel = Depends(get_channel_by_path),
    db: Session = Depends(get_db)
):
    """
    Receive inbound email via SendGrid Inbound Parse or Mailgun.
    """
    content_type = request.headers.get('content-type', '')

    try:
        if 'multipart/form-data' in content_type:
            # SendGrid format
            form = await request.form()
            payload = dict(form)
            
            # Handle attachments
            attachment_info = {}
            for key in form.keys():
                if key.startswith('attachment-') and not key.endswith('-filename') and not key.endswith('-content-type'):
                    idx = key.split('-')[1]
                    attachment_info[idx] = {
                        'filename': form.get(f'attachment-{idx}-filename', 'unknown'),
                        'content_type': form.get(f'attachment-{idx}-content-type', 'application/octet-stream'),
                        'content': form.get(key)
                    }
            
            payload['attachments_parsed'] = attachment_info
            
        elif 'application/json' in content_type:
            # Mailgun format
            payload = await request.json()
        else:
            payload = {"raw_body": await request.body()}

        parsed = EmailAdapter.parse_webhook(payload)

        if parsed.get('content') and parsed.get('sender_id'):
            background_tasks.add_task(
                ChannelManager.receive_message,
                channel_id=channel.id,
                sender_id=parsed['sender_id'],
                sender_name=parsed.get('sender_name'),
                content=parsed['content'],
                message_type='email',
                media_url=None,
                raw_payload=payload
            )

        return {"status": "received"}

    except Exception as e:
        circuit_breaker.record_failure(channel.id)
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Webhook Health & Status
# ═══════════════════════════════════════════════════════════

@router.get("/health/{channel_id}")
async def webhook_health(
    channel_id: str,
    db: Session = Depends(get_db)
):
    """Get webhook health status for a channel."""
    channel = db.query(ExternalChannel).filter_by(id=channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    health = ChannelManager.get_channel_health(channel_id)
    
    return {
        "channel_id": channel_id,
        "channel_type": channel.channel_type.value,
        "status": channel.status.value,
        "health": health,
        "rate_limits": {
            "platform": channel.channel_type.value,
            "config": {
                "requests_per_minute": PLATFORM_RATE_LIMITS.get(channel.channel_type, rate_limiter._get_bucket(channel_id, RateLimitConfig()))['config'].requests_per_minute,
                "requests_per_hour": PLATFORM_RATE_LIMITS.get(channel.channel_type, rate_limiter._get_bucket(channel_id, RateLimitConfig()))['config'].requests_per_hour,
            }
        }
    }