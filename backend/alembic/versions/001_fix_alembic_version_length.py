"""Fix alembic_version.version_num column length

Revision ID: 001_fix_alembic_version_length
Revises: 021_add_workflow_versions_table
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_fix_alembic_version_length'
down_revision = '021_add_workflow_versions_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Increase version_num column from VARCHAR(32) to VARCHAR(100)
    # to accommodate descriptive revision identifiers
    op.alter_column('alembic_version', 'version_num',
                    type_=sa.String(100),
                    existing_type=sa.String(32),
                    existing_nullable=False)


def downgrade() -> None:
    # Revert to original VARCHAR(32)
    op.alter_column('alembic_version', 'version_num',
                    type_=sa.String(32),
                    existing_type=sa.String(100),
                    existing_nullable=False)