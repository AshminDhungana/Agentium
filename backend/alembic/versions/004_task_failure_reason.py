"""task provider-exhaustion failure_reason

Revision ID: 004_task_failure_reason
Revises: 003_provider_rate_limits
"""
from alembic import op
import sqlalchemy as sa

revision = "004_task_failure_reason"
down_revision = "003_provider_rate_limits"
branch_labels = None
depends_on = None


def upgrade():
    # Phase 19.3: structured provider-exhaustion reason
    # (rate_limited | all_keys_invalid | provider_unreachable) recorded when a
    # task fails cleanly after all provider configs are exhausted (Task 12).
    op.add_column(
        "tasks",
        sa.Column("failure_reason", sa.String(50), nullable=True),
    )
    op.create_index(
        "ix_tasks_failure_reason", "tasks", ["failure_reason"], unique=False
    )


def downgrade():
    op.drop_index("ix_tasks_failure_reason", table_name="tasks")
    op.drop_column("tasks", "failure_reason")
