# Alembic Downgrade Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify all Alembic migrations have complete `downgrade()` functions, fix any gaps, and confirm a full round-trip `downgrade base -> upgrade head` on a clean PostgreSQL database.

**Architecture:** Use the existing `docker-compose.test.yml` ephemeral test stack (PostgreSQL-only) to run Alembic in a clean environment. Build a small utility that introspects each migration's `upgrade()` vs `downgrade()` to detect omitted operations, then run the round-trip test against the test database.

**Tech Stack:** Alembic 1.13.x, PostgreSQL 15, SQLAlchemy 2.x, Docker, pytest, Python 3.10+

## Global Constraints

- Must not touch production database (`agentium`); only use the test DB (`agentium_test`).
- All Alembic commands run from the `backend/` directory.
- The existing `backend/alembic.ini` is the single source of truth for Alembic configuration.
- PostgreSQL test connection: `postgresql://agentium:agentium@localhost:5432/agentium_test`
- Docker test stack: `docker-compose.test.yml` (ephemeral, no persistent volumes).
- Every migration that has a `downgrade()` must round-trip cleanly.

---

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `backend/alembic/versions/000_combined_migration.py` | **Analyze & modify** | Huge combined migration with `upgrade()` at line ~64 and `downgrade()` at line ~2402. Verify completeness of reverse operations. |
| `backend/alembic/versions/001_add_model_pricing_table.py` | **Analyze** | Simple migration with complete `upgrade()` and `downgrade()`. Verify correctness. |
| `backend/alembic.ini` | **Read only** | Alembic configuration. |
| `docker-compose.test.yml` | **Read only** | Ephemeral test infrastructure. |
| `backend/tests/alembic/test_downgrade_coverage.py` | **Create** | pytest-based round-trip test script. |
| `backend/tests/alembic/audit_migrations.py` | **Create** | Standalone script to compare `upgrade()` vs `downgrade()` operations. |

---

## Task 1: Create Migration Audit Script

**Files:**
- Create: `backend/tests/alembic/audit_migrations.py`

**Interfaces:**
- Consumes: `backend/alembic/versions/*.py` migration files
- Produces: Mapping of `upgrade()` operations to `downgrade()` reversals; report of gaps.

**Step 1: Write the audit script**

```python
# backend/tests/alembic/audit_migrations.py
"""Alembic migration upgrade/downgrade parity audit."""
import ast
import json
import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "alembic" / "versions"


class OperationExtractor(ast.NodeVisitor):
    ALEMBIC_OPS = {
        "create_table", "drop_table",
        "create_index", "drop_index",
        "add_column", "drop_column",
        "create_foreign_key", "drop_constra", "drop_constraint",
        "create_unique_constraint",
        "execute",
    }

    def __init__(self):
        self.operations = []

    def visit_Call(self, node: ast.Call):
        func_name = self._get_func_name(node.func)
        if func_name and any(func_name.endswith(op) for op in self.ALEMBIC_OPS):
            self.operations.append(func_name)
        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node) -> str | None:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts)) if parts else None


def extract_operations(file_path: Path) -> tuple:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade"):
            extractor = OperationExtractor()
            for stmt in node.body:
                extractor.visit(stmt)
            funcs[node.name] = extractor.operations
    return funcs.get("upgrade", []), funcs.get("downgrade", [])


def extract_enums(source: str) -> tuple:
    create_types = re.findall(r"CREATE TYPE (\w+)", source, re.IGNORECASE)
    drop_types = re.findall(r"DROP TYPE(?:\s+IF EXISTS)?\s+(\w+)", source, re.IGNORECASE)
    return set(create_types), set(drop_types)


def main() -> None:
    results = []
    for py_file in sorted(MIGRATIONS_DIR.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        content = py_file.read_text(encoding="utf-8")
        up_ops, down_ops = extract_operations(py_file)
        up_types, down_types = extract_enums(content)
        results.append({
            "file": py_file.name,
            "upgrade_operations": len(up_ops),
            "downgrade_operations": len(down_ops),
            "has_upgrade": "def upgrade" in content,
            "has_downgrade": "def downgrade" in content,
            "enum_types_in_upgrade": sorted(up_types),
            "enum_types_in_downgrade": sorted(down_types),
            "missing_downgrade_enum": sorted(up_types - down_types),
        })

    report_path = Path("migrations_audit_report.json")
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Report written to {report_path.resolve()}")
    for entry in results:
        status = "OK" if entry["has_downgrade"] else "MISSING DOWNGRADE"
        print(f" [{status}] {entry['file']} -- {entry['upgrade_operations']} up / {entry['downgrade_operations']} down ops")


if __name__ == "__main__":
    main()
```

