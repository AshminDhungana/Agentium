"""add browser tasktype enum value

Revision ID: 002_add_browser_tasktype
Revises: 001_add_model_pricing_table
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "002_add_browser_tasktype"
down_revision = "001_add_model_pricing_table"
branch_labels = None
depends_on = None

def upgrade():
    # PostgreSQL 12+ supports ADD VALUE IF NOT EXISTS inside a transaction.
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'browser';")

def downgrade():
    # PostgreSQL cannot drop a single enum value without recreating the type.
    # Safe no-op: leaving 'browser' in place does not break existing rows.
    pass