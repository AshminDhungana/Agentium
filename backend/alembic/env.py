"""
Alembic environment configuration for Agentium.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.entities.base import Base
from models.entities.agents import Agent, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent
from models.entities.constitution import Constitution, Ethos
from models.entities.voting import AmendmentVoting
from models.entities.task import Task, SubTask, TaskAuditLog
from models.entities.voting import TaskDeliberation
from models.entities.voting import IndividualVote, VotingRecord
from models.entities.audit import AuditLog, ConstitutionViolation, SessionLog, HealthCheck
from models.entities.channels import ExternalChannel, ExternalMessage, ChannelType, ChannelStatus
from models.entities.monitoring import (
    AgentHealthReport, 
    ViolationReport, 
    TaskVerification, 
    PerformanceMetric, 
    MonitoringAlert,
    MonitoringStatus,
    ViolationSeverity
)
from models.entities.user import User
from models.entities.user_config import UserModelConfig
from models.entities.voice_config import VoiceConfig  # NEW

# Phase 6.1 — Tool Management
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.tool_usage_log import ToolUsageLog
from backend.models.entities.tool_marketplace_listing import ToolMarketplaceListing
from backend.models.entities.knowledge_document import KnowledgeDocument

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate
target_metadata = Base.metadata

def get_url():
    """Get database URL from environment or config."""
    return os.getenv(
        "DATABASE_URL", 
        "postgresql://agentium:agentium@localhost:5432/agentium"
    )

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()