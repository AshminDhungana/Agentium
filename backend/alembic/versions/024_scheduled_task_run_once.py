"""Add ScheduledTask run_once/run_at lifecycle columns.

Task 2 of the §10.4 scheduled-tasks work extended the ScheduledTask model with
one-time schedules: a ``run_once`` flag and a ``run_at`` fire-time, and relaxed
``cron_expression`` to nullable (None is legal for one-time rows).  The model
changed at the ORM level but no migration was written, so the migrated
Postgres schema still lacks the columns.  This migration brings the DB schema
in line with the model.

Revision ID: 024_scheduled_task_run_once
Revises: 023_merge_022_heads
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "024_scheduled_task_run_once"
down_revision = "023_merge_022_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # cron_expression may now be omitted for one-time (run_once=True) rows.
    op.alter_column(
        "scheduled_tasks",
        "cron_expression",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    # One-time lifecycle columns (server_default so pre-existing rows are
    # back-filled to run_once=False / run_at=NULL).
    op.add_column(
        "scheduled_tasks",
        sa.Column(
            "run_once",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("run_at", sa.DateTime(), nullable=True),
    )

    # Pre-existing drift: the 000 combined migration created
    # scheduled_task_executions without the BaseEntity columns agentium_id and
    # updated_at.  Any ORM SELECT/INSERT of ScheduledTaskExecution (the
    # dispatcher's _record_execution, plus ScheduledTask.to_dict() serialising
    # execution_history) fails against the migrated schema.  Both columns were
    # already satisfied by BaseEntity at the ORM level for every other table;
    # add them here so the table matches its model.  agentium_id is nullable to
    # match the 000 file's legacy convention (e.g. user_model_configs,
    # browser_sessions) and because executions have no natural agentium_id at
    # insert time; updated_at gets a server default for existing rows.
    op.add_column(
        "scheduled_task_executions",
        sa.Column("agentium_id", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_scheduled_task_executions_agentium_id",
        "scheduled_task_executions",
        ["agentium_id"],
        unique=True,
        postgresql_where=sa.text("agentium_id IS NOT NULL"),
    )
    op.add_column(
        "scheduled_task_executions",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_task_executions", "updated_at")
    op.drop_index(
        "ix_scheduled_task_executions_agentium_id",
        table_name="scheduled_task_executions",
    )
    op.drop_column("scheduled_task_executions", "agentium_id")
    op.drop_column("scheduled_tasks", "run_at")
    op.drop_column("scheduled_tasks", "run_once")
    op.alter_column(
        "scheduled_tasks",
        "cron_expression",
        existing_type=sa.String(length=100),
        nullable=False,
    )