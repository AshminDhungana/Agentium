"""Add Ethos.environment_context column for runtime/host grounding (6.1)

Revision ID: 018_add_ethos_environment_context
Revises: 017_add_effort
Create Date: 2026-07-19

Gives every agent a persistent, core-identity field describing its Docker
runtime and host bind mounts, populated at agent creation.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "018_add_ethos_environment_context"
down_revision = "017_add_effort"
branch_labels = None
depends_on = None


def _column_exists(conn, table, name):
    inspector = inspect(conn)
    return name in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "ethos", "environment_context"):
        op.add_column(
            "ethos",
            sa.Column("environment_context", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "ethos", "environment_context"):
        op.drop_column("ethos", "environment_context")
