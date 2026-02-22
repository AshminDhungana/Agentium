"""
WebSocket endpoint for real-time chat with authentication.
User must authenticate BEFORE or DURING connection.

Broadcast events emitted:
  agent_spawned          — new agent created
  task_escalated         — task promoted to council
  vote_initiated         — deliberation vote started
  constitutional_violation — rule breach detected
  message_routed         — external channel message dispatched to agent
  knowledge_submitted    — NEW: agent submitted knowledge to the KB
  knowledge_approved     — NEW: council approved a knowledge submission
  amendment_proposed     — NEW: constitutional amendment proposed
  agent_liquidated       — NEW: agent terminated / decommissioned
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities import Agent, HeadOfCouncil
from backend.services.chat_service import ChatService
from backend.core.config import settings
from backend.core.auth import get_current_active_user
from backend.models.entities.user import User

router = APIRouter()


class ConnectionManager:
    """Manage authenticated WebSocket connections with heartbeat support."""

    def __init__(self):
        # websocket → user_info
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        # username → websocket  (for direct targeting)
        self.user_connections: Dict[str, WebSocket] = {}

    # ── connection lifecycle ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, token: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        Authenticate before accepting.
        Returns user_info dict on success, None if auth fails.
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            username = payload.get("sub")
            if not username:
                await websocket.close(code=4001, reason="Invalid token: no subject")
                return None

            head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            if not head:
                await websocket.close(code=1011, reason="System not initialized — no Head of Council")
                return None

            await websocket.accept()

            user_info = {
                "username":        username,
                "role":            payload.get("role", "sovereign"),
                "user_id":         payload.get("user_id"),
                "head_agent_id":   head.id,
                "head_agentium_id": head.agentium_id,
            }

            self.active_connections[websocket] = user_info
            self.user_connections[username] = websocket
            print(f"[WebSocket] ✅ Authenticated: {username} ({datetime.utcnow().isoformat()})")
            return user_info

        except JWTError as e:
            await websocket.close(code=4001, reason=f"Invalid authentication: {str(e)}")
            return None
        except Exception as e:
            await websocket.close(code=1011, reason=f"Authentication error: {str(e)}")
            return None

    def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """Remove connection; return username if found."""
        username = None
        if websocket in self.active_connections:
            user_info = self.active_connections.pop(websocket)
            username = user_info.get("username")
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
            except Exception as e:
                print(f"[WebSocket] Error sending to {username}: {e}")
        return False

    async def broadcast(self, message: dict, exclude: Optional[WebSocket] = None) -> None:
        """Broadcast JSON message to all authenticated connections."""
        disconnected = []
        for connection, user_info in self.active_connections.items():
            if connection is exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WebSocket] Broadcast error to {user_info.get('username')}: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    def get_connection_count(self) -> int:
        return len(self.active_connections)

    # ── typed broadcast events ───────────────────────────────────────────────
    # These are the named events the rest of the backend calls directly.
    # Each stamps a `timestamp` automatically.

    async def emit_agent_spawned(self, agent_id: str, agent_name: str,
                                  agent_type: str, tier: str) -> None:
        await self.broadcast({
            "type":       "agent_spawned",
            "agent_id":   agent_id,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "tier":       tier,
            "timestamp":  datetime.utcnow().isoformat(),
        })

    async def emit_task_escalated(self, task_id: str, task_title: str,
                                   escalated_by: str, reason: str) -> None:
        await self.broadcast({
            "type":         "task_escalated",
            "task_id":      task_id,
            "task_title":   task_title,
            "escalated_by": escalated_by,
            "reason":       reason,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_vote_initiated(self, vote_id: str, topic: str,
                                   initiated_by: str, options: list) -> None:
        await self.broadcast({
            "type":         "vote_initiated",
            "vote_id":      vote_id,
            "topic":        topic,
            "initiated_by": initiated_by,
            "options":      options,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_constitutional_violation(self, agent_id: str, rule: str,
                                             severity: str, action_taken: str) -> None:
        await self.broadcast({
            "type":         "constitutional_violation",
            "agent_id":     agent_id,
            "rule":         rule,
            "severity":     severity,
            "action_taken": action_taken,
            "timestamp":    datetime.utcnow().isoformat(),
        })

    async def emit_message_routed(self, channel: str, channel_name: str,
                                   sender: str, task_id: str,
                                   requires_approval: bool = False) -> None:
        await self.broadcast({
            "type":             "message_routed",
            "channel":          channel,
            "channel_name":     channel_name,
            "sender":           sender,
            "task_id":          task_id,
            "requires_approval": requires_approval,
            "timestamp":        datetime.utcnow().isoformat(),
        })

    async def emit_message_created(self, message_data: Dict[str, Any]) -> None:
        """
        Fired when a new unified `ChatMessage` is created, typically arriving from an external channel.
        This forces the Web Dashboard to append the new message instantly.
        """
        await self.broadcast({
            "type": "message_created",
            "message": message_data,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # ── NEW events ───────────────────────────────────────────────────────────

    async def emit_knowledge_submitted(
        self,
        submission_id: str,
        submitted_by: str,       # agentium_id of submitting agent
        title: str,
        category: str,
        pending_review: bool = True,
    ) -> None:
        """
        Fired when an agent submits new knowledge to the knowledge base.
        Council members see this and can approve/reject.
        """
        await self.broadcast({
            "type":           "knowledge_submitted",
            "submission_id":  submission_id,
            "submitted_by":   submitted_by,
            "title":          title,
            "category":       category,
            "pending_review": pending_review,
            "timestamp":      datetime.utcnow().isoformat(),
        })

    async def emit_knowledge_approved(
        self,
        submission_id: str,
        approved_by: str,        # agentium_id of approving council member
        title: str,
        kb_entry_id: str,        # ID of the new KB entry created
    ) -> None:
        """
        Fired when a council member approves a knowledge submission.
        All agents can now query this knowledge.
        """
        await self.broadcast({
            "type":          "knowledge_approved",
            "submission_id": submission_id,
            "approved_by":   approved_by,
            "title":         title,
            "kb_entry_id":   kb_entry_id,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_amendment_proposed(
        self,
        amendment_id: str,
        proposed_by: str,        # agentium_id
        article: str,            # Which constitutional article is affected
        summary: str,            # Human-readable one-liner
        requires_vote: bool = True,
    ) -> None:
        """
        Fired when an agent or council member proposes a constitutional amendment.
        Triggers a vote_initiated event separately once quorum forms.
        """
        await self.broadcast({
            "type":          "amendment_proposed",
            "amendment_id":  amendment_id,
            "proposed_by":   proposed_by,
            "article":       article,
            "summary":       summary,
            "requires_vote": requires_vote,
            "timestamp":     datetime.utcnow().isoformat(),
        })

    async def emit_agent_liquidated(
        self,
        agent_id: str,           # agentium_id of terminated agent
        agent_name: str,
        liquidated_by: str,      # agentium_id of the authority who terminated
        reason: str,
        tasks_reassigned: int = 0,
    ) -> None:
        """
        Fired when an agent is decommissioned / liquidated.
        Frontend should remove the agent from live views.
        """
        await self.broadcast({
            "type":             "agent_liquidated",
            "agent_id":         agent_id,
            "agent_name":       agent_name,
            "liquidated_by":    liquidated_by,
            "reason":           reason,
            "tasks_reassigned": tasks_reassigned,
            "timestamp":        datetime.utcnow().isoformat(),
        })


# ── global singleton used by the rest of the backend ─────────────────────────
manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════
# WebSocket endpoint
# ═══════════════════════════════════════════════════════════

@router.websocket("/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT access token"),
    db: Session = Depends(get_db)
):
    """
    Authenticated WebSocket endpoint for Sovereign ↔ Head of Council chat.

    Connection flow:
    1. Client connects with ?token=JWT in URL
    2. Server validates JWT BEFORE accepting (4001 if invalid)
    3. If valid: connection accepted, welcome message sent
    4. Messages processed through ChatService

    Heartbeat: Client should send {"type": "ping"} every 30 s.
    """
    if not token:
        await websocket.close(code=4001, reason="Token required — provide ?token=JWT")
        return

    user_info = await manager.connect(websocket, token, db)
    if not user_info:
        return

    # ── welcome ───────────────────────────────────────────────────────────────
    try:
        await websocket.send_json({
            "type":      "system",
            "role":      "system",
            "content":   (
                f"Welcome {user_info['username']}. "
                f"Connected to Head of Council ({user_info['head_agentium_id']})."
            ),
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "agent_id":      user_info["head_agentium_id"],
                "connection_id": id(websocket),
            },
        })
        await websocket.send_json({
            "type":      "status",
            "role":      "head_of_council",
            "content":   "Head of Council is ready to receive commands.",
            "agent_id":  user_info["head_agentium_id"],
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        print(f"[WebSocket] Error sending welcome: {e}")
        manager.disconnect(websocket)
        return

    # ── main loop ─────────────────────────────────────────────────────────────
    try:
        while True:
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type":      "error",
                    "content":   "Invalid JSON format",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            message_type = message_data.get("type", "message")

            # ── ping / pong ───────────────────────────────────────────────────
            if message_type == "ping":
                await websocket.send_json({
                    "type":      "pong",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                continue

            # ── chat message ──────────────────────────────────────────────────
            if message_type == "message":
                content = message_data.get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type":      "error",
                        "content":   "Empty message content",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    continue

                await websocket.send_json({
                    "type":      "status",
                    "role":      "system",
                    "content":   "Processing your command...",
                    "timestamp": datetime.utcnow().isoformat(),
                })

                try:
                    # Use the injected 'db' session - DO NOT create a new one
                    head = db.query(HeadOfCouncil).filter_by(
                        id=user_info["head_agent_id"]
                    ).first()

                    if not head:
                        await websocket.send_json({
                            "type":      "error",
                            "content":   "Head of Council not available",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                        continue

                    response = await ChatService.process_message(head, content, db)

                    await websocket.send_json({
                        "type":    "message",
                        "role":    "head_of_council",
                        "content": response.get("content", "No response"),
                        "metadata": {
                            "agent_id":    user_info["head_agentium_id"],
                            "model":       response.get("model"),
                            "task_created": response.get("task_created"),
                            "task_id":     response.get("task_id"),
                            "tokens_used": response.get("tokens_used"),
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                except Exception as e:
                    print(f"[WebSocket] ChatService error: {e}")
                    error_msg = f"Error processing message: {str(e)}"
                    if "bound to a Session" in str(e) or "UserModelConfig" in str(e):
                        error_msg = (
                            "System Connection Refresh Required:\n"
                            "The database connection was interrupted. "
                            "Please reload the page to reconnect."
                        )
                    await websocket.send_json({
                        "type":      "error",
                        "content":   error_msg,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

            else:
                await websocket.send_json({
                    "type":      "error",
                    "content":   f"Unknown message type: {message_type}",
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket] Unexpected error: {e}")
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════
# REST stats endpoint
# ═══════════════════════════════════════════════════════════
@router.get("/ws/stats")
async def get_websocket_stats(current_user: User = Depends(get_current_active_user)):
    """Get WebSocket connection statistics (admin only)."""
    return {
        "active_connections": manager.get_connection_count(),
        "connected_users":    list(manager.user_connections.keys()),
    }

@router.websocket("/sovereign")
async def websocket_sovereign_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for Sovereign real-time system updates.
    Requires admin authentication.
    """
    if not token:
        await websocket.close(code=4001, reason="Token required")
        return

    user_info = await manager.connect(websocket, token, db)
    if not user_info:
        return
    
    # Verify admin privileges
    if not user_info.get("is_admin"):
        await websocket.close(code=4003, reason="Admin privileges required")
        return

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "system",
            "role": "system",
            "content": f"Sovereign console connected. Welcome, {user_info['username']}.",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "connection_id": id(websocket),
                "user": user_info.get("username")
            }
        })

        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type", "ping")

                if msg_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif msg_type == "subscribe":
                    channel = message.get("channel", "all")
                    await websocket.send_json({
                        "type": "subscribed",
                        "channel": channel,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "content": "Invalid JSON format",
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket Sovereign] Error: {e}")
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except:
            pass