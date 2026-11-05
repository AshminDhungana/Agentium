"""add_channel_metrics_table

Revision ID: 5b063a5311bd
Revises: 025_add_session_id_to_chat_tables
Create Date: 2026-11-05 10:22:15.555546

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b063a5311bd'
down_revision = '025_add_session_id_to_chat_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create channel_metrics table with all BaseEntity columns
    op.create_table(
        'channel_metrics',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('agentium_id', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('channel_id', sa.String(36), nullable=False, unique=True, index=True),
        sa.Column('total_requests', sa.Integer(), server_default='0', nullable=False),
        sa.Column('successful_requests', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_requests', sa.Integer(), server_default='0', nullable=False),
        sa.Column('circuit_breaker_state', sa.String(20), server_default='closed', nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_failure_at', sa.DateTime(), nullable=True),
        sa.Column('rate_limit_hits', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_rate_limit_at', sa.DateTime(), nullable=True),
        sa.Column('avg_response_time_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['external_channels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Add check constraint for valid circuit breaker states
    op.create_check_constraint(
        'ck_channel_metrics_circuit_breaker_state',
        'channel_metrics',
        "circuit_breaker_state IN ('closed', 'half_open', 'open')"
    )
    op.create_index(op.f('ix_channel_metrics_agentium_id'), 'channel_metrics', ['agentium_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_channel_metrics_agentium_id'), table_name='channel_metrics')
    op.drop_table('channel_metrics')