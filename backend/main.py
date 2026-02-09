"""
Agentium Main Application with IDLE GOVERNANCE integration.
FastAPI backend with eternal idle council (Head + 2 Council Members).
"""

from datetime import datetime
import json
import logging
import uvicorn
from backend.api import host_access
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.celery_app import celery_app as celery
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from backend.services.api_manager import init_api_manager
import backend.services.api_manager as api_manager_module
from backend.services.model_allocation import init_model_allocator, model_allocator
from backend.services.token_optimizer import init_token_optimizer, token_optimizer, idle_budget

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
from backend.api.routes import auth as auth_routes
from backend.core.auth import get_current_user
from backend.api import sovereign
from backend.api.routes import tool_creation as tool_creation_routes
from backend.api.routes import admin as admin_routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConstitutionUpdateRequest(BaseModel):
    """Constitution update request from frontend."""
    preamble: Optional[str] = None
    articles: Optional[Dict[str, Any]] = None
    prohibited_actions: Optional[List[str]] = None
    sovereign_preferences: Optional[Dict[str, Any]] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan with:
    - Database initialization
    - Persistent Council (IDLE GOVERNANCE)
    - API Manager & Model Allocation
    - Enhanced Token Optimizer
    - Idle Governance Engine
    """
    logger.info("🚀 Starting Agentium with Intelligent Model Allocation & IDLE GOVERNANCE...")
    
    # ─────────────────────────────────────────────────────────────
    # 1. Initialize Database
    # ─────────────────────────────────────────────────────────────
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    # ─────────────────────────────────────────────────────────────
    # 2. Initialize Persistent Council (IDLE GOVERNANCE)
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            council_status = persistent_council.initialize_persistent_council(db)
            
            # Get the initialized persistent agents for token optimizer
            persistent_agents = persistent_council.get_persistent_agents(db)
            agent_list = list(persistent_agents.values())
            
            logger.info(f"✅ Persistent Council initialized: {council_status}")
            logger.info(f"   - Head: {len([a for a in agent_list if a.agentium_id.startswith('0')])}")
            logger.info(f"   - Council: {len([a for a in agent_list if a.agentium_id.startswith('1')])}")
    except Exception as e:
        logger.error(f"❌ Persistent Council initialization failed: {e}")
        raise
    
    # ─────────────────────────────────────────────────────────────
    # 3. Initialize API Manager & Model Allocator
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            # Initialize API Manager (loads all available models)
            manager = init_api_manager(db)
            
            if manager is None:
                raise Exception("API Manager failed to initialize - returned None")
            
            if not hasattr(manager, 'models'):
                raise Exception("API Manager instance missing 'models' attribute")
            
            logger.info(f"✅ API Manager initialized with {len(manager.models)} models")
            
            # Initialize Model Allocation Service
            init_model_allocator(db)
            logger.info("✅ Model Allocator initialized")
            
            # Print available models summary
            for key, model in manager.models.items():
                logger.info(f"   - {key}: {model.model_name} (${model.cost_per_1k_tokens}/1K)")
                
    except Exception as e:
        logger.error(f"❌ API Manager initialization failed: {e}")
        import traceback
        logger.error(f"Detailed traceback: {traceback.format_exc()}")
        raise
    
    # ─────────────────────────────────────────────────────────────
    # 4. Initialize Enhanced Token Optimizer
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            # Initialize with the persistent agents from council
            init_token_optimizer(db, agents=agent_list)
            
            # Log initial status
            status = token_optimizer.get_status()
            logger.info("✅ Enhanced Token Optimizer initialized")
            logger.info(f"   - Idle Threshold: {status['idle_threshold_seconds']}s")
            logger.info(f"   - Single API Mode: {api_manager_module.api_manager.single_api_mode()}")
            logger.info(f"   - Daily Budget: ${idle_budget.daily_cost_limit}")
            
            # If single API mode, log warning
            if api_manager_module.api_manager.single_api_mode():
                logger.warning("⚠️ Single API mode detected - using one provider for all tasks")
            
    except Exception as e:
        logger.error(f"❌ Token Optimizer initialization failed: {e}")
        raise
    
    # ─────────────────────────────────────────────────────────────
    # 5. Start Idle Governance Engine
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            await idle_governance.start(db)
            logger.info("✅ Idle Governance Engine started")
    except Exception as e:
        logger.error(f"❌ Idle Governance startup failed: {e}")
        raise
    
    # ─────────────────────────────────────────────────────────────
    # 6. Print System Summary
    # ─────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("AGENTIUM SYSTEM READY")
    logger.info("=" * 60)
    logger.info(f"🤖 Persistent Agents: {', '.join(token_optimizer.persistent_agents)}")
    logger.info(f"🧠 Available Models: {len(api_manager_module.api_manager.models)}")
    logger.info(f"💰 Daily Budget: ${idle_budget.daily_cost_limit} | Tokens: {idle_budget.daily_token_limit:,}")
    logger.info(f"⚙️ Idle Threshold: {token_optimizer.idle_threshold_seconds}s")
    logger.info("=" * 60)
    
    yield
    
    # ─────────────────────────────────────────────────────────────
    # SHUTDOWN: Gracefully stop all services
    # ─────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down Agentium...")
    
    # Stop Idle Governance
    try:
        await idle_governance.stop()
        logger.info("✅ Idle Governance Engine stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping idle governance: {e}")
    
    # Log final statistics
    try:
        with next(get_db()) as db:
            status = token_optimizer.get_cost_report(db)
            logger.info("📊 Final Statistics:")
            logger.info(f"   - Tokens Saved Today: {status['total_tokens_saved_today']:,}")
            logger.info(f"   - Cost Used: ${status['budget_status']['cost_used_today_usd']}")
            logger.info(f"   - Model Allocations: {status['allocation_report']['total_agents']} agents")
    except Exception as e:
        logger.error(f"❌ Could not generate final statistics: {e}")

# Create FastAPI app
app = FastAPI(
    title="Agentium",
    description="AI Agent Governance System with Eternal Idle Council",
    version="2.0.0-idle",
    lifespan=lifespan
)

# Include routers
app.include_router(auth_routes.router)
app.include_router(model_routes.router, prefix="/api/v1")
app.include_router(chat_routes.router, prefix="/api/v1")
app.include_router(channels_routes.router, prefix="/api/v1")
app.include_router(webhooks_router.router, prefix="/api/v1")
app.include_router(websocket_routes.router, prefix="/api/v1")
app.include_router(host_access.router, prefix="/api/v1")
app.include_router(sovereign.router, prefix="/api/v1")
app.include_router(tool_creation_routes.router, prefix="/api/v1")
app.include_router(admin_routes.router, prefix="/api/v1")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Health Check ====================

@app.get("/api/health")
async def health_check_api():
    """Health check endpoint - API prefix."""
    db_status = check_health()
    
    return {
        "status": "healthy" if db_status["status"] == "healthy" else "unhealthy",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }

# ==================== Agent Management ====================

@app.post("/api/v1/agents/create")
async def create_agent(
    role: str,
    responsibilities: list,
    tier: int = 3,
    db: Session = Depends(get_db)
):
    """Create a new agent with governance compliance."""
    # Validate tier
    if tier not in [0, 1, 2, 3]:
        raise HTTPException(status_code=400, detail="Tier must be 0 (Head), 1 (Council), 2 (Lead), or 3 (Task)")
    
    # Get current constitution
    constitution = db.query(Constitution).filter_by(is_active='Y').order_by(Constitution.effective_date.desc()).first()
    if not constitution:
        raise HTTPException(status_code=500, detail="No active constitution found")
    
    # Create agent
    agent = Agent(
        role=role,
        status=AgentStatus.ACTIVE,
        current_task=None,
        performance_score=100,
        created_by="system",
        tier=tier,
        agentium_id=f"{tier}{len(db.query(Agent).filter_by(tier=tier).all()) + 1:04d}",
        constitution_version=constitution.version,
        supervised_by=None,  # Set by orchestrator
        total_tasks_completed=0,
        successful_tasks=0,
        failed_tasks=0,
        average_task_duration_seconds=0,
        last_active=datetime.utcnow(),
        responsibilities=json.dumps(responsibilities),
        is_persistent=False
    )
    
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    return agent.to_dict()

@app.get("/api/v1/agents")
async def list_agents(
    tier: int = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """List all agents with optional filters."""
    query = db.query(Agent)
    
    if tier is not None:
        query = query.filter_by(tier=tier)
    
    if status:
        try:
            status_enum = AgentStatus(status)
            query = query.filter_by(status=status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    agents = query.all()
    return [agent.to_dict() for agent in agents]

@app.get("/api/v1/agents/{agentium_id}")
async def get_agent(agentium_id: str, db: Session = Depends(get_db)):
    """Get agent details."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return agent.to_dict()

