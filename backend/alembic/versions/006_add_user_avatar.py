"""add avatar columns to users (idempotent)

Revision ID: 006_add_user_avatar
Revises: 005_speaker_profile_is_deleted
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "006_add_user_avatar"
down_revision = "005_speaker_profile_is_deleted"
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    if not _has_column("users", "avatar_url"):
        op.add_column(
            "users",
            sa.Column("avatar_url", sa.String(length=512), nullable=True),
        )
    if not _has_column("users", "avatar_object_name"):
        op.add_column(
            "users",
            sa.Column("avatar_object_name", sa.String(length=512), nullable=True),
        )


def downgrade():
    if _has_column("users", "avatar_object_name"):
        op.drop_column("users", "avatar_object_name")
    if _has_column("users", "avatar_url"):
        op.drop_column("users", "avatar_url")
