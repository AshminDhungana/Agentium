"""Add chat performance indexes
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004_chat_indexes'
down_revision = '003_reasoning_trace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Composite index for /chat/history queries
    op.create_index(
        'idx_chat_messages_user_created',
        'chat_messages',
        ['user_id', sa.text('created_at DESC')],
        unique=False,
        postgresql_using='btree',
    )

    # 2. Per-conversation message loading
    op.create_index(
        'idx_chat_messages_conversation',
        'chat_messages',
        ['conversation_id', sa.text('created_at DESC')],
        unique=False,
        postgresql_using='btree',
    )

    # 3. Inbox conversation list
    op.create_index(
        'idx_conversations_user_last_msg',
        'conversations',
        ['user_id', sa.text('last_message_at DESC')],
        unique=False,
        postgresql_using='btree',
    )

    # 4. Filtered conversation listing (is_deleted / is_archived filters)
    op.create_index(
        'idx_conversations_user_active',
        'conversations',
        ['user_id', 'is_deleted', 'is_archived'],
        unique=False,
        postgresql_using='btree',
    )


def downgrade() -> None:
    op.drop_index('idx_conversations_user_active',   table_name='conversations')
    op.drop_index('idx_conversations_user_last_msg', table_name='conversations')
    op.drop_index('idx_chat_messages_conversation',  table_name='chat_messages')
    op.drop_index('idx_chat_messages_user_created',  table_name='chat_messages')