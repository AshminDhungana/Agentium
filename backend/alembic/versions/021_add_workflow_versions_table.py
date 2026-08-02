"""Add workflow_versions table for WorkflowVersion model

Revision ID: 021_add_workflow_versions_table
Revises: 020_add_workflow_steps_table
"""
from alembic import op
import sqlalchemy as sa

revision = "021_add_workflow_versions_table"
down_revision = "020_add_workflow_steps_table"
branch_labels = None
depends_on = None


def upgrade():
    # Create workflow_versions table if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_versions') THEN
                CREATE TABLE workflow_versions (
                    id         VARCHAR(36) PRIMARY KEY,
                    agentium_id VARCHAR(20) UNIQUE NOT NULL,
                    is_active  BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    deleted_at TIMESTAMP NULL,
                    workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    template_json JSONB NOT NULL
                );
                CREATE INDEX ix_workflow_versions_workflow_id ON workflow_versions (workflow_id);
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS workflow_versions")