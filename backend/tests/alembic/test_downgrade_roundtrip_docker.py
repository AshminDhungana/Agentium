"""Alembic downgrade round-trip test — runs within Docker container."""
import os
import subprocess
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine, text as sa_text

# Database connection (accessing host from within Docker)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://agentium:agentium@host.docker.internal:5432/agentium_test")
BACKEND_DIR = Path("/app").resolve()
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

def cleanup_database():
    """Drop and recreate the test database via SQLAlchemy.
    Uses psycopg2 directly to ensure proper AUTOCOMMIT behavior for DDL."""
    import psycopg2

    # Parse connection string components
    admin_url = DATABASE_URL.rsplit("/", 1)[0] + "/postgres"

    # Extract host and credentials from DATABASE_URL
    # URL format: postgresql://user:pass@host:port/db
    import re
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', DATABASE_URL)
    if match:
        user, password, host, port, _ = match.groups()
    else:
        # Fallback for unix socket or different format
        match = re.match(r'postgresql://([^:]+):([^@]+)@([^/]+)/(.+)', DATABASE_URL)
        user, password, host, _ = match.groups()
        port = 5432

    # Connect to maintenance database (postgres) with autocommit
    conn = psycopg2.connect(
        host=host, port=int(port), database="postgres",
        user=user, password=password
    )
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # Terminate all existing connections to agentium_test
        cur.execute(
            "SELECT pg_terminate_backend(pid) "
            "FROM pg_stat_activity "
            "WHERE datname = 'agentium_test' AND pid <> pg_backend_pid()"
        )
        time.sleep(0.5)
        # Force drop and recreate
        cur.execute("DROP DATABASE IF EXISTS agentium_test")
        cur.execute("CREATE DATABASE agentium_test")
    finally:
        cur.close()
        conn.close()
    print("  Database cleaned and recreated.")

def get_tables_and_enums(engine):
    """Return (set of table names except alembic_version, set of enum names)."""
    with engine.connect() as conn:
        # Get tables
        result = conn.execute(sa_text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        tables = {row[0] for row in result}
        tables.discard("alembic_version")

        # Get custom enums
        result = conn.execute(
            sa_text("SELECT typname FROM pg_type WHERE typtype = 'e' AND typname NOT LIKE 'pg_%'")
        )
        enums = {row[0] for row in result}
    return tables, enums

class AlembicRunner:
    def __init__(self):
        self.ini = str(ALEMBIC_INI)
        self.cwd = str(BACKEND_DIR)

    def _run(self, *args: str) -> str:
        cmd = ["alembic", "-c", self.ini, *args]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"Alembic failed: {' '.join(cmd)}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
        return result.stdout

    def upgrade(self, revision: str) -> str:
        return self._run("upgrade", revision)

    def downgrade(self, revision: str) -> str:
        return self._run("downgrade", revision)


if __name__ == "__main__":
    # Combined round-trip test
    all_pass = True
    try:
        print("=== test_roundtrip (upgrade head -> downgrade base -> verify) ===")

        # Step 1: Clean database
        cleanup_database()

        # Step 2: Upgrade to head
        runner = AlembicRunner()
        runner.upgrade("head")
        print("  Upgraded to head successfully")

        # Step 3: Verify tables exist
        engine = create_engine(DATABASE_URL)
        tables, _ = get_tables_and_enums(engine)
        count = len(tables)
        engine.dispose()
        assert count > 0, "No tables created after upgrading to head"
        print(f"  Tables after upgrade head: {count} tables (OK)")

        # Step 4: Downgrade to base
        runner.downgrade("base")
        print("  Downgraded to base successfully")

        # Step 5: Verify no tables or enums remain
        engine = create_engine(DATABASE_URL)
        tables, enums = get_tables_and_enums(engine)
        engine.dispose()

        assert len(tables) == 0, f"Tables left after downgrade to base: {tables}"
        assert not enums, f"Leftover custom enum types after downgrade: {enums}"
        print("  No leftover tables or enum types (OK)")

        print("PASS: test_roundtrip")
    except Exception as e:
        print(f"FAIL: test_roundtrip: {e}")
        import traceback
        traceback.print_exc()
        all_pass = False

    if not all_pass:
        sys.exit(1)
    print("\n=== All Alembic round-trip tests passed ===")
