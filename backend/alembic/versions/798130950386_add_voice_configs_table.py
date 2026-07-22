"""add voice_configs table

Revision ID: 798130950386
Revises: 020_merge_ethos_overflow
Create Date: 2026-07-21 20:36:40.599229

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '798130950386'
down_revision = '020_merge_ethos_overflow'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'voice_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(length=255), nullable=False, unique=True),
        sa.Column('require_wake_word', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tts_voice', sa.String(length=100), nullable=False, server_default='am_adam'),
        sa.Column('tts_provider', sa.String(length=50), nullable=False, server_default='kokoro'),
        sa.Column('proactive_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('speaker_identification', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_voice_configs_user_id'), 'voice_configs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_voice_configs_user_id'), table_name='voice_configs')
    op.drop_table('voice_configs')