"""Add workflow_steps table for WorkflowStep model

Revision ID: 020_add_workflow_steps_table
Revises: 7a73fcef3cfe
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "020_add_workflow_steps_table"
down_revision = "7a73fcef3cfe"
branch_labels = None
depends_on = None


def upgrade():
    # Create workflow_steps table if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_steps') THEN
                CREATE TABLE workflow_steps (
                    id         VARCHAR(36) PRIMARY KEY,
                    agentium_id VARCHAR(20) UNIQUE NOT NULL,
                    is_active  BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    deleted_at TIMESTAMP NULL,
                    workflow_id VARCHAR(36) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    step_index INTEGER NOT NULL,
                    step_type VARCHAR(32) NOT NULL,
                    config JSONB NOT NULL DEFAULT '{}',
                    on_success_step INTEGER NULL,
                    on_failure_step INTEGER NULL
                );
                CREATE INDEX ix_workflow_steps_workflow_id ON workflow_steps (workflow_id);
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS workflow_steps")