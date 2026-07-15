"""
Database configuration and session management for Agentium.
PostgreSQL-backed with connection pooling and async support.
"""

import os
import sqlite3
import logging
from typing import Generator, Optional
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool

from backend.models.entities.base import Base

logger = logging.getLogger(__name__)

# Configuration — all pool knobs are env-tunable via Settings.
from backend.core.config import settings  # noqa: E402  (kept local to limit import cost)

# Engine configuration with pooling (production-tuned, overridable per deploy)
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
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
def set_connection_params(dbapi_conn, connection_record):
    """Set UTC timezone and UTF-8 encoding for Postgres connections only."""
    # Skip DBAPI-level commands for SQLite connections used in tests
    try:
        if isinstance(dbapi_conn, sqlite3.Connection):
            return
    except Exception:
        # if we can't determine, fall through and attempt safe execution
        pass

    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone TO 'UTC'")
        cursor.execute("SET CLIENT_ENCODING TO 'UTF8'")
        cursor.close()
    except Exception as e:
        # Not a Postgres connection / driver doesn't support these commands — ignore
        try:
            cursor.close()
        except Exception:
            pass
        logger.debug("Skipping connection SET commands (not a Postgres connection): %s", e)


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

    logger.info(f"✅ Added {len(columns_to_add)} API Key Resilience columns to user_model_configs")


def get_next_agentium_id(db: Session, prefix: str) -> str:
    """
    Generate next available ID for a given prefix.
    Thread-safe sequence generation using SELECT FOR UPDATE.
    """
    from backend.models.entities.agents import Agent

    for_update = " FOR UPDATE" if db.get_bind().dialect.name == "postgresql" else ""

    result = db.execute(
        text(f"""
            SELECT agentium_id FROM agents
            WHERE agentium_id LIKE :pattern
            ORDER BY agentium_id DESC
            {for_update}
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
    dialect = db.get_bind().dialect.name
    if dialect != "postgresql":
        # SQLite / other DB: create a compatible table and insert defaults portably
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key         VARCHAR(128) PRIMARY KEY,
                value       TEXT         NOT NULL,
                description TEXT,
                updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("""
            INSERT OR IGNORE INTO system_settings (key, value, description, updated_at)
            VALUES
              ('daily_token_limit', '100000', 'Maximum tokens per day across all API providers', CURRENT_TIMESTAMP),
              ('daily_cost_limit',  '100.0',   'Maximum USD cost per day across all API providers', CURRENT_TIMESTAMP)
        """))
        db.commit()
        return

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key         VARCHAR(128) PRIMARY KEY,
            value       TEXT         NOT NULL,
            description TEXT,
            updated_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    # Ensure key has a unique constraint even if table was created by a model without it
    db.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE c.conrelid = 'system_settings'::regclass
                AND c.contype = 'p'
            ) THEN
                ALTER TABLE system_settings ADD PRIMARY KEY (key);
            END IF;
        END $$;
    """))
    db.execute(text("""
        INSERT INTO system_settings (key, value, description, updated_at)
        SELECT v.key, v.value, v.description, NOW()
        FROM (VALUES
            ('daily_token_limit', '100000',
             'Maximum tokens per day across all API providers'),
            ('daily_cost_limit',  '100.0',
             'Maximum USD cost per day across all API providers')
        ) AS v(key, value, description)
        WHERE NOT EXISTS (
            SELECT 1 FROM system_settings s WHERE s.key = v.key
        )
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
    
    # ── Dynamic Model Pricing ────────────────────────────────────────────────
    from backend.models.entities.model_pricing import ModelPricing  # noqa: F401

    # Create all tables that don't exist yet
    Base.metadata.create_all(bind=engine)

    # Phase 19 Known Issue: enable pg_stat_statements so slow-query analytics
    # (GET /admin/slow-queries + the daily Celery summary task) return data
    # instead of silently empty. Defensive: never block startup on optional
    # analytics if the module is not preloaded.
    try:
        from backend.services.slow_query_service import ensure_pg_stat_statements
        with get_db_context() as db:
            ensure_pg_stat_statements(db)
    except Exception as exc:  # pragma: no cover - optional, non-fatal
        logger.warning("[init_db] pg_stat_statements enable skipped: %s", exc)

    # Seed initial/system data
    with get_db_context() as db:
        create_initial_data(db)