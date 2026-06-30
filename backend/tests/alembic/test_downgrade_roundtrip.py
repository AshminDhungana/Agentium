"""Test that Alembic migrations round-trip cleanly on a fresh test database."""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse


BACKEND_DIR = Path(__file__).parent.parent.parent.resolve()
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Allow override via env var; default connects to the test postgres on the host
DEFAULT_URL = "postgresql://agentium:agentium@host.docker.internal:5432/agentium_test"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_URL)


def _psql(sql: str, db_url: str = None) -> tuple[int, str]:
    """Run a psql command via shell, return (returncode, output)."""
    target = db_url or DATABASE_URL
    cmd = [
        "psql",
        "--tuples-only", "--no-align", "--quiet",
        target,
        "-c",
        sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return 0 if result.returncode == 0 else 1, result.stdout


class AlembicRunner:
    def __init__(self, ini_path: Path, cwd: Path) -> None:
        self.ini = str(ini_path)
        self.cwd = cwd

    def _run(self, *args: str) -> str:
        cmd = ["alembic", "-c", self.ini, *args]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"Alembic command failed: {' '.join(cmd)}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
        return result.stdout

    def upgrade(self, revision: str) -> str:
        return self._run("upgrade", revision)

    def downgrade(self, revision: str) -> str:
        return self._run("downgrade", revision)

    def current(self) -> str:
        return self._run("current")


def get_tables_enum() -> tuple[set[str], set[str]]:
    """Return (tables, enum_types) currently in the test database."""
    retcode, tables_out = _psql(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
    )
    retcode2, enums_out = _psql(
        "SELECT typname FROM pg_type WHERE typtype = 'e' AND typname NOT LIKE 'pg_%';"
    )
    tables = set(tables_out.strip().splitlines())
    enums = set(enums_out.strip().splitlines())
    return tables, enums


def drop_and_recreate_test_db():
    """Connect to postgres template DB (stripping the db name from the URL)
    and drop/recreate the target test database."""
    parsed = urlparse(DATABASE_URL)
    # Build a URL that points at the 'postgres' maintenance DB instead
    admin_url = urlunparse(
        parsed._replace(path="/postgres" if not parsed.path else "/postgres")
    )
    # Get the DB name from the original URL
    db_name = Path(parsed.path).name or "agentium_test"

    cmd = [
        "psql", admin_url, "-c",
        f"DROP DATABASE IF EXISTS {db_name}; CREATE DATABASE {db_name};"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to recreate test DB:\n{result.stdout}\n{result.stderr}"
        )
    print(f"Dropped and recreated {db_name}")


# ------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------
def test_upgrade_head_creates_tables():
    runner = AlembicRunner(ALEMBIC_INI, BACKEND_DIR)
    drop_and_recreate_test_db()
    runner.upgrade("head")

    tables, _ = get_tables_enum()
    assert len(tables) > 0, "No tables created after upgrading to head"
    print(f"Tables after upgrade head: {len(tables)} tables")


def test_full_downgrade_base_removes_all():
    runner = AlembicRunner(ALEMBIC_INI, BACKEND_DIR)
    drop_and_recreate_test_db()

    runner.upgrade("head")
    print("Upgraded to head successfully")

    runner.downgrade("base")
    print("Downgraded to base successfully")

    tables, enums = get_tables_enum()
    tables.discard("alembic_version")  # managed by alembic
    tables.discard("")  # possible empty string from psql output
    enums.discard("")

    assert len(tables) == 0, f"Tables left after downgrade to base: {tables}"
    print(f"No leftover tables (OK)")

    assert not enums, f"Leftover custom enum types after downgrade: {enums}"
    print("No leftover enum types (OK)")


def test_roundtrip():
    runner = AlembicRunner(ALEMBIC_INI, BACKEND_DIR)
    drop_and_recreate_test_db()

    # Full round-trip
    runner.upgrade("head")
    print("  Upgraded to head")
    runner.downgrade("base")
    print("  Downgraded to base")
    runner.upgrade("head")
    print("  Re-upgraded to head")

    tables, _ = get_tables_enum()
    assert len(tables) > 0, "Expected tables after re-upgrade"
    print(f"Tables after full round-trip: {len(tables)} tables (OK)")


if __name__ == "__main__":
    tests = {
        "test_upgrade_head_creates_tables": test_upgrade_head_creates_tables,
        "test_full_downgrade_base_removes_all": test_full_downgrade_base_removes_all,
        "test_roundtrip": test_roundtrip,
    }

    targets = sys.argv[1:] or list(tests.keys())
    all_pass = True
    for name in targets:
        if name in targets:
            print(f"\n=== {name} ===")
            try:
                tests[name]()
                print(f"PASS: {name}")
            except Exception as e:
                print(f"FAIL: {name}: {e}")
                import traceback
                traceback.print_exc()
                all_pass = False

    if not all_pass:
        sys.exit(1)
    print("\n=== All tests passed ===")
