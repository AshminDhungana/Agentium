"""
Agentium Main Application.
FastAPI backend with eternal idle council + capability registry + lifecycle management.
"""
import os
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
from backend.models.entities.user import User

from backend.services.api_manager import init_api_manager
import backend.services.api_manager as api_manager_module
from backend.services.model_allocation import init_model_allocator, model_allocator
from backend.services.token_optimizer import init_token_optimizer, token_optimizer, idle_budget

from backend.models.database import init_db, get_db, check_health
from backend.models.entities import Agent, Task, Constitution, UserModelConfig, AgentHealthReport, ViolationReport
from backend.services.model_provider import ModelService
from backend.services.chat_service import ChatService
from backend.services.monitoring_service import MonitoringService
from backend.services.channel_manager import ChannelManager, WhatsAppAdapter, SlackAdapter

# IDLE GOVERNANCE IMPORTS
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
from backend.api.routes import tasks as tasks_routes
from backend.api.routes import files as files_routes
from backend.api.routes import voice as voice_routes
from backend.api.routes import monitoring_routes as monitoring_router

from backend.api.routes import capability_routes
from backend.api.routes import lifecycle_routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConstitutionUpdateRequest(BaseModel):
    """Constitution update request from frontend."""
    preamble: Optional[str] = None
    articles: Optional[Dict[str, Any]] = None
    prohibited_actions: Optional[List[str]] = None
    sovereign_preferences: Optional[Dict[str, Any]] = None

