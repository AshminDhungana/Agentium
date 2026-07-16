"""drop unique constraint on model_usage_logs.agentium_id (idempotent)

model_usage_logs is a log table (one row per API call) but its migration
created agentium_id as UNIQUE, so every second usage log for the same agent
failed with a duplicate-key violation.  Drop the unique constraint; the column
stays as a plain (nullable) reference.

Revision ID: 008_modelusage_agentium_id
Revises: 007_tool_agentium_id
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "008_modelusage_agentium_id"
down_revision = "007_tool_agentium_id"
branch_labels = None
depends_on = None


def _has_constraint(table, name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return name in [c["name"] for c in inspector.get_unique_constraints(table)]


def upgrade():
    if _has_constraint("model_usage_logs", "model_usage_logs_agentium_id_key"):
        op.drop_constraint(
            "model_usage_logs_agentium_id_key",
            "model_usage_logs",
            type_="unique",
        )


def downgrade():
    if not _has_constraint("model_usage_logs", "model_usage_logs_agentium_id_key"):
        op.create_unique_constraint(
            "model_usage_logs_agentium_id_key",
            "model_usage_logs",
            ["agentium_id"],
        )
