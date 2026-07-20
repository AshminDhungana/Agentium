"""Add Ethos.working_method column for standard operating procedure (6.3)

Revision ID: 019_add_ethos_working_method
Revises: 018_add_ethos_environment_context
Create Date: 2026-07-20

Gives every agent a persistent, core-identity field describing its standard
working procedure / method, populated at agent creation alongside mission,
rules, and capabilities.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "019_add_ethos_working_method"
down_revision = "018_add_ethos_env_context"
branch_labels = None
depends_on = None


def _column_exists(conn, table, name):
    inspector = inspect(conn)
    return name in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "ethos", "working_method"):
        op.add_column(
            "ethos",
            sa.Column("working_method", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "ethos", "working_method"):
        op.drop_column("ethos", "working_method")
