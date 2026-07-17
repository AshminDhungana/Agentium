"""Add Task.decision_id column to correlate tasks with DecisionEngine decisions

Revision ID: 014_add_task_decision_id
Revises: 013_add_pending_identity_edit
Create Date: 2026-07-17

Each decision produced by the DecisionEngine now carries a `decision_id`
(UUID). When a decision spawns a task, the task stores that id as
`decision_id` so it can be traced back to the audit-log entry emitted with
the same value in `AuditLog.correlation_id`. This enables end-to-end
observability of the "decision -> work" chain.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "014_add_task_decision_id"
down_revision = "013_add_pending_identity_edit"
branch_labels = None
depends_on = None


def _column_exists(conn, table, name):
    inspector = inspect(conn)
    return name in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "tasks", "decision_id"):
        op.add_column(
            "tasks",
            sa.Column("decision_id", sa.String(64), nullable=True),
        )
        op.create_index(
            "ix_tasks_decision_id", "tasks", ["decision_id"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "tasks", "decision_id"):
        op.drop_index("ix_tasks_decision_id", table_name="tasks")
        op.drop_column("tasks", "decision_id")
