"""
Channel Manager - Routes external messages to appropriate agents.

Adapters implemented:
  - WhatsAppAdapter   (WhatsApp Business API / Graph API)
  - SlackAdapter      (Slack Bot API + signing-secret verification)
  - TelegramAdapter   (Telegram Bot API)
  - EmailAdapter      (SMTP send / IMAP receive)
  - DiscordAdapter    (Discord Bot API)
  - SignalAdapter     (signal-cli JSON-RPC)
  - GoogleChatAdapter (Google Chat REST API / webhook)
  - TeamsAdapter      (Microsoft Bot Framework / Incoming Webhook)
  - ZaloAdapter       (Zalo Official Account API)
  - MatrixAdapter     (Matrix Client-Server API via matrix-nio)
  - iMessageAdapter   (macOS only — AppleScript / BlueBubbles)

Features:
  - Rate limiting per platform
  - Circuit breaker pattern for failure recovery
  - IMAP email receiving with IDLE support
  - Rich media format translation
  - Multi-channel concurrent handling with connection pooling
"""

import hashlib
import hmac
import json
import secrets
import subprocess
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading

from sqlalchemy.orm import Session

from backend.models.database import get_db_context
from backend.models.entities.channels import ExternalChannel, ExternalMessage, ChannelType, ChannelStatus
from backend.services.channels.whatsapp_unified import UnifiedWhatsAppAdapter
from backend.models.entities import Agent, HeadOfCouncil, Task, TaskType, TaskPriority
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.model_provider import ModelService


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rate Limiting & Circuit Breaker Infrastructure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class RateLimitConfig:
    """Platform-specific rate limits."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_allowance: int = 10
    retry_after_seconds: int = 60


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3


@dataclass
class ChannelMetrics:
    """Metrics for channel health monitoring."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_request_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    consecutive_failures: int = 0
    rate_limit_hits: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_opened_at: Optional[datetime] = None
    half_open_calls: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


