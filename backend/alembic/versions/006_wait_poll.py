"""006_wait_poll — create wait_conditions table

Revision ID: 006_wait_poll
Revises: 005_speaker_profiles
Create Date: 2025-01-01 00:00:00.000000

Non-breaking: adds a new table; no existing columns are modified.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ── Revision identifiers ──────────────────────────────────────────────────────

revision      = "006_wait_poll"
down_revision = "005_speaker_profiles"
branch_labels = None
depends_on    = None


# ── Enums (created idempotently) ──────────────────────────────────────────────
# create_type=False tells SQLAlchemy NOT to emit CREATE TYPE automatically.
# The DO $$ blocks in upgrade() handle creation safely on any PG version.

wait_strategy_enum = postgresql.ENUM(
    "http_poll", "redis_key", "timeout", "webhook", "manual",
    name="waitstrategy",
    create_type=False,
)

wait_condition_status_enum = postgresql.ENUM(
    "pending", "active", "resolved", "expired", "cancelled",
    name="waitconditionstatus",
    create_type=False,
)


def upgrade() -> None:
    # ── Create enum types ─────────────────────────────────────────────────
    # CREATE TYPE IF NOT EXISTS only works on PG 14+; use a DO block
    # checking pg_type instead — works on PG 9.6+ including Alpine PG 15.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'waitstrategy') THEN
                CREATE TYPE waitstrategy AS ENUM
                    ('http_poll','redis_key','timeout','webhook','manual');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'waitconditionstatus') THEN
                CREATE TYPE waitconditionstatus AS ENUM
                    ('pending','active','resolved','expired','cancelled');
            END IF;
        END $$;
    """)

    # ── Add WAITING to taskstatus enum ────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'waiting';
            END IF;
        END $$;
    """)

    # ── Add WAIT_ENTERED to checkpointphase enum ──────────────────────────
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'checkpointphase') THEN
                ALTER TYPE checkpointphase ADD VALUE IF NOT EXISTS 'wait_entered';
            END IF;
        END $$;
    """)

    # ── Create wait_conditions table ──────────────────────────────────────
    op.create_table(
        "wait_conditions",

        # BaseEntity columns (mirrors existing pattern)
        sa.Column("id",          sa.String(36),  nullable=False, primary_key=True),
        sa.Column("agentium_id", sa.String(20),  nullable=True,  unique=True),
        sa.Column("created_at",  sa.DateTime(),  nullable=True),
        sa.Column("updated_at",  sa.DateTime(),  nullable=True),
        sa.Column("is_active",   sa.Boolean(),   nullable=True,  server_default="true"),

        # Domain columns
        sa.Column("task_id", sa.String(36),
                  sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                  nullable=False),

        # ← Use the module-level ENUM objects (create_type=False) so SQLAlchemy
        #   does NOT fire a second CREATE TYPE after the DO $$ blocks above.
        sa.Column("strategy", wait_strategy_enum, nullable=False),

        sa.Column("status", wait_condition_status_enum,
                  nullable=False, server_default="pending"),

        # sa.text() is required for any server_default that contains a SQL
        # expression (cast, function call, etc.). Without it SQLAlchemy wraps
        # the value in extra quotes, producing invalid SQL like '''{}''::json'.
        sa.Column("config",                postgresql.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("max_attempts",          sa.Integer(), nullable=False, server_default="60"),
        sa.Column("attempt_count",         sa.Integer(), nullable=False, server_default="0"),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("expires_at",            sa.DateTime(), nullable=True),
        sa.Column("resolved_at",           sa.DateTime(), nullable=True),
        sa.Column("resolution_data",       postgresql.JSON(), nullable=True),
        sa.Column("failure_reason",        sa.Text(), nullable=True),
        sa.Column("created_by_agent_id",   sa.String(36), nullable=True),
    )

    # ── Indexes ───────────────────────────────────────────────────────────
    # Defined explicitly here — removed index=True from task_id column above
    # to avoid Alembic emitting a duplicate index.
    op.create_index("ix_wait_conditions_task_id", "wait_conditions", ["task_id"])
    op.create_index("ix_wait_conditions_status",  "wait_conditions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_wait_conditions_status",  table_name="wait_conditions")
    op.drop_index("ix_wait_conditions_task_id", table_name="wait_conditions")
    op.drop_table("wait_conditions")

    # Note: we intentionally do NOT remove 'waiting' from taskstatus or
    # 'wait_entered' from checkpointphase on downgrade — enum value removal
    # requires table rewrites and is almost never safe in production.
    op.execute("DROP TYPE IF EXISTS waitconditionstatus")
    op.execute("DROP TYPE IF EXISTS waitstrategy")