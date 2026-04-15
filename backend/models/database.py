"""
Database configuration and session management for Agentium.
PostgreSQL-backed with connection pooling and async support.
"""

import os
from typing import Generator, Optional
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool

from backend.models.entities.base import Base

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://agentium:agentium@localhost:5432/agentium"
)

# Engine configuration with pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,   # Prevent DetachedInstanceError in streaming contexts
    bind=engine
)

# Thread-local sessions
db_session = scoped_session(SessionLocal)


@event.listens_for(Engine, "connect")
def set_timezone(dbapi_conn, connection_record):
    """Set UTC timezone for all connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("SET timezone TO 'UTC'")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI endpoints.
    Yields a database session and ensures cleanup.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for database sessions in non-request contexts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_api_key_resilience_columns(db: Session):
    """
    Add Phase 5.4 columns to user_model_configs table if they don't exist.
    Uses SQLAlchemy inspector to avoid transaction state issues.
    """
    inspector = inspect(db.get_bind())

    try:
        existing_columns = {
            col['name'] for col in inspector.get_columns('user_model_configs')
        }
    except Exception:
        return

    columns_to_add = []

    if 'priority' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 999 NOT NULL"
        )
    if 'failure_count' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0 NOT NULL"
        )
    if 'last_failure_at' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS last_failure_at TIMESTAMP NULL"
        )
    if 'cooldown_until' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS cooldown_until TIMESTAMP NULL"
        )
    if 'monthly_budget_usd' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS monthly_budget_usd FLOAT DEFAULT 0.0 NOT NULL"
        )
    if 'current_spend_usd' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS current_spend_usd FLOAT DEFAULT 0.0 NOT NULL"
        )
    if 'last_spend_reset' not in existing_columns:
        columns_to_add.append(
            "ADD COLUMN IF NOT EXISTS last_spend_reset TIMESTAMP DEFAULT NOW() NOT NULL"
        )

    if not columns_to_add:
        return

    for alter_stmt in columns_to_add:
        try:
            db.execute(text(f"ALTER TABLE user_model_configs {alter_stmt}"))
            db.commit()
        except Exception as e:
            db.rollback()
            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                raise

    print(f"✅ Added {len(columns_to_add)} API Key Resilience columns to user_model_configs")


def get_next_agentium_id(db: Session, prefix: str) -> str:
    """
    Generate next available ID for a given prefix.
    Thread-safe sequence generation using SELECT FOR UPDATE.
    """
    from backend.models.entities.agents import Agent

    result = db.execute(
        text("""
            SELECT agentium_id FROM agents
            WHERE agentium_id LIKE :pattern
            ORDER BY agentium_id DESC
            FOR UPDATE
        """),
        {"pattern": f"{prefix}%"}
    ).fetchone()

    if result:
        last_num = int(result[0][1:])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{prefix}{new_num:04d}"


def check_health() -> dict:
    """Check database connectivity and performance."""
    try:
        start = datetime.utcnow()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database": "disconnected"
        }


def _ensure_system_settings(db: Session):
    """
    Create the system_settings table if it doesn't exist and seed
    default budget values. Uses raw SQL so it works before Alembic
    has run the dedicated migration.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key         VARCHAR(128) PRIMARY KEY,
            value       TEXT         NOT NULL,
            description TEXT,
            updated_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    db.execute(text("""
        INSERT INTO system_settings (key, value, description, updated_at)
        VALUES
            ('daily_token_limit', '100000',
             'Maximum tokens per day across all API providers', NOW()),
            ('daily_cost_limit',  '100.0',
             'Maximum USD cost per day across all API providers', NOW())
        ON CONFLICT (key) DO NOTHING
    """))
    db.commit()


def create_initial_data(db: Session):
    """
    Minimal seeding after tables are created.
    Constitution and Head of Council are created by PersistentCouncilService.
    """
    _ensure_system_settings(db)
    _ensure_api_key_resilience_columns(db)


def get_system_agent_id(db: Session) -> str:
    """
    Get the UUID (id) of Head of Council (00001).
    Used when system-level processes need to create alerts/monitoring records.
    """
    from backend.models.entities.agents import Agent

    head = db.query(Agent).filter(Agent.agentium_id == '00001').first()
    if not head:
        raise RuntimeError("Head of Council (00001) not found. Run genesis protocol.")
    return str(head.id)


