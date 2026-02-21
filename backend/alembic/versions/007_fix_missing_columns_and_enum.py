"""Fix missing columns and taskstatus enum mismatch.

Revision ID: 007_fix_missing_columns_and_enum
Revises: 006_sync_task_and_voting_schema
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = '007_fix_missing_columns_and_enum'
down_revision = '006_sync_task_and_voting_schema'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_ethos_cols = {c['name'] for c in inspector.get_columns('ethos')}
    ethos_columns_to_add = [
        ('current_objective',         sa.Column('current_objective',         sa.Text(),  nullable=True)),
        ('active_plan',               sa.Column('active_plan',               sa.Text(),  nullable=True)),
        ('constitutional_references', sa.Column('constitutional_references',  sa.JSON(),  nullable=True)),
        ('task_progress_markers',     sa.Column('task_progress_markers',     sa.JSON(),  nullable=True)),
        ('reasoning_artifacts',       sa.Column('reasoning_artifacts',       sa.JSON(),  nullable=True)),
        ('outcome_summary',           sa.Column('outcome_summary',           sa.Text(),  nullable=True)),
        ('lessons_learned',           sa.Column('lessons_learned',           sa.Text(),  nullable=True)),
    ]
    for col_name, col_def in ethos_columns_to_add:
        if col_name not in existing_ethos_cols:
            op.add_column('ethos', col_def)

    existing_umc_cols = {c['name'] for c in inspector.get_columns('user_model_configs')}
    if 'agentium_id' not in existing_umc_cols:
        op.add_column('user_model_configs', sa.Column('agentium_id', sa.String(20), nullable=True))
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_model_configs_agentium_id ON user_model_configs (agentium_id) WHERE agentium_id IS NOT NULL")

    existing_enum_values = set(
        row[0] for row in conn.execute(
            text("SELECT unnest(enum_range(NULL::taskstatus))::text")
        ).fetchall()
    )
    for val in ['PENDING','DELIBERATING','APPROVED','REJECTED','DELEGATING','ASSIGNED','IN_PROGRESS','REVIEW','COMPLETED','FAILED','CANCELLED','IDLE_PENDING','IDLE_RUNNING','IDLE_PAUSED','IDLE_COMPLETED']:
        if val not in existing_enum_values:
            op.execute(text(f"ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS '{val}'"))

    existing_tasks_cols = {c['name'] for c in inspector.get_columns('tasks')}
    if 'agentium_id' not in existing_tasks_cols:
        op.add_column('tasks', sa.Column('agentium_id', sa.String(20), nullable=True))

    # Allow user_id to be NULL so system/sovereign configs don't need a real user
    try:
        op.execute(text("ALTER TABLE user_model_configs ALTER COLUMN user_id DROP NOT NULL"))
    except Exception:
        pass  # Already nullable, skip


def downgrade():
    pass