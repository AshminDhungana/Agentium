"""Add Agent.is_temporary_overflow_head flag for overflow recovery (7.1)

Revision ID: 019_add_overflow_head_flag
Revises: 018_add_ethos_environment_context
Create Date: 2026-07-20

Marks the temporary secondary Head spawned during ID-pool exhaustion so it can
be excluded from normal governance/idle loops and scoped for safe self-termination.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "019_add_overflow_head_flag"
down_revision = "018_add_ethos_env_context"
branch_labels = None
depends_on = None


def _column_exists(conn, table, name):
    inspector = inspect(conn)
    return name in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "agents", "is_temporary_overflow_head"):
        op.add_column(
            "agents",
            sa.Column(
                "is_temporary_overflow_head",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "agents", "is_temporary_overflow_head"):
        op.drop_column("agents", "is_temporary_overflow_head")
