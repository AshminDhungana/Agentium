"""add is_deleted to speaker_profiles (idempotent)

Revision ID: 005_speaker_profile_is_deleted
Revises: 004_task_failure_reason
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "005_speaker_profile_is_deleted"
down_revision = "004_task_failure_reason"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    if not _has_column("speaker_profiles", "is_deleted"):
        op.add_column(
            "speaker_profiles",
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade():
    if _has_column("speaker_profiles", "is_deleted"):
        op.drop_column("speaker_profiles", "is_deleted")
