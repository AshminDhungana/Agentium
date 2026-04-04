"""
WebSocket endpoint for real-time chat with authentication.
"""

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, get_db
from backend.models.entities import Agent, HeadOfCouncil
from backend.services.chat_service import ChatService
from backend.core.config import settings
from backend.models.entities.user import User
from backend.api.dependencies.auth import get_current_user
import redis.asyncio as redis

router = APIRouter()


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
        print(f"[WebSocket] file_processor import/call failed: {exc}")
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

    async def _get_redis(self) -> redis.Redis:
        if not self.redis_client:
            self.redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
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
                    await websocket.close(code=1011, reason="System not initialised — no Head of Council")
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
        print(f"[WebSocket] ✅ Authenticated: {username} ({datetime.utcnow().isoformat()})")
        return user_info

    def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """Remove connection; return username if found."""
        username = None
        if websocket in self.active_connections:
            user_info = self.active_connections.pop(websocket)
            username  = user_info.get("username")
            if username and username in self.user_connections:
                del self.user_connections[username]
            print(f"[WebSocket] ❌ Disconnected: {username}")
        return username

    # ── send helpers ─────────────────────────────────────────────────────────

    async def send_personal_message(self, message: dict, username: str) -> bool:
        """Send JSON message to a specific connected user."""
        if username in self.user_connections:
            try:
                await self.user_connections[username].send_json(message)
                return True
            except Exception as exc:
                print(f"[WebSocket] Error sending to {username}: {exc}")
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
            print(f"[WebSocket] Event buffer push error: {exc}")

        disconnected = []
        for connection, user_info in list(self.active_connections.items()):
            if connection is exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception as exc:
                print(f"[WebSocket] Broadcast error to {user_info.get('username')}: {exc}")
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
            "timestamp":  datetime.utcnow().isoformat(),
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


# ── global singleton ──────────────────────────────────────────────────────────
manager = ConnectionManager()


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

    user_info: Optional[Dict[str, Any]] = None

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

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

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

            # ── Chat message ──────────────────────────────────────────────────
            if msg_type == "message":
                content     = data.get("content", "").strip()
                attachments: List[dict] = data.get("attachments") or []

                enriched_message = _build_enriched_message(content, attachments)

                if not enriched_message:
                    continue

                with get_fresh_db() as db:
                    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
                    if not head:
                        await websocket.send_json({
                            "type":      "error",
                            "content":   "Head of Council is unavailable. Check system status.",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        continue

                    response = await ChatService.process_message(head, enriched_message, db)

                await websocket.send_json({
                    "type":      "message",
                    "role":      "head_of_council",
                    "content":   response.get("content", ""),
                    "metadata":  response.get("metadata", {}),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            # ── Unknown message type ──────────────────────────────────────────
            await websocket.send_json({
                "type":      "error",
                "content":   f"Unknown message type: {msg_type!r}",
                "timestamp": datetime.utcnow().isoformat(),
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        print(f"[WebSocket] Unexpected error: {exc}")
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


@router.get("/replay")
async def replay_events(since: str, current_user=Depends(get_current_user)):
    """Fetch buffered broadcast events for reconnection replay."""
    try:
        r          = await manager._get_redis()
        events_str = await r.lrange("agentium:ws:buffer", 0, 99)
        events     = []
        for e_str in events_str:
            try:
                e_obj = json.loads(e_str)
                if e_obj.get("timestamp", "") > since:
                    events.append(e_obj)
            except Exception:
                pass

        events.sort(key=lambda x: x.get("timestamp", ""))
        return {"events": events}
    except Exception as exc:
        print(f"[WebSocket] Replay fetch error: {exc}")
        return {"events": []}