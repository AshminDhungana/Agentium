"""add_mcp_tools_table

Revision ID: 002_mcp_tools
Revises: 001_schema
Create Date: 2026-02-22

Phase 6.7 — MCP Server Integration
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '002_mcp_tools'
down_revision = '001_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mcp_tools',

        # ── Primary key & base columns ─────────────────────────────────────────
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),

        # ── Identity ───────────────────────────────────────────────────────────
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('server_url', sa.String(512), nullable=False),

        # ── Constitutional classification ──────────────────────────────────────
        sa.Column('tier', sa.String(32), nullable=False, server_default='restricted'),
        sa.Column('constitutional_article', sa.String(64), nullable=True),

        # ── Approval state ─────────────────────────────────────────────────────
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('approved_by_council', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('approval_vote_id', sa.String(64), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(64), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_by', sa.String(64), nullable=True),
        sa.Column('revocation_reason', sa.Text(), nullable=True),

        # ── Capabilities ───────────────────────────────────────────────────────
        sa.Column('capabilities', sa.JSON(), nullable=False, server_default='[]'),

        # ── Health tracking ────────────────────────────────────────────────────
        sa.Column('health_status', sa.String(32), nullable=False, server_default='unknown'),
        sa.Column('last_health_check_at', sa.DateTime(), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),

        # ── Usage statistics ───────────────────────────────────────────────────
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),

        # ── Audit trail ────────────────────────────────────────────────────────
        sa.Column('audit_log', sa.JSON(), nullable=False, server_default='[]'),

        # ── Proposal metadata ──────────────────────────────────────────────────
        sa.Column('proposed_by', sa.String(64), nullable=True),
        sa.Column('proposed_at', sa.DateTime(), nullable=True),
    )

    # Indexes
    op.create_index('ix_mcp_tools_name',       'mcp_tools', ['name'],       unique=True)
    op.create_index('ix_mcp_tools_server_url',  'mcp_tools', ['server_url'], unique=False)
    op.create_index('ix_mcp_tools_status',      'mcp_tools', ['status'],     unique=False)
    op.create_index('ix_mcp_tools_tier',        'mcp_tools', ['tier'],       unique=False)


def downgrade() -> None:
    op.drop_index('ix_mcp_tools_tier',       table_name='mcp_tools')
    op.drop_index('ix_mcp_tools_status',     table_name='mcp_tools')
    op.drop_index('ix_mcp_tools_server_url', table_name='mcp_tools')
    op.drop_index('ix_mcp_tools_name',       table_name='mcp_tools')
    op.drop_table('mcp_tools')