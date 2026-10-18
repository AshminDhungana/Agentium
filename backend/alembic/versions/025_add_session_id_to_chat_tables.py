"""Add session_id columns for session isolation (19.3.3).

Adds session_id column to chat_messages and conversations tables with indexes
to support session-scoped queries and prevent cross-session data leakage.

Revision ID: 025_add_session_id_to_chat_tables
Revises: 024_scheduled_task_run_once
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "025_add_session_id_to_chat_tables"
down_revision = "024_scheduled_task_run_once"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add session_id to chat_messages
    op.add_column(
        "chat_messages",
        sa.Column("session_id", sa.String(36), nullable=True, index=True),
    )

    # Add session_id to conversations
    op.add_column(
        "conversations",
        sa.Column("session_id", sa.String(36), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "session_id")
    op.drop_column("chat_messages", "session_id")