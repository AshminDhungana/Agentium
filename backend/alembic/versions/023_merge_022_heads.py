"""Merge 022 heads

Revision ID: 023_merge_022_heads
Revises: b2c3d4e5f6a7, a1b2c3d4e5f6
Create Date: 2026-09-01 10:19:57.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023_merge_022_heads'
down_revision = ('b2c3d4e5f6a7', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass