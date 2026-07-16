"""set skills.embedding_model server_default to bge-base

Revision ID: 010_skill_embedding_bge
Revises: 009_mcp_voting_id
"""
from alembic import op
import sqlalchemy as sa

revision = "010_skill_embedding_bge"
down_revision = "009_mcp_voting_id"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "skills",
        "embedding_model",
        server_default="BAAI/bge-base-en-v1.5",
        existing_type=sa.String(100),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "skills",
        "embedding_model",
        server_default="sentence-transformers/all-MiniLM-L6-v2",
        existing_type=sa.String(100),
        existing_nullable=True,
    )