**Step 2: Run the audit script**

```bash
cd backend
python tests/alembic/audit_migrations.py
```

Expected: Reports all migrations have `downgrade()` defined. Flags any missing enum reversals.

---

## Task 2: Implement or Fix `downgrade()` for Any Incomplete Migration

**Files:**
- Modify: `backend/alembic/versions/000_combined_migration.py` (if gaps found in Task 1)
- Modify: `backend/alembic/versions/001_add_model_pricing_table.py` (if gaps found)

**Interfaces:**
- Consumes: Audit report from Task 1
- Produces: Complete, reversible `downgrade()` in every migration file.

**Step 1: Inspect `000_combined_migration.py` for gaps**

Open lines 2402-2630. The `downgrade()` is already large, but verify every `upgrade()` operation is reversed:
- Every `op.create_table()` in `upgrade()` must have `op.drop_table()` in `downgrade()`
- Every `op.add_column()` must have `op.drop_column()`
- Every `op.create_index()` must have `op.drop_index()`
- Every `op.create_foreign_key()` must have `op.drop_constraint(type_='foreignkey')`
- Every `op.execute("CREATE TYPE ...")` must have `DROP TYPE IF EXISTS ...`
- Every `op.create_unique_constraint()` must have `op.drop_constraint(type_='unique')`

**Step 2: Write missing downgrade operations**

If the audit found missing operations, append them to the `downgrade()` function. Example pattern:

```python
def downgrade() -> None:
    # ... existing code ...
    inspector = Inspector.from_engine(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    # Missing: drop reasoning_traces indexes
    if 'reasoning_traces' in existing_tables:
        for idx in ('ix_reasoning_traces_trace_id', 'ix_reasoning_traces_task_id'):
            op.execute(f"DROP INDEX IF EXISTS {idx}")
        op.drop_table('reasoning_traces')
```

**Step 3: Verify with `alembic check`**

```bash
cd backend
alembic check
```

Alternative for older Alembic versions:

```bash
cd backend
alembic revision --autogenerate -m "autogenerated_check" --sql
```

---

## Task 3: Write Downgrade Round-Trip Test Script

**Files:**
- Create: `backend/tests/alembic/test_downgrade_coverage.py`

**Interfaces:**
- Consumes: Test DB at `postgresql://agentium:agentium@localhost:5432/agentium_test`
- Produces: pytest output showing PASS/FAIL for each migration's round-trip.

**Step 1: Create the test script**

```python
# backend/tests/alembic/test_downgrade_coverage.py
"""Round-trip Alembic downgrade/upgrade coverage test."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic.ini"
DATABASE_URL = "postgresql://agentium:agentium@localhost:5432/agentium_test"


class AlembicRunner:
    def __init__(self):
        self.ini = str(ALEMBIC_INI)

    def _run(self, *args: str) -> str:
        cmd = ["alembic", "-c", self.ini, *args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(ALEMBIC_INI.parent),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Alembic failed: {' '.join(cmd)}\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        return result.stdout

    def upgrade(self, revision: str) -> str:
        return self._run("upgrade", revision)

    def downgrade(self, revision: str) -> str:
        return self._run("downgrade", revision)


@pytest.fixture(scope="module")
def engine() -> Engine:
    return create_engine(DATABASE_URL)


@pytest.fixture(scope="module")
def fresh_database(engine: Engine):
    """Ensure a clean test database."""
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))
        conn.execute(text("DROP DATABASE IF EXISTS agentium_test"))
        conn.execute(text("CREATE DATABASE agentium_test"))
        conn.close()


def test_upgrade_head_creates_tables(engine, fresh_database):
    runner = AlembicRunner()
    runner.upgrade("head")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = {row[0] for row in result}
    assert len(tables) > 0, "No tables created after upgrading to head"


def test_downgrade_base_removes_all_tables(engine, fresh_database):
    runner = AlembicRunner()
    runner.upgrade("head")
    runner.downgrade("base")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = {row[0] for row in result}
    tables.discard("alembic_version")
    assert len(tables) == 0, f"Tables left after downgrade to base: {tables}"


def test_roundtrip_individual_migrations(engine, fresh_database):
    """Apply each migration one at a time, then downgrade it."""
    runner = AlembicRunner()
    runner.downgrade("base")
    # Get ordered list of migration IDs
    output = runner._run("history")
    rev_ids = []
    for line in output.strip().splitlines():
        parts = line.split()
        if parts:
            rev_ids.append(parts[0])

    for rev in rev_ids:
        runner.upgrade(rev)
        runner.downgrade(rev + "-1" if rev != "base" else "base")
        runner.upgrade(rev)

    runner.upgrade("head")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
        enums = {row[0] for row in result}
    assert not enums, f"Leftover custom enum types: {enums}"
```

