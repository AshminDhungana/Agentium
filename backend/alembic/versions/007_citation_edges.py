"""007_citation_edges — create citation_edges table

Revision ID: 007_citation_edges
Revises: 006_wait_poll
Create Date: 2026-04-15 00:00:00.000000

Non-breaking: adds a new table; no existing columns are modified.
"""

from alembic import op
import sqlalchemy as sa

# ── Revision identifiers ──────────────────────────────────────────────────────

revision      = "007_citation_edges"
down_revision = "006_wait_poll"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "citation_edges",

        sa.Column("id",              sa.String(36),  nullable=False, primary_key=True),
        sa.Column("source_doc_id",   sa.String(255), nullable=False),
        sa.Column("cited_by_doc_id", sa.String(255), nullable=False),
        sa.Column("task_id",         sa.String(36),
                  sa.ForeignKey("tasks.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("collection_key",  sa.String(64),  nullable=False, server_default=""),
        sa.Column("relevance_score", sa.Float(),      nullable=False, server_default="0.0"),
        sa.Column("created_at",      sa.DateTime(),   nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── Indexes ───────────────────────────────────────────────────────────
    op.create_index("ix_citation_edges_source_doc_id",   "citation_edges", ["source_doc_id"])
    op.create_index("ix_citation_edges_cited_by_doc_id", "citation_edges", ["cited_by_doc_id"])
    op.create_index("ix_citation_edges_task_id",         "citation_edges", ["task_id"])
    op.create_index("ix_citation_edges_created_at",      "citation_edges", ["created_at"])
    op.create_index(
        "ix_citation_edges_source_collection",
        "citation_edges",
        ["source_doc_id", "collection_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_citation_edges_source_collection", table_name="citation_edges")
    op.drop_index("ix_citation_edges_created_at",        table_name="citation_edges")
    op.drop_index("ix_citation_edges_task_id",           table_name="citation_edges")
    op.drop_index("ix_citation_edges_cited_by_doc_id",   table_name="citation_edges")
    op.drop_index("ix_citation_edges_source_doc_id",     table_name="citation_edges")
    op.drop_table("citation_edges")
