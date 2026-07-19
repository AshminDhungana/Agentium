"""add effort column to user_model_configs

Revision ID: 017_add_effort
Revises: 016_speaker_profiles_cols
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "017_add_effort"
down_revision = "016_speaker_profiles_cols"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_model_configs",
        sa.Column("effort", sa.String(16), nullable=False, server_default="none"),
    )


def downgrade():
    op.drop_column("user_model_configs", "effort")