**Step 2: Run the test**

```bash
# Start test infrastructure
docker compose -f docker-compose.test.yml up -d

# Run the test
cd backend
pytest tests/alembic/test_downgrade_coverage.py -v
```

Expected: All tests PASS, or clear output showing which migration's `downgrade()` is incomplete.

---

## Task 4: Fix Any Round-Trip Failures

**Files:**
- Modify: `backend/alembic/versions/000_combined_migration.py` (most likely candidate for fixes)
- Possibly modify: `backend/alembic/versions/001_add_model_pricing_table.py`

**Interfaces:**
- Consumes: Failure output from Task 3 round-trip test
- Produces: Fixed `downgrade()` functions that cleanly reverse their `upgrade()`.

**Step 1: Parse test failure**

Example failure:
```
RuntimeError: Alembic command failed: alembic downgrade -1
STDERR: (OperationalError) cannot drop table tasks because other objects depend on it
```

**Step 2: Add the missing drop order / missing drop constraint**

If a table cannot be dropped because of FK dependencies, the `downgrade()` needs to drop dependent tables or FK constraints first. Add the missing `op.drop_table()` or `op.drop_constraint()` calls.

```python
# In downgrade(), before dropping the table:
inspector = Inspector.from_engine(op.get_bind())
existing_tables = set(inspector.get_table_names())

if 'some_child_table' in existing_tables:
    op.drop_table('some_child_table')

if 'parent_table' in existing_tables:
    op.drop_table('parent_table')
```

**Step 3: Re-run the round-trip test**

```bash
cd backend
pytest tests/alembic/test_downgrade_coverage.py -v --tb=short
```

Repeat until all tests pass.

---

## Task 5: Document Migration Best Practices

**Files:**
- Create/Modify: `docs/CONTRIBUTING.md` or `backend/README.md`

**Step 1: Add a section on migration best practices**

```markdown
## Alembic Migrations

Every new migration file must include a complete `downgrade()` function.
Use the round-trip test to verify:
```bash
cd backend
pytest tests/alembic/test_downgrade_coverage.py -v
```

If you added a new table, column, index, or custom type in `upgrade()`,
the corresponding `downgrade()` must remove it.

### Quick checklist for new migrations

- [ ] `op.create_table()` -> `op.drop_table()`
- [ ] `op.add_column()` -> `op.drop_column()`
- [ ] `op.create_index()` -> `op.drop_index()`
- [ ] `op.create_foreign_key()` -> `op.drop_constraint(type_='foreignkey')`
- [ ] `op.create_unique_constraint()` -> `op.drop_constraint(type_='unique')`
- [ ] `op.execute("CREATE TYPE ...")` -> `op.execute("DROP TYPE IF EXISTS ...")`
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] Run `alembic check` against live database -> Tasks 1-2
   - [x] Write missing `downgrade()` for any migration with only `upgrade()` -> Task 2
   - [x] Verify full round-trip `downgrade base -> upgrade head` on clean DB -> Tasks 3-4

2. **Placeholder scan:**
   - [x] No "TBD", "TODO", or "fill in later" in any step
   - [x] Every step has concrete code, commands, and expected output

3. **Type consistency:**
   - [x] All file paths verified against actual repo structure
   - [x] All commands reference actual files in the repo

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-30-alembic-downgrade-coverage.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