# Platform-specific rate limits
PLATFORM_RATE_LIMITS: Dict[ChannelType, RateLimitConfig] = {
    ChannelType.WHATSAPP: RateLimitConfig(requests_per_minute=80, requests_per_hour=5000),
    ChannelType.SLACK: RateLimitConfig(requests_per_minute=100, requests_per_hour=10000),
    ChannelType.TELEGRAM: RateLimitConfig(requests_per_minute=30, requests_per_hour=1000),
    ChannelType.DISCORD: RateLimitConfig(requests_per_minute=50, requests_per_hour=5000),
    ChannelType.EMAIL: RateLimitConfig(requests_per_minute=20, requests_per_hour=500),
    ChannelType.SIGNAL: RateLimitConfig(requests_per_minute=10, requests_per_hour=300),
    ChannelType.GOOGLE_CHAT: RateLimitConfig(requests_per_minute=60, requests_per_hour=3000),
    ChannelType.TEAMS: RateLimitConfig(requests_per_minute=40, requests_per_hour=2000),
    ChannelType.ZALO: RateLimitConfig(requests_per_minute=30, requests_per_hour=1500),
    ChannelType.MATRIX: RateLimitConfig(requests_per_minute=60, requests_per_hour=6000),
    ChannelType.IMESSAGE: RateLimitConfig(requests_per_minute=15, requests_per_hour=200),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Global Rate Limiter & Circuit Breaker Manager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RateLimiter:
    """Token bucket rate limiter per channel."""
    
    def __init__(self):
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def _get_bucket(self, channel_id: str, config: RateLimitConfig) -> Dict[str, Any]:
        """Get or create token bucket for channel."""
        with self._lock:
            if channel_id not in self._buckets:
                now = time.time()
                self._buckets[channel_id] = {
                    'tokens': config.burst_allowance,
                    'last_update': now,
                    'config': config,
                    'minute_window': [],
                    'hour_window': [],
                }
            return self._buckets[channel_id]
    
    def acquire(self, channel_id: str, config: RateLimitConfig) -> tuple[bool, Optional[int]]:
        """
        Attempt to acquire rate limit token.
        Returns (success, retry_after_seconds).
        """
        bucket = self._get_bucket(channel_id, config)
        now = time.time()
        
        with self._lock:
            # Clean old window entries
            bucket['minute_window'] = [t for t in bucket['minute_window'] if now - t < 60]
            bucket['hour_window'] = [t for t in bucket['hour_window'] if now - t < 3600]
            
            # Check limits
            if len(bucket['minute_window']) >= config.requests_per_minute:
                retry_after = 60 - int(now - bucket['minute_window'][0])
                return False, max(retry_after, 1)
            
            if len(bucket['hour_window']) >= config.requests_per_hour:
                retry_after = 3600 - int(now - bucket['hour_window'][0])
                return False, max(retry_after, 1)
            
            # Add token to windows
            bucket['minute_window'].append(now)
            bucket['hour_window'].append(now)
            
            return True, None
    
    def get_status(self, channel_id: str) -> Dict[str, Any]:
        """Get current rate limit status."""
        bucket = self._buckets.get(channel_id, {})
        return {
            'minute_usage': len(bucket.get('minute_window', [])),
            'hour_usage': len(bucket.get('hour_window', [])),
            'minute_limit': bucket.get('config', RateLimitConfig()).requests_per_minute,
            'hour_limit': bucket.get('config', RateLimitConfig()).requests_per_hour,
        }


class CircuitBreaker:
    """Circuit breaker for channel failure recovery."""
    
    def __init__(self):
        self._metrics: Dict[str, ChannelMetrics] = defaultdict(ChannelMetrics)
        self._configs: Dict[str, CircuitBreakerConfig] = {}
        self._lock = threading.Lock()
    
    def register_channel(self, channel_id: str, config: CircuitBreakerConfig = None):
        """Register channel with circuit breaker."""
        self._configs[channel_id] = config or CircuitBreakerConfig()
    
    def can_execute(self, channel_id: str) -> bool:
        """Check if request can execute based on circuit state."""
        with self._lock:
            metrics = self._metrics[channel_id]
            config = self._configs.get(channel_id, CircuitBreakerConfig())
            
            if metrics.circuit_state == CircuitState.OPEN:
                # Check if recovery timeout elapsed
                if metrics.circuit_opened_at:
                    elapsed = (datetime.utcnow() - metrics.circuit_opened_at).total_seconds()
                    if elapsed >= config.recovery_timeout:
                        metrics.circuit_state = CircuitState.HALF_OPEN
                        metrics.half_open_calls = 0
                        print(f"[CircuitBreaker] Channel {channel_id} entering HALF_OPEN state")
                        return True
                return False
            
            if metrics.circuit_state == CircuitState.HALF_OPEN:
                if metrics.half_open_calls >= config.half_open_max_calls:
                    return False
                metrics.half_open_calls += 1
                return True
            
            return True
    
    def record_success(self, channel_id: str):
        """Record successful request."""
        with self._lock:
            metrics = self._metrics[channel_id]
            metrics.total_requests += 1
            metrics.successful_requests += 1
            metrics.consecutive_failures = 0
            metrics.last_request_time = datetime.utcnow()
            
            if metrics.circuit_state == CircuitState.HALF_OPEN:
                # Recovery successful, close circuit
                metrics.circuit_state = CircuitState.CLOSED
                metrics.circuit_opened_at = None
                metrics.half_open_calls = 0
                print(f"[CircuitBreaker] Channel {channel_id} circuit CLOSED (recovered)")
    
    def record_failure(self, channel_id: str) -> bool:
        """
        Record failed request.
        Returns True if circuit opened.
        """
        with self._lock:
            metrics = self._metrics[channel_id]
            config = self._configs.get(channel_id, CircuitBreakerConfig())
            
            metrics.total_requests += 1
            metrics.failed_requests += 1
            metrics.consecutive_failures += 1
            metrics.last_failure_time = datetime.utcnow()
            
            # Check if should open circuit
            if metrics.circuit_state == CircuitState.CLOSED:
                if metrics.consecutive_failures >= config.failure_threshold:
                    metrics.circuit_state = CircuitState.OPEN
                    metrics.circuit_opened_at = datetime.utcnow()
                    print(f"[CircuitBreaker] Channel {channel_id} circuit OPENED (too many failures)")
                    return True
            
            elif metrics.circuit_state == CircuitState.HALF_OPEN:
                # Failure in half-open, re-open circuit
                metrics.circuit_state = CircuitState.OPEN
                metrics.circuit_opened_at = datetime.utcnow()
                metrics.half_open_calls = 0
                print(f"[CircuitBreaker] Channel {channel_id} circuit RE-OPENED (recovery failed)")
                return True
            
            return False
    
    def get_metrics(self, channel_id: str) -> Dict[str, Any]:
        """Get circuit breaker metrics."""
        metrics = self._metrics[channel_id]
        return {
            'circuit_state': metrics.circuit_state.value,
            'success_rate': metrics.success_rate,
            'consecutive_failures': metrics.consecutive_failures,
            'total_requests': metrics.total_requests,
            'last_failure': metrics.last_failure_time.isoformat() if metrics.last_failure_time else None,
        }


# Global instances
rate_limiter = RateLimiter()
circuit_breaker = CircuitBreaker()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rich Media Format Translation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RichMediaContent:
    """Universal rich media format for cross-platform translation."""
    text: str = ""
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MediaTranslator:
    """Translate rich media between platform formats."""
    
    @staticmethod
    def to_slack_blocks(media: RichMediaContent) -> List[Dict[str, Any]]:
        """Convert to Slack Block Kit format."""
        blocks = []
        
        # Header if present
        if media.metadata.get('header'):
            blocks.append({
                "type": "header",
                "text": {"type": "plain_text", "text": media.metadata['header']}
            })
        
        # Text sections
        for block in media.blocks:
            if block['type'] == 'text':
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": block['content']}
                })
            elif block['type'] == 'image':
                blocks.append({
                    "type": "image",
                    "image_url": block['url'],
                    "alt_text": block.get('alt', 'image')
                })
            elif block['type'] == 'divider':
                blocks.append({"type": "divider"})
        
        # Actions
        if media.actions:
            elements = []
            for action in media.actions:
                if action['type'] == 'button':
                    elements.append({
                        "type": "button",
                        "text": {"type": "plain_text", "text": action['label']},
                        "value": action['value'],
                        "action_id": action.get('id', f"action_{len(elements)}")
                    })
            if elements:
                blocks.append({"type": "actions", "elements": elements})
        
        return blocks
    
    @staticmethod
    def to_discord_embeds(media: RichMediaContent) -> List[Dict[str, Any]]:
        """Convert to Discord embed format."""
        embeds = []
        
        embed = {
            "title": media.metadata.get('header', ''),
            "description": media.text[:4096],
            "color": media.metadata.get('color', 0x5865F2),
            "fields": [],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        for block in media.blocks:
            if block['type'] == 'text' and len(embed['fields']) < 25:
                embed['fields'].append({
                    "name": block.get('title', '\u200b'),
                    "value": block['content'][:1024],
                    "inline": block.get('inline', False)
                })
            elif block['type'] == 'image' and not embed.get('image'):
                embed['image'] = {"url": block['url']}
        
        embeds.append(embed)
        return embeds
    
    @staticmethod
    def to_telegram_html(media: RichMediaContent) -> str:
        """Convert to Telegram HTML format."""
        parts = []
        
        if media.metadata.get('header'):
            parts.append(f"<b>{media.metadata['header']}</b>\n")
        
        for block in media.blocks:
            if block['type'] == 'text':
                parts.append(f"{block['content']}\n")
            elif block['type'] == 'divider':
                parts.append("─" * 20 + "\n")
        
        if media.actions:
            parts.append("\n<b>Actions:</b>")
            for action in media.actions:
                if action['type'] == 'button':
                    parts.append(f"• {action['label']}")
        
        return "".join(parts)[:4096]
    
    @staticmethod
    def to_teams_adaptive_card(media: RichMediaContent) -> Dict[str, Any]:
        """Convert to Microsoft Teams Adaptive Card."""
        body = []
        
        if media.metadata.get('header'):
            body.append({
                "type": "TextBlock",
                "text": media.metadata['header'],
                "weight": "bolder",
                "size": "large"
            })
        
        for block in media.blocks:
            if block['type'] == 'text':
                body.append({
                    "type": "TextBlock",
                    "text": block['content'],
                    "wrap": True
                })
            elif block['type'] == 'image':
                body.append({
                    "type": "Image",
                    "url": block['url'],
                    "altText": block.get('alt', 'image')
                })
        
        # Actions
        actions = []
        for action in media.actions:
            if action['type'] == 'button':
                actions.append({
                    "type": "Action.Submit",
                    "title": action['label'],
                    "data": {"value": action['value']}
                })
        
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body
        }
        if actions:
            card["actions"] = actions
        
        return card
    
    @staticmethod
    def parse_incoming_media(platform: ChannelType, payload: Dict[str, Any]) -> RichMediaContent:
        """Parse platform-specific payload into universal format."""
        media = RichMediaContent()
        
        if platform == ChannelType.WHATSAPP:
            message = payload.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0]
            msg_type = message.get('type', 'text')
            
            if msg_type == 'text':
                media.text = message.get('text', {}).get('body', '')
            elif msg_type == 'image':
                media.text = message.get('image', {}).get('caption', '[Image]')
                media.attachments.append({
                    'type': 'image',
                    'url': message.get('image', {}).get('link'),
                    'mime_type': message.get('image', {}).get('mime_type', 'image/jpeg')
                })
            elif msg_type == 'document':
                media.text = f"[Document: {message.get('document', {}).get('filename', 'unknown')}]"
                media.attachments.append({
                    'type': 'document',
                    'url': message.get('document', {}).get('link'),
                    'filename': message.get('document', {}).get('filename')
                })
            elif msg_type == 'audio':
                media.text = '[Voice message]'
                media.attachments.append({
                    'type': 'audio',
                    'url': message.get('audio', {}).get('link')
                })
            elif msg_type == 'video':
                media.text = message.get('video', {}).get('caption', '[Video]')
                media.attachments.append({
                    'type': 'video',
                    'url': message.get('video', {}).get('link')
                })
            elif msg_type == 'location':
                loc = message.get('location', {})
                media.text = f"[Location: {loc.get('latitude')}, {loc.get('longitude')}]"
                media.metadata['location'] = loc
        
        elif platform == ChannelType.TELEGRAM:
            message = payload.get('message', {})
            
            if 'photo' in message:
                photos = message['photo']
                largest = photos[-1] if photos else None
                media.text = message.get('caption', '[Photo]')
                if largest:
                    media.attachments.append({
                        'type': 'image',
                        'file_id': largest['file_id'],
                        'width': largest.get('width'),
                        'height': largest.get('height')
                    })
            elif 'document' in message:
                doc = message['document']
                media.text = f"[Document: {doc.get('file_name', 'unknown')}]"
                media.attachments.append({
                    'type': 'document',
                    'file_id': doc['file_id'],
                    'mime_type': doc.get('mime_type'),
                    'file_name': doc.get('file_name')
                })
            elif 'voice' in message:
                media.text = '[Voice message]'
                media.attachments.append({
                    'type': 'audio',
                    'file_id': message['voice']['file_id'],
                    'duration': message['voice'].get('duration')
                })
            elif 'video' in message:
                media.text = message.get('caption', '[Video]')
                media.attachments.append({
                    'type': 'video',
                    'file_id': message['video']['file_id']
                })
            elif 'location' in message:
                loc = message['location']
                media.text = f"[Location: {loc['latitude']}, {loc['longitude']}]"
                media.metadata['location'] = loc
            else:
                media.text = message.get('text', '')
        
        elif platform == ChannelType.DISCORD:
            # Discord already parsed in adapter
            media.text = payload.get('content', '')
            for attachment in payload.get('attachments', []):
                media.attachments.append({
                    'type': attachment.get('content_type', '').split('/')[0] if '/' in attachment.get('content_type', '') else 'file',
                    'url': attachment['url'],
                    'filename': attachment.get('filename'),
                    'size': attachment.get('size')
                })
            for embed in payload.get('embeds', []):
                media.blocks.append({
                    'type': 'embed',
                    'title': embed.get('title'),
                    'description': embed.get('description'),
                    'url': embed.get('url')
                })
        
        elif platform == ChannelType.SLACK:
            event = payload.get('event', {})
            files = event.get('files', [])
            for f in files:
                media.attachments.append({
                    'type': f.get('mimetype', '').split('/')[0] if '/' in f.get('mimetype', '') else 'file',
                    'url': f.get('url_private'),
                    'name': f.get('name'),
                    'size': f.get('size')
                })
            media.text = event.get('text', '')
        
        elif platform == ChannelType.EMAIL:
            # Email parsing
            media.text = payload.get('text', '') or payload.get('body-plain', '')
            html_body = payload.get('html', '') or payload.get('body-html', '')
            if html_body:
                media.metadata['html_content'] = html_body
            
            # Attachments
            attachment_count = payload.get('attachments', 0)
            if attachment_count:
                media.metadata['attachment_count'] = attachment_count
                for i in range(int(attachment_count)):
                    key = f'attachment-{i}'
                    if key in payload:
                        media.attachments.append({
                            'type': 'file',
                            'name': payload.get(f'{key}-filename', 'unknown'),
                            'content': payload[key]
                        })
        
        else:
            # Default text extraction
            media.text = str(payload.get('text', payload.get('message', payload.get('content', ''))))
        
        return media


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Email IMAP Receiver (Background Service)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IMAPEmailReceiver:
    """
    IMAP email receiver with IDLE support for real-time email processing.
    Runs as background asyncio task.
    """
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._connections: Dict[str, Any] = {}
    
    async def start_channel(self, channel_id: str, config: Dict[str, Any]):
        """Start IMAP monitoring for a channel."""
        if channel_id in self._tasks:
            return
        
        task = asyncio.create_task(self._monitor_mailbox(channel_id, config))
        self._tasks[channel_id] = task
        print(f"[IMAP] Started monitoring for channel {channel_id}")
    
    async def stop_channel(self, channel_id: str):
        """Stop IMAP monitoring for a channel."""
        if channel_id in self._tasks:
            self._tasks[channel_id].cancel()
            del self._tasks[channel_id]
            if channel_id in self._connections:
                try:
                    await self._connections[channel_id].logout()
                except:
                    pass
                del self._connections[channel_id]
            print(f"[IMAP] Stopped monitoring for channel {channel_id}")
    
    async def _monitor_mailbox(self, channel_id: str, config: Dict[str, Any]):
        """
        Monitor IMAP mailbox for new messages.
        Uses IDLE when supported, falls back to polling.
        """
        import aioimaplib
        import email
        from email.policy import default
        
        imap_host = config.get('imap_host', config.get('smtp_host', ''))
        imap_port = int(config.get('imap_port', 993))
        username = config.get('smtp_user', config.get('imap_user', ''))
        password = config.get('smtp_pass', config.get('imap_pass', ''))
        folder = config.get('imap_folder', 'INBOX')
        use_ssl = config.get('imap_ssl', True)
        poll_interval = int(config.get('imap_poll_interval', 60))
        
        last_check = datetime.utcnow()
        processed_uids = set()
        
        # Load last 100 UIDs to avoid reprocessing
        try:
            with get_db_context() as db:
                recent_msgs = db.query(ExternalMessage).filter(
                    ExternalMessage.channel_id == channel_id
                ).order_by(ExternalMessage.created_at.desc()).limit(100).all()
                for msg in recent_msgs:
                    if msg.raw_payload and 'uid' in msg.raw_payload:
                        processed_uids.add(msg.raw_payload['uid'])
        except Exception as e:
            print(f"[IMAP] Error loading processed UIDs: {e}")
        
        while True:
            try:
                # Connect to IMAP server
                client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port) if use_ssl else aioimaplib.IMAP4(host=imap_host, port=imap_port)
                self._connections[channel_id] = client
                
                await client.wait_hello_from_server()
                await client.login(username, password)
                await client.select(folder)
                
                print(f"[IMAP] Connected to {imap_host} for channel {channel_id}")
                
                # Check for new messages
                while True:
                    try:
                        # Search for unseen messages
                        search_resp = await client.search('UNSEEN')
                        if search_resp and search_resp[0] == 'OK':
                            message_uids = search_resp[1][0].decode().split() if search_resp[1][0] else []
                            
                            for uid in message_uids:
                                if uid in processed_uids:
                                    continue
                                
                                # Fetch message
                                fetch_resp = await client.fetch(uid, '(RFC822)')
                                if fetch_resp[0] == 'OK':
                                    msg_data = fetch_resp[1][1]
                                    email_msg = email.message_from_bytes(msg_data, policy=default)
                                    
                                    # Parse email
                                    subject = email_msg['subject'] or '(no subject)'
                                    from_addr = email_msg['from'] or ''
                                    to_addr = email_msg['to'] or ''
                                    
                                    # Extract body
                                    text_body = ''
                                    html_body = ''
                                    attachments = []
                                    
                                    if email_msg.is_multipart():
                                        for part in email_msg.walk():
                                            content_type = part.get_content_type()
                                            content_disposition = part.get_content_disposition()
                                            
                                            if content_type == 'text/plain' and not content_disposition:
                                                text_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                            elif content_type == 'text/html' and not content_disposition:
                                                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                            elif content_disposition and 'attachment' in content_disposition:
                                                filename = part.get_filename()
                                                if filename:
                                                    attachments.append({
                                                        'filename': filename,
                                                        'content_type': content_type,
                                                        'size': len(part.get_payload(decode=True) or b'')
                                                    })
                                    else:
                                        content_type = email_msg.get_content_type()
                                        if content_type == 'text/plain':
                                            text_body = email_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        elif content_type == 'text/html':
                                            html_body = email_msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    
                                    # Create payload
                                    payload = {
                                        'from': from_addr,
                                        'to': to_addr,
                                        'subject': subject,
                                        'text': text_body,
                                        'html': html_body,
                                        'attachments': len(attachments),
                                        'uid': uid,
                                        'date': email_msg['date'],
                                        'message_id': email_msg['message-id'],
                                    }
                                    
                                    # Process through channel manager
                                    await ChannelManager.receive_message(
                                        channel_id=channel_id,
                                        sender_id=from_addr,
                                        sender_name=from_addr.split('<')[0].strip() if '<' in from_addr else from_addr,
                                        content=f"Subject: {subject}\n\n{text_body[:2000]}",
                                        message_type='email',
                                        raw_payload=payload
                                    )
                                    
                                    processed_uids.add(uid)
                                    print(f"[IMAP] Processed message {uid} from {from_addr}")
                                    
                                    # Mark as seen
                                    await client.store(uid, '+FLAGS', '\\Seen')
                        
                        # Try IDLE if supported, otherwise sleep
                        try:
                            idle_resp = await client.idle()
                            if idle_resp[0] == 'OK':
                                # Wait for IDLE response with timeout
                                done = asyncio.Event()
                                await asyncio.wait_for(done.wait(), timeout=300)  # 5 min IDLE timeout
                            else:
                                await asyncio.sleep(poll_interval)
                        except (asyncio.TimeoutError, Exception):
                            await asyncio.sleep(poll_interval)
                            
                    except Exception as e:
                        print(f"[IMAP] Error processing messages: {e}")
                        await asyncio.sleep(poll_interval)
                        
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[IMAP] Connection error for channel {channel_id}: {e}")
                await asyncio.sleep(poll_interval)
    
    async def stop_all(self):
        """Stop all IMAP monitoring."""
        for channel_id in list(self._tasks.keys()):
            await self.stop_channel(channel_id)
        self._running = False


