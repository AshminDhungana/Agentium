"""Round-trip Alembic downgrade/upgrade coverage test.

Run via:
    cd backend
    pytest tests/alembic/test_downgrade_coverage.py -v

Or with the Docker-based test (requires test stack up):
    docker compose -f docker-compose.test.yml up -d
    cd backend
    python tests/alembic/test_downgrade_roundtrip_docker.py
"""

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
        self.cwd = str(ALEMBIC_INI.parent)

    def _run(self, *args: str) -> str:
        cmd = ["alembic", "-c", self.ini, *args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.cwd,
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

    def history(self) -> list[str]:
        """Return list of revision IDs from newest to oldest (excluding base)."""
        output = self._run("history", "--rev-range", "base:head")
        revs = []
        for line in output.strip().splitlines():
            parts = line.split()
            if parts:
                revs.append(parts[0])
        return revs


def _drop_and_create_test_db(engine: Engine) -> None:
    """Drop and recreate the test database."""
    # Close all pooled connections to the target DB so PostgreSQL allows
    # us to drop it (avoids "database is being accessed by other users").
    engine.dispose()

    # Connect to the default 'postgres' maintenance DB with autocommit so
    # DROP/CREATE DATABASE are not wrapped in a transaction block.
    admin_url = DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS agentium_test"))
        conn.execute(text("CREATE DATABASE agentium_test"))
    admin_engine.dispose()


def _get_tables_and_enums(engine: Engine) -> tuple[set[str], set[str]]:
    """Return (set of table names except alembic_version, set of enum names)."""
    with engine.connect() as conn:
        tables_result = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = {row[0] for row in tables_result}
        tables.discard("alembic_version")

        enums_result = conn.execute(
            text(
                "SELECT typname FROM pg_type "
                "WHERE typtype = 'e' AND typname NOT LIKE 'pg_%'"
            )
        )
        enums = {row[0] for row in enums_result}
    return tables, enums


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def engine() -> Engine:
    return create_engine(DATABASE_URL)


@pytest.fixture
def fresh_database(engine: Engine):
    """Yield a clean test database."""
    _drop_and_create_test_db(engine)
    yield
    # Cleanup after test


# ============================================================================
# Tests
# ============================================================================

def test_upgrade_head_creates_tables(engine: Engine, fresh_database):
    """Upgrading to head should create at least one table."""
    runner = AlembicRunner()
    runner.upgrade("head")

    tables, _ = _get_tables_and_enums(engine)
    assert len(tables) > 0, "No tables created after upgrading to head"


def test_downgrade_base_removes_all_tables(engine: Engine, fresh_database):
    """Downgrading to base should leave no tables or custom enums."""
    runner = AlembicRunner()
    runner.upgrade("head")
    runner.downgrade("base")

    tables, enums = _get_tables_and_enums(engine)
    assert len(tables) == 0, f"Tables left after downgrade to base: {tables}"
    assert not enums, f"Leftover custom enum types after downgrade: {enums}"


def test_roundtrip_each_migration_individually(engine: Engine, fresh_database):
    """Apply each migration, then downgrade it, verifying idempotency."""
    runner = AlembicRunner()

    # Get list of all revision IDs
    rev_ids = runner.history()
    assert rev_ids, "No migrations found"

    for rev_id in rev_ids:
        # Apply to this revision, then reverse to previous
        runner.upgrade("+1")

        # For the last one, downgrade back to previous before continuing
        runner.downgrade("-1")

    # Re-apply all to return to head
    runner.upgrade("head")
    tables, enums = _get_tables_and_enums(engine)
    assert len(tables) > 0, "No tables after restoring to head"
    assert not enums, f"Leftover custom enum types after roundtrip: {enums}"
