"""Settings page improvements — audit & user schema fixes

Revision ID: 007_improvements
Revises: 006_workflow
Create Date: 2026-03-19

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '007_improvements'
down_revision = '006_workflow'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    print("🚀 Starting migration 007_settings_improvements ...")

    # ── C4: Widen audit_logs.actor_id ────────────────────────────────────────
    # Previous size (10) was smaller than the max username length (50),
    # causing truncation / DB errors once audit entries are correctly persisted.
    print("\n--- C4: Widen audit_logs.actor_id VARCHAR(10) → VARCHAR(100) ---")

    existing_columns = {
        col['name']: col
        for col in inspector.get_columns('audit_logs')
    }

    if 'actor_id' in existing_columns:
        op.alter_column(
            'audit_logs',
            'actor_id',
            existing_type=sa.String(10),
            type_=sa.String(100),
            nullable=False,
        )
        print("  ✅ audit_logs.actor_id widened to VARCHAR(100)")
    else:
        print("  ⚠️  actor_id column not found on audit_logs — skipping")

    # ── D3: Add users.last_login_at ──────────────────────────────────────────
    # Nullable so existing rows are unaffected. The auth login route will
    # populate this on every successful DB-backed login going forward.
    print("\n--- D3: Add users.last_login_at ---")

    user_columns = {col['name'] for col in inspector.get_columns('users')}

    if 'last_login_at' not in user_columns:
        op.add_column(
            'users',
            sa.Column(
                'last_login_at',
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        print("  ✅ users.last_login_at column added")
    else:
        print("  ℹ️  users.last_login_at already exists — skipping")

    print("\n" + "=" * 60)
    print("✅ Migration 007_settings_improvements completed!")
    print("=" * 60)


def downgrade() -> None:
    print("🔄 Downgrading migration 007_settings_improvements ...")

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # Remove last_login_at
    user_columns = {col['name'] for col in inspector.get_columns('users')}
    if 'last_login_at' in user_columns:
        op.drop_column('users', 'last_login_at')
        print("  ✅ Dropped users.last_login_at")

    # Restore actor_id width (data may be truncated — acceptable for downgrade)
    audit_columns = {col['name'] for col in inspector.get_columns('audit_logs')}
    if 'actor_id' in audit_columns:
        op.alter_column(
            'audit_logs',
            'actor_id',
            existing_type=sa.String(100),
            type_=sa.String(10),
            nullable=False,
        )
        print("  ✅ audit_logs.actor_id restored to VARCHAR(10)")

    print("✅ Downgrade 007_settings_improvements completed.")