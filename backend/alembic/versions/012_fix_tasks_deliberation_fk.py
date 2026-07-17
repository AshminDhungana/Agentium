"""Fix tasks.deliberation_id FK name to match SQLAlchemy model

Revision ID: 012_fix_tasks_deliberation_fk
Revises: 011_add_knowledge_documents
Create Date: 2026-07-17

The Task model declares:
    deliberation_id = Column(String(36),
        ForeignKey('task_deliberations.id', use_alter=True,
                   name='fk_tasks_deliberation_id'), nullable=True)

`use_alter=True` means SQLAlchemy expects the FK to be created by a
separate ALTER TABLE statement named `fk_tasks_deliberation_id`.
The combined migration instead created it inline during create_table
under the name `tasks_deliberation_id_fkey`. The mismatch means the
model's expected constraint never existed, causing
`ALTER TABLE tasks DROP CONSTRAINT fk_tasks_deliberation_id` to fail
and breaking task-to-deliberation binding.

This migration adds the correctly-named FK constraint idempotently.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers
revision = "012_fix_tasks_deliberation_fk"
down_revision = "011_add_knowledge_documents"
branch_labels = None
depends_on = None


def _fk_exists(conn, table, name):
    inspector = inspect(conn)
    return name in {fk.get("name") for fk in inspector.get_foreign_keys(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _fk_exists(conn, "tasks", "fk_tasks_deliberation_id"):
        op.create_foreign_key(
            "fk_tasks_deliberation_id",
            "tasks",
            "task_deliberations",
            ["deliberation_id"],
            ["id"],
        )
        print("✅ Created FK fk_tasks_deliberation_id on tasks.deliberation_id")
    else:
        print("⏭️  FK fk_tasks_deliberation_id already exists — skipped")


def downgrade() -> None:
    conn = op.get_bind()
    if _fk_exists(conn, "tasks", "fk_tasks_deliberation_id"):
        op.drop_constraint("fk_tasks_deliberation_id", "tasks", type_="foreignkey")
        print("↩️  Dropped FK fk_tasks_deliberation_id")