@app.put("/api/v1/agents/{agentium_id}/status")
async def update_agent_status(
    agentium_id: str,
    status: str,
    db: Session = Depends(get_db)
):
    """Update agent status."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    try:
        new_status = AgentStatus(status)
        agent.status = new_status
        agent.last_active = datetime.utcnow()
        db.commit()
        
        return {"message": f"Agent {agentium_id} status updated to {status}"}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

# ==================== Task Management ====================

@app.post("/api/v1/tasks/create")
async def create_task(
    description: str,
    task_type: str = "general",
    priority: str = "medium",
    assigned_to: str = None,
    db: Session = Depends(get_db)
):
    """Create a new task."""
    try:
        task_type_enum = TaskType(task_type)
        priority_enum = TaskPriority(priority)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # If assigned_to specified, verify agent exists
    assigned_agent = None
    if assigned_to:
        assigned_agent = db.query(Agent).filter_by(agentium_id=assigned_to).first()
        if not assigned_agent:
            raise HTTPException(status_code=404, detail=f"Agent {assigned_to} not found")
    
    task = Task(
        description=description,
        task_type=task_type_enum,
        priority=priority_enum,
        status=TaskStatus.PENDING,
        created_by="user",
        assigned_to=assigned_agent.id if assigned_agent else None,
        created_at=datetime.utcnow(),
        token_budget=None,
        estimated_tokens=None
    )
    
    db.add(task)
    db.commit()
    db.refresh(task)
    
    return task.to_dict()

@app.get("/api/v1/tasks")
async def list_tasks(
    status: str = None,
    agent_id: str = None,
    db: Session = Depends(get_db)
):
    """List tasks with optional filters."""
    query = db.query(Task)
    
    if status:
        try:
            status_enum = TaskStatus(status)
            query = query.filter_by(status=status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    if agent_id:
        agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
        if agent:
            query = query.filter_by(assigned_to=agent.id)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    return [task.to_dict() for task in tasks]

@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get task details."""
    task = db.query(Task).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task.to_dict()