# Global IMAP receiver instance
imap_receiver = IMAPEmailReceiver()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Channel Manager (Core Router) - UPDATED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ChannelManager:
    """
    Central router for all external channel communications.
    Features: rate limiting, circuit breaker, rich media translation, IMAP support.
    """

    @staticmethod
    async def initialize_channel(db: Session, channel: ExternalChannel):
        """Initialize channel with rate limiting and circuit breaker.

        Additional provider-specific initialisation:
        - WhatsApp ``web_bridge``: starts the WebSocket bridge connection so the
          QR code is available as soon as the channel is created.
        - Email with IMAP: starts the background IMAP polling / IDLE task.
        """
        circuit_breaker.register_channel(channel.id)

        # WhatsApp — start bridge connection for web_bridge provider
        if channel.channel_type == ChannelType.WHATSAPP:
            provider = (channel.config or {}).get("provider", "cloud_api")
            if provider == "web_bridge":
                try:
                    adapter = UnifiedWhatsAppAdapter(channel)
                    await adapter.initialize()
                    print(f"[ChannelManager] WhatsApp web_bridge initialised for {channel.id}")
                except Exception as exc:
                    print(f"[ChannelManager] WhatsApp web_bridge init failed for {channel.id}: {exc}")

        # Start IMAP for email channels
        if channel.channel_type == ChannelType.EMAIL:
            if channel.config.get('imap_host') or channel.config.get('enable_imap'):
                await imap_receiver.start_channel(channel.id, channel.config)
                print(f"[ChannelManager] Started IMAP receiver for {channel.id}")

    @staticmethod
    async def shutdown_channel(channel_id: str, db: Session = None):
        """Shutdown channel resources.

        Stops the IMAP receiver (email channels) and, for WhatsApp ``web_bridge``
        channels, gracefully closes the WebSocket bridge connection.
        """
        # Stop IMAP if running
        await imap_receiver.stop_channel(channel_id)

        # Teardown WhatsApp bridge if applicable
        if db is not None:
            channel = db.query(ExternalChannel).filter_by(id=channel_id).first()
            if (
                channel is not None
                and channel.channel_type == ChannelType.WHATSAPP
                and (channel.config or {}).get("provider") == "web_bridge"
            ):
                try:
                    adapter = UnifiedWhatsAppAdapter(channel)
                    await adapter.shutdown()
                    print(f"[ChannelManager] WhatsApp web_bridge shut down for {channel_id}")
                except Exception as exc:
                    print(f"[ChannelManager] WhatsApp web_bridge shutdown error for {channel_id}: {exc}")

        print(f"[ChannelManager] Shutdown channel {channel_id}")

    @staticmethod
    async def receive_message(
        channel_id: str,
        sender_id: str,
        sender_name: Optional[str],
        content: str,
        message_type: str = "text",
        media_url: Optional[str] = None,
        raw_payload: Optional[Dict] = None,
        db: Session = None
    ) -> ExternalMessage:
        """
        Process incoming message from any channel with rate limiting and circuit breaker.
        """
        if db is None:
            with get_db_context() as db:
                return await ChannelManager._process_message(
                    channel_id, sender_id, sender_name, content,
                    message_type, media_url, raw_payload, db
                )
        else:
            return await ChannelManager._process_message(
                channel_id, sender_id, sender_name, content,
                message_type, media_url, raw_payload, db
            )

    @staticmethod
    async def _process_message(
        channel_id: str,
        sender_id: str,
        sender_name: Optional[str],
        content: str,
        message_type: str,
        media_url: Optional[str],
        raw_payload: Optional[Dict],
        db: Session
    ) -> ExternalMessage:
        """Internal processing logic with resilience patterns."""

        # Get channel
        channel = db.query(ExternalChannel).filter_by(id=channel_id).first()
        if not channel or channel.status != ChannelStatus.ACTIVE:
            raise ValueError(f"Channel {channel_id} not found or inactive")

        # Circuit breaker check
        if not circuit_breaker.can_execute(channel_id):
            raise Exception(f"Circuit breaker open for channel {channel_id}")

        # Rate limiting check
        rate_config = PLATFORM_RATE_LIMITS.get(channel.channel_type, RateLimitConfig())
        allowed, retry_after = rate_limiter.acquire(channel_id, rate_config)
        
        if not allowed:
            # Record rate limit hit
            metrics = circuit_breaker._metrics[channel_id]
            metrics.rate_limit_hits += 1
            
            AuditLog.log(
                level=AuditLevel.WARNING,
                category=AuditCategory.COMMUNICATION,
                actor_type="system",
                actor_id="RATE_LIMITER",
                action="rate_limit_exceeded",
                target_type="external_channel",
                target_id=channel_id,
                description=f"Rate limit exceeded for {channel.channel_type.value}",
                metadata={'retry_after': retry_after}
            )
            db.commit()
            
            raise Exception(f"Rate limit exceeded. Retry after {retry_after}s")

        try:
            # Parse rich media if raw_payload provided
            rich_media = None
            if raw_payload:
                rich_media = MediaTranslator.parse_incoming_media(
                    channel.channel_type, raw_payload
                )

            # Create message record
            message = ExternalMessage(
                channel_id=channel_id,
                sender_id=sender_id,
                sender_name=sender_name or sender_id,
                content=content,
                message_type=message_type,
                media_url=media_url,
                raw_payload={
                    **(raw_payload or {}),
                    'rich_media': {
                        'text': rich_media.text if rich_media else content,
                        'attachments': rich_media.attachments if rich_media else [],
                        'metadata': rich_media.metadata if rich_media else {}
                    }
                },
                status="received"
            )

            db.add(message)
            channel.messages_received += 1
            channel.last_message_at = datetime.utcnow()
            db.commit()
            db.refresh(message)

            # Record success
            circuit_breaker.record_success(channel_id)

            # Audit log
            AuditLog.log(
                level=AuditLevel.INFO,
                category=AuditCategory.COMMUNICATION,
                actor_type="system",
                actor_id="CHANNEL_ROUTER",
                action="external_message_received",
                target_type="external_message",
                target_id=message.id,
                description=f"Received {channel.channel_type.value} message from {sender_id}",
                metadata={
                    'channel_type': channel.channel_type.value,
                    'channel_name': channel.name,
                    'sender': sender_id,
                    'has_attachments': len(rich_media.attachments) if rich_media else 0,
                    'rate_limit_status': rate_limiter.get_status(channel_id)
                }
            )
            db.commit()

            # Auto-create task if enabled
            if channel.auto_create_tasks:
                await ChannelManager._create_task_for_message(message, channel, db, rich_media)

            return message
            
        except Exception as e:
            # Record failure and check if circuit should open
            circuit_opened = circuit_breaker.record_failure(channel_id)
            
            if circuit_opened:
                # Update channel status to error
                channel.status = ChannelStatus.ERROR
                channel.error_message = f"Circuit breaker opened: {str(e)}"
                db.commit()
                
                # Broadcast circuit open event
                try:
                    from backend.api.websocket import manager as ws_manager
                    await ws_manager.broadcast({
                        "type": "channel_error",
                        "channel_id": channel_id,
                        "error": "Circuit breaker opened due to repeated failures",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except:
                    pass
            
            raise

    @staticmethod
    async def _create_task_for_message(
        message: ExternalMessage,
        channel: ExternalChannel,
        db: Session,
        rich_media: Optional[RichMediaContent] = None
    ):
        """Create a task from external message with rich media context."""

        # Determine which agent handles this
        if channel.default_agent_id:
            assigned_agent = db.query(Agent).filter_by(id=channel.default_agent_id).first()
        else:
            assigned_agent = db.query(HeadOfCouncil).first()

        if not assigned_agent:
            message.last_error = "No agent available to handle message"
            message.error_count += 1
            db.commit()
            return

        # Build rich description with media context
        description_parts = [
            f"External message from {channel.channel_type.value} ({message.sender_id}):\n\n",
            f"{message.content}\n\n",
            f"[Channel: {channel.name} | Sender: {message.sender_name or message.sender_id}]"
        ]
        
        if rich_media and rich_media.attachments:
            description_parts.append(f"\n\n📎 Attachments ({len(rich_media.attachments)}):")
            for i, att in enumerate(rich_media.attachments, 1):
                att_desc = f"\n  {i}. [{att.get('type', 'file').upper()}] "
                if 'filename' in att:
                    att_desc += att['filename']
                elif 'file_id' in att:
                    att_desc += f"File ID: {att['file_id']}"
                description_parts.append(att_desc)

        # Create task
        task = Task(
            title=f"{channel.name}: {message.content[:50]}{'...' if len(message.content) > 50 else ''}",
            description="".join(description_parts),
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.HIGH if channel.require_approval else TaskPriority.NORMAL,
            created_by=f"channel:{channel.id}",
            head_of_council_id=(
                assigned_agent.id
                if assigned_agent.agent_type.value == "head_of_council"
                else None
            ),
            requires_deliberation=channel.require_approval,
            metadata={
                'channel_id': channel.id,
                'message_id': message.id,
                'sender_id': message.sender_id,
                'has_attachments': len(rich_media.attachments) if rich_media else 0,
                'message_type': message.message_type
            }
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        # Link message to task
        message.task_id = task.id
        message.mark_processing(assigned_agent.id)
        db.commit()

        # Broadcast WebSocket event
        if channel.require_approval:
            try:
                from backend.api.websocket import manager as ws_manager
                await ws_manager.broadcast({
                    "type": "message_routed",
                    "channel": channel.channel_type.value,
                    "channel_name": channel.name,
                    "sender": message.sender_name or message.sender_id,
                    "task_id": task.id,
                    "requires_approval": True,
                    "has_attachments": len(rich_media.attachments) if rich_media else 0,
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as ws_err:
                print(f"[ChannelManager] WebSocket broadcast failed: {ws_err}")

    @staticmethod
    async def send_response(
        message_id: str,
        response_content: str,
        agent_id: str,
        rich_media: Optional[RichMediaContent] = None,
        db: Session = None
    ) -> bool:
        """
        Send response back to external channel with rich media support.
        """
        if db is None:
            with get_db_context() as db:
                return await ChannelManager._send_response(message_id, response_content, agent_id, rich_media, db)
        else:
            return await ChannelManager._send_response(message_id, response_content, agent_id, rich_media, db)

    @staticmethod
    async def _send_response(
        message_id: str,
        response_content: str,
        agent_id: str,
        rich_media: Optional[RichMediaContent],
        db: Session
    ) -> bool:
        """Send response via the appropriate channel adapter with resilience."""

        message = db.query(ExternalMessage).filter_by(id=message_id).first()
        if not message:
            return False

        channel = message.channel

        # Circuit breaker check
        if not circuit_breaker.can_execute(channel.id):
            message.error_count += 1
            message.last_error = "Circuit breaker open"
            db.commit()
            return False

        # Rate limiting check
        rate_config = PLATFORM_RATE_LIMITS.get(channel.channel_type, RateLimitConfig())
        allowed, retry_after = rate_limiter.acquire(channel.id, rate_config)
        
        if not allowed:
            message.error_count += 1
            message.last_error = f"Rate limit exceeded, retry after {retry_after}s"
            db.commit()
            return False

        success = False
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries and not success:
            try:
                ct = channel.channel_type
                config = channel.config

                # Use rich media if provided, otherwise plain text
                if rich_media:
                    if ct == ChannelType.SLACK:
                        success = await SlackAdapter.send_rich_message(config, message.sender_id, rich_media)
                    elif ct == ChannelType.DISCORD:
                        success = await DiscordAdapter.send_rich_message(config, message.sender_id, rich_media)
                    elif ct == ChannelType.TELEGRAM:
                        success = await TelegramAdapter.send_rich_message(config, message.sender_id, rich_media)
                    elif ct == ChannelType.TEAMS:
                        success = await TeamsAdapter.send_rich_message(config, message.sender_id, rich_media)
                    else:
                        # Fall back to plain text for other platforms
                        success = await ChannelManager._send_plain_text(ct, config, message.sender_id, response_content)
                else:
                    success = await ChannelManager._send_plain_text(ct, config, message.sender_id, response_content)

                if success:
                    circuit_breaker.record_success(channel.id)
                    message.mark_responded(response_content, agent_id)
                    
                    AuditLog.log(
                        level=AuditLevel.INFO,
                        category=AuditCategory.COMMUNICATION,
                        actor_type="agent",
                        actor_id=agent_id,
                        action="external_response_sent",
                        target_type="external_message",
                        target_id=message_id,
                        description=f"Response sent via {channel.channel_type.value}",
                        metadata={
                            'channel': channel.name,
                            'recipient': message.sender_id,
                            'response_length': len(response_content),
                            'rich_media': rich_media is not None,
                            'retry_count': retry_count
                        }
                    )
                    db.commit()
                    break

            except Exception as e:
                retry_count += 1
                print(f"[ChannelManager] Send attempt {retry_count} failed: {e}")
                
                if retry_count >= max_retries:
                    circuit_opened = circuit_breaker.record_failure(channel.id)
                    message.error_count += 1
                    message.last_error = f"Failed after {max_retries} retries: {str(e)}"
                    
                    if circuit_opened:
                        channel.status = ChannelStatus.ERROR
                        channel.error_message = f"Circuit breaker opened: {str(e)}"
                    
                    db.commit()
                    
                    # Queue for retry later
                    await ChannelManager._queue_for_retry(message_id, agent_id, response_content, rich_media)
                    break
                
                # Exponential backoff
                await asyncio.sleep(2 ** retry_count)

        return success

    @staticmethod
    async def _send_plain_text(channel_type: ChannelType, config: Dict, recipient: str, content: str) -> bool:
        """Send plain text message to specific channel type.

        For WhatsApp channels the :class:`UnifiedWhatsAppAdapter` is used so that
        both ``cloud_api`` and ``web_bridge`` providers are handled transparently.
        The adapter requires an :class:`ExternalChannel` instance; a lightweight
        temporary object is constructed from the supplied *config* dict.
        """
        if channel_type == ChannelType.WHATSAPP:
            # Build a minimal ExternalChannel-like object for the unified adapter
            temp_channel = ExternalChannel(
                config=config,
                channel_type=channel_type,
                status=ChannelStatus.ACTIVE,
            )
            adapter = UnifiedWhatsAppAdapter(temp_channel)

            # Wrap the bare text in a minimal ExternalMessage so the adapter can
            # read sender_id and content from a consistent interface.
            temp_message = ExternalMessage(
                sender_id=recipient,
                content=content,
                raw_payload={},
            )
            return await adapter.send_message(temp_message)
        elif channel_type == ChannelType.SLACK:
            return await SlackAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.TELEGRAM:
            return await TelegramAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.EMAIL:
            return await EmailAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.DISCORD:
            return await DiscordAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.SIGNAL:
            return await SignalAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.GOOGLE_CHAT:
            return await GoogleChatAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.TEAMS:
            return await TeamsAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.ZALO:
            return await ZaloAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.MATRIX:
            return await MatrixAdapter.send_message(config, recipient, content)
        elif channel_type == ChannelType.IMESSAGE:
            return await iMessageAdapter.send_message(config, recipient, content)
        else:
            raise ValueError(f"No adapter for channel type: {channel_type.value}")

    @staticmethod
    async def _queue_for_retry(message_id: str, agent_id: str, content: str, rich_media: Optional[RichMediaContent]):
            """Queue failed message for later retry via Celery."""
            try:
                # Import from task_executor instead of channel_retry
                from backend.services.tasks.task_executor import retry_channel_message
                
                rich_media_dict = None
                if rich_media:
                    rich_media_dict = {
                        'text': rich_media.text,
                        'blocks': rich_media.blocks,
                        'attachments': rich_media.attachments,
                        'actions': rich_media.actions,
                        'metadata': rich_media.metadata
                    }
                
                retry_channel_message.apply_async(
                    args=[message_id, agent_id, content],
                    kwargs={'rich_media_dict': rich_media_dict},
                    countdown=300,  # 5 minutes
                    max_retries=3
                )
                print(f"[ChannelManager] Queued message {message_id} for retry")
            except Exception as e:
                print(f"[ChannelManager] Failed to queue retry: {e}")

    @staticmethod
    def get_channel_health(channel_id: str) -> Dict[str, Any]:
        """Get comprehensive health status for a channel."""
        circuit_metrics = circuit_breaker.get_metrics(channel_id)
        rate_status = rate_limiter.get_status(channel_id)
        
        return {
            'circuit_breaker': circuit_metrics,
            'rate_limiting': rate_status,
            'overall_status': 'healthy' if circuit_metrics['circuit_state'] == 'closed' and 
                              circuit_metrics['success_rate'] > 0.8 else 'degraded'
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Channel Adapters (Updated with Rich Media Support)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WhatsAppAdapter:
    """
    WhatsApp Business API (Meta Graph API v17+).
    Config keys: phone_number_id, access_token
    """

    @staticmethod
    async def send_message(config: Dict, recipient: str, content: str) -> bool:
        import httpx

        phone_number_id = config.get('phone_number_id')
        access_token = config.get('access_token')

        if not phone_number_id or not access_token:
            raise ValueError("WhatsApp not configured: missing phone_number_id or access_token")

        url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
        
        # Handle long messages by splitting
        chunks = [content[i:i+4096] for i in range(0, len(content), 4096)]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunks:
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "text",
                    "text": {"body": chunk}
                }
                
                response = await client.post(
                    url, json=payload,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if response.status_code != 200:
                    raise Exception(f"WhatsApp API error: {response.text}")
                
                # Rate limit handling
                if response.status_code == 429:
                    retry_after = int(response.headers.get('retry-after', 60))
                    await asyncio.sleep(retry_after)
                    # Retry once
                    response = await client.post(
                        url, json=payload,
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    if response.status_code != 200:
                        raise Exception(f"WhatsApp API error after retry: {response.text}")

        return True

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse incoming WhatsApp Cloud API webhook payload."""
        try:
            entry = payload.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            messages = value.get('messages', [{}])[0]
            contacts = value.get('contacts', [{}])[0]
            
            if not messages or not messages.get('from'):
                raise ValueError("No message data in webhook")

            msg_type = messages.get('type', 'text')
            media_url = None
            mime_type = None

            content_map = {
                'text': lambda: messages.get('text', {}).get('body', ''),
                'image': lambda: (messages.get('image', {}).get('caption', '[Image]'), 
                                 messages.get('image', {}).get('link'),
                                 messages.get('image', {}).get('mime_type')),
                'document': lambda: (f"[Document: {messages.get('document', {}).get('filename', 'unknown')}]",
                                     messages.get('document', {}).get('link'),
                                     messages.get('document', {}).get('mime_type')),
                'audio': lambda: ('[Voice message]', 
                                messages.get('audio', {}).get('link'),
                                messages.get('audio', {}).get('mime_type')),
                'video': lambda: (messages.get('video', {}).get('caption', '[Video]'),
                                 messages.get('video', {}).get('link'),
                                 messages.get('video', {}).get('mime_type')),
                'sticker': lambda: ('[Sticker]', None, None),
                'location': lambda: (f"[Location: {messages.get('location', {}).get('latitude')}, {messages.get('location', {}).get('longitude')}]",
                                   None, None),
                'contacts': lambda: ('[Shared contact]', None, None),
            }

            content = ''
            if msg_type in content_map:
                result = content_map[msg_type]()
                if isinstance(result, tuple):
                    content, media_url, mime_type = result
                else:
                    content = result

            return {
                'sender_id': messages.get('from'),
                'sender_name': contacts.get('profile', {}).get('name') if contacts else None,
                'content': content,
                'message_type': msg_type,
                'media_url': media_url,
                'mime_type': mime_type,
                'timestamp': messages.get('timestamp'),
                'message_id': messages.get('id'),
                'raw_payload': payload
            }
        except Exception as e:
            raise ValueError(f"Failed to parse WhatsApp webhook: {e}")

    @staticmethod
    async def download_media(config: Dict, media_id: str) -> bytes:
        """Download media from WhatsApp servers."""
        import httpx
        
        access_token = config.get('access_token')
        url = f"https://graph.facebook.com/v17.0/{media_id}"
        
        async with httpx.AsyncClient() as client:
            # Get media URL
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            data = resp.json()
            media_url = data.get('url')
            
            if not media_url:
                raise ValueError(f"No media URL for ID {media_id}")
            
            # Download media
            media_resp = await client.get(
                media_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return media_resp.content


class SlackAdapter:
    """
    Slack Bot API.
    Config keys: bot_token, signing_secret (optional, for request verification)
    """

    @staticmethod
    async def send_message(config: Dict, channel_id: str, content: str) -> bool:
        """Send plain text message."""
        import httpx

        bot_token = config.get('bot_token')
        if not bot_token:
            raise ValueError("Slack not configured: missing bot_token")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                json={
                    "channel": channel_id,
                    "text": content[:4000],
                    "parse": "full",
                    "unfurl_links": True
                },
                headers={"Authorization": f"Bearer {bot_token}"}
            )
            data = response.json()
            if data.get('ok'):
                return True
            raise Exception(f"Slack API error: {data.get('error')}")

    @staticmethod
    async def send_rich_message(config: Dict, channel_id: str, media: RichMediaContent) -> bool:
        """Send rich message with Block Kit."""
        import httpx

        bot_token = config.get('bot_token')
        blocks = MediaTranslator.to_slack_blocks(media)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                json={
                    "channel": channel_id,
                    "text": media.text[:4000],
                    "blocks": blocks[:50],  # Slack limit
                    "parse": "full"
                },
                headers={"Authorization": f"Bearer {bot_token}"}
            )
            data = response.json()
            if data.get('ok'):
                return True
            raise Exception(f"Slack API error: {data.get('error')}")

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Slack Events API payload."""
        # Slash command
        if 'command' in payload:
            return {
                'sender_id': payload.get('channel_id'),
                'sender_name': payload.get('user_name'),
                'content': payload.get('text', ''),
                'message_type': 'slash_command',
                'command': payload.get('command'),
                'response_url': payload.get('response_url'),
                'raw_payload': payload
            }

        event = payload.get('event', {})
        event_type = event.get('type', 'message')
        
        # Ignore bot messages
        if event.get('bot_id') or event.get('subtype') == 'bot_message':
            raise ValueError("Ignoring bot message")

        text = event.get('text', '')
        
        # Strip bot mentions
        if event_type == 'app_mention':
            import re
            text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()

        # Handle file shares
        files = event.get('files', [])
        attachments = []
        for f in files:
            attachments.append({
                'type': f.get('mimetype', '').split('/')[0] if '/' in f.get('mimetype', '') else 'file',
                'name': f.get('name'),
                'url': f.get('url_private'),
                'size': f.get('size')
            })

        return {
            'sender_id': event.get('channel'),
            'sender_name': event.get('user'),
            'content': text,
            'message_type': event_type,
            'thread_ts': event.get('thread_ts'),
            'files': attachments,
            'raw_payload': payload
        }

    @staticmethod
    def verify_signature(signing_secret: str, timestamp: str, body: str, signature: str) -> bool:
        """Verify Slack request authenticity."""
        base = f"v0:{timestamp}:{body}"
        computed = "v0=" + hmac.new(
            signing_secret.encode(), base.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, signature)


class TelegramAdapter:
    """
    Telegram Bot API.
    Config keys: bot_token
    """

    @staticmethod
    async def send_message(config: Dict, chat_id: str, content: str) -> bool:
        """Send plain text message."""
        import httpx

        bot_token = config.get('bot_token')
        if not bot_token:
            raise ValueError("Telegram not configured: missing bot_token")

        # Split long messages
        chunks = [content[i:i+4096] for i in range(0, len(content), 4096)]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunks:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False
                    }
                )
                data = response.json()
                if not data.get('ok'):
                    # Try without Markdown on parse error
                    if data.get('description', '').startswith('Can\'t find end'):
                        response = await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": chunk,
                                "parse_mode": None
                            }
                        )
                        data = response.json()
                    
                    if not data.get('ok'):
                        raise Exception(f"Telegram API error: {data.get('description')}")

        return True

    @staticmethod
    async def send_rich_message(config: Dict, chat_id: str, media: RichMediaContent) -> bool:
        """Send rich HTML message."""
        import httpx

        bot_token = config.get('bot_token')
        html_content = MediaTranslator.to_telegram_html(media)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": html_content,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
            )
            data = response.json()
            if data.get('ok'):
                return True
            
            # Fallback to plain text
            return await TelegramAdapter.send_message(config, chat_id, media.text)

    @staticmethod
    async def send_media_group(config: Dict, chat_id: str, media_files: List[Dict]) -> bool:
        """Send multiple photos/documents as album."""
        import httpx

        bot_token = config.get('bot_token')
        media_group = []
        
        for i, f in enumerate(media_files[:10]):  # Telegram limit
            item = {
                "type": f.get('type', 'photo'),
                "media": f.get('file_id') or f.get('url')
            }
            if i == 0 and f.get('caption'):
                item['caption'] = f['caption'][:1024]
            media_group.append(item)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMediaGroup",
                json={
                    "chat_id": chat_id,
                    "media": media_group
                }
            )
            return response.json().get('ok', False)

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Telegram Update object."""
        message = payload.get('message') or payload.get('edited_message', {})
        callback = payload.get('callback_query')
        
        if callback:
            return {
                'sender_id': str(callback.get('from', {}).get('id')),
                'sender_name': callback.get('from', {}).get('first_name'),
                'content': callback.get('data', ''),
                'message_type': 'callback_query',
                'message_id': callback.get('message', {}).get('message_id'),
                'raw_payload': payload
            }

        from_user = message.get('from', {})
        chat = message.get('chat', {})
        
        # Determine content type
        content_types = {
            'text': lambda: message.get('text', ''),
            'photo': lambda: f"[Photo] {message.get('caption', '')}",
            'video': lambda: f"[Video] {message.get('caption', '')}",
            'audio': lambda: "[Audio message]",
            'voice': lambda: "[Voice message]",
            'document': lambda: f"[Document: {message.get('document', {}).get('file_name', 'unknown')}]",
            'sticker': lambda: "[Sticker]",
            'location': lambda: f"[Location: {message.get('location', {}).get('latitude')}, {message.get('location', {}).get('longitude')}]",
            'contact': lambda: "[Contact]",
        }

        msg_type = 'text'
        content = ''
        
        for type_key, extractor in content_types.items():
            if type_key in message:
                msg_type = type_key
                content = extractor()
                break

        return {
            'sender_id': str(chat.get('id')),
            'sender_name': from_user.get('first_name') or from_user.get('username'),
            'content': content,
            'message_type': msg_type,
            'chat_type': chat.get('type'),
            'message_id': message.get('message_id'),
            'raw_payload': payload
        }

    @staticmethod
    async def set_webhook(config: Dict, webhook_url: str) -> bool:
        """Register webhook URL with Telegram."""
        import httpx

        bot_token = config.get('bot_token')
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_url, "max_connections": 20}
            )
            return response.json().get('ok', False)

    @staticmethod
    async def get_file(config: Dict, file_id: str) -> str:
        """Get file URL from file_id."""
        import httpx

        bot_token = config.get('bot_token')
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id}
            )
            data = response.json()
            if data.get('ok'):
                file_path = data['result']['file_path']
                return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            raise ValueError(f"Cannot get file: {data}")


class EmailAdapter:
    """
    Email via SMTP (send) / IMAP (receive).
    Config keys: smtp_host, smtp_port, smtp_user, smtp_pass, from_email,
                 imap_host, imap_port, imap_user, imap_pass, imap_folder
    """

    @staticmethod
    async def send_message(config: Dict, to_email: str, content: str, subject: str = "Response", 
                          html_content: str = None, attachments: List[Dict] = None) -> bool:
        """Send email via SMTP with TLS and optional HTML/attachments."""
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        import mimetypes

        smtp_host = config.get('smtp_host')
        smtp_port = int(config.get('smtp_port', 587))
        smtp_user = config.get('smtp_user')
        smtp_pass = config.get('smtp_pass')
        from_email = config.get('from_email', smtp_user)

        if not all([smtp_host, smtp_user, smtp_pass]):
            raise ValueError("Email not configured: missing SMTP settings")

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        # Plain text part
        msg.attach(MIMEText(content, 'plain'))

        # HTML part
        if html_content:
            msg.attach(MIMEText(html_content, 'html'))

        # Attachments
        if attachments:
            for att in attachments:
                filename = att.get('filename', 'attachment')
                content_type = att.get('content_type') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                maintype, subtype = content_type.split('/', 1) if '/' in content_type else ('application', 'octet-stream')
                
                part = MIMEBase(maintype, subtype)
                part.set_payload(att.get('content') or att.get('data', b''))
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)

        try:
            smtp = aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port)
            await smtp.connect()
            await smtp.starttls()
            await smtp.login(smtp_user, smtp_pass)
            await smtp.send_message(msg)
            await smtp.quit()
            return True
        except Exception as e:
            raise Exception(f"SMTP error: {e}")

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse inbound email payload (SendGrid Inbound Parse / Mailgun)."""
        sender = payload.get('from') or payload.get('sender', '')
        subject = payload.get('subject', '(no subject)')
        
        # Extract body
        text_body = payload.get('text') or payload.get('body-plain', '')
        html_body = payload.get('html') or payload.get('body-html', '')
        
        # Handle multipart form data from SendGrid
        if not text_body and 'email' in payload:
            # Some providers wrap the email
            email_data = payload['email']
            text_body = email_data.get('text', '')
            html_body = email_data.get('html', '')

        # Count attachments
        attachment_count = 0
        if 'attachments' in payload:
            attachment_count = len(payload['attachments'])
        elif 'attachment-info' in payload:
            attachment_count = len(payload['attachment-info'])

        return {
            'sender_id': sender,
            'sender_name': sender.split('<')[0].strip() if '<' in sender else sender,
            'content': f"Subject: {subject}\n\n{text_body}",
            'message_type': 'email',
            'subject': subject,
            'html_content': html_body,
            'attachment_count': attachment_count,
            'raw_payload': payload
        }

    @staticmethod
    async def verify_imap(config: Dict) -> bool:
        """Verify IMAP connection settings."""
        try:
            import aioimaplib
            
            imap_host = config.get('imap_host', config.get('smtp_host', ''))
            imap_port = int(config.get('imap_port', 993))
            username = config.get('smtp_user', config.get('imap_user', ''))
            password = config.get('smtp_pass', config.get('imap_pass', ''))
            
            client = aioimaplib.IMAP4_SSL(host=imap_host, port=imap_port)
            await client.wait_hello_from_server()
            await client.login(username, password)
            await client.select('INBOX')
            await client.logout()
            return True
        except Exception as e:
            print(f"[EmailAdapter] IMAP verification failed: {e}")
            return False


class DiscordAdapter:
    """
    Discord Bot API (REST).
    Config keys: bot_token, application_id
    """

    @staticmethod
    async def send_message(config: Dict, channel_id: str, content: str) -> bool:
        """Send plain text message with chunking for long messages."""
        import httpx

        bot_token = config.get('bot_token')
        if not bot_token:
            raise ValueError("Discord not configured: missing bot_token")

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

        # Discord limit: 2000 chars
        chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for chunk in chunks:
                response = await client.post(
                    url,
                    json={"content": chunk},
                    headers=headers
                )
                if response.status_code not in (200, 201):
                    raise Exception(f"Discord API error {response.status_code}: {response.text}")
                # Rate limit handling
                if response.status_code == 429:
                    retry_after = int(response.headers.get('X-RateLimit-Reset-After', 1))
                    await asyncio.sleep(retry_after)
                    response = await client.post(
                        url,
                        json={"content": chunk},
                        headers=headers
                    )
                    if response.status_code not in (200, 201):
                        raise Exception(f"Discord API error after retry: {response.text}")

        return True

    @staticmethod
    async def send_rich_message(config: Dict, channel_id: str, media: RichMediaContent) -> bool:
        """Send rich embed message."""
        import httpx

        bot_token = config.get('bot_token')
        embeds = MediaTranslator.to_discord_embeds(media)

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={"embeds": embeds[:10]},  # Discord limit
                headers=headers
            )
            return response.status_code in (200, 201)

    @staticmethod
    async def send_embed(config: Dict, channel_id: str, title: str, description: str,
                          color: int = 0x5865F2, fields: List[Dict] = None) -> bool:
        """Send a rich embed message."""
        import httpx

        bot_token = config.get('bot_token')
        
        embed = {
            "title": title[:256],
            "description": description[:4096],
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Agentium AI"}
        }
        
        if fields:
            embed["fields"] = [
                {"name": f['name'][:256], "value": f['value'][:1024], "inline": f.get('inline', False)}
                for f in fields[:25]
            ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                json={"embeds": [embed]},
                headers={"Authorization": f"Bot {bot_token}"}
            )
            return response.status_code in (200, 201)

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Discord Interactions or Gateway events."""
        interaction_type = payload.get('type')

        # PING
        if interaction_type == 1:
            return {'type': 'ping', 'raw_payload': payload}

        # Slash command
        if interaction_type == 2:
            data = payload.get('data', {})
            options = {opt['name']: opt.get('value') for opt in data.get('options', [])}
            content = ' '.join(str(v) for v in options.values()) if options else data.get('name', '')
            
            member = payload.get('member', {})
            user = member.get('user', payload.get('user', {}))

            return {
                'sender_id': payload.get('channel_id', ''),
                'sender_name': user.get('username'),
                'content': content,
                'message_type': 'slash_command',
                'command': data.get('name'),
                'options': options,
                'interaction_id': payload.get('id'),
                'interaction_token': payload.get('token'),
                'application_id': payload.get('application_id'),
                'raw_payload': payload
            }

        # Message component
        if interaction_type == 3:
            return {
                'sender_id': payload.get('channel_id', ''),
                'sender_name': payload.get('member', {}).get('user', {}).get('username'),
                'content': payload.get('data', {}).get('custom_id', ''),
                'message_type': 'component_interaction',
                'interaction_id': payload.get('id'),
                'interaction_token': payload.get('token'),
                'raw_payload': payload
            }

        # Gateway MESSAGE_CREATE
        author = payload.get('author', {})
        
        # Skip bot messages
        if author.get('bot'):
            raise ValueError("Ignoring bot message")

        return {
            'sender_id': payload.get('channel_id'),
            'sender_name': author.get('username'),
            'content': payload.get('content', ''),
            'message_type': 'text',
            'message_id': payload.get('id'),
            'attachments': payload.get('attachments', []),
            'raw_payload': payload
        }

    @staticmethod
    async def respond_to_interaction(config: Dict, interaction_id: str, interaction_token: str,
                                      application_id: str, content: str, embeds: List[Dict] = None) -> bool:
        """Respond to a Discord slash command interaction."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback",
                json={
                    "type": 4,
                    "data": {
                        "content": content[:2000],
                        "embeds": embeds or []
                    }
                }
            )
            return response.status_code in (200, 204)

    @staticmethod
    async def edit_original_response(config: Dict, application_id: str, interaction_token: str,
                                      content: str) -> bool:
        """Edit original interaction response."""
        import httpx

        bot_token = config.get('bot_token')
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}/messages/@original",
                json={"content": content[:2000]},
                headers={"Authorization": f"Bot {bot_token}"}
            )
            return response.status_code == 200


