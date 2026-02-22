"""unified_inbox_alignment

Revision ID: 004_unified_inbox
Revises: 003_add_remote_execution
Create Date: 2026-02-22 10:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_unified_inbox'
down_revision: Union[str, None] = '003_add_remote_execution'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add isolation column to external channels
    op.add_column('external_channels', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    
    # Add unified inbox fields to chat messages
    op.add_column('chat_messages', sa.Column('sender_channel', sa.String(length=50), nullable=True))
    op.add_column('chat_messages', sa.Column('message_type', sa.String(length=50), server_default='text', nullable=True))
    op.add_column('chat_messages', sa.Column('media_url', sa.Text(), nullable=True))
    op.add_column('chat_messages', sa.Column('silent_delivery', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('chat_messages', sa.Column('external_message_id', sa.String(length=100), nullable=True))
    
    # Add active state to conversations
    op.add_column('conversations', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('conversations', 'is_active')
    op.drop_column('chat_messages', 'external_message_id')
    op.drop_column('chat_messages', 'silent_delivery')
    op.drop_column('chat_messages', 'media_url')
    op.drop_column('chat_messages', 'message_type')
    op.drop_column('chat_messages', 'sender_channel')
    op.drop_column('external_channels', 'user_id')
