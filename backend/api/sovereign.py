"""
Sovereign API Endpoints - Human override control for Head of Council operations.
This gives YOU (the human) visibility and control over the AI agent system.
"""

from fastapi import APIRouter, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from functools import lru_cache
import asyncio
import json
import os
import logging
import psutil  # FIX: added for reliable system metrics (replaces fragile sudo subprocess chain)

from backend.models.database import get_db
from backend.services.host_access import HostAccessService, RestrictedHostAccess
from backend.api.middleware.auth import get_current_user  # Use your existing auth
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.user import User  # Your user model
from pydantic import BaseModel

from backend.core.exceptions import ForbiddenError, BadRequestError
from backend.api.schemas.examples import build_responses

router = APIRouter(prefix="/sovereign", tags=["sovereign"])

logger = logging.getLogger(__name__)

# ── Pydantic request models ───────────────────────────────────────────────────

class SovereignCommandRequest(BaseModel):
    command: str
    params: dict = {}
    target: str = "head_of_council"
    requireApproval: bool = False
    timeout: int = 300

class BlockAgentRequest(BaseModel):
    reason: str

class WriteFileRequest(BaseModel):
    path: str
    content: str

# ── WebSocket connection registry ─────────────────────────────────────────────

# NOTE: This module-level list works correctly in single-worker deployments.
# For multi-worker production (gunicorn with workers > 1), replace with
# a Redis pub/sub channel so all workers share the same connection pool.
active_connections: List[WebSocket] = []

# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_sovereign_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify that the current user is the Sovereign (admin)."""
    if not current_user or not current_user.is_admin:
        raise ForbiddenError(
            error="Only the Sovereign can access this endpoint",
            code="SOVEREIGN_ONLY",
        )
    return current_user

# ── C10: HostAccessService singleton ─────────────────────────────────────────
# Previously every endpoint called HostAccessService("00001") directly, which
# opened a new Docker client socket on each HTTP request. lru_cache(maxsize=1)
# makes the service — and its underlying Docker client — a process-level
# singleton. Errors in Docker connectivity surface once at startup rather
# than once per request, and connection overhead is eliminated.

@lru_cache(maxsize=1)
def _get_head_service() -> HostAccessService:
    return HostAccessService("00001")


# ── System status ─────────────────────────────────────────────────────────────

