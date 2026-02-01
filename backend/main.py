"""
Agentium Main Application with IDLE GOVERNANCE integration.
FastAPI backend with eternal idle council (Head + 2 Council Members).
"""

from datetime import datetime
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.models.database import init_db, get_db, check_health
from backend.models.entities import Agent, Task, Constitution, UserModelConfig, AgentHealthReport, ViolationReport
from backend.services.model_provider import ModelService
from backend.services.chat_service import ChatService
from backend.services.monitoring_service import MonitoringService

# IDLE GOVERNANCE IMPORTS (NEW)
from backend.services.persistent_council import persistent_council
from backend.services.idle_governance import idle_governance
from backend.services.token_optimizer import token_optimizer, idle_budget
from backend.models.entities.task import TaskType, TaskPriority, TaskStatus
from backend.models.entities.agents import AgentStatus

# API Routes
from backend.api.routes import chat as chat_routes
from backend.api.routes import channels as channels_routes
from backend.api.routes import webhooks as webhooks_router
from backend.api.routes import models as model_routes
from backend.api.routes import websocket as websocket_routes
from backend.core.auth import get_current_user

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan with IDLE GOVERNANCE initialization.
    """
    logger.info("🚀 Starting Agentium with IDLE GOVERNANCE...")
    
    # Initialize database
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    # IDLE GOVERNANCE: Initialize Persistent Council (NEW)
    try:
        with next(get_db()) as db:
            council_status = persistent_council.initialize_persistent_council(db)
            logger.info(f"✅ Persistent Council initialized: {council_status}")
    except Exception as e:
        logger.error(f"❌ Persistent Council initialization failed: {e}")
        raise
    
    # IDLE GOVERNANCE: Start the eternal idle loop (NEW)
    try:
        with next(get_db()) as db:
            await idle_governance.start(db)
            logger.info("✅ Idle Governance Engine started")
    except Exception as e:
        logger.error(f"❌ Idle Governance startup failed: {e}")
        raise
    
    yield
    
    # Shutdown: Stop idle governance gracefully
    logger.info("🛑 Shutting down Agentium...")
    try:
        await idle_governance.stop()
        logger.info("✅ Idle Governance Engine stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping idle governance: {e}")

# Create FastAPI app
app = FastAPI(
    title="Agentium",
    description="AI Agent Governance System with Eternal Idle Council",
    version="2.0.0-idle",
    lifespan=lifespan
)

# Include routers
app.include_router(model_routes.router)
app.include_router(chat_routes.router)
app.include_router(channels_routes.router)
app.include_router(webhooks_router.router)
app.include_router(websocket_routes.router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IDLE GOVERNANCE: Middleware to wake from idle on user requests (NEW)
@app.middleware("http")
async def wake_on_request(request, call_next):
    """Wake system from idle mode when user makes a request."""
    with next(get_db()) as db:
        # Record activity to prevent idle transition
        token_optimizer.record_activity()
        
        # Check if we need to transition out of idle
        if token_optimizer.idle_mode_active:
            await token_optimizer.wake_from_idle(db)
    
    response = await call_next(request)
    return response

# ==================== IDLE GOVERNANCE ENDPOINTS (NEW) ====================

@app.get("/idle/status")
async def get_idle_status():
    """Get current idle governance status."""
    return {
        "idle_governance": idle_governance.get_statistics(),
        "token_optimizer": token_optimizer.get_status(),
        "budget": idle_budget.get_status()
    }

@app.post("/idle/wake")
async def manual_wake():
    """Manually wake system from idle mode."""
    with next(get_db()) as db:
        await token_optimizer.wake_from_idle(db)
    return {"message": "System woken from idle mode", "timestamp": datetime.utcnow().isoformat()}

@app.post("/idle/enter")
async def manual_enter_idle():
    """Manually enter idle mode (for testing)."""
    with next(get_db()) as db:
        await token_optimizer.enter_idle_mode(db)
    return {"message": "System entered idle mode", "timestamp": datetime.utcnow().isoformat()}

@app.get("/idle/persistent-agents")
async def get_persistent_agents(db: Session = Depends(get_db)):
    """Get status of the 3 eternal agents."""
    agents = persistent_council.get_persistent_agents(db)
    return {
        "count": len(agents),
        "agents": {aid: agent.to_dict() for aid, agent in agents.items()}
    }

@app.get("/idle/statistics")
async def get_idle_statistics(db: Session = Depends(get_db)):
    """Get comprehensive idle governance statistics."""
    head = persistent_council.get_head_of_council(db)
    council = persistent_council.get_idle_council(db)
    
    # Get idle task stats
    completed_tasks = db.query(Task).filter_by(
        is_idle_task=True, 
        status=TaskStatus.IDLE_COMPLETED
    ).count()
    
    failed_tasks = db.query(Task).filter_by(
        is_idle_task=True,
        status=TaskStatus.FAILED
    ).count()
    
    # Calculate total tokens saved
    total_tokens_saved = sum(agent.idle_tokens_saved for agent in db.query(Agent).filter_by(is_persistent=True))
    
    return {
        "system_status": {
            "is_idle": token_optimizer.idle_mode_active,
            "time_since_activity": (datetime.utcnow() - token_optimizer.last_activity_at).total_seconds(),
            "idle_threshold": token_optimizer.idle_threshold_seconds
        },
        "persistent_council": {
            "head_of_council": head.to_dict() if head else None,
            "council_members": [m.to_dict() for m in council]
        },
        "performance": {
            "completed_idle_tasks": completed_tasks,
            "failed_idle_tasks": failed_tasks,
            "total_tokens_saved": total_tokens_saved,
            "uptime_hours": idle_governance.get_statistics().get('session_duration_hours', 0)
        },
        "budget": idle_budget.get_status()
    }

# ==================== Health & System ====================

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """System health check with idle governance status."""
    db_health = check_health()
    persistent_agents = persistent_council.get_persistent_agents(db)
    
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "components": {
            "database": db_health,
            "api": "healthy",
            "idle_governance": "running" if idle_governance.is_running else "stopped",
            "persistent_council": "active" if len(persistent_agents) == 3 else "degraded"
        },
        "idle_mode": token_optimizer.get_status()
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Agentium with Eternal Idle Council",
        "version": "2.0.0-idle",
        "status": "operational",
        "persistent_agents": "00001, 10001, 10002",
        "docs": "/docs"
    }

# ==================== Agent Management ====================

@app.get("/agents")
async def list_agents(
    agent_type: str = None,
    status: str = None,
    is_persistent: bool = None,  # NEW: Filter persistent agents
    db: Session = Depends(get_db)
):
    """List all agents with optional filtering."""
    query = db.query(Agent)
    
    if agent_type:
        query = query.filter(Agent.agent_type == agent_type)
    if status:
        query = query.filter(Agent.status == status)
    if is_persistent is not None:
        query = query.filter(Agent.is_persistent == is_persistent)  # NEW
    
    agents = query.all()
    return {
        "count": len(agents),
        "persistent_count": sum(1 for a in agents if a.is_persistent),  # NEW
        "agents": [agent.to_dict() for agent in agents]
    }

@app.get("/agents/{agentium_id}")
async def get_agent(agentium_id: str, db: Session = Depends(get_db)):
    """Get specific agent details."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.to_dict()

