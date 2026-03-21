"""Add task delegation engine tables and columns

Revision ID: 009_task_delegation
Revises: 008_skills
Create Date: 2026-03-21

What this migration does
─────────────────────────
Phase 13.1 — Automatic Task Delegation Engine

1. Creates `task_dependencies` table for DAG-based sub-task ordering.
2. Adds three new columns to `tasks`:
   - complexity_score      (Integer, nullable)
   - escalation_timeout_seconds (Integer, default 300)
   - delegation_metadata   (JSONB, nullable) — decision trail

All columns are nullable or have server defaults so this migration is
safe to run against a live database without downtime.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '009_task_delegation'
down_revision = '008_skills'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🚀 Starting migration 009_task_delegation ...")

    # =========================================================================
    # task_dependencies
    # =========================================================================
    if 'task_dependencies' not in existing_tables:
        op.create_table(
            'task_dependencies',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('parent_task_id', sa.String(36),
                      sa.ForeignKey('tasks.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('child_task_id', sa.String(36),
                      sa.ForeignKey('tasks.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('dependency_order', sa.Integer(), nullable=False,
                      server_default='0'),
            sa.Column('status', sa.String(20), nullable=False,
                      server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False,
                      server_default=sa.text('NOW()')),
        )

        op.create_index(
            'ix_task_deps_parent',
            'task_dependencies', ['parent_task_id'],
        )
        op.create_index(
            'ix_task_deps_child',
            'task_dependencies', ['child_task_id'],
        )
        op.create_index(
            'ix_task_deps_order',
            'task_dependencies', ['parent_task_id', 'dependency_order'],
        )

        print("  ✅ Created task_dependencies table")
    else:
        print("  ℹ️  task_dependencies already exists — skipping creation")

    # =========================================================================
    # New columns on tasks
    # =========================================================================
    existing_cols = {
        col['name'] for col in inspector.get_columns('tasks')
    }

    if 'complexity_score' not in existing_cols:
        op.add_column('tasks', sa.Column(
            'complexity_score', sa.Integer(), nullable=True,
        ))
        print("  ✅ Added complexity_score to tasks")

    if 'escalation_timeout_seconds' not in existing_cols:
        op.add_column('tasks', sa.Column(
            'escalation_timeout_seconds', sa.Integer(), nullable=False,
            server_default='300',
        ))
        print("  ✅ Added escalation_timeout_seconds to tasks")

    if 'delegation_metadata' not in existing_cols:
        op.add_column('tasks', sa.Column(
            'delegation_metadata', sa.JSON(), nullable=True,
        ))
        print("  ✅ Added delegation_metadata to tasks")

    print("\n" + "=" * 60)
    print("✅ Migration 009_task_delegation completed!")
    print("=" * 60)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🔄 Downgrading migration 009_task_delegation ...")

    # Drop new columns from tasks
    existing_cols = {
        col['name'] for col in inspector.get_columns('tasks')
    }

    for col_name in ('delegation_metadata', 'escalation_timeout_seconds', 'complexity_score'):
        if col_name in existing_cols:
            op.drop_column('tasks', col_name)
            print(f"  ✅ Dropped {col_name} from tasks")

    if 'task_dependencies' in existing_tables:
        op.drop_index('ix_task_deps_order', table_name='task_dependencies')
        op.drop_index('ix_task_deps_child', table_name='task_dependencies')
        op.drop_index('ix_task_deps_parent', table_name='task_dependencies')
        op.drop_table('task_dependencies')
        print("  ✅ Dropped task_dependencies")

    print("✅ Downgrade 009_task_delegation completed.")
