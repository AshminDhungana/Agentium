"""add nullable agentium_id to tool tables (idempotent)

ToolVersion, ToolStaging and ToolUsageLog inherit `agentium_id` from BaseEntity
but their original migration never created that column, causing
"column tool_versions.agentium_id does not exist" at query time.  Add the
column as nullable (matching the existing tool_marketplace_listings fix).

Revision ID: 007_tool_agentium_id
Revises: 006_add_user_avatar
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "007_tool_agentium_id"
down_revision = "006_add_user_avatar"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    for table in ("tool_versions", "tool_staging", "tool_usage_logs"):
        if not _has_column(table, "agentium_id"):
            op.add_column(
                table,
                sa.Column("agentium_id", sa.String(length=20), nullable=True),
            )


def downgrade():
    for table in ("tool_versions", "tool_staging", "tool_usage_logs"):
        if _has_column(table, "agentium_id"):
            op.drop_column(table, "agentium_id")