def init_db():
    """
    Initialize database — create all tables via SQLAlchemy metadata.
    Imports every entity so their mappers register with Base.metadata
    before create_all() runs.
    """
    # ── Core / Base ──────────────────────────────────────────────────────────
    from backend.models.entities.base import Base  # noqa: F401

    # ── User & Auth ──────────────────────────────────────────────────────────
    from backend.models.entities.user import User  # noqa: F401
    from backend.models.entities.user_config import (  # noqa: F401
        UserModelConfig, ModelUsageLog, ProviderType, ConnectionStatus
    )

    # ── User Preferences ─────────────────────────────────────────────────────
    from backend.models.entities.user_preference import (  # noqa: F401
        UserPreference, UserPreferenceHistory
    )

    # ── Chat ─────────────────────────────────────────────────────────────────
    from backend.models.entities.chat_message import (  # noqa: F401
        ChatMessage, Conversation
    )

    # ── Constitution & Ethos ─────────────────────────────────────────────────
    from backend.models.entities.constitution import (  # noqa: F401
        Constitution, Ethos, DocumentType
    )

    # ── Agents ───────────────────────────────────────────────────────────────
    from backend.models.entities.agents import (  # noqa: F401
        Agent, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
        AgentType, AgentStatus
    )

    # ── Tasks ────────────────────────────────────────────────────────────────
    from backend.models.entities.task import (  # noqa: F401
        Task, SubTask, TaskAuditLog, TaskStatus, TaskPriority, TaskType
    )

    # ── Voting ───────────────────────────────────────────────────────────────
    from backend.models.entities.voting import (  # noqa: F401
        TaskDeliberation, IndividualVote, VotingRecord,
        AmendmentVoting, AmendmentStatus
    )

    # ── Audit ────────────────────────────────────────────────────────────────
    from backend.models.entities.audit import (  # noqa: F401
        AuditLog, ConstitutionViolation, SessionLog, HealthCheck,
        AuditLevel, AuditCategory
    )

    # ── Monitoring ───────────────────────────────────────────────────────────
    from backend.models.entities.monitoring import (  # noqa: F401
        AgentHealthReport, ViolationReport, ViolationSeverity,
        TaskVerification, PerformanceMetric, MonitoringAlert, MonitoringStatus
    )

    # ── Critics ──────────────────────────────────────────────────────────────
    from backend.models.entities.critics import (  # noqa: F401
        CriticAgent, CritiqueReview, CriticType, CriticVerdict
    )

    # ── Phase 6.1: Tool Management ───────────────────────────────────────────
    from backend.models.entities.tool_staging import ToolStaging  # noqa: F401
    from backend.models.entities.tool_version import ToolVersion  # noqa: F401
    from backend.models.entities.tool_usage_log import ToolUsageLog  # noqa: F401
    from backend.models.entities.tool_marketplace_listing import (  # noqa: F401
        ToolMarketplaceListing
    )

    # ── Channels ─────────────────────────────────────────────────────────────
    from backend.models.entities.channels import (  # noqa: F401
        ExternalChannel, ExternalMessage, ChannelType, ChannelStatus
    )

    # ── Scheduled Tasks ──────────────────────────────────────────────────────
    from backend.models.entities.scheduled_task import (  # noqa: F401
        ScheduledTask, ScheduledTaskExecution
    )

    # ── Phase 6.5: Checkpointing & Time-Travel Recovery ──────────────────────
    from backend.models.entities.checkpoint import (  # noqa: F401
        ExecutionCheckpoint, CheckpointPhase
    )

    # ── Workflow Engine (006_workflow) ────────────────────────────────────────
    from backend.models.entities.workflow import (  # noqa: F401
        WorkflowExecution, WorkflowSubTask
    )

    # ── Skills (Fix 12) ──────────────────────────────────────────────────────
    # Without this import Base.metadata.create_all() never sees SkillDB or
    # SkillSubmission and the skills / skill_submissions tables are not created.
    from backend.models.entities.skill import SkillDB, SkillSubmission  # noqa: F401

    # ── Phase 16.3: Citation Graph ───────────────────────────────────────────
    from backend.models.entities.citation_edge import CitationEdge  # noqa: F401

    # Create all tables that don't exist yet
    Base.metadata.create_all(bind=engine)

    # Seed initial/system data
    with get_db_context() as db:
        create_initial_data(db)