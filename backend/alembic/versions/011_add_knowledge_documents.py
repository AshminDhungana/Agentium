"""add knowledge_documents parent-text store

Revision ID: 011_add_knowledge_documents
Revises: 010_skill_embedding_bge
"""
from alembic import op
import sqlalchemy as sa

revision = "011_add_knowledge_documents"
down_revision = "010_skill_embedding_bge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("collection_key", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.String(length=128), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("doc_metadata", sa.JSON(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("collection_key", "parent_id", name="uq_knowledge_doc_coll_parent"),
    )
    op.create_index("ix_knowledge_documents_collection_key", "knowledge_documents", ["collection_key"])
    op.create_index("ix_knowledge_documents_parent_id", "knowledge_documents", ["parent_id"])


def downgrade():
    op.drop_index("ix_knowledge_documents_parent_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_collection_key", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
