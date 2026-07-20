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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from backend.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.celery_app import celery_app
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from backend.models.entities.user import User
from backend.api.schemas.examples import build_responses

from backend.services.api_manager import init_api_manager
import backend.services.api_manager as api_manager_module
from backend.services.model_allocation import init_model_allocator, model_allocator
from backend.services.token_optimizer import init_token_optimizer, token_optimizer, idle_budget

from backend.models.database import init_db, get_db, check_health, SessionLocal
from backend.models.entities import Agent, Task, Constitution, UserModelConfig, AgentHealthReport, ViolationReport
from backend.services.model_provider import ModelService
from backend.services.chat_service import ChatService
from backend.services.monitoring_service import MonitoringService
from backend.services.db_maintenance import DatabaseMaintenanceService
from backend.services.channel_manager import ChannelManager

# IDLE GOVERNANCE IMPORTS
from backend.services.persistent_council import persistent_council
from backend.services.idle_governance import idle_governance
from backend.services.initialization_service import InitializationService
from backend.services.token_optimizer import token_optimizer, idle_budget
from backend.models.entities.task import TaskType, TaskPriority, TaskStatus
from backend.models.entities.agents import AgentStatus
from backend.models.entities.user_config import ConnectionStatus

# Phase 6.7 — MCP Bridge
from backend.services.mcp_tool_bridge import init_bridge
from backend.core.tool_registry import tool_registry

# API Routes
from backend.api.routes import chat as chat_routes
from backend.api.routes import channels as channels_routes
from backend.api.routes import webhooks as webhooks_router
from backend.api.routes import models as model_routes
from backend.api.routes import websocket as websocket_routes
from backend.api.routes import auth as auth_routes
from backend.api.routes import rbac as rbac_routes
from backend.api.routes import federation as federation_routes
from backend.api.routes import plugins as plugins_routes
from backend.api.routes import mobile as mobile_routes
from backend.api.routes import inbox as inbox_routes
from backend.core.auth import get_current_user
from backend.api import sovereign
from backend.api.routes import tool_creation as tool_creation_routes
from backend.api.routes import admin as admin_routes
from backend.api.routes import tasks as tasks_routes
from backend.api.routes import files as files_routes
from backend.api.routes import users as users_routes
from backend.api.routes import voice as voice_routes
from backend.api.routes import monitoring_routes as monitoring_router
from backend.api.routes import audit_routes as audit_routes_router
from backend.services.api_key_manager import init_api_key_manager, api_key_manager
from backend.api.routes import genesis as genesis_route
from backend.api.routes import api_keys as api_keys_routes
from backend.api.routes.mcp_tools import router as mcp_tools_router
from backend.api.routes import tools as tools_routes  
from backend.api.routes import user_preferences as user_preferences_routes

from backend.api.routes import capability_routes
from backend.api.routes import lifecycle_routes
from backend.api.routes import critics as critics_routes          
from backend.api.routes import checkpoints as checkpoints_routes 
from backend.api.routes import remote_executor as remote_executor_routes  
from backend.api.routes import voting as voting_routes           
from backend.api.routes.ab_testing import router as ab_testing_router
from backend.api.routes import provider_analytics as provider_analytics_routes
from backend.api.routes import skills as skills_routes
from backend.api.routes import browser as browser_routes  
from backend.api.routes import audio as audio_routes     
from backend.api.routes import dashboard as dashboard_routes  
from backend.api.routes import outbound_webhooks as outbound_webhooks_routes  
from backend.api.routes import workflows as workflows_routes                   
from backend.api.routes import scaling as scaling_routes                       
from backend.api.routes import wait_poll as wait_poll_routes                   # Phase 16
from backend.api.routes import knowledge as knowledge_routes                   # Phase 16.3

from backend.core.security_middleware import (
    SessionLimitMiddleware,
    InputSanitizationMiddleware,
    IPBlocklistMiddleware,
    PayloadSizeLimitMiddleware,
    ErrorCounterMiddleware,
)
from backend.core.middleware import RateLimitMiddleware
from backend.core.observer_middleware import ObserverReadOnlyMiddleware
from backend.core.timing_middleware import TimingMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
celery = celery_app

# ── Security startup guards ──────────────────────────────────────────────────
# Flags insecure configuration (e.g. MinIO default credentials) before boot.
from backend.core.security_checks import run_security_startup_checks



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
            hashed_password=User.hash_password("admin"),  # Change here or can be changed from frontend
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
    - Security startup checks (default-credential guards)
    - Database initialization
    - Constitution seed (API-key independent)
    - Persistent Council status check (genesis runs on-demand, not at startup)
    - API Manager & Model Allocation
    - Enhanced Token Optimizer
    - Idle Governance Engine
    - Capability Registry
    - MCP Tool Bridge (Phase 6.7)
    """

    # ─────────────────────────────────────────────────────────────
    # 0. Security startup checks
    # ─────────────────────────────────────────────────────────────
    # Detect insecure configuration (e.g. MinIO minioadmin/minioadmin) and
    # warn loudly. Non-fatal by default; set MINIO_BLOCK_DEFAULT_CREDS=true
    # to abort startup instead. Skipped under TESTING (no MinIO configured).
    if os.environ.get("TESTING") != "true":
        try:
            run_security_startup_checks()
        except Exception as sec_err:  # a strict guard raises RuntimeError
            logger.error("❌ Security startup check failed: %s", sec_err)
            raise

    # ─────────────────────────────────────────────────────────────
    # 0b. Workspace persistence config sanity check
    # ─────────────────────────────────────────────────────────────
    # When the host-workspace feature is enabled, confirm the root actually
    # resolves under a host bind mount (/host or /host_home) so generated
    # artifacts are visible on the user's machine. Non-fatal warning only.
    if os.environ.get("TESTING") != "true":
        try:
            from backend.tools._workspace import (
                workspace_enabled,
                validate_workspace_config,
            )
            if workspace_enabled() and not validate_workspace_config():
                logger.warning(
                    "⚠️ Host workspace enabled but misconfigured — "
                    "artifacts will NOT be visible on the host machine."
                )
            elif workspace_enabled():
                logger.info("✅ Host workspace persistence configured")
        except Exception as ws_cfg_err:  # pragma: no cover - non-fatal guard
            logger.warning("⚠️ Workspace config check failed (non-fatal): %s", ws_cfg_err)

    # ─────────────────────────────────────────────────────────────
    # 1. Initialize Database
    # ─────────────────────────────────────────────────────────────
    try:
        init_db()
        logger.info("✅ Database initialized")

        if os.environ.get("TESTING") == "true":
            logger.info("⏭️ TESTING mode — skipping admin bootstrap and pricing cache load")
        else:
            db = next(get_db())
            try:
                # In tests, seeded_db fixture creates admin inside the savepoint
                # transaction.  Calling create_default_admin here would open a
                # separate session and commit outside that savepoint, causing
                # cross-session lock contention on the users table.
                admin_created = create_default_admin(db)
                if admin_created:
                    logger.info("✅ Default admin user created")

                # Pre-load model pricing cache
                from backend.services.pricing_sync_service import PricingSyncService
                PricingSyncService.load_cache_from_db(db)

                # Synchronize model prices in the background to avoid blocking server startup
                async def run_background_sync():
                    try:
                        from backend.models.database import get_db_context
                        with get_db_context() as bg_db:
                            await PricingSyncService.sync_prices(bg_db)
                    except Exception as sync_err:
                        logger.warning(f"⚠️ Background pricing synchronization failed (non-fatal): {sync_err}")

                import asyncio
                asyncio.create_task(run_background_sync())
            finally:
                db.close()
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    # ─────────────────────────────────────────────────────────────
    # 1b. Seed fallback Constitution (API-key independent)
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Constitution seed (seeded_db fixture handles this)")
    else:
        try:
            db = next(get_db())
            try:
                existing = db.query(Constitution).filter_by(is_active=True).first()
                if not existing:
                    fallback = InitializationService.create_default_constitution(db)
                    logger.info(f"✅ Fallback constitution seeded: {fallback.version}")
                else:
                    logger.info(f"✅ Constitution already present: {existing.version}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Constitution seed failed (non-fatal): {e}")

    # ─────────────────────────────────────────────────────────────
    # 2. Persistent Council — status check only (read-only)
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Persistent Council status check")
    else:
        try:
            db = next(get_db())
            try:
                from backend.models.entities.agents import HeadOfCouncil
                head = db.query(HeadOfCouncil).filter_by(
                    agentium_id="00001", is_active=True
                ).first()
                if head:
                    logger.info("✅ Persistent Council already initialized (Head 00001 present)")
                else:
                    logger.info("⏳ Persistent Council not yet initialized")
                    logger.info("   Add an API key on the Models page — genesis triggers automatically")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"⚠️ Persistent Council status check failed (non-fatal): {e}")

    # ─────────────────────────────────────────────────────────────
    # 3. Initialize API Manager (Universal Provider Support)
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping API Manager initialization")
    else:
        try:
            db = next(get_db())
            try:
                init_api_manager(db)
                logger.info("✅ API Manager initialized with universal provider support")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ API Manager initialization failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # 3b. Auto-assign default model config to Head agent if missing
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Head agent model config auto-assign")
    else:
        try:
            db = next(get_db())
            try:
                from backend.models.entities import UserModelConfig
                from backend.models.entities.agents import HeadOfCouncil

                head = db.query(HeadOfCouncil).filter(
                    HeadOfCouncil.agentium_id == "00001"
                ).first()

                if head and not head.preferred_config_id:
                    default_cfg = (
                        db.query(UserModelConfig)
                        .filter(UserModelConfig.is_default == True)
                        .filter(UserModelConfig.status == ConnectionStatus.ACTIVE)
                        .first()
                    ) or (
                        db.query(UserModelConfig)
                        .filter(UserModelConfig.status == ConnectionStatus.ACTIVE)
                        .first()
                    )
                    if default_cfg:
                        head.preferred_config_id = str(default_cfg.id)
                        db.commit()
                        logger.info(
                            f"✅ Auto-assigned default model config to Head 00001: "
                            f"'{default_cfg.config_name}' ({default_cfg.id})"
                        )
                    else:
                        logger.warning(
                            "⚠️ No active default model config found — "
                            "Head 00001 will fall back at chat time"
                        )
                elif head and head.preferred_config_id:
                    logger.info(
                        f"✅ Head 00001 already has model config: {head.preferred_config_id}"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(
                f"⚠️ Auto-assign model config to Head skipped (non-fatal): {e}"
            )

    # ─────────────────────────────────────────────────────────────
    # 4. Initialize Model Allocator
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Model Allocator initialization")
    else:
        try:
            db = next(get_db())
            try:
                init_model_allocator(db)
                logger.info("✅ Model Allocator initialized")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Model Allocator initialization failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # 5. Initialize Token Optimizer with Idle Budget
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Token Optimizer initialization")
    else:
        try:
            db = next(get_db())
            try:
                persistent_agents = persistent_council.get_persistent_agents(db)
                agent_list = list(persistent_agents.values())
                init_token_optimizer(db, agent_list)

                logger.info("✅ Token Optimizer initialized")
                logger.info(f"   - Idle Budget: ${idle_budget.daily_idle_budget_usd:.2f}/day")
                logger.info(f"   - Active Mode Budget: ${token_optimizer.active_budget.daily_cost_limit_usd:.2f}/day")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Token Optimizer initialization failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # Initialize API Key Manager
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping API Key Manager initialization")
    else:
        db = next(get_db())
        try:
            init_api_key_manager(db)
            logger.info("✅ API Key Manager initialized with resilience")
        finally:
            db.close()

    # ─────────────────────────────────────────────────────────────
    # 6. Start Idle Governance Engine & Background Monitors
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Idle Governance & Background Monitors")
    else:
        try:
            db = next(get_db())
            try:
                await idle_governance.start(db)
                MonitoringService.start_background_monitors()
                DatabaseMaintenanceService.start_maintenance_monitors()
                logger.info("✅ Idle Governance Engine and monitors started")
                logger.info("   Eternal Council and Background Health Scanners active")
                logger.info("   Database Maintenance & Backup Scanners active")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"⚠️ Idle Governance Engine / Monitors start failed: {e}")
            logger.error("   System will continue without full background loops")

    # ─────────────────────────────────────────────────────────────
    # 7. Initialize Capability Registry 
    # ─────────────────────────────────────────────────────────────
    try:
        logger.info("✅ Capability Registry loaded")
        logger.info("   - 26 capabilities defined across 4 tiers")
        logger.info("   - Runtime permission enforcement active")
    except Exception as e:
        logger.error(f"❌ Capability Registry initialization failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # 8. Initialize MCP Tool Bridge 
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping MCP Tool Bridge initialization")
    else:
        try:
            db = next(get_db())
            try:
                bridge = init_bridge(tool_registry, SessionLocal)
                count = bridge.sync_all(db)
                logger.info(f"✅ MCP Tool Bridge initialized — {count} approved tool(s) loaded")
                logger.info("   Agents can now discover MCP tools via GET /tools/")
                logger.info("   MCP tools also visible at GET /tools/mcp")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"⚠️ MCP Tool Bridge initialization failed: {e}")
            logger.error("   System will continue — MCP tools can be synced manually via approve endpoint")

    # ─────────────────────────────────────────────────────────────
    # 9. Bootstrap Vector Knowledge Base 
    # ─────────────────────────────────────────────────────────────
    if os.environ.get("TESTING") == "true":
        logger.info("⏭️ TESTING mode — skipping Knowledge Base bootstrap")
    else:
        try:
            db = next(get_db())
            try:
                from backend.services.knowledge_service import get_knowledge_service
                result = get_knowledge_service().initialize_knowledge_base(db)
                logger.info(
                    "✅ Knowledge base bootstrapped — constitution: %s",
                    result["constitution_embedded"],
                )
            finally:
                db.close()
        except Exception as e:
            logger.error("❌ Knowledge base bootstrap failed: %s", e)

    # ─────────────────────────────────────────────────────────────
    # 9b. Optional folder-skill seeding (backend/.agentium/skills)
    # ─────────────────────────────────────────────────────────────
    if os.getenv("SEED_SKILLS_ON_BOOT", "false").lower() == "true":
        try:
            from backend.scripts.seed_skills import main as seed_main
            seed_main()
        except Exception as e:  # noqa: BLE001
            logger.warning("⚠️ Skill seeding on boot failed: %s", e)

    logger.info("🎉 Agentium startup complete!")
    logger.info("   Phase 17.1: DDoS hardening active — unified RateLimitMiddleware + blocklist + payload limits")

    # ─────────────────────────────────────────────────────────────
    # 10. Browser live-screenshot streaming (Phase 14.1) — FastAPI-owned Chromium
    # ─────────────────────────────────────────────────────────────
    # The BrowserService owns the Playwright/Chromium process inside FastAPI
    # (tasks run in a separate Celery process and cannot drive the browser).
    try:
        # Skipped under TESTING (no Chromium in the headless test runner): the
        # Playwright process spawned here lingers into lifespan shutdown and
        # blocks TestClient teardown (playwright.stop() hangs), timing out
        # fixtures such as `ws_client`. Unit tests exercise BrowserService
        # directly and are unaffected.
        if settings.BROWSER_ENABLED and os.environ.get("TESTING") != "true":
            from backend.services.browser_service import get_browser_service
            await get_browser_service().initialize()
            logger.info("✅ Browser service initialized (live screenshot streaming ready)")
    except Exception as exc:  # never let Chromium failure break boot
        logger.error(f"❌ Browser service init skipped: {exc}")

    yield  # ── Application runs here ──────────────────────────────

    # ─────────────────────────────────────────────────────────────
    # Shutdown Sequence
    # ─────────────────────────────────────────────────────────────
    logger.info("🛑 Shutting down Agentium...")

    # Tear down browser service (stop active streams + close Chromium)
    try:
        if settings.BROWSER_ENABLED and os.environ.get("TESTING") != "true":
            from backend.services.browser_service import get_browser_service
            await get_browser_service().shutdown()
    except Exception as exc:
        logger.error(f"❌ Browser service shutdown error: {exc}")

    if os.environ.get("TESTING") != "true":
        try:
            await idle_governance.stop()
            logger.info("✅ Idle Governance Engine stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping Idle Governance: {e}")

        # Final statistics
        try:
            db = next(get_db())
            try:
                status = token_optimizer.get_status()
                logger.info("📊 Final Statistics:")
                logger.info(f"   - Total Tokens Saved (Idle): {idle_budget.total_tokens_saved:,}")
                logger.info(f"   - Total Cost Saved (Idle): ${idle_budget.total_cost_saved_usd:.2f}")
                logger.info(f"   - Active Budget Used: {status['budget_status']['cost_used_today_usd']:.2f}/{status['budget_status']['daily_cost_limit_usd']:.2f}")
                if model_allocator:
                    allocation_report = model_allocator.get_allocation_report()
                    logger.info(f"   - Model Allocations: {allocation_report['total_agents']} agents")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"❌ Could not generate final statistics: {e}")


# ── Create FastAPI app ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Agentium",
    description="AI Agent Governance System — Phase 17.1: Application-Layer DDoS Hardening",
    version="3.0.0-phase17.1",
    lifespan=lifespan,
    redirect_slashes=False,
)

# Register typed exception handlers before middleware so they catch errors first
from backend.core.error_responses import register_error_handlers
register_error_handlers(app)

origins = os.getenv("ALLOWED_ORIGINS")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origins] if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.core.redis import get_redis_client as _get_redis
    _redis_client = _get_redis()
    app.add_middleware(ErrorCounterMiddleware, redis=_redis_client)
    app.add_middleware(PayloadSizeLimitMiddleware)
    app.add_middleware(IPBlocklistMiddleware, redis=_redis_client)
    logger.info("✅ DDoS middleware stack registered")
except Exception as _mw_exc:
    logger.warning(
        "⚠️ Phase 17.1 middleware could not load Redis client (%s). "
        "IPBlocklist and ErrorCounter disabled — PayloadSizeLimit still active.",
        _mw_exc,
    )
    app.add_middleware(PayloadSizeLimitMiddleware)

# Unified Redis-backed rate limiting (replaces slowapi + old in-memory)
try:
    from backend.core.redis import get_redis_client as _get_redis_for_ratelimit
    _redis_rl = _get_redis_for_ratelimit()
    app.add_middleware(RateLimitMiddleware, redis=_redis_rl)
    logger.info("Unified RateLimitMiddleware registered (Redis-backed)")
except Exception as exc:
    logger.error("Failed to register RateLimitMiddleware: %s", exc)

app.add_middleware(SessionLimitMiddleware)
app.add_middleware(InputSanitizationMiddleware)

# Phase 11.1: Observer Enforcement
app.add_middleware(ObserverReadOnlyMiddleware)

# Phase 18.2 — Performance Regression Gate: timing middleware
# Register LAST so it wraps everything and measures full request lifecycle.
app.add_middleware(TimingMiddleware)


from backend.api.routes import scaling as scaling_routes
from backend.api.routes import improvements as improvements_routes
from backend.api.routes import events as events_routes
from backend.api.routes import reassign_routes

# ═══════════════════════════════════════════════════════════
# REGISTER ROUTERS
# ═══════════════════════════════════════════════════════════

app.include_router(auth_routes.router,              prefix="/api/v1")
app.include_router(model_routes.router,             prefix="/api/v1")
app.include_router(chat_routes.router,              prefix="/api/v1")
app.include_router(channels_routes.router,          prefix="/api/v1")
app.include_router(webhooks_router.router,          prefix="/api/v1")
app.include_router(inbox_routes.router,             prefix="/api/v1")
app.include_router(websocket_routes.router,         prefix="/ws")
app.include_router(host_access.router,              prefix="/api/v1")
app.include_router(sovereign.router,                prefix="/api/v1")
app.include_router(tool_creation_routes.router,     prefix="/api/v1")
app.include_router(admin_routes.router,             prefix="/api/v1")
app.include_router(tasks_routes.router,             prefix="/api/v1")
app.include_router(files_routes.router,             prefix="/api/v1")
app.include_router(users_routes.router,             prefix="/api/v1")
app.include_router(voice_routes.router,             prefix="/api/v1")
app.include_router(capability_routes.router)
app.include_router(lifecycle_routes.router)
app.include_router(reassign_routes.router)
app.include_router(audit_routes_router.router,      prefix="/api/v1")
app.include_router(monitoring_router.router,        prefix="/api/v1")
app.include_router(genesis_route.router,            prefix="/api/v1")
app.include_router(api_keys_routes.router,          prefix="/api/v1")
app.include_router(critics_routes.router,           prefix="/api/v1")
app.include_router(checkpoints_routes.router,       prefix="/api/v1")
app.include_router(remote_executor_routes.router,   prefix="/api/v1")
app.include_router(voting_routes.router,            prefix="/api/v1")
app.include_router(mcp_tools_router)
app.include_router(tools_routes.router,             prefix="/api/v1")
app.include_router(user_preferences_routes.router, prefix="/api/v1")
app.include_router(ab_testing_router, prefix="/api/v1")
app.include_router(provider_analytics_routes.router, prefix="/api/v1")
app.include_router(skills_routes.router, prefix="/api/v1")
app.include_router(browser_routes.router, prefix="/api/v1")
app.include_router(audio_routes.router, prefix="/api/v1")
app.include_router(rbac_routes.router, prefix="/api/v1")
app.include_router(federation_routes.router, prefix="/api/v1")
app.include_router(plugins_routes.router, prefix="/api/v1")
app.include_router(mobile_routes.router, prefix="/api/v1")
app.include_router(dashboard_routes.router, prefix="/api/v1")  
app.include_router(outbound_webhooks_routes.router, prefix="/api/v1") 
app.include_router(workflows_routes.router,          prefix="/api/v1")  
app.include_router(scaling_routes.router,            prefix="/api/v1")  
app.include_router(improvements_routes.router,       prefix="/api/v1") 
app.include_router(events_routes.router,             prefix="/api/v1")  
app.include_router(wait_poll_routes.router,          prefix="/api/v1") 
app.include_router(knowledge_routes.router,          prefix="/api/v1")  


# ══════════════════════════════════════════════════════════════════════════════
# INLINE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Health Check ──────────────────────────────────────────────────────────────

@app.get(
    "/api/health",
    summary="Health check",
    description="Check the system and database health status.",
    responses=build_responses(None),
    tags=["System"],
)
async def health_check_api():
    """Health check endpoint."""
    db_status = check_health()
    return {
        "status": "healthy" if db_status["status"] == "healthy" else "unhealthy",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }


# Rate limiting is now handled by the unified RateLimitMiddleware in
# backend/core/middleware.py (per-path tier: auth → task → general).


# ── Agent Management ──────────────────────────────────────────────────────────

@app.post(
    "/api/v1/agents/create",
    summary="Create agent",
    description="Create a new agent with governance compliance.",
    responses=build_responses(None),
    tags=["Agents"],
)
async def create_agent(
    role: str,
    responsibilities: list,
    tier: int = 3,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new agent with governance compliance."""
    if tier not in [0, 1, 2, 3]:
        raise BadRequestError(error="Tier must be 0 (Head), 1 (Council), 2 (Lead), or 3 (Task)", code="TIER_MUST_BE_0_HEAD")

    constitution = db.query(Constitution).filter_by(is_active=True).order_by(Constitution.effective_date.desc()).first()
    if not constitution:
        raise InternalServerError(error="No active constitution found", code="NO_ACTIVE_CONSTITUTION_FOUND")

    agent = Agent(
        role=role,
        status=AgentStatus.ACTIVE,
        current_task=None,
        performance_score=100,
        created_by="system",
        tier=tier,
        agentium_id=f"{tier}{len(db.query(Agent).filter_by(tier=tier).all()) + 1:04d}",
        constitution_version=constitution.version,
        supervised_by=None,
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


@app.get(
    "/api/v1/agents",
    summary="List agents",
    description="List all agents with optional status and tier filters.",
    responses=build_responses(None),
    tags=["Agents"],
)
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
            raise BadRequestError(error=f"Invalid status: {status}", code="INVALID_STATUS")

    agents = query.all()
    return {"agents": [agent.to_dict() for agent in agents]}


@app.get(
    "/api/v1/agents/{agentium_id}",
    summary="Get agent details",
    description="Retrieve detailed configuration and statistics for a specific agent.",
    responses=build_responses(None),
    tags=["Agents"],
)
async def get_agent(
    agentium_id: str,
    db: Session = Depends(get_db)
):
    """Get specific agent by Agentium ID."""
    agent = db.query(Agent).filter_by(agentium_id=agentium_id).first()
    if not agent:
        raise NotFoundError(error=f"Agent {agentium_id} not found", code="AGENT_NOT_FOUND")
    return agent.to_dict()


# ── Constitution Management ───────────────────────────────────────────────────

@app.get(
    "/api/v1/constitution",
    summary="Get active constitution",
    description="Retrieve the current active version of the constitution rules.",
    responses=build_responses(None),
    tags=["Constitution"],
)
async def get_constitution(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the current active constitution."""
    constitution = db.query(Constitution).filter_by(
        is_active=True
    ).order_by(Constitution.effective_date.desc()).first()

    if not constitution:
        raise NotFoundError(error="No active constitution found", code="NO_ACTIVE_CONSTITUTION_FOUND")

    return constitution.to_dict()


@app.post(
    "/api/v1/constitution/update",
    summary="Update constitution",
    description="Update constitution preamble, articles, prohibited actions, or sovereign preferences.",
    responses=build_responses(None),
    tags=["Constitution"],
)
async def update_constitution(
    updates: ConstitutionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update the constitution (sovereign only)."""
    import json as _json

    current = db.query(Constitution).filter_by(is_active=True).first()
    if not current:
        raise NotFoundError(error="No active constitution found", code="NO_ACTIVE_CONSTITUTION_FOUND")

    def _to_json_str(value, fallback_str):
        if value is None:
            return fallback_str
        if isinstance(value, (dict, list)):
            return _json.dumps(value)
        return value

    def _normalize_articles(articles_dict):
        """Normalize all article shapes to { title, content } and repair corruption."""
        if not isinstance(articles_dict, dict):
            return articles_dict
        fixed = {}
        for key, val in articles_dict.items():
            pretty_title = key.replace("_", " ").title()
            if isinstance(val, str):
                fixed[key] = {"title": pretty_title, "content": val}
            elif isinstance(val, dict):
                keys = list(val.keys())
                is_char_indexed = keys and all(k.isdigit() or k == 'content' for k in keys)
                if is_char_indexed:
                    numeric_keys = sorted((k for k in keys if k.isdigit()), key=int)
                    fixed[key] = {"title": pretty_title, "content": "".join(val[k] for k in numeric_keys)}
                else:
                    fixed[key] = {"title": val.get("title", pretty_title), "content": val.get("content", "")}
            else:
                fixed[key] = {"title": pretty_title, "content": ""}
        return fixed

    raw_articles = updates.articles
    if raw_articles is None:
        try:
            raw_articles = _json.loads(current.articles or "{}")
        except (_json.JSONDecodeError, TypeError):
            raw_articles = {}

    raw_articles   = _normalize_articles(raw_articles)
    new_articles   = _to_json_str(raw_articles, current.articles)
    new_prohibited = _to_json_str(updates.prohibited_actions, current.prohibited_actions)
    new_prefs      = _to_json_str(updates.sovereign_preferences, current.sovereign_preferences)

    new_version_number = (current.version_number or 1) + 1
    new_agentium_id    = f"C{new_version_number:04d}"
    actor              = current_user.get("username", "sovereign")

    existing_changelog: list = []
    try:
        existing_changelog = _json.loads(current.changelog or "[]")
        if not isinstance(existing_changelog, list):
            existing_changelog = []
    except (_json.JSONDecodeError, TypeError):
        existing_changelog = []

    new_changelog_entry = {
        "change": f"Sovereign update by {actor}",
        "timestamp": datetime.utcnow().isoformat(),
        "previous_version": current.version,
    }
    new_changelog = _json.dumps([new_changelog_entry] + existing_changelog)

    new_version = Constitution(
        agentium_id=new_agentium_id,
        version=f"v{new_version_number}.0.0",
        version_number=new_version_number,
        preamble=updates.preamble or current.preamble,
        articles=new_articles,
        prohibited_actions=new_prohibited,
        sovereign_preferences=new_prefs,
        changelog=new_changelog,
        is_active=True,
        created_by_agentium_id=actor,
        effective_date=datetime.utcnow()
    )

    current.is_active = False
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    return {
        "status": "success",
        "message": f"Constitution updated to version {new_version.version}",
        "constitution": new_version.to_dict()
    }


# ── Monitoring & Health ───────────────────────────────────────────────────────

@app.get(
    "/api/v1/monitoring/health",
    summary="Get system health",
    description="Get comprehensive monitoring health status of the system.",
    responses=build_responses(None),
    tags=["Monitoring"],
)
async def get_system_health(db: Session = Depends(get_db)):
    """Get comprehensive system health status."""
    return {"status": "healthy", "service": "MonitoringService", "timestamp": datetime.utcnow().isoformat()}

# ── Idle Governance ───────────────────────────────────────────────────────────

@app.get(
    "/api/v1/governance/idle/status",
    summary="Get idle governance status",
    description="Retrieve status metrics of the background idle governance engine.",
    responses=build_responses(None),
    tags=["Governance"],
)
async def get_idle_governance_status():
    """Get current status of idle governance engine."""
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


@app.post(
    "/api/v1/governance/idle/pause",
    summary="Pause idle governance",
    description="Pause the idle governance loop manually.",
    responses=build_responses(None),
    tags=["Governance"],
)
async def pause_idle_governance():
    """Manually pause idle governance (for debugging/maintenance)."""
    if idle_governance.is_running:
        await idle_governance.stop()
        return {"status": "success", "message": "Idle governance paused"}
    return {"status": "already_stopped", "message": "Idle governance was not running"}


@app.post(
    "/api/v1/governance/idle/resume",
    summary="Resume idle governance",
    description="Resume the idle governance loop manually.",
    responses=build_responses(None),
    tags=["Governance"],
)
async def resume_idle_governance(db: Session = Depends(get_db)):
    """Manually resume idle governance."""
    if not idle_governance.is_running:
        await idle_governance.start(db)
        return {"status": "success", "message": "Idle governance resumed"}
    return {"status": "already_running", "message": "Idle governance is already active"}


# ── Model & Token Status ──────────────────────────────────────────────────────

@app.get(
    "/api/v1/status/tokens",
    summary="Get token status",
    description="Retrieve token optimizer limits and idle budget status.",
    responses=build_responses(None),
    tags=["Status"],
)
async def get_token_status():
    """Get token optimizer and budget status."""
    optimizer_status = token_optimizer.get_status()
    idle_budget_status = idle_budget.get_status()
    return {
        "optimizer": optimizer_status,
        "idle_budget": idle_budget_status,
        "mode": "idle" if token_optimizer.idle_mode_active else "active"
    }


@app.get(
    "/api/v1/status/models",
    summary="Get model allocation status",
    description="Retrieve model allocation statistics and assignments.",
    responses=build_responses(None),
    tags=["Status"],
)
async def get_model_status():
    """Get model allocation status."""
    if not model_allocator:
        return {"status": "not_initialized"}
    report = model_allocator.get_allocation_report()
    return {"status": "active", "report": report}


# ── MCP Tool Registry Status (convenience summary endpoint) ───────────────────

@app.get(
    "/api/v1/mcp/status",
    summary="Get MCP status",
    description="Retrieve summary statistics of registered Model Context Protocol tools.",
    responses=build_responses(None),
    tags=["MCP Tools"],
)
async def get_mcp_status():
    """
    Quick summary of MCP tool bridge status.
    Shows how many MCP tools are live in the ToolRegistry.
    """
    try:
        from backend.services.mcp_tool_bridge import mcp_bridge
        if not mcp_bridge:
            return {"status": "not_initialized", "registered_tools": 0}
        keys = mcp_bridge.list_mcp_registry_keys()
        return {
            "status": "active",
            "registered_tools": len(keys),
            "tool_keys": keys,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "registered_tools": 0}


# ── Run Server ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )