"""Merge heads: ethos.working_method (6.3) + agents.is_temporary_overflow_head (7.1)

Revision ID: 020_merge_ethos_overflow
Revises: 019_add_ethos_working_method, 019_add_overflow_head_flag
Create Date: 2026-07-20

Both child revisions add independent, idempotent columns and perform their own
work in their respective upgrade() steps, so this merge carries no operations.
It exists only to give Alembic a single linear head again.
"""

from alembic import op


# revision identifiers
revision = "020_merge_ethos_overflow"
down_revision = ("019_add_ethos_working_method", "019_add_overflow_head_flag")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
