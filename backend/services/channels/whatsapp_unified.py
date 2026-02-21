"""
Unified WhatsApp Adapter supporting both Cloud API and Web Bridge (Baileys) modes.
"""

import asyncio
import json
import secrets
import websockets
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import httpx
import hmac
import hashlib

from backend.services.channels.base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage, ExternalChannel, ChannelStatus


class WhatsAppProvider(Enum):
    CLOUD_API = "cloud_api"      # Official Meta Graph API
    WEB_BRIDGE = "web_bridge"    # Baileys/WebSocket bridge


@dataclass
class BridgeConnection:
    """Tracks WebSocket bridge connection state."""
    ws: Optional[Any] = None
    connected: bool = False
    qr_code: Optional[str] = None
    qr_expires_at: Optional[datetime] = None
    authenticated: bool = False
    last_ping: Optional[datetime] = None
    message_queue: list = field(default_factory=list)


class UnifiedWhatsAppAdapter(BaseChannelAdapter):
    """
    Unified adapter for WhatsApp supporting both official Cloud API and unofficial Web Bridge.
    
    Provider selection via config:
    - provider: "cloud_api" -> Uses Meta Graph API (production, official)
    - provider: "web_bridge" -> Uses Baileys WebSocket bridge (development, QR-based)
    """
    
    # Cloud API constants
    CLOUD_API_BASE = "https://graph.facebook.com/v18.0"
    
    # Bridge connections registry (class-level to persist across instances)
    _bridge_connections: Dict[str, BridgeConnection] = {}
    _bridge_tasks: Dict[str, asyncio.Task] = {}
    
    def __init__(self, channel: ExternalChannel):
        super().__init__(channel)
        self.provider = WhatsAppProvider(self.config.get("provider", "cloud_api"))
        self._cloud_client: Optional[httpx.AsyncClient] = None
        
    # ═══════════════════════════════════════════════════════════
    # PUBLIC API (Common Interface)
    # ═══════════════════════════════════════════════════════════
    
    async def send_message(self, message: ExternalMessage) -> bool:
        """Send message via selected provider."""
        if self.provider == WhatsAppProvider.CLOUD_API:
            return await self._send_cloud_api(message)
        else:
            return await self._send_bridge(message)
    
    async def validate_config(self) -> bool:
        """Validate configuration for selected provider."""
        if self.provider == WhatsAppProvider.CLOUD_API:
            return self._validate_cloud_config()
        else:
            return self._validate_bridge_config()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get detailed status including QR code for bridge mode."""
        if self.provider == WhatsAppProvider.CLOUD_API:
            return await self._get_cloud_status()
        else:
            return self._get_bridge_status()
    
    async def initialize(self) -> bool:
        """Initialize the adapter (start bridge connection if needed)."""
        if self.provider == WhatsAppProvider.WEB_BRIDGE:
            return await self._start_bridge_connection()
        return True
    
    async def shutdown(self) -> None:
        """Cleanup resources."""
        if self.provider == WhatsAppProvider.WEB_BRIDGE:
            await self._stop_bridge_connection()
        if self._cloud_client:
            await self._cloud_client.aclose()
    
    # ═══════════════════════════════════════════════════════════
    # CLOUD API IMPLEMENTATION (Official Meta API)
    # ═══════════════════════════════════════════════════════════
    
    def _validate_cloud_config(self) -> bool:
        """Validate Cloud API credentials."""
        required = ["phone_number_id", "access_token"]
        return all(k in self.config for k in required)
    
    async def _send_cloud_api(self, message: ExternalMessage) -> bool:
        """Send via Meta Graph API."""
        phone_number_id = self.config.get("phone_number_id")
        access_token = self.config.get("access_token")
        recipient = message.sender_id
        
        if not all([phone_number_id, access_token, recipient]):
            raise ValueError("Missing Cloud API configuration")
        
        url = f"{self.CLOUD_API_BASE}/{phone_number_id}/messages"
        
        # Build payload based on message type
        payload = self._build_cloud_payload(message)
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                return True
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('retry-after', 60))
                await asyncio.sleep(retry_after)
                response = await client.post(url, json=payload, headers=headers)
                return response.status_code == 200
            
            raise Exception(f"Cloud API error: {response.text}")
    
    def _build_cloud_payload(self, message: ExternalMessage) -> Dict[str, Any]:
        """Build appropriate payload for Cloud API."""
        recipient = message.sender_id
        content = message.content or ""
        
        # Check for media attachments
        raw_payload = message.raw_payload or {}
        rich_media = raw_payload.get('rich_media', {})
        attachments = rich_media.get('attachments', [])
        
        # If has media, send as media message
        if attachments:
            att = attachments[0]
            att_type = att.get('type', 'text')
            
            if att_type == 'image':
                return {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "image",
                    "image": {
                        "link": att.get('url'),
                        "caption": content[:1024] if content else None
                    }
                }
            elif att_type == 'document':
                return {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": recipient,
                    "type": "document",
                    "document": {
                        "link": att.get('url'),
                        "filename": att.get('filename', 'document.pdf')
                    }
                }
        
        # Default text message
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"body": content[:4096]}
        }
    
    async def _get_cloud_status(self) -> Dict[str, Any]:
        """Get Cloud API connection status."""
        access_token = self.config.get("access_token")
        phone_number_id = self.config.get("phone_number_id")
        
        if not all([access_token, phone_number_id]):
            return {
                "connected": False,
                "error": "Missing credentials",
                "provider": "cloud_api"
            }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.CLOUD_API_BASE}/{phone_number_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                data = response.json()
                
                return {
                    "connected": response.status_code == 200 and 'id' in data,
                    "provider": "cloud_api",
                    "phone_number": data.get('display_phone_number'),
                    "verified": data.get('is_valid_number', False),
                    "account_mode": data.get('account_mode', 'unknown')
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "provider": "cloud_api"
            }
    
    # ═══════════════════════════════════════════════════════════
    # WEB BRIDGE IMPLEMENTATION (Baileys/WebSocket)
    # ═══════════════════════════════════════════════════════════
    
    def _validate_bridge_config(self) -> bool:
        """Validate Web Bridge configuration."""
        bridge_url = self.config.get("bridge_url", "ws://localhost:3000")
        return bool(bridge_url)
    
    async def _start_bridge_connection(self) -> bool:
        """Start WebSocket connection to Node.js bridge."""
        channel_id = self.channel.id
        
        # Stop existing if any
        await self._stop_bridge_connection()
        
        # Create new connection state
        conn = BridgeConnection()
        self._bridge_connections[channel_id] = conn
        
        # Start connection task
        task = asyncio.create_task(self._bridge_connection_loop())
        self._bridge_tasks[channel_id] = task
        
        return True
    
    async def _stop_bridge_connection(self) -> None:
        """Stop bridge connection."""
        channel_id = self.channel.id
        
        # Cancel task
        if channel_id in self._bridge_tasks:
            self._bridge_tasks[channel_id].cancel()
            try:
                await self._bridge_tasks[channel_id]
            except asyncio.CancelledError:
                pass
            del self._bridge_tasks[channel_id]
        
        # Close WebSocket
        if channel_id in self._bridge_connections:
            conn = self._bridge_connections[channel_id]
            if conn.ws and not conn.ws.closed:
                await conn.ws.close()
            del self._bridge_connections[channel_id]
    
    async def _bridge_connection_loop(self) -> None:
        """Maintain persistent WebSocket connection to bridge."""
        channel_id = self.channel.id
        bridge_url = self.config.get("bridge_url", "ws://localhost:3000")
        bridge_token = self.config.get("bridge_token")
        
        reconnect_delay = 5
        max_reconnect_delay = 60
        
        while True:
            try:
                print(f"[WhatsApp Bridge {channel_id}] Connecting to {bridge_url}...")
                
                async with websockets.connect(bridge_url) as ws:
                    conn = self._bridge_connections.get(channel_id)
                    if conn:
                        conn.ws = ws
                        conn.connected = True
                        conn.last_ping = datetime.utcnow()
                    
                    # Send auth if token configured
                    if bridge_token:
                        await ws.send(json.dumps({
                            "type": "auth",
                            "token": bridge_token
                        }))
                    
                    print(f"[WhatsApp Bridge {channel_id}] Connected")
                    
                    # Listen for messages
                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            print(f"[WhatsApp Bridge {channel_id}] Message handler error: {e}")
                
            except asyncio.CancelledError:
                print(f"[WhatsApp Bridge {channel_id}] Connection cancelled")
                raise
            except Exception as e:
                print(f"[WhatsApp Bridge {channel_id}] Connection error: {e}")
                
                # Update connection state
                conn = self._bridge_connections.get(channel_id)
                if conn:
                    conn.connected = False
                    conn.authenticated = False
                
                # Exponential backoff
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def _handle_bridge_message(self, raw_message: str) -> None:
        """Handle incoming message from bridge."""
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            print(f"[WhatsApp Bridge] Invalid JSON: {raw_message[:200]}")
            return
        
        msg_type = data.get("type")
        channel_id = self.channel.id
        conn = self._bridge_connections.get(channel_id)
        
        if msg_type == "qr":
            # QR code received - store for polling
            if conn:
                conn.qr_code = data.get("qr")
                conn.qr_expires_at = datetime.utcnow() + timedelta(minutes=5)
                conn.authenticated = False
            print(f"[WhatsApp Bridge {channel_id}] QR code received")
            
        elif msg_type == "status":
            status = data.get("status")
            if conn:
                conn.authenticated = (status == "connected")
                if status == "connected":
                    conn.qr_code = None  # Clear QR on success
            print(f"[WhatsApp Bridge {channel_id}] Status: {status}")
            
        elif msg_type == "message":
            # Incoming WhatsApp message
            await self._process_bridge_incoming(data)
            
        elif msg_type == "error":
            print(f"[WhatsApp Bridge {channel_id}] Error: {data.get('error')}")
    
    async def _process_bridge_incoming(self, data: Dict[str, Any]) -> None:
        """Process incoming message from bridge and route to ChannelManager."""
        from backend.services.channel_manager import ChannelManager
        
        # Extract sender info
        sender_pn = data.get("pn", "")  # Old phone number format
        sender_lid = data.get("sender", "")  # New LID format
        content = data.get("content", "")
        is_group = data.get("isGroup", False)
        
        # Use LID if available, fallback to PN
        sender_id = sender_lid if sender_lid else sender_pn
        chat_id = sender_lid if sender_lid else sender_pn
        
        # Clean sender ID (remove @s.whatsapp.net)
        sender_clean = sender_id.split("@")[0] if "@" in sender_id else sender_id
        
        # Handle voice messages
        if content == "[Voice Message]":
            content = "[Voice Message: Transcription not available]"
        
        # Route through ChannelManager
        await ChannelManager.receive_message(
            channel_id=self.channel.id,
            sender_id=sender_clean,
            sender_name=data.get("pushName") or sender_clean,
            content=content,
            message_type="text",
            media_url=None,
            raw_payload={
                "bridge_message": data,
                "is_group": is_group,
                "sender_lid": sender_lid,
                "sender_pn": sender_pn
            }
        )
    
    async def _send_bridge(self, message: ExternalMessage) -> bool:
        """Send message via WebSocket bridge."""
        channel_id = self.channel.id
        conn = self._bridge_connections.get(channel_id)
        
        if not conn or not conn.ws or not conn.connected:
            raise Exception("Bridge not connected")
        
        # Build bridge payload
        # Bridge expects full JID format for recipient
        recipient = message.sender_id
        if "@" not in recipient:
            # Assume it's a phone number, append domain
            recipient = f"{recipient}@s.whatsapp.net"
        
        payload = {
            "type": "send",
            "to": recipient,
            "text": message.content or ""
        }
        
        try:
            await conn.ws.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as e:
            raise Exception(f"Bridge send failed: {e}")
    
    def _get_bridge_status(self) -> Dict[str, Any]:
        """Get Web Bridge connection status."""
        channel_id = self.channel.id
        conn = self._bridge_connections.get(channel_id)
        
        if not conn:
            return {
                "connected": False,
                "authenticated": False,
                "qr_code": None,
                "provider": "web_bridge"
            }
        
        # Check if QR expired
        qr_valid = False
        if conn.qr_code and conn.qr_expires_at:
            qr_valid = datetime.utcnow() < conn.qr_expires_at
        
        return {
            "connected": conn.connected,
            "authenticated": conn.authenticated,
            "qr_code": conn.qr_code if qr_valid else None,
            "qr_expires_at": conn.qr_expires_at.isoformat() if conn.qr_expires_at else None,
            "provider": "web_bridge",
            "has_pending_messages": len(conn.message_queue) > 0
        }
    
    # ═══════════════════════════════════════════════════════════
    # WEBHOOK PARSING (Cloud API)
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def parse_cloud_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Meta Graph API webhook payload."""
        try:
            entry = payload.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            messages = value.get('messages', [])
            contacts = value.get('contacts', [])
            
            if not messages:
                raise ValueError("No messages in webhook")
            
            msg = messages[0]
            contact = contacts[0] if contacts else {}
            
            msg_type = msg.get('type', 'text')
            
            # Extract content based on type
            content = ""
            media_url = None
            
            if msg_type == 'text':
                content = msg.get('text', {}).get('body', '')
            elif msg_type == 'image':
                content = msg.get('image', {}).get('caption', '[Image]')
                media_url = msg.get('image', {}).get('link')
            elif msg_type == 'document':
                content = f"[Document: {msg.get('document', {}).get('filename', 'unknown')}]"
                media_url = msg.get('document', {}).get('link')
            elif msg_type == 'audio':
                content = '[Voice message]'
                media_url = msg.get('audio', {}).get('link')
            elif msg_type == 'video':
                content = msg.get('video', {}).get('caption', '[Video]')
                media_url = msg.get('video', {}).get('link')
            elif msg_type == 'location':
                loc = msg.get('location', {})
                content = f"[Location: {loc.get('latitude')}, {loc.get('longitude')}]"
            
            return {
                'sender_id': msg.get('from'),
                'sender_name': contact.get('profile', {}).get('name') if contact else None,
                'content': content,
                'message_type': msg_type,
                'media_url': media_url,
                'timestamp': msg.get('timestamp'),
                'message_id': msg.get('id'),
                'raw_payload': payload
            }
            
        except Exception as e:
            raise ValueError(f"Failed to parse Cloud API webhook: {e}")
    
    @staticmethod
    def verify_cloud_signature(app_secret: str, body: bytes, signature: str) -> bool:
        """Verify Meta webhook signature."""
        if not signature:
            return False
        
        expected = hmac.new(
            app_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if signature.startswith('sha256='):
            expected = f"sha256={expected}"
        
        return hmac.compare_digest(expected, signature)