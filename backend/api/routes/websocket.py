"""
WebSocket endpoint for real-time chat with authentication.
"""

import json
import logging
import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, get_db
from backend.models.entities import Agent, HeadOfCouncil
from backend.services.chat_service import ChatService
from backend.services.model_provider import is_thinking_config
from backend.models.entities.user_config import UserModelConfig
from backend.core.config import settings
from backend.models.entities.user import User
from backend.api.dependencies.auth import get_current_user
from backend.core.redis import get_redis_client
import redis.asyncio as redis

from backend.core.correlation_middleware import ws_correlation_manager
from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter()

logger = logging.getLogger(__name__)


# ── DB session helper ─────────────────────────────────────────────────────────

@contextmanager
def get_fresh_db():
    """
    Yield a brand-new SQLAlchemy session and always close it afterwards.
    Used inside the WebSocket message loop so every message gets a clean
    session — avoids stale-data and detached-instance bugs on long-lived
    connections.
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── JWT helper ────────────────────────────────────────────────────────────────

def _decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT.  Returns the payload dict on success,
    or None on any failure.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if not payload.get("sub"):
            return None
        return payload
    except JWTError:
        return None


# ── File context helper ───────────────────────────────────────────────────────

def _build_enriched_message(content: str, attachments: List[dict]) -> str:
    """
    Combine the user's text message with extracted file content.
    """
    if not attachments:
        return content

    try:
        from backend.services.file_processor import build_file_context_for_ai
        file_context = build_file_context_for_ai(attachments, max_total_chars=30_000)
    except Exception as exc:
        logger.error(f"[WebSocket] file_processor import/call failed: {exc}")
        file_context = ""

    if not file_context:
        return content

    if content:
        return f"{content}\n\n{file_context}"
    return file_context


# ═══════════════════════════════════════════════════════════
# Connection Manager
# ═══════════════════════════════════════════════════════════

class ConnectionManager:
    """Manage authenticated WebSocket connections with heartbeat support."""

    def __init__(self):
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        self.user_connections: Dict[str, WebSocket] = {}
        self.redis_client: Optional[redis.Redis] = None
        # Track which event loop the cached redis client is bound to.  Celery
        # broadcast tasks spin up (and close) a fresh loop on every invocation,
        # so a client bound to a closed loop raises "Event loop is closed".
        self._redis_loop: Optional["asyncio.AbstractEventLoop"] = None

        # ── Pub/Sub for cross-worker event distribution (13.3) ──────────────────
        self._pubsub: Optional["redis.client.PubSub"] = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._user_channels: set = set()  # Track subscribed ws:user:{username}

    async def _get_redis(self) -> redis.Redis:
        current_loop = asyncio.get_running_loop()
        if self.redis_client is None or self._redis_loop is not current_loop:
            if self.redis_client is not None:
                try:
                    await self.redis_client.aclose()
                except Exception:
                    pass
            self.redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis_loop = current_loop
        return self.redis_client

    # ── connection lifecycle ─────────────────────────────────────────────────

    async def authenticate(
        self,
        websocket: WebSocket,
        token: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate JWT and resolve the Head of Council identity.
        Returns user_info dict on success, None on failure.
        """
        payload = _decode_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return None

        username = payload["sub"]

        try:
            with get_fresh_db() as db:
                head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
                if not head:
                    # Head of Council not yet created.  Two sub-cases:
                    #
                    # 1. genesis_triggered=False — no API key has been saved yet.
                    #    The frontend should stay silent; showing a banner here
                    #    would be premature (the user hasn't done anything yet).
                    #
                    # 2. genesis_triggered=True — an API key exists so genesis
                    #    has been kicked off and is still running.  The frontend
                    #    shows a "System Initializing…" banner and polls every 10 s.
                    #
                    # We determine this by checking whether any UserModelConfig row
                    # exists, which is created when the user saves their first API
                    # key on the Models page (POST /api/v1/models/configs).
                    genesis_triggered = False
                    try:
                        from backend.models.entities import UserModelConfig
                        genesis_triggered = db.query(UserModelConfig).limit(1).first() is not None
                    except Exception:
                        pass  # if the table doesn't exist yet, treat as not triggered

                    try:
                        await websocket.send_json({
                            "type":              "system_not_ready",
                            # genesis_triggered tells the frontend whether to show
                            # the initializing banner (True) or stay silent (False).
                            "genesis_triggered": genesis_triggered,
                            "content":           (
                                "System is initializing — genesis is running. "
                                "This usually takes under a minute."
                            ) if genesis_triggered else (
                                "System is not yet initialized. "
                                "Please add an API key on the Models page — "
                                "genesis will start automatically."
                            ),
                            "timestamp":         datetime.utcnow().isoformat(),
                        })
                    except Exception:
                        pass  # socket may already be closing
                    await websocket.close(code=1013, reason="Genesis in progress — Head of Council not yet created")
                    return None
                head_agent_id    = head.id
                head_agentium_id = head.agentium_id
        except Exception as exc:
            await websocket.close(code=1011, reason=f"DB error during auth: {exc}")
            return None

        user_info = {
            "username":         username,
            "role":             payload.get("role", "sovereign"),
            "user_id":          payload.get("user_id"),
            "head_agent_id":    head_agent_id,
            "head_agentium_id": head_agentium_id,
        }

        self.active_connections[websocket] = user_info
        self.user_connections[username]    = websocket

        # Subscribe to user's per-user Pub/Sub channel
        await self.subscribe_user(username)

        logger.info(f"[WebSocket] ✅ Authenticated: {username} ({datetime.utcnow().isoformat()})")
        return user_info

    def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """Remove connection; return username if found."""
        username = None
        if websocket in self.active_connections:
            user_info = self.active_connections.pop(websocket)
            username  = user_info.get("username")
            if username and username in self.user_connections:
                del self.user_connections[username]
            # Unsubscribe from user's per-user Pub/Sub channel
            if username:
                # Run unsubscribe in background since we're in a sync method
                asyncio.create_task(self.unsubscribe_user(username))
            # Clear WebSocket correlation context
            ws_correlation_manager.clear_connection_context(websocket)
            logger.error(f"[WebSocket] ❌ Disconnected: {username}")
        return username

    # ── Pub/Sub for cross-worker event distribution (13.3) ──────────────────────

    async def _ensure_pubsub(self):
        """Lazy-init Pub/Sub subscription to ws:broadcast."""
        if self._pubsub is None:
            r = await self._get_redis()
            self._pubsub = await r.pubsub()
            await self._pubsub.subscribe("ws:broadcast")
            self._pubsub_task = asyncio.create_task(self._listen_pubsub())
            logger.info("[ConnectionManager] Pub/Sub initialized, subscribed to ws:broadcast")

    async def subscribe_user(self, username: str):
        """Subscribe to per-user channel when user connects."""
        await self._ensure_pubsub()
        channel = f"ws:user:{username}"
        if channel not in self._user_channels:
            await self._pubsub.subscribe(channel)
            self._user_channels.add(channel)
            logger.info(f"[ConnectionManager] Subscribed to {channel} for user {username}")

    async def unsubscribe_user(self, username: str):
        """Unsubscribe from per-user channel when user disconnects."""
        if self._pubsub:
            channel = f"ws:user:{username}"
            if channel in self._user_channels:
                await self._pubsub.unsubscribe(channel)
                self._user_channels.discard(channel)
                logger.info(f"[ConnectionManager] Unsubscribed from {channel} for user {username}")

    async def _listen_pubsub(self):
        """Background task: forward Pub/Sub messages to local WebSocket connections."""
        try:
            async for message in self._pubsub.listen():
                if message['type'] == 'message':
                    try:
                        event = json.loads(message['data'])
                        channel = message['channel']

                        # Determine target: global, user, or room
                        if channel == "ws:broadcast":
                            await self._broadcast_local(event)
                        elif channel.startswith("ws:user:"):
                            username = channel.split("ws:user:", 1)[1]
                            await self.send_personal_message(event, username)
                        elif channel.startswith("ws:room:"):
                            # Future: forward to all users in room
                            pass
                    except json.JSONDecodeError:
                        logger.warning(f"[ConnectionManager] Invalid JSON in Pub/Sub message: {message['data']}")
                    except Exception as e:
                        logger.error(f"[ConnectionManager] Error processing Pub/Sub message: {e}")
        except asyncio.CancelledError:
            logger.info("[ConnectionManager] Pub/Sub listener cancelled")
        except Exception as e:
            logger.error(f"[ConnectionManager] Pub/Sub listen error: {e}")

    async def _broadcast_local(self, message: dict, exclude: Optional[WebSocket] = None) -> None:
        """Broadcast JSON message to local connections only (no Redis Pub/Sub)."""
        disconnected = []
        for connection, user_info in list(self.active_connections.items()):
            if connection is exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.error(f"[WebSocket] Local broadcast error to {user_info.get('username')}: {exc}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    # ── send helpers ─────────────────────────────────────────────────────────

    async def send_personal_message(self, message: dict, username: str) -> bool:
        """Send JSON message to a specific connected user."""
        if username in self.user_connections:
            try:
                await self.user_connections[username].send_json(message)
                return True
            except Exception as exc:
                logger.error(f"[WebSocket] Error sending to {username}: {exc}")
        return False

    async def broadcast(self, message: dict, exclude: Optional[WebSocket] = None) -> None:
        """Broadcast JSON message to all authenticated connections."""
        try:
            r        = await self._get_redis()
            msg_str  = json.dumps(message)
            pipeline = r.pipeline()
            pipeline.lpush("agentium:ws:buffer", msg_str)
            pipeline.ltrim("agentium:ws:buffer", 0, 99)
            pipeline.expire("agentium:ws:buffer", 60)
            await pipeline.execute()
        except Exception as exc:
            logger.error(f"[WebSocket] Event buffer push error: {exc}")

        disconnected = []
        for connection, user_info in list(self.active_connections.items()):
            if connection is exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.error(f"[WebSocket] Broadcast error to {user_info.get('username')}: {exc}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    def get_connection_count(self) -> int:
        return len(self.active_connections)

    # ── typed broadcast events ────────────────────────────────────────────────

    async def emit_agent_spawned(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        parent_id: Optional[str] = None,
    ) -> None:
        await self.broadcast({
            "type":       "agent_spawned",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "parent_id":  parent_id,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_browser_frame(
        self,
        task_id: str,
        frame: str,
        url: str,
        title: str,
        action_log: List[dict],
        frame_number: int,
    ) -> None:
        """Broadcast a live browser frame."""
        await self.broadcast({
            "type":         "browser_frame",
            "task_id":      task_id,
            "frame":        frame,
            "url":          url,
            "title":        title,
            "action_log":   action_log,
            "frame_number": frame_number,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_task_escalated(
        self,
        task_id: str,
        task_title: str,
        escalated_by: str,
        reason: str,
    ) -> None:
        await self.broadcast({
            "type":         "task_escalated",
            "task_id":      task_id,
            "task_title":   task_title,
            "escalated_by": escalated_by,
            "reason":       reason,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_vote_initiated(
        self,
        vote_id: str,
        subject: str,
        initiated_by: str,
        quorum_required: int,
    ) -> None:
        await self.broadcast({
            "type":            "vote_initiated",
            "vote_id":         vote_id,
            "subject":         subject,
            "initiated_by":    initiated_by,
            "quorum_required": quorum_required,
            "timestamp":       datetime.utcnow().isoformat(),
        })

    async def emit_constitutional_violation(
        self,
        violator_id: str,
        article: str,
        severity: str,
        description: str,
        requires_vote: bool = False,
    ) -> None:
        await self.broadcast({
            "type":          "constitutional_violation",
            "violator_id":   violator_id,
            "article":       article,
            "severity":      severity,
            "description":   description,
            "requires_vote": requires_vote,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_message_routed(
        self,
        channel: str,
        sender: str,
        task_id: str,
        requires_approval: bool = False,
    ) -> None:
        await self.broadcast({
            "type":              "message_routed",
            "channel":           channel,
            "sender":            sender,
            "task_id":           task_id,
            "requires_approval": requires_approval,
            "timestamp":         datetime.utcnow().isoformat(),
        })

    async def emit_knowledge_submitted(
        self,
        agent_id: str,
        topic: str,
        requires_vote: bool = True,
    ) -> None:
        await self.broadcast({
            "type":          "knowledge_submitted",
            "agent_id":      agent_id,
            "topic":         topic,
            "requires_vote": requires_vote,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_knowledge_approved(
        self,
        topic: str,
        approved_by: str,
    ) -> None:
        await self.broadcast({
            "type":        "knowledge_approved",
            "topic":       topic,
            "approved_by": approved_by,
            "timestamp":   datetime.utcnow().isoformat(),
        })

    async def emit_amendment_proposed(
        self,
        proposer_id: str,
        article: str,
        description: str,
        requires_vote: bool = True,
    ) -> None:
        await self.broadcast({
            "type":          "amendment_proposed",
            "proposer_id":   proposer_id,
            "article":       article,
            "description":   description,
            "requires_vote": requires_vote,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_agent_liquidated(
        self,
        agent_id: str,
        agent_name: str,
        liquidated_by: str,
        reason: str,
        tasks_reassigned: int = 0,
    ) -> None:
        await self.broadcast({
            "type":             "agent_liquidated",
            "agent_id":         agent_id,
            "agent_name":       agent_name,
            "liquidated_by":    liquidated_by,
            "reason":           reason,
            "tasks_reassigned": tasks_reassigned,
            "timestamp":        datetime.utcnow().isoformat(),
        })

    async def emit_agent_promoted(
        self,
        old_agentium_id: str,
        new_agentium_id: str,
        agent_name: str,
        promoted_by: str,
        reason: str,
    ) -> None:
        """Broadcast when a Task Agent is promoted to Lead Agent."""
        await self.broadcast({
            "type":            "agent_promoted",
            "old_agentium_id": old_agentium_id,
            "new_agentium_id": new_agentium_id,
            "agent_name":      agent_name,
            "promoted_by":     promoted_by,
            "reason":          reason,
            "timestamp":       datetime.utcnow().isoformat(),
        })

    async def emit_agent_status_changed(
        self,
        agent_id: str,
        agent_name: str,
        old_status: str,
        new_status: str,
    ) -> None:
        """Broadcast when an agent's status changes."""
        await self.broadcast({
            "type":       "agent_status_changed",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "old_status": old_status,
            "new_status": new_status,
            "status":     new_status,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_agent_status(
        self,
        agent_id: str,
        status: str,
        agent_name: Optional[str] = None,
        old_status: Optional[str] = None,
    ) -> None:
        """Broadcast agent status update in real-time (TODO 13.2.1)."""
        await self.broadcast({
            "type":       "agent_status",
            "agent_id":   agent_id,
            "agent_name": agent_name or agent_id,
            "status":     status,
            "new_status": status,
            "old_status": old_status,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_task_update(
        self,
        task_id: str,
        status: str,
        progress: Optional[int] = None,
        title: Optional[str] = None,
        result_summary: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Broadcast task progress and state update in real-time (TODO 13.2.2)."""
        await self.broadcast({
            "type":           "task_update",
            "task_id":        task_id,
            "status":         status,
            "progress":       progress,
            "title":          title,
            "result_summary": result_summary,
            "metadata":       metadata or {},
            "timestamp":      datetime.utcnow().isoformat(),
        })

    async def emit_channel_status(
        self,
        channel_id: str,
        status: str,
        health_status: Optional[str] = None,
        metrics: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Broadcast channel status and health update in real-time (TODO 13.2.5)."""
        await self.broadcast({
            "type":          "channel_status",
            "channel_id":    channel_id,
            "status":        status,
            "health_status": health_status or status,
            "metrics":       metrics or {},
            "error":         error,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_system_alert(
        self,
        message: str,
        severity: str = "warning",
        alert_type: str = "general",
        metadata: Optional[dict] = None,
    ) -> None:
        """Broadcast system alert notification to all connected clients (TODO 13.2.6)."""
        await self.broadcast({
            "type":       "system_alert",
            "message":    message,
            "severity":   severity,
            "alert_type": alert_type,
            "metadata":   metadata or {},
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_vote_update(
        self,
        vote_id: str,
        vote_type: str,
        voter: str,
        vote: str,
        tally: dict,
        status: Optional[str] = None,
    ) -> None:
        """Broadcast vote tally update to all connected clients (TODO 13.2.7)."""
        await self.broadcast({
            "type":      "vote_update",
            "vote_id":   vote_id,
            "vote_type": vote_type,
            "voter":     voter,
            "vote":      vote,
            "tally":     tally,
            "status":    status,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def emit_tool_execution(
        self,
        tool_name: Optional[str] = None,
        status: str = "in_progress",
        tool_count: Optional[int] = None,
        tool_names: Optional[List[str]] = None,
        stream_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """Broadcast tool execution progress in real-time (TODO 13.2.8)."""
        names = tool_names or ([tool_name] if tool_name else [])
        await self.broadcast({
            "type":        "tool_execution",
            "tool_name":   tool_name or (names[0] if names else "tool"),
            "tool_names":  names,
            "tool_count":  tool_count or len(names),
            "status":      status,
            "stream_id":   stream_id,
            "agent_id":    agent_id,
            "timestamp":   datetime.utcnow().isoformat(),
        })


    # ── Phase 15.2: MCP stats broadcast ──────────────────────────────────────

    async def emit_mcp_stats_update(
        self,
        stats: List[Dict[str, Any]],
    ) -> None:
        """
        Phase 15.2: Broadcast real-time MCP tool stats to all connected clients.

        Called by the Celery beat task `broadcast_mcp_stats` every 30 seconds.
        Frontend MCPToolRegistry subscribes to 'mcp_stats_update' and updates
        the Invocations / Avg Latency / Error Rate columns in real-time.

        Args:
            stats: List of per-tool stat dicts from mcp_stats_service.get_all_stats()
                   Each dict: { tool_id, invocation_count, avg_latency_ms,
                                error_rate, error_count, last_used_ts }
        """
        await self.broadcast({
            "type":      "mcp_stats_update",
            "stats":     stats,
            "count":     len(stats),
            "timestamp": datetime.utcnow().isoformat(),
        })

    # ── Phase 15.2 / Phase 6: MCP revocation broadcast ────────────────────────

    async def emit_mcp_tool_revoked(
        self,
        tool_id: str,
        tool_name: str,
        reason: str,
        revoked_by: str,
    ) -> None:
        """
        Broadcast MCP tool revocation to all connected clients.

        Called synchronously from the revoke endpoint after successful Redis write.

        WebSocket payload:
            {
                "type":       "mcp_tool_revoked",
                "tool_id":    "<uuid>",
                "tool_name":  "<name>",
                "reason":     "<revocation reason>",
                "revoked_by": "<agentium_id>",
                "timestamp":  "<ISO8601>"
            }
        """
        await self.broadcast({
            "type":       "mcp_tool_revoked",
            "tool_id":    tool_id,
            "tool_name":  tool_name,
            "reason":     reason,
            "revoked_by": revoked_by,
            "timestamp":  datetime.utcnow().isoformat(),
        })


# ── global singleton ──────────────────────────────────────────────────────────
manager = ConnectionManager()


# ── genesis prompt re-delivery on fresh connections ───────────────────────────

async def _send_genesis_prompt_if_awaiting(websocket: WebSocket) -> None:
    """Push the nation-name prompt to a newly-authenticated client.

    After Head 00001 is early-committed, the WebSocket handshake succeeds and
    the client enters the ``active`` phase — but genesis may still be paused on
    the country-name prompt. The original broadcast was sent before this socket
    existed (nobody to receive it), so we re-deliver it here.
    """
    from backend.services import initialization_service as _init_svc

    active = _init_svc.get_active_genesis()
    if active is None or not getattr(active, "awaiting_country_name", False):
        return

    try:
        await websocket.send_json({
            "type":      "genesis_prompt",
            "role":      "head_of_council",
            "content":   active.country_name_prompt,
            "is_urgent": True,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "requires_response":  True,
                "timeout_seconds":    active.COUNTRY_NAME_TIMEOUT_SECONDS,
                "prompt_type":        "country_name",
            },
        })
        logger.info("[WebSocket] Re-delivered genesis_prompt to newly authenticated client")
    except Exception as exc:
        logger.warning(f"[WebSocket] Failed to re-deliver genesis_prompt: {exc}")


# ═══════════════════════════════════════════════════════════
# WebSocket endpoint (unchanged)
# ═══════════════════════════════════════════════════════════

@router.websocket("/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="[DEPRECATED] JWT — send via auth message instead"),
):
    """
    Authenticated WebSocket endpoint for Sovereign ↔ Head of Council chat.

    Preferred connection flow:
      1. Client connects (no token in URL)
      2. Client immediately sends: {"type": "auth", "token": "<JWT>"}
      3. Server validates and replies with welcome message
      4. All subsequent messages are processed

    Phase 15.2: also receives 'mcp_stats_update' broadcasts pushed by Celery.
    """
    await websocket.accept()

    # Extract correlation ID from headers for distributed tracing
    request_id = websocket.headers.get("x-request-id") or websocket.headers.get("x-correlation-id")
    ws_correlation_manager.set_connection_context(websocket, request_id)

    user_info: Optional[Dict[str, Any]] = None

    # Per-connection registry of in-flight streams so a later `cancel` message
    # can signal an ongoing generation via its asyncio.Event.
    active_streams: Dict[str, asyncio.Event] = {}
    pending_tasks: Dict[str, asyncio.Task] = {}

    if token:
        user_info = await manager.authenticate(websocket, token)
        if not user_info:
            return

        await websocket.send_json({
            "type":      "system",
            "role":      "system",
            "content":   (
                f"Welcome {user_info['username']}. "
                f"Connected to Head of Council ({user_info['head_agentium_id']}). "
                f"[Note: token-in-URL is deprecated; switch to auth-message flow]"
            ),
            "timestamp": datetime.utcnow().isoformat(),
        })
        # If genesis is currently awaiting the country name, push the prompt
        # directly to this newly-connected client.  The original broadcast
        # was sent before this socket existed (Head 00001 was early-committed
        # but the WS hadn't reconnected yet), so the client never saw it.
        await _send_genesis_prompt_if_awaiting(websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            # Use message context for correlation ID propagation
            message_request_id = data.get("request_id")
            with ws_correlation_manager.message_context(websocket, message_request_id):
                msg_type = data.get("type", "")

                # ── Auth message ──────────────────────────────────────────────────
                if msg_type == "auth":
                    if user_info is not None:
                        await websocket.send_json({
                            "type":      "system",
                            "content":   "Already authenticated.",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        continue

                    auth_token = data.get("token", "")
                    user_info  = await manager.authenticate(websocket, auth_token)
                    if not user_info:
                        return

                    await websocket.send_json({
                        "type":      "system",
                        "role":      "system",
                        "content":   (
                            f"Welcome {user_info['username']}. "
                            f"Connected to Head of Council ({user_info['head_agentium_id']})."
                        ),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    # See comment above — push genesis prompt if awaiting.
                    await _send_genesis_prompt_if_awaiting(websocket)
                    continue

            # ── Require authentication ────────────────────────────────────────
            if user_info is None:
                await websocket.send_json({
                    "type":      "auth_required",
                    "content":   "Please send an auth message first.",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            # ── Ping / heartbeat ──────────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({
                    "type":      "pong",
                    "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
                })
                continue

            # ── Cancel an in-flight stream ───────────────────────────────────
            if msg_type == "cancel":
                sid = data.get("stream_id")
                ev = active_streams.get(sid)
                if ev:
                    ev.set()
                continue

            # ── Chat message (supports 'message' and 'chat_message' - TODO 13.2.3) ──
            if msg_type in ("message", "chat_message"):
                content     = data.get("content", "").strip()
                attachments: List[dict] = data.get("attachments") or []
                card_response = data.get("card_response")

                enriched_message = _build_enriched_message(content, attachments)

                # A card answer carries no free-text content; don't drop it.
                if not enriched_message and not card_response:
                    continue

                loop = asyncio.get_running_loop()

                def _lookup_head_and_config():
                    with get_fresh_db() as db_s:
                        head = db_s.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
                        if not head:
                            return None, False
                        thinking_enabled = False
                        if head.preferred_config_id:
                            head_cfg = (
                                db_s.query(UserModelConfig)
                                .filter_by(id=head.preferred_config_id)
                                .first()
                            )
                            if head_cfg and is_thinking_config(head_cfg):
                                thinking_enabled = True
                        return head.id, thinking_enabled

                head_id, thinking_enabled = await loop.run_in_executor(None, _lookup_head_and_config)
                if not head_id:
                    await websocket.send_json({
                        "type":      "error",
                        "content":   "Head of Council is unavailable. Check system status.",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    continue

                extra_metadata = {"card_response": card_response} if card_response else None

                stream_id  = str(uuid.uuid4())
                message_id = str(uuid.uuid4())
                cancel_event = asyncio.Event()
                active_streams[stream_id] = cancel_event

                await websocket.send_json({
                    "type":       "message_start",
                    "stream_id":  stream_id,
                    "role":       "head_of_council",
                    "message_id": message_id,
                    "thinking":   thinking_enabled,
                    "timestamp":  datetime.utcnow().isoformat(),
                })

                # Run the (potentially long) generation in a background task
                # instead of awaiting it inside the receive loop. Awaiting
                # here would block the server from answering heartbeat pings
                # while the model streams a reply, causing the client's
                # pong-timeout to wrongly drop a healthy — but busy —
                # connection ("Head of Council goes offline mid-chat").
                # Defaults capture this iteration's values to avoid the
                # Python late-binding closure pitfall across loop iterations.

                async def on_delta(text: str, sid: str = stream_id) -> None:
                    try:
                        # Existing message_delta
                        await websocket.send_json({
                            "type":      "message_delta",
                            "stream_id": sid,
                            "delta":     text,
                        })
                        # chat_stream event for TODO 13.2.4
                        await websocket.send_json({
                            "type":      "chat_stream",
                            "stream_id": sid,
                            "chunk":     text,
                            "delta":     text,
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                    except Exception:
                        pass  # socket may be closing; the task handles it

                async def on_tool_start(
                    tool_calls: List[Dict],
                    cumulative: int,
                    sid: str = stream_id,
                ) -> None:
                    try:
                        tool_names = [
                            tc.get("function", {}).get("name", "tool")
                            if isinstance(tc, dict)
                            else getattr(getattr(tc, "function", None), "name", "tool")
                            for tc in tool_calls
                        ]
                        # tool_execution event for TODO 13.2.8
                        await websocket.send_json({
                            "type":        "tool_execution",
                            "stream_id":   sid,
                            "tool_names":  tool_names,
                            "tool_name":   tool_names[0] if tool_names else "tool",
                            "tool_count":  cumulative,
                            "status":      "in_progress",
                            "timestamp":   datetime.utcnow().isoformat(),
                        })
                        # tool_progress for backward compatibility
                        await websocket.send_json({
                            "type":       "tool_progress",
                            "stream_id":  sid,
                            "tool_count": cumulative,
                            "tool_names": tool_names,
                        })
                    except Exception:
                        pass

                async def _run_generation(
                    sid: str = stream_id,
                    msg: str = enriched_message,
                    meta: Optional[dict] = extra_metadata,
                    hid: Any = head_id,
                    cevent: asyncio.Event = cancel_event,
                ) -> None:
                    try:
                        with get_fresh_db() as gen_db:
                            gen_head = gen_db.query(HeadOfCouncil).filter_by(id=hid).first()
                            if not gen_head:
                                await websocket.send_json({
                                    "type":      "error",
                                    "content":   "Head of Council is unavailable. Check system status.",
                                    "timestamp": datetime.utcnow().isoformat(),
                                })
                                return

                            response = await ChatService.process_message(
                                gen_head, msg, gen_db,
                                extra_metadata=meta,
                                on_delta=on_delta,
                                on_tool_start=on_tool_start,
                                cancel_event=cevent,
                            )

                            finish = response.get("finish_reason", "stop") or "stop"
                            timestamp = datetime.utcnow().isoformat()
                            metadata = {
                                "model":        response.get("model"),
                                "tokens_used":  response.get("tokens_used", 0),
                                "task_created": response.get("task_created", False),
                                "task_id":      response.get("task_id"),
                                "agent_spawned": response.get("agent_spawned"),
                                "context_compressed": response.get("context_compressed", False),
                                "raw_turn_count": response.get("raw_turn_count", 0),
                                "estimated_tokens": response.get("estimated_tokens", 0),
                                "card": (response.get("metadata") or {}).get("card")
                                if isinstance(response.get("metadata"), dict) else None,
                                "media_urls": (response.get("metadata") or {}).get("media_urls", [])
                                if isinstance(response.get("metadata"), dict) else [],
                            }
                            await websocket.send_json({
                                "type":         "message_end",
                                "stream_id":    sid,
                                "content":      response.get("content", ""),
                                "metadata":     metadata,
                                "finish_reason": finish,
                                "timestamp":    timestamp,
                            })
                            # Deliver chat_message event for TODO 13.2.3
                            await websocket.send_json({
                                "type":         "chat_message",
                                "role":         "head_of_council",
                                "content":      response.get("content", ""),
                                "message_id":   message_id,
                                "stream_id":    sid,
                                "metadata":     metadata,
                                "timestamp":    timestamp,
                            })
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error(f"[WebSocket] process_message failed: {exc}")
                        try:
                            await websocket.send_json({
                                "type":         "message_end",
                                "stream_id":    sid,
                                "content":      f"⚠️ An error occurred while processing your message: {str(exc)[:300]}",
                                "metadata":     {},
                                "finish_reason": "error",
                                "timestamp":    datetime.utcnow().isoformat(),
                            })
                        except Exception:
                            pass  # socket already closing — error is logged above
                    finally:
                        active_streams.pop(sid, None)
                        pending_tasks.pop(sid, None)

                task = asyncio.create_task(_run_generation())
                pending_tasks[stream_id] = task
                continue

            # ── Unknown message type ──────────────────────────────────────────
            await websocket.send_json({
                "type":      "error",
                "content":   f"Unknown message type: {msg_type!r}",
                "timestamp": datetime.utcnow().isoformat(),
            })

    except WebSocketDisconnect:
        # Don't cancel generation tasks — let them complete so the
        # reply is persisted to DB. The client's send_json calls fail
        # silently (handled by on_delta / message_end try/except).
        # On reconnect, the frontend loads the persisted reply from
        # chat history.
        pending_tasks.clear()
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"[WebSocket] Unexpected error: {exc}")
        for t in pending_tasks.values():
            t.cancel()
        pending_tasks.clear()
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


@router.get(
    "/genesis-status",
    summary="Genesis Status",
    description="Lightweight HTTP status check for the genesis bootstrap process. The chat WebSocket connection is gated on Head 00001 existing, but a client that hits that gate is closed before it's ever added to ConnectionManager — so it cannot receive a WebSocket broadcast telling it genesis has finished. This endpoint gives the frontend something cheap to poll instead of repeatedly retrying the full WS handshake. Returns one of: - \"not_started\": no API key configured yet, genesis hasn't been triggered - \"running\":      API key exists, genesis is in progress - \"complete\":     Head 00001 exists, chat is ready to connect.",
    responses=build_responses(None),
    tags=["WebSocket"],
)
async def genesis_status(current_user=Depends(get_current_user)):
    """
    Lightweight HTTP status check for the genesis bootstrap process.

    Resolution precedence:
      1. Head 00001 exists                     -> {"status": "complete"}
      2. Redis genesis:state phase == "failed" -> {"status": "failed", "reason"}
      3. API key (UserModelConfig) exists       -> {"status": "running"}
      4. otherwise                              -> {"status": "not_started"}

    Returns one of: "not_started", "running", "complete", "failed", "awaiting_name".
    """
    # If a genesis task is currently paused waiting for the Sovereign to name
    # the nation, surface that as a dedicated status so the dashboard can show
    # the name-entry prompt. The chat WebSocket is gated until Head 00001
    # exists, so the in-process prompt broadcast cannot reach the client — and
    # Head 00001 already exists by the time the prompt fires, so this check
    # must run before the "complete" check below.
    from backend.services import initialization_service as _init_svc
    active = _init_svc.get_active_genesis()
    if active is not None:
        if getattr(active, "awaiting_country_name", False):
            return {
                "status": "awaiting_name",
                "prompt": active.country_name_prompt,
                "timeout_seconds": active.COUNTRY_NAME_TIMEOUT_SECONDS,
            }
        # Genesis instance exists but past the naming prompt — still in
        # progress (running remaining steps). Don't return "complete" yet.
        return {"status": "running"}

    # Failure check BEFORE Head-exists check: genesis may have committed
    # Head 00001 (early commit) but then failed in a later step, so the
    # Head query alone is not a reliable indicator of success.
    try:
        _redis = await get_redis_client()
        raw = await _redis.get("genesis:state")
        if raw:
            state = json.loads(raw)
            if state.get("phase") == "failed":
                return {"status": "failed", "reason": state.get("reason", "Unknown genesis error")}
    except Exception as rexc:
        logger.warning(f"genesis-status redis read failed: {rexc}")

    with get_fresh_db() as db:
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if head:
            return {"status": "complete"}

        genesis_triggered = False
        try:
            from backend.models.entities import UserModelConfig
            genesis_triggered = db.query(UserModelConfig).limit(1).first() is not None
        except Exception:
            pass

        return {"status": "running" if genesis_triggered else "not_started"}


@router.get(
    "/replay",
    summary="Replay Events",
    description="Fetch buffered broadcast events for reconnection replay. Supports per-user history streams.",
    responses=build_responses(None),
    tags=["WebSocket"],
)
async def replay_events(
    since: str = Query(..., description="Timestamp to fetch events since"),
    username: Optional[str] = Query(default=None, description="Username for per-user replay (sovereign only)"),
    current_user=Depends(get_current_user)
):
    print('DEBUG: replay_events function loaded')  # DEBUG
    """
    Fetch missed events for reconnection replay.

    - If username is provided and current_user is sovereign, replay that user's events
    - If username is not provided, replay current user's events
    - Non-sovereign users can only replay their own events
    """
    # Determine target user for replay
    target_username = username or current_user["username"]

    # Authorization: users can only replay their own events unless sovereign
    if target_username != current_user["username"] and current_user.get("role") != "sovereign":
        raise HTTPException(
            status_code=403,
            detail="Cannot replay other users' events"
        )

    try:
        r = await manager._get_redis()
        stream_key = f"ws:user:{target_username}:history"

        # Read from per-user history stream since timestamp
        # xread with count=500 to match stream maxlen
        entries = await r.xread({stream_key: since}, count=500)

        events = []
        for stream_name, stream_entries in entries:
            for msg_id, fields in stream_entries:
                try:
                    event_data = fields.get("data", "{}")
                    event = json.loads(event_data)
                    events.append(event)
                except Exception:
                    pass

        # Sort by timestamp
        events.sort(key=lambda x: x.get("timestamp", ""))
        return {"events": events}
    except Exception as exc:
        logger.error(f"[WebSocket] Replay fetch error: {exc}")
        return {"events": []}