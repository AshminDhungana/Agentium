"""Complete speaker_profiles BaseEntity columns (idempotent)

speaker_profiles was hand-created in 000_combined_migration without the
BaseEntity columns. 015 added ``agentium_id`` (NOT NULL, unique). This
migration adds the two remaining BaseEntity columns that the ORM model
references:

  * ``deleted_at``  (DateTime, nullable)  — soft-delete timestamp
  * ``is_active``   (Boolean, NOT NULL, default true)

Without them every query (e.g. GET /api/v1/audio/speakers ->
``list_profiles``) fails with ``UndefinedColumn: speaker_profiles.deleted_at
does not exist`` -> HTTP 500.

Revision ID: 016_speaker_profiles_baseentity_cols
Revises: 015_speaker_profiles_agentium_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "016_speaker_profiles_cols"
down_revision = "015_speaker_profiles_agentium_id"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    if not _has_column("speaker_profiles", "deleted_at"):
        op.add_column(
            "speaker_profiles",
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
    if not _has_column("speaker_profiles", "is_active"):
        op.add_column(
            "speaker_profiles",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade():
    if _has_column("speaker_profiles", "is_active"):
        op.drop_column("speaker_profiles", "is_active")
    if _has_column("speaker_profiles", "deleted_at"):
        op.drop_column("speaker_profiles", "deleted_at")