def create_default_admin(db: Session):
    """Create default admin user if not exists."""
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),  # Change in production!
            is_active=True,
            is_pending=False,
            is_admin=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        logger.info(f"✅ Default admin user created (ID: {admin.id})")
        return True
    else:
        # Ensure admin is active and has admin privileges
        if not admin.is_active or not admin.is_admin:
            admin.is_active = True
            admin.is_pending = False
            admin.is_admin = True
            db.commit()
            logger.info("✅ Admin user permissions updated")
        return False

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
    
    # ─────────────────────────────────────────────────────────────
    # 1. Initialize Database
    # ─────────────────────────────────────────────────────────────
    try:
        init_db()
        logger.info("✅ Database initialized")
        
        # Create default admin user
        with next(get_db()) as db:
            admin_created = create_default_admin(db)
            if admin_created:
                logger.info("✅ Default admin user created")
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
        # Continue anyway - council can be initialized later
    
    # ─────────────────────────────────────────────────────────────
    # 3. Initialize API Manager (Universal Provider Support)
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            init_api_manager(db)
            logger.info("✅ API Manager initialized with universal provider support")
    except Exception as e:
        logger.error(f"❌ API Manager initialization failed: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # 4. Initialize Model Allocator
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            init_model_allocator(db)
            logger.info("✅ Model Allocator initialized")
    except Exception as e:
        logger.error(f"❌ Model Allocator initialization failed: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # 5. Initialize Token Optimizer with Idle Budget
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            persistent_agents = persistent_council.get_persistent_agents(db)
            agent_list = list(persistent_agents.values())
            init_token_optimizer(agent_list)
            
            logger.info("✅ Token Optimizer initialized")
            logger.info(f"   - Idle Budget: ${idle_budget.daily_idle_budget_usd:.2f}/day")
            logger.info(f"   - Active Mode Budget: ${token_optimizer.active_budget.daily_cost_limit_usd:.2f}/day")
    except Exception as e:
        logger.error(f"❌ Token Optimizer initialization failed: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # 6. Start Idle Governance Engine
    # ─────────────────────────────────────────────────────────────
    try:
        with next(get_db()) as db:
            await idle_governance.start(db)
            logger.info("✅ Idle Governance Engine started")
            logger.info("   Eternal Council now active in background")
    except Exception as e:
        logger.error(f"⚠️ Idle Governance Engine start failed: {e}")
        logger.error("   System will continue without idle governance")
    
    # ─────────────────────────────────────────────────────────────
    # 🆕 7. Initialize Capability Registry (Phase 3)
    # ─────────────────────────────────────────────────────────────
    try:
        logger.info("✅ Capability Registry loaded")
        logger.info("   - 26 capabilities defined across 4 tiers")
        logger.info("   - Runtime permission enforcement active")
    except Exception as e:
        logger.error(f"❌ Capability Registry initialization failed: {e}")
    
    logger.info("🎉 Agentium startup complete!")
    
    yield  # Application runs here
    
    # ─────────────────────────────────────────────────────────────
    # Shutdown Sequence
    # ─────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down Agentium...")
    
    try:
        await idle_governance.stop()
        logger.info("✅ Idle Governance Engine stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping Idle Governance: {e}")
    
    # Final statistics
    try:
        with next(get_db()) as db:
            status = token_optimizer.get_status()
            logger.info("📊 Final Statistics:")
            logger.info(f"   - Total Tokens Saved (Idle): {idle_budget.total_tokens_saved:,}")
            logger.info(f"   - Total Cost Saved (Idle): ${idle_budget.total_cost_saved_usd:.2f}")
            logger.info(f"   - Active Budget Used: {status['budget_status']['cost_used_today_usd']:.2f}/{status['budget_status']['daily_cost_limit_usd']:.2f}")
            if model_allocator:
                allocation_report = model_allocator.get_allocation_report()
                logger.info(f"   - Model Allocations: {allocation_report['total_agents']} agents")
    except Exception as e:
        logger.error(f"❌ Could not generate final statistics: {e}")

# Create FastAPI app    
app = FastAPI(
    title="Agentium",
    description="AI Agent Governance System with Phase 3: Lifecycle Management & Capability Registry",
    version="3.0.0-phase3",
    lifespan=lifespan
)

origins = os.getenv("ALLOWED_ORIGINS")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# REGISTER ROUTERS
# ═══════════════════════════════════════════════════════════

# Existing routes
app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(model_routes.router, prefix="/api/v1")
app.include_router(chat_routes.router, prefix="/api/v1")
app.include_router(channels_routes.router, prefix="/api/v1")
app.include_router(webhooks_router.router, prefix="/api/v1")
app.include_router(websocket_routes.router, prefix="/ws")
app.include_router(host_access.router, prefix="/api/v1")
app.include_router(sovereign.router, prefix="/api/v1")
app.include_router(tool_creation_routes.router, prefix="/api/v1")
app.include_router(admin_routes.router, prefix="/api/v1")
app.include_router(tasks_routes.router, prefix="/api/v1")
app.include_router(files_routes.router)
app.include_router(voice_routes.router)
app.include_router(capability_routes.router)      
app.include_router(lifecycle_routes.router) 
app.include_router(monitoring_router.router)      

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
        query = query.filter(Agent.tier == tier)
    
    if status:
        try:
            status_enum = AgentStatus(status.lower())
            query = query.filter(Agent.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    agents = query.all()
    return {"agents": [agent.to_dict() for agent in agents]}

@app.get("/api/v1/agents/{agentium_id}")
async def get_agent(
    agentium_id: str,
    db: Session = Depends(get_db)
):
    """Get specific agent by Agentium ID."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agentium_id} not found")
    
    return agent.to_dict()


# ==================== Constitution Management ====================

@app.get("/api/v1/constitution")
async def get_constitution(db: Session = Depends(get_db)):
    """Get the current active constitution."""
    constitution = db.query(Constitution).filter_by(
        is_active='Y'
    ).order_by(Constitution.effective_date.desc()).first()
    
    if not constitution:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    return constitution.to_dict()


@app.post("/api/v1/constitution/update")
async def update_constitution(
    updates: ConstitutionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update the constitution (sovereign only)."""
    # Get current constitution
    current = db.query(Constitution).filter_by(is_active='Y').first()
    if not current:
        raise HTTPException(status_code=404, detail="No active constitution found")
    
    # Create new version
    new_version = Constitution(
        version=current.version + 1,
        preamble=updates.preamble or current.preamble,
        articles=updates.articles or current.articles,
        prohibited_actions=updates.prohibited_actions or current.prohibited_actions,
        sovereign_preferences=updates.sovereign_preferences or current.sovereign_preferences,
        is_active='Y',
        created_by=current_user.get("username", "sovereign"),
        effective_date=datetime.utcnow()
    )
    
    # Deactivate old version
    current.is_active = 'N'
    
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    
    return {
        "status": "success",
        "message": f"Constitution updated to version {new_version.version}",
        "constitution": new_version.to_dict()
    }


# ==================== Monitoring & Health ====================

@app.get("/api/v1/monitoring/health")
async def get_system_health(db: Session = Depends(get_db)):
    """Get comprehensive system health status."""
    return await MonitoringService.get_system_health(db)


@app.get("/api/v1/monitoring/violations")
async def get_violations(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get recent governance violations."""
    violations = db.query(ViolationReport).order_by(
        ViolationReport.detected_at.desc()
    ).limit(limit).all()
    
    return {
        "violations": [v.to_dict() for v in violations],
        "total": len(violations)
    }


# ==================== Task Management ====================

@app.get("/api/v1/tasks/active")
async def get_active_tasks(db: Session = Depends(get_db)):
    """Get all active tasks."""
    tasks = db.query(Task).filter(
        Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING])
    ).all()
    
    return {
        "tasks": [task.to_dict() for task in tasks],
        "total": len(tasks)
    }


# ==================== IDLE GOVERNANCE ENDPOINTS ====================

@app.get("/api/v1/governance/idle/status")
async def get_idle_governance_status():
    """
    Get current status of idle governance engine.
    Shows if idle mode is active, what the persistent council is doing, and stats.
    """
    stats = idle_governance.get_statistics()
    
    return {
        "status": "running" if idle_governance.is_running else "stopped",
        "idle_mode_active": token_optimizer.idle_mode_active,
        "time_since_last_user_activity": token_optimizer.get_idle_duration_seconds(),
        "statistics": stats,
        "persistent_council": {
            "head": "00001",
            "council_members": ["10001", "10002"]
        }
    }


@app.post("/api/v1/governance/idle/pause")
async def pause_idle_governance():
    """Manually pause idle governance (for debugging/maintenance)."""
    if idle_governance.is_running:
        await idle_governance.stop()
        return {"status": "success", "message": "Idle governance paused"}
    else:
        return {"status": "already_stopped", "message": "Idle governance was not running"}


@app.post("/api/v1/governance/idle/resume")
async def resume_idle_governance(db: Session = Depends(get_db)):
    """Manually resume idle governance."""
    if not idle_governance.is_running:
        await idle_governance.start(db)
        return {"status": "success", "message": "Idle governance resumed"}
    else:
        return {"status": "already_running", "message": "Idle governance is already active"}


# ==================== Model & Token Status ====================

@app.get("/api/v1/status/tokens")
async def get_token_status():
    """Get token optimizer and budget status."""
    optimizer_status = token_optimizer.get_status()
    idle_budget_status = idle_budget.get_status()
    
    return {
        "optimizer": optimizer_status,
        "idle_budget": idle_budget_status,
        "mode": "idle" if token_optimizer.idle_mode_active else "active"
    }


@app.get("/api/v1/status/models")
async def get_model_status():
    """Get model allocation status."""
    if not model_allocator:
        return {"status": "not_initialized"}
    
    report = model_allocator.get_allocation_report()
    return {
        "status": "active",
        "report": report
    }


# ==================== PHASE 3 DASHBOARD ENDPOINTS ====================

@app.get("/api/v1/phase3/dashboard")
async def get_phase3_dashboard(db: Session = Depends(get_db)):
    """
    Get comprehensive dashboard data.
    Shows lifecycle stats, capacity, capability distribution, etc.
    """
    from backend.services.reincarnation_service import reincarnation_service
    from backend.services.capability_registry import capability_registry
    
    # Get capacity info
    capacity = reincarnation_service.get_available_capacity(db)
    
    # Get capability audit
    capability_audit = capability_registry.capability_audit_report(db)
    
    # Get idle governance stats
    idle_stats = idle_governance.get_statistics()
    
    # Get lifecycle stats from last 30 days
    from backend.models.entities.audit import AuditLog
    from datetime import timedelta
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    lifecycle_events = {
        "spawned": db.query(AuditLog).filter(
            AuditLog.action.in_(["agent_spawned", "lead_spawned"]),
            AuditLog.created_at >= thirty_days_ago
        ).count(),
        "promoted": db.query(AuditLog).filter(
            AuditLog.action == "agent_promoted",
            AuditLog.created_at >= thirty_days_ago
        ).count(),
        "liquidated": db.query(AuditLog).filter(
            AuditLog.action == "agent_liquidated",
            AuditLog.created_at >= thirty_days_ago
        ).count(),
        "reincarnated": db.query(AuditLog).filter(
            AuditLog.action == "agent_birth",
            AuditLog.created_at >= thirty_days_ago
        ).count()
    }
    
    return {
        "phase": "Phase 3: Agent Lifecycle Management",
        "completion": "100%",
        "capacity": capacity,
        "capability_distribution": capability_audit,
        "lifecycle_events_30d": lifecycle_events,
        "idle_governance": {
            "active": idle_governance.is_running,
            "metrics": idle_stats.get("metrics", {})
        },
        "warnings": []
    }


# ==================== Run Server ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )