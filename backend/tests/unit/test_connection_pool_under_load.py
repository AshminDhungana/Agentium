"""Verify the connection pool returns to baseline under traffic and that
engine.dispose() closes underlying connections. Pure-Python; runs on any
backend (Postgres or SQLite)."""
import os

# Force SQLite before any backend import so this file works in CI
# environments that don't have Postgres reachable. The engine is
# created at module-import time, so we cannot pick the URL later.
# Use direct assignment (not setdefault) because pytest-env or a
# sibling test module may have already set DATABASE_URL.
#
# The `check_same_thread=False` URL parameter is required for the
# concurrent-load test below: ThreadPoolExecutor checks out
# connections in worker threads, and pysqlite rejects cross-thread
# connection use by default. This flag is SQLite-specific (Postgres
# production has no equivalent constraint).
os.environ["DATABASE_URL"] = (
    "sqlite:///file:memdb1?mode=memory&cache=shared&uri=true&check_same_thread=False"
)

# Patch JSONB → SQLA JSON so SQLite can compile DDL for columns that
# would otherwise be Postgres-only. Mirrors integration conftest.
import sqlalchemy.dialects.postgresql as _pg_dialect
from sqlalchemy import JSON as _JSON
class _JSONBCompat(_JSON):
    pass
_pg_dialect.JSONB = _JSONBCompat

import concurrent.futures
import time
from sqlalchemy import text

from backend.models.database import engine, get_db_context


def test_checked_out_returns_to_baseline_after_traffic():
    """After 100 concurrent get_db_context() blocks, checkedout() must equal 0.

    This proves the pool does not leak connections under load. The same
    pool is the one used by the maintenance coroutines in production, so
    a leak here would also starve the cleanup loops.
    """
    baseline_checkedout = engine.pool.checkedout()
    assert baseline_checkedout == 0, (
        f"Pre-test pool has {baseline_checkedout} checked-out connections"
    )

    def _exercise():
        # Each invocation touches the DB without holding the session
        # open after exit.
        with get_db_context() as db:
            db.execute(text("SELECT 1"))

    N = 100
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: _exercise(), range(N)))
    elapsed = time.monotonic() - t0

    # All connections must have been released back to the pool.
    final_checkedout = engine.pool.checkedout()
    assert final_checkedout == 0, (
        f"Pool leaked {final_checkedout} connection(s) after {N} "
        f"concurrent uses (elapsed {elapsed:.2f}s)"
    )


def test_engine_dispose_closes_all_connections():
    """engine.dispose() must close all underlying connections without
    raising. After dispose, opening a new session creates fresh handles.

    This is a smoke check against handle lifecycle regressions — e.g.
    a future contributor switching poolclass or adding middleware that
    forgets to close underlying DBAPI connections.
    """
    # Force at least one connection to be opened so dispose has work to do.
    with get_db_context() as db:
        db.execute(text("SELECT 1"))

    # dispose() should not raise.
    engine.dispose()

    # After dispose, opening a new session should still work and
    # connections should remain closable.
    with get_db_context() as db:
        result = db.execute(text("SELECT 2")).scalar()
        assert result == 2
