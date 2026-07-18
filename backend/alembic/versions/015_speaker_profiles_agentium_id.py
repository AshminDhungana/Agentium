"""Add agentium_id to speaker_profiles (idempotent)

SpeakerProfile inherits ``agentium_id`` (non-nullable, unique) from BaseEntity,
but the original ``speaker_profiles`` table was created without that column
(see 000_combined_migration). Every query (e.g. GET /api/v1/audio/speakers via
``list_profiles``) and every insert (``enroll``) therefore fails with a missing
column / NOT NULL violation -> HTTP 500.

Add the column, backfill any existing rows, then enforce NOT NULL to match the
model. The ``enroll`` path now also sets ``agentium_id`` at insert time.

Revision ID: 015_speaker_profiles_agentium_id
Revises: 014_add_task_decision_id
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "015_speaker_profiles_agentium_id"
down_revision = "014_add_task_decision_id"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    bind = op.get_bind()
    if not _has_column("speaker_profiles", "agentium_id"):
        op.add_column(
            "speaker_profiles",
            sa.Column("agentium_id", sa.String(20), nullable=True),
        )

    # Backfill any rows that lack an agentium_id (pre-existing profiles).
    result = bind.execute(
        sa.text("SELECT id FROM speaker_profiles WHERE agentium_id IS NULL")
    )
    for (profile_id,) in result.fetchall():
        bind.execute(
            sa.text("UPDATE speaker_profiles SET agentium_id = :val WHERE id = :pid"),
            {"val": f"SP{uuid.uuid4().hex[:8]}", "pid": profile_id},
        )

    # Enforce NOT NULL to match the BaseEntity model contract.
    op.alter_column(
        "speaker_profiles",
        "agentium_id",
        existing_type=sa.String(20),
        nullable=False,
    )


def downgrade():
    op.drop_column("speaker_profiles", "agentium_id")
