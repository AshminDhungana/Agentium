"""
WebSocket endpoint for real-time chat with authentication.

Broadcast events emitted:
  agent_spawned            — new agent created
  agent_liquidated         — agent terminated / decommissioned
  agent_promoted           — task agent promoted to lead
  agent_status_changed     — agent status updated (active/working/deliberating/…)
  task_escalated           — task promoted to council
  vote_initiated           — deliberation vote started
  constitutional_violation — rule breach detected
  message_routed           — external channel message dispatched to agent
  knowledge_submitted      — agent submitted knowledge to the KB
  knowledge_approved       — council approved a knowledge submission
  amendment_proposed       — constitutional amendment proposed
"""

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, get_db
from backend.models.entities import Agent, HeadOfCouncil
from backend.services.chat_service import ChatService
from backend.core.config import settings
from backend.models.entities.user import User

router = APIRouter()


# ── DB session helper ─────────────────────────────────────────────────────────

@contextmanager
def get_fresh_db():
    """
    Yield a brand-new SQLAlchemy session and always close it afterwards.
    Used inside the WebSocket message loop so every message gets a clean
    session — avoids stale-data and detached-instance bugs on long-lived
    connections (FIX #4).
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


# ═══════════════════════════════════════════════════════════
# Connection Manager
# ═══════════════════════════════════════════════════════════

class ConnectionManager:
    """Manage authenticated WebSocket connections with heartbeat support."""

    def __init__(self):
        # websocket → user_info
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        # username → websocket  (for direct targeting)
        self.user_connections: Dict[str, WebSocket] = {}

    # ── connection lifecycle ─────────────────────────────────────────────────

    async def authenticate(
        self,
        websocket: WebSocket,
        token: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate JWT and resolve the Head of Council identity.
        Uses a *short-lived* session that is closed immediately after.
        Returns user_info dict on success, None on failure.
        """
        payload = _decode_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return None

        username = payload["sub"]

        # Resolve head_agent_id with a fresh, short-lived session
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
        agent_id:   str,
        agent_name: str,
        agent_type: str,
        parent_id:  Optional[str] = None,
    ) -> None:
        await self.broadcast({
            "type":       "agent_spawned",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "parent_id":  parent_id,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_task_escalated(
        self,
        task_id:      str,
        task_title:   str,
        escalated_by: str,
        reason:       str,
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
        vote_id:         str,
        subject:         str,
        initiated_by:    str,
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
        violator_id:  str,
        article:      str,
        severity:     str,
        description:  str,
        requires_vote: bool = False,
    ) -> None:
        await self.broadcast({
            "type":         "constitutional_violation",
            "violator_id":  violator_id,
            "article":      article,
            "severity":     severity,
            "description":  description,
            "requires_vote": requires_vote,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_message_routed(
        self,
        channel:      str,
        sender:       str,
        task_id:      str,
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
        agent_id:    str,
        topic:       str,
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
        topic:       str,
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
        article:     str,
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
        agent_id:         str,
        agent_name:       str,
        liquidated_by:    str,
        reason:           str,
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
        agent_name:      str,
        promoted_by:     str,
        reason:          str,
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
        agent_id:   str,
        agent_name: str,
        old_status: str,
        new_status: str,
    ) -> None:
        """Broadcast when an agent's status changes (active/working/deliberating/…)."""
        await self.broadcast({
            "type":       "agent_status_changed",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp":  datetime.utcnow().isoformat(),
        })


# ── global singleton ──────────────────────────────────────────────────────────
manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════
# WebSocket endpoint
# ═══════════════════════════════════════════════════════════

@router.websocket("/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    # DEPRECATED: query-param token kept for backward-compat only.
    # Prefer sending {"type":"auth","token":"<JWT>"} as the first message.
    token: Optional[str] = Query(None, description="[DEPRECATED] JWT — send via auth message instead"),
):
    """
    Authenticated WebSocket endpoint for Sovereign ↔ Head of Council chat.

    Preferred connection flow (FIX #11 — token NOT in URL):
      1. Client connects (no token in URL)
      2. Client immediately sends: {"type": "auth", "token": "<JWT>"}
      3. Server validates and replies with welcome message
      4. All subsequent messages are processed

    Legacy flow (still supported, will be removed in a future version):
      1. Client connects with ?token=JWT query param
      2. Server validates immediately

    Heartbeat: Client sends {"type": "ping"} every 30 s.
    Each chat message: {"type": "message", "content": "..."}
    """
    await websocket.accept()

    user_info: Optional[Dict[str, Any]] = None

    # ── Legacy: token in query param ─────────────────────────────────────────
    if token:
        user_info = await manager.authenticate(websocket, token)
        if not user_info:
            return  # authenticate() already closed the socket

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

    # ── Main message loop ─────────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            # ── Auth message (new preferred flow) ─────────────────────────
            if msg_type == "auth":
                if user_info is not None:
                    await websocket.send_json({
                        "type":    "system",
                        "content": "Already authenticated.",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    continue

                auth_token = data.get("token", "")
                user_info  = await manager.authenticate(websocket, auth_token)
                if not user_info:
                    return  # socket closed inside authenticate()

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

            # ── Require authentication for all subsequent messages ─────────
            if user_info is None:
                await websocket.send_json({
                    "type":    "auth_required",
                    "content": "Please send an auth message first.",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            # ── Ping / heartbeat ──────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({
                    "type":      "pong",
                    "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
                })
                continue

            # ── Chat message ──────────────────────────────────────────────
            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                with get_fresh_db() as db:
                    chat_service = ChatService(db)
                    response = await chat_service.process_message(
                        user_message=content,
                        head_agent_id=user_info["head_agent_id"],
                        user_id=user_info.get("user_id"),
                    )

                await websocket.send_json({
                    "type":      "message",
                    "role":      "head_of_council",
                    "content":   response.get("response", ""),
                    "metadata":  response.get("metadata", {}),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            # ── Unknown message type ──────────────────────────────────────
            await websocket.send_json({
                "type":    "error",
                "content": f"Unknown message type: {msg_type!r}",
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