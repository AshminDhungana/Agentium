"""
Database configuration and session management for Agentium.
PostgreSQL-backed with connection pooling and async support.
"""

import os
from typing import Generator, Optional
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool

from backend.models.entities import Base

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://agentium:agentium@localhost:5432/agentium"
)

# Engine configuration with pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,              # Default connections in pool
    max_overflow=10,           # Extra connections when pool is full
    pool_pre_ping=True,        # Verify connections before using
    pool_recycle=3600,         # Recycle connections after 1 hour
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Thread-local sessions
db_session = scoped_session(SessionLocal)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Configure connection settings."""
    # Enable timezone awareness
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


def init_db():
    """Initialize database - create all tables."""
    # Import all models to register them with Base
    from backend.models.entities import (
        Constitution, Ethos, AmendmentVoting,
        Agent, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
        Task, SubTask, TaskAuditLog,
        TaskDeliberation, IndividualVote, VotingRecord,
        AuditLog, ConstitutionViolation, SessionLog, HealthCheck
    )
    
    Base.metadata.create_all(bind=engine)
    
    # Create initial data if empty
    with get_db_context() as db:
        create_initial_data(db)


def create_initial_data(db: Session):
    """
    Database initialization - minimal seeding only.
    NOTE: Constitution and Head of Council are created by PersistentCouncilService.
    """
    pass  # PersistentCouncilService handles all initialization


def get_next_agentium_id(db: Session, prefix: str) -> str:
    """
    Generate next available ID for a given prefix.
    Thread-safe sequence generation.
    """
    from backend.models.entities.agents import Agent
    
    # Lock table to prevent race conditions
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
        last_num = int(result[0][1:])  # Remove prefix
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