# ==================== Task Execution (MODIFIED WITH WAKE) ====================

@app.post("/api/v1/tasks/{task_id}/execute")
async def execute_task(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    Execute a task with wake functionality.
    Wakes from idle mode when user requests task execution.
    """
    # CRITICAL: Wake from idle on user task request
    token_optimizer.record_activity()
    if token_optimizer.idle_mode_active:
        await token_optimizer.wake_from_idle(db)
    
    task = db.query(Task).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not task.assigned_to:
        raise HTTPException(status_code=400, detail="Task has no assigned agent")
    
    agent = db.query(Agent).filter_by(id=task.assigned_to).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Assigned agent not found")
    
    # Mark task and agent as in progress
    task.start()
    agent.start_task()
    db.commit()
    
    # Get active model configuration
    config = db.query(UserModelConfig).filter_by(
        is_active='Y',
        is_default=True
    ).first()
    
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

@app.post("/api/v1/chat")
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

@app.get("/api/v1/constitution/current")
async def get_current_constitution(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # ✅ FIXED: using get_current_user
):
    """Get the currently active constitution. Creates default if none exists."""
    import json
    from datetime import datetime
    
    constitution = db.query(Constitution).filter_by(
        is_active='Y'
    ).order_by(Constitution.effective_date.desc()).first()
    
    if not constitution:
        from backend.services.initialization_service import InitializationService
        constitution = InitializationService.create_default_constitution(db)
    
    return {
        'id': constitution.id,
        'version': constitution.version,
        'version_number': constitution.version_number,
        'preamble': constitution.preamble or "",
        'articles': constitution.get_articles_dict(),
        'prohibited_actions': constitution.get_prohibited_actions_list(),
        'sovereign_preferences': constitution.get_sovereign_preferences(),
        'effective_date': constitution.effective_date.isoformat() if constitution.effective_date else datetime.utcnow().isoformat(),
        'created_by': constitution.created_by_agentium_id,
        'is_active': constitution.is_active == 'Y'
    }


@app.post("/api/v1/constitution/update")
async def update_constitution(
    request: ConstitutionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # ✅ FIXED: using get_current_user
):
    """Update constitution - creates new version."""
    import json
    from datetime import datetime
    
    # Check permissions - adapt this based on what get_current_user returns
    # If get_current_user returns a User object, adjust accordingly
    if hasattr(current_user, 'is_admin'):
        # If it's a User object
        is_admin = current_user.is_admin
        username = current_user.username
    else:
        # If it's a dict
        is_admin = current_user.get("is_admin", False)
        username = current_user.get("username", "sovereign")
    
    if not is_admin:
        # For now, allow all authenticated users until proper permissions are set
        pass
    
    current = db.query(Constitution).filter_by(
        is_active='Y'
    ).order_by(Constitution.effective_date.desc()).first()
    
    if not current:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    # Archive current
    current.is_active = 'N'
    if hasattr(current, 'archived_date'):
        current.archived_date = datetime.utcnow()
    
    # Version increment
    try:
        current_version_num = int(current.version.replace('v', '').split('.')[0])
        new_version_num = current_version_num + 1
        new_version = f"v{new_version_num}.0.0"
    except (ValueError, AttributeError):
        new_version = f"v{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        new_version_num = 1
    
    # Prepare data
    new_preamble = request.preamble if request.preamble is not None else current.preamble
    new_articles = json.dumps(request.articles) if request.articles is not None else current.articles
    new_prohibited = json.dumps(request.prohibited_actions) if request.prohibited_actions is not None else current.prohibited_actions
    new_preferences = json.dumps(request.sovereign_preferences) if request.sovereign_preferences is not None else current.sovereign_preferences
    
    # Changelog
    changes = []
    if request.preamble is not None:
        changes.append("Updated preamble")
    if request.articles is not None:
        changes.append("Modified articles")
    if request.prohibited_actions is not None:
        changes.append("Updated prohibited actions")
    if request.sovereign_preferences is not None:
        changes.append("Updated preferences")
    
    changelog_data = [{
        "version": new_version,
        "changes": changes or ["Manual update"],
        "updated_by": username,
        "timestamp": datetime.utcnow().isoformat()
    }]
    
    # Create new version
    new_constitution = Constitution(
        version=new_version,
        version_number=new_version_num,
        preamble=new_preamble,
        articles=new_articles,
        prohibited_actions=new_prohibited,
        sovereign_preferences=new_preferences,
        changelog=json.dumps(changelog_data),
        effective_date=datetime.utcnow(),
        is_active='Y',
        created_by_agentium_id=username
    )
    
    # Only set replaces_version_id if the field exists
    if hasattr(new_constitution, 'replaces_version_id'):
        new_constitution.replaces_version_id = current.id
    
    db.add(new_constitution)
    db.commit()
    db.refresh(new_constitution)
    
    return {
        'id': new_constitution.id,
        'version': new_constitution.version,
        'version_number': new_constitution.version_number,
        'preamble': new_constitution.preamble or "",
        'articles': new_constitution.get_articles_dict(),
        'prohibited_actions': new_constitution.get_prohibited_actions_list(),
        'sovereign_preferences': new_constitution.get_sovereign_preferences(),
        'effective_date': new_constitution.effective_date.isoformat(),
        'created_by': new_constitution.created_by_agentium_id,
        'is_active': True
    }
# ==================== Monitoring & Oversight ====================

@app.get("/api/v1/monitoring/agents/{agentium_id}/health")
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
    uvicorn.run(app, host="0.0.0.0", port=8000)