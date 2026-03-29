"""Phase 13.6 — event_triggers & event_logs tables

Revision ID: 004_event_triggers
Revises: 003_consolidated
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '004_event_triggers'
down_revision = '003_consolidated'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── event_triggers ────────────────────────────────────────────────────
    op.create_table(
        'event_triggers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('trigger_type', sa.Enum(
            'webhook', 'schedule', 'threshold', 'api_poll',
            name='triggertype', create_type=True,
        ), nullable=False),
        sa.Column('config', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('target_workflow_id', sa.String(36),
                  sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True),
        sa.Column('target_agent_id', sa.String(36),
                  sa.ForeignKey('agents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_fired_at', sa.DateTime, nullable=True),
        sa.Column('fire_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_fires_per_minute', sa.Integer, nullable=False, server_default='10'),
        sa.Column('pause_duration_seconds', sa.Integer, nullable=False, server_default='300'),
        sa.Column('paused_until', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_event_triggers_trigger_type', 'event_triggers', ['trigger_type'])
    op.create_index('ix_event_triggers_is_active', 'event_triggers', ['is_active'])

    # ── event_logs ────────────────────────────────────────────────────────
    op.create_table(
        'event_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agentium_id', sa.String(10), unique=True, nullable=False, index=True),
        sa.Column('trigger_id', sa.String(36),
                  sa.ForeignKey('event_triggers.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('event_payload', sa.JSON, nullable=False, server_default='{}'),
        sa.Column('status', sa.Enum(
            'processed', 'dead_letter', 'duplicate',
            name='eventlogstatus', create_type=True,
        ), nullable=False),
        sa.Column('correlation_id', sa.String(36), nullable=True, index=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_event_logs_status', 'event_logs', ['status'])


def downgrade() -> None:
    op.drop_table('event_logs')
    op.drop_table('event_triggers')

    # Drop the custom enum types created above
    sa.Enum(name='eventlogstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='triggertype').drop(op.get_bind(), checkfirst=True)
