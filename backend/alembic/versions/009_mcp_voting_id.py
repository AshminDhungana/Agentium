"""add voting_id to mcp_tools

Revision ID: 009_mcp_voting_id
Revises: 008_modelusage_agentium_id
"""
from alembic import op
import sqlalchemy as sa

revision = "009_mcp_voting_id"
down_revision = "008_modelusage_agentium_id"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mcp_tools",
        sa.Column("voting_id", sa.String(64), nullable=True),
    )


def downgrade():
    op.drop_column("mcp_tools", "voting_id")
