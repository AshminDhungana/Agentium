"""Add Agent.pending_identity_edit column for staged ethos identity edits

Revision ID: 013_add_pending_identity_edit
Revises: 012_fix_tasks_deliberation_fk
Create Date: 2026-07-17

The ethos tool stages core-identity edits (mission/rules/restrictions/
capabilities) on the owning Agent until a Lead/Head verifies them. The
staged patch is stored as JSON text on `agents.pending_identity_edit`,
gated by the existing `agents.ethos_action_pending` flag.

This column was added to the live ORM model but missed an Alembic
migration; this migration makes it present in fresh databases
(incl. the CI `agentium_test` db) so the tool works end-to-end.
"""

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "013_add_pending_identity_edit"
down_revision = "012_fix_tasks_deliberation_fk"
branch_labels = None
depends_on = None


def _column_exists(table, name):
    if context.is_offline_mode():
        return False
    conn = op.get_bind()
    inspector = inspect(conn)
    return name in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("agents", "pending_identity_edit"):
        op.add_column(
            "agents",
            sa.Column("pending_identity_edit", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("agents", "pending_identity_edit"):
        op.drop_column("agents", "pending_identity_edit")