class SignalAdapter:
    """
    Signal via signal-cli (https://github.com/AsamK/signal-cli).
    Config keys: number, rpc_host, rpc_port
    """

    @staticmethod
    def _rpc_url(config: Dict) -> str:
        host = config.get('rpc_host', '127.0.0.1')
        port = config.get('rpc_port', 7583)
        return f"http://{host}:{port}"

    @staticmethod
    async def send_message(config: Dict, recipient: str, content: str) -> bool:
        """Send Signal message via signal-cli JSON-RPC daemon."""
        import httpx

        number = config.get('number')
        if not number:
            raise ValueError("Signal not configured: missing number")

        rpc_payload = {
            "jsonrpc": "2.0",
            "method": "send",
            "id": secrets.token_hex(8),
            "params": {
                "account": number,
                "recipient": [recipient],
                "message": content[:65536]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    SignalAdapter._rpc_url(config),
                    json=rpc_payload
                )
                result = response.json()
                if 'error' in result:
                    raise Exception(f"signal-cli RPC error: {result['error']}")
                return True
        except httpx.ConnectError:
            raise Exception(
                "Cannot reach signal-cli daemon. "
                "Ensure it is running: signal-cli -u +YOURNUM daemon --http"
            )

    @staticmethod
    async def send_via_subprocess(config: Dict, recipient: str, content: str) -> bool:
        """Fallback: send via signal-cli subprocess."""
        number = config.get('number')
        if not number:
            raise ValueError("Signal not configured: missing number")

        cmd = [
            "signal-cli", "-u", number,
            "send", "-m", content,
            recipient
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise Exception(f"signal-cli error: {result.stderr}")
        return True

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse signal-cli receive JSON output."""
        envelope = payload.get('envelope', payload)
        data_message = envelope.get('dataMessage', {})
        sync_message = envelope.get('syncMessage', {})
        
        # Use syncMessage for sent messages, dataMessage for received
        msg = data_message if data_message else sync_message.get('sent', {})
        
        source = envelope.get('source') or envelope.get('sourceNumber', '')
        
        # Skip our own messages if needed
        if sync_message and not data_message:
            raise ValueError("Ignoring self-sent message")

        return {
            'sender_id': source,
            'sender_name': envelope.get('sourceName'),
            'content': msg.get('message', ''),
            'message_type': 'text',
            'timestamp': envelope.get('timestamp'),
            'raw_payload': payload
        }

    @staticmethod
    async def receive_messages(config: Dict, callback: Callable) -> None:
        """Receive messages via signal-cli JSON-RPC receive method."""
        import httpx
        
        rpc_payload = {
            "jsonrpc": "2.0",
            "method": "receive",
            "id": secrets.token_hex(8),
            "params": {"timeout": 10}
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                try:
                    response = await client.post(
                        SignalAdapter._rpc_url(config),
                        json=rpc_payload
                    )
                    result = response.json()
                    
                    if 'result' in result:
                        for envelope in result['result']:
                            await callback(envelope)
                            
                except Exception as e:
                    print(f"[SignalAdapter] Receive error: {e}")
                    await asyncio.sleep(5)


class GoogleChatAdapter:
    """
    Google Chat REST API.
    Config keys: service_account_json, space_name, webhook_url
    """

    @staticmethod
    async def send_message(config: Dict, space_or_thread: str, content: str) -> bool:
        """Send message via OAuth or incoming webhook."""
        if config.get('webhook_url'):
            return await GoogleChatAdapter.send_incoming_webhook(config['webhook_url'], content)
        return await GoogleChatAdapter._send_via_api(config, space_or_thread, content)

    @staticmethod
    async def _send_via_api(config: Dict, space_or_thread: str, content: str) -> bool:
        """Send via Google Chat API with service account."""
        import httpx

        service_account_json = config.get('service_account_json')
        if not service_account_json:
            raise ValueError("Google Chat not configured: missing service_account_json")

        token = await GoogleChatAdapter._get_access_token(service_account_json)
        
        target = space_or_thread if space_or_thread.startswith('spaces/') else config.get('space_name', space_or_thread)
        
        body = {
            "text": content[:4096],
        }

        url = f"https://chat.googleapis.com/v1/{target}/messages"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return True
            raise Exception(f"Google Chat API error: {response.text}")

    @staticmethod
    async def send_rich_card(config: Dict, space_or_thread: str, title: str, 
                             content: str, image_url: str = None, buttons: List[Dict] = None) -> bool:
        """Send rich card with optional image and buttons."""
        import httpx

        service_account_json = config.get('service_account_json')
        token = await GoogleChatAdapter._get_access_token(service_account_json)
        
        target = space_or_thread if space_or_thread.startswith('spaces/') else config.get('space_name', space_or_thread)
        
        widgets = [{"textParagraph": {"text": content[:4096]}}]
        
        if image_url:
            widgets.insert(0, {
                "image": {
                    "imageUrl": image_url,
                    "onClick": {"openLink": {"url": image_url}}
                }
            })
        
        if buttons:
            action_widgets = []
            for btn in buttons[:3]:  # Max 3 buttons
                action_widgets.append({
                    "textButton": {
                        "text": btn['text'],
                        "onClick": {
                            "openLink": {"url": btn['url']} if btn.get('url') else {
                                "action": {"actionMethodName": btn.get('action', 'snackbar')}
                            }
                        }
                    }
                })
            widgets.append({"buttons": action_widgets})

        body = {
            "cardsV2": [{
                "cardId": f"agentium-{int(time.time())}",
                "card": {
                    "header": {
                        "title": title[:256],
                        "imageUrl": "https://www.gstatic.com/images/icons/material/product/1x/chat_48dp.png"
                    },
                    "sections": [{"widgets": widgets}]
                }
            }]
        }

        url = f"https://chat.googleapis.com/v1/{target}/messages"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"}
            )
            return response.status_code == 200

    @staticmethod
    async def _get_access_token(service_account_json: str) -> str:
        """Exchange service account credentials for access token."""
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            import json as _json

            creds_info = _json.loads(service_account_json)
            scopes = ["https://www.googleapis.com/auth/chat.bot"]
            credentials = service_account.Credentials.from_service_account_info(
                creds_info, scopes=scopes
            )
            credentials.refresh(Request())
            return credentials.token
        except ImportError:
            raise Exception("google-auth package required: pip install google-auth")

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Google Chat event webhook."""
        event_type = payload.get('type', 'MESSAGE')
        message = payload.get('message', {})
        sender = message.get('sender', {})
        space = payload.get('space', {})
        thread = message.get('thread', {})

        text = message.get('argumentText', '') or message.get('text', '')
        
        # Strip bot mention
        if text.startswith('@'):
            text = ' '.join(text.split()[1:])

        return {
            'sender_id': space.get('name', '') + (f"/{thread.get('name', '')}" if thread else ''),
            'sender_name': sender.get('displayName'),
            'content': text,
            'message_type': event_type.lower(),
            'space_type': space.get('spaceType'),
            'raw_payload': payload
        }

    @staticmethod
    async def send_incoming_webhook(webhook_url: str, content: str, card: Dict = None) -> bool:
        """Send via simple incoming webhook (no auth required)."""
        import httpx

        body = {"text": content[:4096]}
        if card:
            body["cardsV2"] = [card]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=body)
            return response.status_code == 200


class TeamsAdapter:
    """
    Microsoft Teams via Bot Framework or Incoming Webhooks.
    Config keys: webhook_url, tenant_id, client_id, client_secret, service_url
    """

    @staticmethod
    async def send_message(config: Dict, conversation_id: str, content: str) -> bool:
        """Send message via webhook or Bot Framework."""
        if config.get('webhook_url'):
            return await TeamsAdapter._send_via_incoming_webhook(config, content)
        return await TeamsAdapter._send_via_bot_framework(config, conversation_id, content)

    @staticmethod
    async def _send_via_incoming_webhook(config: Dict, content: str) -> bool:
        """Send via Teams incoming webhook."""
        import httpx

        webhook_url = config['webhook_url']
        
        # Simple text for incoming webhook
        payload = {"text": content[:28000]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=payload)
            return response.status_code == 200

    @staticmethod
    async def _send_via_bot_framework(config: Dict, conversation_id: str, content: str) -> bool:
        """Send via Bot Framework."""
        import httpx

        token = await TeamsAdapter._get_bot_token(config)
        service_url = config.get('service_url', 'https://smba.trafficmanager.net/apis')

        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        
        payload = {
            "type": "message",
            "text": content[:28000],
            "textFormat": "markdown"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"}
            )
            return response.status_code in (200, 201)

    @staticmethod
    async def send_rich_message(config: Dict, conversation_id: str, media: RichMediaContent) -> bool:
        """Send Adaptive Card message."""
        import httpx

        token = await TeamsAdapter._get_bot_token(config)
        service_url = config.get('service_url', 'https://smba.trafficmanager.net/apis')
        
        card = MediaTranslator.to_teams_adaptive_card(media)

        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card
            }]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"}
            )
            return response.status_code in (200, 201)

    @staticmethod
    async def _get_bot_token(config: Dict) -> str:
        """Obtain Bot Framework OAuth2 token."""
        import httpx

        tenant_id = config.get('tenant_id', 'botframework.com')
        client_id = config.get('client_id')
        client_secret = config.get('client_secret')

        if not client_id or not client_secret:
            raise ValueError("Teams Bot Framework not configured: missing client_id or client_secret")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://api.botframework.com/.default"
                }
            )
            data = response.json()
            if 'access_token' not in data:
                raise Exception(f"Teams token error: {data}")
            return data['access_token']

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Bot Framework Activity."""
        activity_type = payload.get('type', 'message')
        from_user = payload.get('from', {})
        conversation = payload.get('conversation', {})

        text = payload.get('text', '')
        
        # Strip @bot mention
        if '<at>' in text:
            import re
            text = re.sub(r'<at>[^<]+</at>', '', text).strip()

        return {
            'sender_id': conversation.get('id'),
            'sender_name': from_user.get('name'),
            'content': text,
            'message_type': activity_type,
            'locale': payload.get('locale'),
            'service_url': payload.get('serviceUrl'),
            'raw_payload': payload
        }


class ZaloAdapter:
    """
    Zalo Official Account (OA) API.
    Config keys: access_token, oa_id
    """

    ZALO_API_BASE = "https://openapi.zalo.me/v2.0/oa"

    @staticmethod
    async def send_message(config: Dict, user_id: str, content: str) -> bool:
        """Send text message to Zalo user."""
        import httpx

        access_token = config.get('access_token')
        if not access_token:
            raise ValueError("Zalo not configured: missing access_token")

        payload = {
            "recipient": {"user_id": user_id},
            "message": {"text": content[:2000]}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ZaloAdapter.ZALO_API_BASE}/message",
                json=payload,
                headers={"access_token": access_token}
            )
            data = response.json()
            if data.get('error') == 0:
                return True
            raise Exception(f"Zalo API error {data.get('error')}: {data.get('message')}")

    @staticmethod
    async def send_template_message(config: Dict, user_id: str,
                                     title: str, subtitle: str, image_url: str = None,
                                     buttons: List[Dict] = None) -> bool:
        """Send structured list template message."""
        import httpx

        access_token = config.get('access_token')
        
        element = {
            "title": title[:80],
            "subtitle": subtitle[:200]
        }
        if image_url:
            element["image_url"] = image_url
        
        if buttons:
            element["default_action"] = {
                "type": "oa.open.url",
                "url": buttons[0].get('url', 'https://zalo.me')
            }

        payload = {
            "recipient": {"user_id": user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "list",
                        "elements": [element]
                    }
                }
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ZaloAdapter.ZALO_API_BASE}/message",
                json=payload,
                headers={"access_token": access_token}
            )
            data = response.json()
            return data.get('error') == 0

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Zalo OA webhook event."""
        event_name = payload.get('event_name', 'user_send_text')
        sender = payload.get('sender', {})
        message = payload.get('message', {})

        content = ''
        msg_type = 'text'

        event_map = {
            'user_send_text': lambda: (message.get('text', ''), 'text'),
            'user_send_image': lambda: (message.get('text', '[Image]'), 'image'),
            'user_send_audio': lambda: ('[Audio]', 'audio'),
            'user_send_video': lambda: (message.get('text', '[Video]'), 'video'),
            'user_send_file': lambda: (f"[File: {message.get('attachments', [{}])[0].get('name', 'unknown')}]", 'file'),
            'user_send_location': lambda: (f"[Location: {message.get('attachments', [{}])[0].get('payload', {}).get('coordinates', {})}]", 'location'),
            'follow': lambda: ('[User followed OA]', 'follow'),
            'unfollow': lambda: ('[User unfollowed OA]', 'unfollow'),
        }

        if event_name in event_map:
            content, msg_type = event_map[event_name]()

        return {
            'sender_id': sender.get('id'),
            'sender_name': sender.get('display_name') or sender.get('id'),
            'content': content,
            'message_type': msg_type,
            'event_name': event_name,
            'raw_payload': payload
        }