@router.get(
    "/system/status",
    summary="Get system status",
    description="Retrieve real-time host system status (CPU, memory, disk, network) using psutil.",
    responses=build_responses(None),
)
async def get_system_status(
    current_user: User = Depends(get_current_sovereign_user)
):
    """
    Get real-time host system status (CPU, memory, disk, network).

    FIX: Previously used HostAccessService.execute_command() which prepends
    'sudo -n' to every shell call. Inside Docker, sudo is unavailable, so
    every command returned success=False and all metrics fell back to 0.0.

    Also fixed: the old single-snapshot /proc/stat CPU formula is mathematically
    incorrect — it computes cumulative ticks since boot, not current usage.

    Disk fix: psutil.disk_usage("/") reads the container overlay filesystem
    (showing wrong free space). We now use /host which is a bind-mount of the
    real host "/" defined in docker-compose (volumes: - /:/host:rw).
    Falls back to "/" when running outside Docker (local dev).
    """

    # ── CPU ────────────────────────────────────────────────────────────────────
    # interval=0.5 takes two /proc/stat snapshots 500 ms apart and returns the
    # real delta percentage — the only correct single-call approach.
    cpu_usage: float = psutil.cpu_percent(interval=0.5)
    cpu_cores: int   = psutil.cpu_count(logical=True) or 1
    load_avg: list   = list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [0.0, 0.0, 0.0]

    # ── Memory ─────────────────────────────────────────────────────────────────
    vm              = psutil.virtual_memory()
    mem_total:  int = vm.total
    mem_used:   int = vm.used
    mem_free:   int = vm.available
    mem_pct:  float = round(vm.percent, 1)

    # ── Disk ───────────────────────────────────────────────────────────────────
    _disk_path = "/host" if os.path.ismount("/host") else "/"
    try:
        disk            = psutil.disk_usage(_disk_path)
        disk_total: int = disk.total
        disk_used:  int = disk.used
        disk_free:  int = disk.free
        disk_pct: float = round(disk.percent, 1)
    except Exception:
        disk_total = disk_used = disk_free = 0
        disk_pct = 0.0

    # ── Uptime ─────────────────────────────────────────────────────────────────
    try:
        boot_ts        = psutil.boot_time()
        uptime_seconds = int(datetime.utcnow().timestamp() - boot_ts)
    except Exception:
        uptime_seconds = 0

    hours, remainder  = divmod(uptime_seconds, 3600)
    minutes, _seconds = divmod(remainder, 60)

    # ── Network connections ────────────────────────────────────────────────────
    try:
        net_conns = len(psutil.net_connections())
    except Exception:
        net_conns = 0

    return {
        "cpu": {
            "usage":  round(cpu_usage, 1),
            "cores":  cpu_cores,
            "load":   [round(x, 2) for x in load_avg],
        },
        "memory": {
            "total":      mem_total,
            "used":       mem_used,
            "free":       mem_free,
            "percentage": mem_pct,
        },
        "disk": {
            "total":      disk_total,
            "used":       disk_used,
            "free":       disk_free,
            "percentage": disk_pct,
        },
        "uptime": {
            "seconds":   uptime_seconds,
            "formatted": f"{hours}h {minutes}m",
        },
        "network": {
            "interfaces":  [],
            "connections": net_conns,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

# ── Containers ────────────────────────────────────────────────────────────────

@router.get(
    "/containers",
    summary="List containers",
    description="List all Docker containers (agents) on the host system.",
    responses=build_responses(None),
)
async def list_containers(
    current_user: User = Depends(get_current_sovereign_user)
):
    """List all Docker containers (agents) on host system."""
    # C10: reuse cached service instead of instantiating a new Docker client
    head = _get_head_service()
    return head.list_containers()

@router.post(
    "/containers/{container_id}/{action}",
    summary="Manage container",
    description="Start, stop, restart, or remove agent containers.",
    responses=build_responses(None),
)
async def manage_container(
    container_id: str,
    action: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Start, stop, restart, or remove agent containers."""
    if action not in ['start', 'stop', 'restart', 'remove']:
        raise BadRequestError(
            error="Invalid action",
            code="INVALID_CONTAINER_ACTION",
        )

    # C10: reuse cached service
    head = _get_head_service()

    # Log sovereign intervention
    audit = AuditLog(
        level=AuditLevel.WARNING,
        category=AuditCategory.GOVERNANCE,
        actor_type="sovereign",
        actor_id=current_user.username,
        action=f"container_{action}",
        target_type="container",
        target_id=container_id,
        description=f"Sovereign manually {action}ed container {container_id}",
        after_state={"action": action, "container": container_id},
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    result = head.manage_container(action, container_id)
    if not result.get("success"):
        raise BadRequestError(
            error=result.get("error", "Container action failed"),
            code="CONTAINER_ACTION_FAILED",
            detail={"error": result.get("error")},
        )
    return result

# ── Commands ──────────────────────────────────────────────────────────────────

@router.post(
    "/command",
    summary="Execute sovereign command",
    description="Execute an emergency override command (execute command, read file, or write file) bypassing the Head of Council.",
    responses=build_responses(None),
)
async def execute_sovereign_command(
    command_req: SovereignCommandRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """
    Execute command as Sovereign (human override).
    This bypasses the Head of Council and executes directly on host.
    """
    # C10: reuse cached service
    head = _get_head_service()

    # Log the sovereign command
    audit = AuditLog(
        level=AuditLevel.CRITICAL,
        category=AuditCategory.GOVERNANCE,
        actor_type="sovereign",
        actor_id=current_user.username,
        action="sovereign_command",
        target_type="host_system",
        target_id="root",
        description=f"Sovereign executed: {command_req.command}",
        after_state={"command": command_req.command, "params": command_req.params},
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    # Execute command
    if command_req.command == "execute":
        result = head.execute_command(
            command_req.params.get("command", []),
            cwd=command_req.params.get("cwd")
        )
    elif command_req.command == "read_file":
        result = head.read_file(command_req.params.get("path", "/"))
    elif command_req.command == "write_file":
        result = head.write_file(
            command_req.params.get("path", "/"),
            command_req.params.get("content", "")
        )
    else:
        raise BadRequestError(
            error="Unknown command type",
            code="UNKNOWN_COMMAND",
        )

    return {
        "id": f"sov_{datetime.utcnow().timestamp()}",
        "agentium_id": "SOVEREIGN",
        "agent_type": "sovereign",
        "action": command_req.command,
        "target": command_req.params.get("path", "host"),
        "status": "completed" if result.get("success") else "failed",
        "result": result,
        "requested_at": datetime.utcnow().isoformat()
    }

# ── Audit logs ────────────────────────────────────────────────────────────────

@router.get(
    "/audit",
    summary="Get audit logs",
    description="Retrieve filtered, ordered system audit logs.",
    responses=build_responses(None),
)
async def get_audit_logs(
    agentium_id: Optional[str] = None,
    level: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Get detailed audit logs with filtering."""
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())

    if agentium_id:
        query = query.filter(AuditLog.actor_id == agentium_id)
    if level:
        query = query.filter(AuditLog.level == level)
    if start_time:
        query = query.filter(AuditLog.created_at >= start_time)
    if end_time:
        query = query.filter(AuditLog.created_at <= end_time)

    logs = query.limit(limit).all()
    return [log.to_dict() for log in logs]

# ── Agent block / unblock ─────────────────────────────────────────────────────

@router.post(
    "/agents/{agentium_id}/block",
    summary="Block agent",
    description="Emergency block an agent from executing further actions.",
    responses=build_responses(None),
)
async def block_agent(
    agentium_id: str,
    req: BlockAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Emergency block an agent from further actions."""
    audit = AuditLog(
        level=AuditLevel.CRITICAL,
        category=AuditCategory.SECURITY,
        actor_type="sovereign",
        actor_id=current_user.username,
        action="agent_blocked",
        target_type="agent",
        target_id=agentium_id,
        description=f"Agent {agentium_id} blocked by sovereign: {req.reason}",
        after_state={"reason": req.reason, "blocked": True},
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    # Notify via WebSocket
    await notify_sovereign({
        "type": "agent_blocked",
        "agentium_id": agentium_id,
        "reason": req.reason,
        "timestamp": datetime.utcnow().isoformat()
    })

    return {"status": "blocked", "agentium_id": agentium_id}

@router.post(
    "/agents/{agentium_id}/unblock",
    summary="Unblock agent",
    description="Remove an active emergency block from a previously blocked agent.",
    responses=build_responses(None),
)
async def unblock_agent(
    agentium_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Unblock a previously blocked agent."""
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.SECURITY,
        actor_type="sovereign",
        actor_id=current_user.username,
        action="agent_unblocked",
        target_type="agent",
        target_id=agentium_id,
        description=f"Agent {agentium_id} unblocked by sovereign",
        after_state={"blocked": False},
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    return {"status": "unblocked", "agentium_id": agentium_id}

# ── File system ───────────────────────────────────────────────────────────────

@router.get(
    "/files",
    summary="Read file",
    description="Read file contents directly from the host filesystem.",
    responses=build_responses(None),
)
async def read_file(
    path: str = Query(...),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Read file from host filesystem."""
    # C10: reuse cached service
    head = _get_head_service()
    return head.read_file(path)

@router.post(
    "/files",
    summary="Write file",
    description="Write file contents directly to the host filesystem (human-initiated override).",
    responses=build_responses(None),
)
async def write_file(
    req: WriteFileRequest,
    current_user: User = Depends(get_current_sovereign_user)
):
    """Write file to host filesystem (Sovereign only)."""
    # C10: reuse cached service
    head = _get_head_service()
    return head.write_file(req.path, req.content)

@router.get(
    "/directory",
    summary="List directory",
    description="List directory entries on the host filesystem.",
    responses=build_responses(None),
)
async def list_directory(
    path: str = Query(default="/"),
    current_user: User = Depends(get_current_sovereign_user)
):
    """List directory contents."""
    # C10: reuse cached service
    head = _get_head_service()
    return head.list_directory(path)

# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def sovereign_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time sovereign notifications."""

    # Validate token presence
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # Validate JWT and check admin privileges
    try:
        from jose import jwt, JWTError
        from backend.core.config import settings

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            await websocket.close(code=4001, reason="Invalid token: no subject")
            return

        # Verify user exists and is admin
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_admin:
            await websocket.close(code=4003, reason="Forbidden: admin access required")
            return

    except JWTError as e:
        await websocket.close(code=4001, reason=f"Invalid authentication: {str(e)}")
        return
    except Exception as e:
        await websocket.close(code=1011, reason=f"Authentication error: {str(e)}")
        return

    # Accept connection only after successful auth
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"[Sovereign WebSocket] ✅ Admin connected: {username}")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("action") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif message.get("action") == "subscribe":
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": message.get("channel"),
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Unknown action: {message.get('action')}",
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        logger.error(f"[Sovereign WebSocket] ❌ Disconnected: {username}")
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "content": "Invalid JSON format",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"[Sovereign WebSocket] Error: {e}")
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except Exception:
            pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)

# ── Broadcast helper ──────────────────────────────────────────────────────────

async def notify_sovereign(message: dict):
    """Send notification to all connected sovereign dashboards."""
    disconnected = []
    for conn in active_connections:
        try:
            await conn.send_json(message)
        except Exception:
            disconnected.append(conn)

    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)

# ── Command history ───────────────────────────────────────────────────────────

@router.get(
    "/commands",
    summary="Get command history",
    description="Get sovereign manual command intervention history.",
    responses=build_responses(None),
)
async def get_command_history(
    limit: int = Query(50, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_sovereign_user)
):
    """Get sovereign command history."""
    # C9: added "container_remove" — previously remove actions were silently
    #     omitted from the history log because the filter list was incomplete.
    logs = db.query(AuditLog).filter(
        AuditLog.actor_type == "sovereign",
        AuditLog.action.in_([
            "sovereign_command",
            "container_start",
            "container_stop",
            "container_restart",
            "container_remove",   # C9: was missing
        ])
    ).order_by(AuditLog.created_at.desc()).limit(limit).all()

    return [log.to_dict() for log in logs]

# C8: parse_meminfo() and parse_df() removed — both were dead code left over
# from the old subprocess-based metrics approach. psutil replaced them entirely
# and neither function was imported or called anywhere else in the codebase.