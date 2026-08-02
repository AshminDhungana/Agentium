"""Add agentium_id column to workflow_executions table

Revision ID: 022_agentium_id_workflow_exec
Revises: 021_add_workflow_versions_table
"""
from alembic import op
import sqlalchemy as sa

revision = "022_agentium_id_workflow_exec"
down_revision = "021_add_workflow_versions_table"
branch_labels = None
depends_on = None


def upgrade():
    # Add agentium_id column to workflow_executions if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'workflow_executions' AND column_name = 'agentium_id'
            ) THEN
                ALTER TABLE workflow_executions ADD COLUMN agentium_id VARCHAR(20) UNIQUE NOT NULL DEFAULT 'WX00000';
                -- Update existing rows with unique agentium_ids
                WITH numbered AS (
                    SELECT id, 'WX' || LPAD(ROW_NUMBER() OVER (ORDER BY created_at)::text, 5, '0') as new_id
                    FROM workflow_executions
                )
                UPDATE workflow_executions
                SET agentium_id = numbered.new_id
                FROM numbered
                WHERE workflow_executions.id = numbered.id;
                -- Make it NOT NULL without default
                ALTER TABLE workflow_executions ALTER COLUMN agentium_id DROP DEFAULT;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE workflow_executions DROP COLUMN IF EXISTS agentium_id")