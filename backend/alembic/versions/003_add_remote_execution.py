"""Add remote execution tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Create remote_executions table
    op.create_table(
        'remote_executions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agentium_id', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('execution_id', sa.String(length=50), nullable=False),
        sa.Column('agent_id', sa.String(length=5), nullable=False),
        sa.Column('task_id', sa.String(length=50), nullable=True),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=True),
        sa.Column('dependencies', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('input_data_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expected_output_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('summary', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('cpu_time_seconds', sa.Float(), nullable=True),
        sa.Column('memory_peak_mb', sa.Float(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('sandbox_id', sa.String(length=50), nullable=True),
        sa.Column('sandbox_container_id', sa.String(length=100), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.agentium_id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id'),
    )

    # Create indexes
    op.create_index('ix_remote_executions_execution_id', 'remote_executions', ['execution_id'])
    op.create_index('ix_remote_executions_agent_id', 'remote_executions', ['agent_id'])
    op.create_index('ix_remote_executions_status', 'remote_executions', ['status'])
    op.create_index('ix_remote_executions_created_at', 'remote_executions', ['created_at'])

    # Create sandboxes table
    op.create_table(
        'sandboxes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agentium_id', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sandbox_id', sa.String(length=50), nullable=False),
        sa.Column('container_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('cpu_limit', sa.Float(), nullable=True),
        sa.Column('memory_limit_mb', sa.Integer(), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True),
        sa.Column('network_mode', sa.String(length=20), nullable=True),
        sa.Column('allowed_hosts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('volume_mounts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('max_disk_mb', sa.Integer(), nullable=True),
        sa.Column('current_execution_id', sa.String(length=50), nullable=True),
        sa.Column('created_by_agent_id', sa.String(length=5), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('destroyed_at', sa.DateTime(), nullable=True),
        sa.Column('destroy_reason', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sandbox_id'),
    )

    # Create indexes
    op.create_index('ix_sandboxes_sandbox_id', 'sandboxes', ['sandbox_id'])
    op.create_index('ix_sandboxes_agent_id', 'sandboxes', ['created_by_agent_id'])
    op.create_index('ix_sandboxes_status', 'sandboxes', ['status'])


def downgrade():
    op.drop_index('ix_sandboxes_status', table_name='sandboxes')
    op.drop_index('ix_sandboxes_agent_id', table_name='sandboxes')
    op.drop_index('ix_sandboxes_sandbox_id', table_name='sandboxes')
    op.drop_table('sandboxes')

    op.drop_index('ix_remote_executions_created_at', table_name='remote_executions')
    op.drop_index('ix_remote_executions_status', table_name='remote_executions')
    op.drop_index('ix_remote_executions_agent_id', table_name='remote_executions')
    op.drop_index('ix_remote_executions_execution_id', table_name='remote_executions')
    op.drop_table('remote_executions')
