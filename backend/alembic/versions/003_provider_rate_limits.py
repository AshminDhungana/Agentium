"""provider rate-limit fields

Revision ID: 003_provider_rate_limits
Revises: 002_add_browser_tasktype
"""
from alembic import op
import sqlalchemy as sa

revision = "003_provider_rate_limits"
down_revision = "002_add_browser_tasktype"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("user_model_configs", "rate_limit",
                    new_column_name="requests_per_minute",
                    existing_type=sa.Integer(), existing_nullable=True)
    op.execute("UPDATE user_model_configs SET requests_per_minute = 60 "
               "WHERE requests_per_minute IS NULL")
    op.alter_column("user_model_configs", "requests_per_minute",
                    existing_type=sa.Integer(), nullable=False)
    op.add_column("user_model_configs",
                  sa.Column("tokens_per_minute", sa.Integer(), nullable=True))
    op.add_column("user_model_configs",
                  sa.Column("max_concurrent_requests", sa.Integer(), nullable=False,
                            server_default=sa.text("10")))


def downgrade():
    op.drop_column("user_model_configs", "max_concurrent_requests")
    op.drop_column("user_model_configs", "tokens_per_minute")
    op.alter_column("user_model_configs", "requests_per_minute",
                    new_column_name="rate_limit",
                    existing_type=sa.Integer(), existing_nullable=True)