class MatrixAdapter:
    """
    Matrix Client-Server API.
    Config keys: homeserver_url, access_token, room_id
    """

    @staticmethod
    async def send_message(config: Dict, room_id: str, content: str) -> bool:
        """Send plain text and HTML message."""
        import httpx
        import uuid

        homeserver_url = config.get('homeserver_url', 'https://matrix.org').rstrip('/')
        access_token = config.get('access_token')

        if not access_token:
            raise ValueError("Matrix not configured: missing access_token")

        target_room = room_id if room_id.startswith('!') else config.get('room_id', room_id)
        event_id = str(uuid.uuid4()).replace('-', '')
        
        url = f"{homeserver_url}/_matrix/client/v3/rooms/{target_room}/send/m.room.message/{event_id}"

        body = {
            "msgtype": "m.text",
            "body": content[:65536],
            "format": "org.matrix.custom.html",
            "formatted_body": f"<p>{content[:65536].replace(chr(10), '<br>')}</p>"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                url,
                json=body,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if response.status_code == 200:
                return True
            raise Exception(f"Matrix API error {response.status_code}: {response.text}")

    @staticmethod
    async def send_notice(config: Dict, room_id: str, content: str) -> bool:
        """Send m.notice (bot-style, typically not highlighted)."""
        import httpx
        import uuid

        homeserver_url = config.get('homeserver_url', 'https://matrix.org').rstrip('/')
        access_token = config.get('access_token')
        target_room = room_id if room_id.startswith('!') else config.get('room_id', room_id)
        event_id = str(uuid.uuid4()).replace('-', '')

        url = f"{homeserver_url}/_matrix/client/v3/rooms/{target_room}/send/m.room.message/{event_id}"

        body = {
            "msgtype": "m.notice",
            "body": content[:65536]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                url,
                json=body,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 200

    @staticmethod
    async def send_rich_message(config: Dict, room_id: str, media: RichMediaContent) -> bool:
        """Send formatted message with potential images."""
        # Matrix doesn't have native rich cards, use HTML formatting
        return await MatrixAdapter.send_message(config, room_id, media.text)

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse Matrix event (from Application Service or webhook)."""
        content_obj = payload.get('content', {})
        msgtype = content_obj.get('msgtype', 'm.text')
        sender = payload.get('sender', '')
        room_id = payload.get('room_id', '')

        text = content_obj.get('body', '')
        msg_type = 'text'
        format_type = content_obj.get('format', '')

        type_map = {
            'm.image': ('[Image]', 'image'),
            'm.audio': ('[Audio]', 'audio'),
            'm.video': ('[Video]', 'video'),
            'm.file': (f"[File: {content_obj.get('body', 'unknown')}]", 'file'),
            'm.location': ('[Location]', 'location'),
        }

        if msgtype in type_map:
            text, msg_type = type_map[msgtype]
            if msgtype == 'm.image':
                url = content_obj.get('url', '')
                # MXC to HTTP conversion would happen here if needed
            elif msgtype == 'm.location':
                geo = content_obj.get('geo_uri', '')
                text = f"[Location: {geo}]"

        return {
            'sender_id': room_id,
            'sender_name': sender,
            'content': text,
            'message_type': msg_type,
            'format': format_type,
            'raw_payload': payload
        }

    @staticmethod
    async def login(homeserver_url: str, username: str, password: str) -> Dict[str, str]:
        """Obtain access_token via password login."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{homeserver_url}/_matrix/client/v3/login",
                json={
                    "type": "m.login.password",
                    "identifier": {"type": "m.id.user", "user": username},
                    "password": password
                }
            )
            data = response.json()
            if 'access_token' not in data:
                raise Exception(f"Matrix login failed: {data}")
            return {
                'access_token': data['access_token'],
                'device_id': data.get('device_id'),
                'user_id': data.get('user_id')
            }


class iMessageAdapter:
    """
    iMessage — macOS only.
    Backends: "applescript" (default) or "bluebubbles"
    Config keys: backend, bb_url, bb_password
    """

    @staticmethod
    async def send_message(config: Dict, recipient: str, content: str) -> bool:
        """Send iMessage via selected backend."""
        backend = config.get('backend', 'applescript')

        if backend == 'bluebubbles':
            return await iMessageAdapter._send_via_bluebubbles(config, recipient, content)
        else:
            return await iMessageAdapter._send_via_applescript(recipient, content)

    @staticmethod
    async def _send_via_applescript(recipient: str, content: str) -> bool:
        """Send via AppleScript/osascript."""
        import asyncio

        # Sanitize for AppleScript
        safe_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        safe_recipient = recipient.replace('"', '\\"')

        script = f'''
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "{safe_recipient}" of targetService
    send "{safe_content}" to targetBuddy
end tell
'''

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=30
            )
        )

        if result.returncode != 0:
            raise Exception(f"AppleScript error: {result.stderr.strip()}")
        return True

    @staticmethod
    async def _send_via_bluebubbles(config: Dict, recipient: str, content: str) -> bool:
        """Send via BlueBubbles REST API."""
        import httpx

        bb_url = config.get('bb_url', 'http://localhost:1234').rstrip('/')
        bb_password = config.get('bb_password')

        if not bb_password:
            raise ValueError("iMessage (BlueBubbles) not configured: missing bb_password")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{bb_url}/api/v1/message/text",
                params={"password": bb_password},
                json={
                    "chatGuid": f"iMessage;-;{recipient}",
                    "message": content[:65536],
                    "method": "apple-script"
                }
            )
            data = response.json()
            if data.get('status') == 200:
                return True
            raise Exception(f"BlueBubbles error: {data.get('message', response.text)}")

    @staticmethod
    def parse_webhook(payload: Dict) -> Dict[str, Any]:
        """Parse incoming iMessage from BlueBubbles."""
        # BlueBubbles format
        if 'data' in payload:
            data = payload['data']
            handle = data.get('handle', {})
            text = data.get('text', '')
            is_from_me = data.get('isFromMe', False)

            if is_from_me:
                raise ValueError("Ignoring self-sent iMessage")

            return {
                'sender_id': handle.get('address'),
                'sender_name': handle.get('displayName') or handle.get('address'),
                'content': text,
                'message_type': 'text',
                'date': data.get('date'),
                'raw_payload': payload
            }

        # Generic format
        return {
            'sender_id': payload.get('sender') or payload.get('from'),
            'sender_name': payload.get('sender_name'),
            'content': payload.get('content') or payload.get('text', ''),
            'message_type': 'text',
            'raw_payload': payload
        }

    @staticmethod
    def is_available() -> bool:
        """Check if iMessage sending is possible."""
        import platform
        if platform.system() != 'Darwin':
            return False
        result = subprocess.run(
            ['osascript', '-e', 'tell application "Messages" to get name'],
            capture_output=True, text=True
        )
        return result.returncode == 0

    @staticmethod
    async def get_chats(config: Dict) -> List[Dict]:
        """Get recent chats via BlueBubbles."""
        import httpx

        bb_url = config.get('bb_url', 'http://localhost:1234').rstrip('/')
        bb_password = config.get('bb_password')

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{bb_url}/api/v1/chat/query",
                params={"password": bb_password, "limit": 20}
            )
            data = response.json()
            if data.get('status') == 200:
                return data.get('data', [])
            return []