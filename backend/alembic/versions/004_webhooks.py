"""Phase 12 — Outbound Webhook tables

Revision ID: 004_webhooks
Revises: 003_migration
Create Date: 2026-03-13

What this migration does
─────────────────────────
010  webhook_subscriptions and webhook_delivery_logs tables for the outbound
     event webhook system (Phase 12.2).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '004_webhooks'
down_revision = '003_migration'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🚀 Starting migration 004_webhooks (Phase 12) ...")

    # =========================================================================
    # 010 — Outbound Webhook System
    # =========================================================================
    print("\n--- 010: Outbound Webhooks ---")

    if 'webhook_subscriptions' not in existing_tables:
        op.create_table(
            'webhook_subscriptions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('url', sa.String(500), nullable=False),
            sa.Column('secret', sa.String(255), nullable=False),
            sa.Column('description', sa.String(500), nullable=True),
            sa.Column('events', sa.JSON(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_webhook_subscriptions_user_id',
                        'webhook_subscriptions', ['user_id'])
        op.create_index('ix_webhook_subscriptions_is_active',
                        'webhook_subscriptions', ['is_active'])
        print("  ✅ Created webhook_subscriptions table")
    else:
        print("  ℹ️  webhook_subscriptions already exists")

    if 'webhook_delivery_logs' not in existing_tables:
        op.create_table(
            'webhook_delivery_logs',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('subscription_id', sa.String(36),
                      sa.ForeignKey('webhook_subscriptions.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('delivery_id', sa.String(36), nullable=False, unique=True),
            sa.Column('event_type', sa.String(50), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=False),
            sa.Column('status_code', sa.Integer(), nullable=True),
            sa.Column('response_body', sa.Text(), nullable=True),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
            sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_webhook_delivery_logs_subscription_id',
                        'webhook_delivery_logs', ['subscription_id'])
        op.create_index('ix_webhook_delivery_logs_event_type',
                        'webhook_delivery_logs', ['event_type'])
        op.create_index('ix_webhook_delivery_logs_next_retry',
                        'webhook_delivery_logs', ['next_retry_at'])
        print("  ✅ Created webhook_delivery_logs table")
    else:
        print("  ℹ️  webhook_delivery_logs already exists")

    print("\n" + "=" * 60)
    print("✅ Migration 004_webhooks completed!")
    print("=" * 60)


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = set(inspector.get_table_names())

    print("🔄 Downgrading migration 004_webhooks ...")

    if 'webhook_delivery_logs' in existing_tables:
        op.drop_table('webhook_delivery_logs')
        print("  ✅ Dropped webhook_delivery_logs")

    if 'webhook_subscriptions' in existing_tables:
        op.drop_table('webhook_subscriptions')
        print("  ✅ Dropped webhook_subscriptions")
