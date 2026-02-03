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

from backend.models.entities.base import Base
from backend.models.entities.agents import Agent, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent
from backend.models.entities.constitution import Constitution, Ethos, AmendmentVoting
from backend.models.entities.task import Task, SubTask, TaskAuditLog, TaskDeliberation
from backend.models.entities.voting import IndividualVote, VotingRecord
from backend.models.entities.audit import AuditLog, ConstitutionViolation, SessionLog, HealthCheck
from backend.models.entities.channels import Channel, ChannelMessage
from backend.models.entities.monitoring import SystemMetric, AgentMetric
from backend.models.entities.user import User
from backend.models.entities.user_config import UserModelConfig

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