@app.post("/agents/{agentium_id}/spawn")
async def spawn_agent(
    agentium_id: str,
    child_type: str,
    name: str,
    db: Session = Depends(get_db)
):
    """Spawn a new child agent under parent authority."""
    # Wake from idle first
    token_optimizer.record_activity()
    
    parent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent agent not found")
    
    from backend.models.entities.agents import AgentType
    
    try:
        child_enum = AgentType(child_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid agent type: {child_type}")
    
    try:
        new_agent = parent.spawn_child(child_enum, db, name=name)
        db.commit()
        db.refresh(new_agent)
        
        return {
            "message": "Agent spawned successfully",
            "agent": new_agent.to_dict()
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agents/{agentium_id}/terminate")
async def terminate_agent(
    agentium_id: str,
    reason: str,
    violation: bool = False,
    db: Session = Depends(get_db)
):
    """Terminate an agent (cannot terminate persistent agents without violation flag)."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Cannot terminate persistent agents without violation
    if agent.is_persistent and not violation:
        raise HTTPException(
            status_code=403, 
            detail="Cannot terminate persistent agent without violation flag. Set violation=true to force terminate."
        )
    
    try:
        agent.terminate(reason, violation)
        db.commit()
        return {
            "message": f"Agent {agentium_id} terminated",
            "reason": reason,
            "violation": violation
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

# ==================== Task Management ====================

@app.post("/tasks")
async def create_task(
    title: str,
    description: str,
    task_type: str = "execution",
    priority: str = "normal",
    db: Session = Depends(get_db)
):
    """Create a new task (wakes system from idle)."""
    # Wake from idle mode
    token_optimizer.record_activity()
    
    from backend.models.entities.task import Task, TaskType, TaskPriority
    
    try:
        task = Task(
            title=title,
            description=description,
            task_type=TaskType(task_type),
            priority=TaskPriority(priority),
            created_by="sovereign"
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Auto-start deliberation if not critical or idle
        if task.priority not in [TaskPriority.CRITICAL, TaskPriority.IDLE]:
            council = db.query(Agent).filter_by(agent_type="council_member").all()
            if council:
                task.start_deliberation([c.agentium_id for c in council])
                db.commit()
        
        return {
            "message": "Task created",
            "task": task.to_dict()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks")
async def list_tasks(
    status: str = None,
    agent_id: str = None,
    include_idle: bool = False,  # NEW: Default to false to hide idle tasks
    db: Session = Depends(get_db)
):
    """List tasks with filtering."""
    query = db.query(Task)
    
    # By default, exclude idle tasks unless specifically requested
    if not include_idle:
        query = query.filter(Task.is_idle_task == False)
    
    if status:
        query = query.filter(Task.status == status)
    if agent_id:
        query = query.filter(
            (Task.lead_agent_id == agent_id) | 
            (Task.assigned_task_agent_ids.contains(agent_id))
        )
    
    tasks = query.order_by(Task.created_at.desc()).all()
    return {
        "count": len(tasks),
        "tasks": [task.to_dict() for task in tasks]
    }

@app.post("/tasks/{task_id}/execute")
async def execute_task(
    task_id: str,
    agent_id: str,
    db: Session = Depends(get_db)
):
    """Execute a task using specified agent."""
    # Wake from idle
    token_optimizer.record_activity()
    
    task = db.query(Task).filter_by(agentium_id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.current_task_id:
        raise HTTPException(status_code=400, detail="Agent is busy with another task")
    
    config = agent.get_model_config(db)
    if not config:
        raise HTTPException(
            status_code=400, 
            detail="No active model configuration found. Please configure in settings."
        )
    
    try:
        result = await ModelService.generate_with_agent(
            agent=agent,
            user_message=task.description,
            config_id=config.id
        )
        
        task.complete(
            result_summary=result["content"],
            result_data={"model": result["model"], "tokens": result["tokens_used"]}
        )
        agent.complete_task(success=True)
        
        db.commit()
        
        return {
            "message": "Task executed",
            "result": result["content"],
            "usage": {
                "tokens": result["tokens_used"],
                "latency_ms": result["latency_ms"]
            }
        }
        
    except Exception as e:
        agent.complete_task(success=False)
        task.fail(str(e))
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Chat with Wake (MODIFIED) ====================

@app.post("/chat")
async def chat_with_head(
    message: str,
    db: Session = Depends(get_db)
):
    """Chat with Head of Council - wakes from idle mode."""
    # CRITICAL: Wake from idle on user message
    token_optimizer.record_activity()
    
    head = db.query(Agent).filter_by(agentium_id="00001").first()
    if not head:
        raise HTTPException(status_code=500, detail="Head of Council not initialized")
    
    result = await ChatService.process_message(head, message, db)
    
    return result

# ==================== WebSocket with Wake (MODIFIED) ====================

class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket for real-time updates with IDLE WAKE functionality.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            
            # CRITICAL: Wake from idle on user WebSocket activity
            token_optimizer.record_activity()
            if token_optimizer.idle_mode_active:
                await token_optimizer.wake_from_idle(db)
            
            # Broadcast to all clients
            await manager.broadcast(data)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ==================== Constitution ====================

@app.get("/constitution/current")
async def get_current_constitution(db: Session = Depends(get_db)):
    """Get current active constitution."""
    constitution = db.query(Constitution).filter_by(
        is_active='Y'
    ).order_by(Constitution.effective_date.desc()).first()
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    return constitution.to_dict()

# ==================== Monitoring & Oversight ====================

@app.get("/monitoring/agents/{agentium_id}/health")
async def get_agent_health(agentium_id: str, db: Session = Depends(get_db)):
    """Get health reports for a specific agent."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    latest = db.query(AgentHealthReport).filter_by(
        subject_agent_id=agent.id
    ).order_by(AgentHealthReport.created_at.desc()).first()
    
    violations = db.query(ViolationReport).filter_by(
        violator_agent_id=agent.id,
        status="open"
    ).count()
    
    return {
        "agent": agentium_id,
        "current_status": agent.status.value,
        "health_score": latest.overall_health_score if latest else 100,
        "latest_report": latest.to_dict() if latest else None,
        "open_violations": violations,
        "is_persistent": agent.is_persistent,
        "idle_stats": {
            "tasks_completed": agent.idle_task_count,
            "tokens_saved": agent.idle_tokens_saved
        } if agent.is_persistent else None
    }

# Additional monitoring endpoints...
# (monitoring/health-check, monitoring/report-violation, etc. - keep existing)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)