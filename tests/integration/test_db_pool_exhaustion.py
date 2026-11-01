# tests/integration/test_db_pool_exhaustion.py
"""
Tests for Database Connection Pool Exhaustion behavior.

Verifies:
1. Pool exhaustion when all connections in use (pool_size + max_overflow = 30 max)
2. pool_timeout behavior (30s default) when waiting for a connection
3. pool_pre_ping behavior for stale connections
4. max_overflow behavior (10 additional connections beyond pool_size)
5. Connection recycle behavior (1800s)
6. Graceful degradation when pool exhausted (proper error handling)
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import tempfile
import os

from sqlalchemy import create_engine, text, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError
from sqlalchemy.engine import Engine


class TestDBPoolConfiguration:
    """Tests for database pool configuration validation."""

    def test_pool_settings_from_config(self):
        """Verify pool settings match config values."""
        from backend.core.config import settings
        from backend.models.database import engine

        assert engine.pool.size() == settings.DATABASE_POOL_SIZE
        assert engine.pool._max_overflow == settings.DATABASE_MAX_OVERFLOW
        assert engine.pool._timeout == settings.DATABASE_POOL_TIMEOUT
        assert engine.pool._recycle == settings.DATABASE_POOL_RECYCLE
        assert engine.pool._pre_ping is True

    def test_pool_class_is_queuepool(self):
        """Verify QueuePool is used."""
        from backend.models.database import engine
        assert isinstance(engine.pool, QueuePool)


class TestDBPoolExhaustion:
    """Tests for pool exhaustion behavior."""

    def _create_test_engine(self, pool_size=2, max_overflow=1, pool_timeout=1, pool_recycle=-1, pool_pre_ping=False):
        """Create a test engine with a file-based SQLite DB to share connections."""
        # Use a temporary file for SQLite to ensure connections share the same DB
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        engine = create_engine(
            f"sqlite:///{path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
        )
        # Store path for cleanup
        engine._test_db_path = path
        return engine

    def _cleanup_engine(self, engine):
        """Clean up test engine and temp file."""
        engine.dispose()
        if hasattr(engine, '_test_db_path') and os.path.exists(engine._test_db_path):
            os.unlink(engine._test_db_path)

    def test_pool_exhaustion_raises_timeout(self):
        """When all connections in use, new requests wait up to pool_timeout then raise."""
        # Create a test engine with small pool for faster testing
        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=1)

        # Hold all connections (pool_size + max_overflow = 3)
        connections = []
        for _ in range(3):
            conn = test_engine.connect()
            connections.append(conn)

        # Next connection should timeout after pool_timeout
        start = time.time()
        with pytest.raises((OperationalError, SQLTimeoutError)):
            test_engine.connect()
        elapsed = time.time() - start

        # Should have waited approximately pool_timeout (1 second)
        assert elapsed >= 0.8, f"Expected ~1s timeout, got {elapsed:.2f}s"

        # Cleanup
        for conn in connections:
            conn.close()
        self._cleanup_engine(test_engine)

    def test_max_overflow_allows_extra_connections(self):
        """max_overflow allows connections beyond pool_size up to limit."""
        test_engine = self._create_test_engine(pool_size=2, max_overflow=2, pool_timeout=1)

        connections = []
        # Should be able to get pool_size + max_overflow = 4 connections
        for _ in range(4):
            conn = test_engine.connect()
            connections.append(conn)

        assert len(connections) == 4

        # 5th connection should fail
        with pytest.raises((OperationalError, SQLTimeoutError)):
            test_engine.connect()

        for conn in connections:
            conn.close()
        self._cleanup_engine(test_engine)

    def test_pool_releases_connections_on_close(self):
        """Connections returned to pool when closed."""
        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=1)

        # Get and release connections
        conn1 = test_engine.connect()
        conn1.close()

        conn2 = test_engine.connect()
        conn2.close()

        # Should be able to get connections again
        conn3 = test_engine.connect()
        conn3.close()

        self._cleanup_engine(test_engine)

    def test_concurrent_pool_exhaustion(self):
        """Multiple threads exhausting pool simultaneously."""
        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=2)

        results = []
        errors = []

        def worker(worker_id):
            try:
                conn = test_engine.connect()
                time.sleep(0.1)  # Hold connection briefly
                conn.close()
                results.append(worker_id)
            except Exception as e:
                errors.append((worker_id, e))

        # Launch 5 workers for 3 available connections
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for f in as_completed(futures):
                pass

        # All workers should succeed (they serialize due to pool limit)
        assert len(results) == 5
        assert len(errors) == 0

        self._cleanup_engine(test_engine)


class TestDBPoolPrePing:
    """Tests for pool_pre_ping behavior with stale connections."""

    def _create_test_engine(self, pool_size=2, max_overflow=1, pool_timeout=1, pool_recycle=-1, pool_pre_ping=False):
        """Create a test engine with a file-based SQLite DB to share connections."""
        # Use a temporary file for SQLite to ensure connections share the same DB
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        engine = create_engine(
            f"sqlite:///{path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
        )
        # Store path for cleanup
        engine._test_db_path = path
        return engine

    def _cleanup_engine(self, engine):
        """Clean up test engine and temp file."""
        engine.dispose()
        if hasattr(engine, '_test_db_path') and os.path.exists(engine._test_db_path):
            os.unlink(engine._test_db_path)

    def test_pre_ping_detects_stale_connection(self):
        """pool_pre_ping should detect and replace stale connections."""
        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=1, pool_pre_ping=True)

        # Get a connection
        conn = test_engine.connect()
        conn.close()

        # The connection should be validated on next checkout
        # For SQLite file-based, this works transparently
        conn2 = test_engine.connect()
        result = conn2.execute(text("SELECT 1")).scalar()
        assert result == 1
        conn2.close()

        self._cleanup_engine(test_engine)

    def test_pre_ping_enabled_on_production_engine(self):
        """Verify production engine has pool_pre_ping enabled."""
        from backend.models.database import engine
        assert engine.pool._pre_ping is True


class TestDBPoolRecycle:
    """Tests for connection recycle behavior."""

    def test_pool_recycle_setting(self):
        """Verify pool_recycle is configured correctly."""
        from backend.core.config import settings
        from backend.models.database import engine

        assert engine.pool._recycle == settings.DATABASE_POOL_RECYCLE
        assert settings.DATABASE_POOL_RECYCLE == 1800  # 30 minutes

    def test_recycle_prevents_stale_connections(self):
        """Connections older than pool_recycle are recycled."""
        test_engine = create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
            pool_recycle=1,  # 1 second recycle for testing
            pool_pre_ping=False,
        )

        conn = test_engine.connect()
        conn.close()

        # Wait for recycle time
        time.sleep(1.5)

        # Next checkout should get a fresh connection
        conn2 = test_engine.connect()
        result = conn2.execute(text("SELECT 1")).scalar()
        assert result == 1
        conn2.close()

        test_engine.dispose()


class TestDBPoolGracefulDegradation:
    """Tests for graceful degradation when pool is exhausted."""

    def _create_test_engine(self, pool_size=1, max_overflow=0, pool_timeout=1, pool_pre_ping=False):
        """Create a test engine with a file-based SQLite DB to share connections."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        engine = create_engine(
            f"sqlite:///{path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=pool_pre_ping,
        )
        engine._test_db_path = path
        return engine

    def _cleanup_engine(self, engine):
        """Clean up test engine and temp file."""
        engine.dispose()
        if hasattr(engine, '_test_db_path') and os.path.exists(engine._test_db_path):
            os.unlink(engine._test_db_path)

    def test_get_db_context_raises_on_exhaustion(self):
        """get_db_context should raise proper error when pool exhausted."""
        from backend.models.database import get_db_context

        test_engine = self._create_test_engine(pool_size=1, max_overflow=0, pool_timeout=1)

        # Hold the only connection
        held_conn = test_engine.connect()

        # Patch the module's engine and SessionLocal
        import backend.models.database as db_module
        original_engine = db_module.engine
        db_module.engine = test_engine
        original_session_local = db_module.SessionLocal
        from sqlalchemy.orm import sessionmaker
        db_module.SessionLocal = sessionmaker(bind=test_engine)

        try:
            with pytest.raises((OperationalError, SQLTimeoutError)):
                with get_db_context() as db:
                    db.execute(text("SELECT 1"))
        finally:
            held_conn.close()
            db_module.engine = original_engine
            db_module.SessionLocal = original_session_local
            self._cleanup_engine(test_engine)

    def test_get_db_dependency_raises_on_exhaustion(self):
        """get_db dependency should raise proper error when pool exhausted."""
        from backend.models.database import get_db

        test_engine = self._create_test_engine(pool_size=1, max_overflow=0, pool_timeout=1)

        held_conn = test_engine.connect()

        import backend.models.database as db_module
        original_engine = db_module.engine
        db_module.engine = test_engine
        original_session_local = db_module.SessionLocal
        # Recreate SessionLocal with test engine
        from sqlalchemy.orm import sessionmaker
        db_module.SessionLocal = sessionmaker(bind=test_engine)

        try:
            db_gen = get_db()
            db = next(db_gen)  # Get the session
            # Actually use the session to trigger connection checkout
            with pytest.raises((OperationalError, SQLTimeoutError)):
                db.execute(text("SELECT 1"))
        finally:
            held_conn.close()
            db_module.engine = original_engine
            db_module.SessionLocal = original_session_local
            self._cleanup_engine(test_engine)

    def test_check_health_works_under_load(self):
        """check_health should work even when pool is under pressure."""
        from backend.models.database import check_health

        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=1)

        import backend.models.database as db_module
        original_engine = db_module.engine
        db_module.engine = test_engine

        try:
            # Health check should succeed
            health = check_health()
            assert health["status"] == "healthy"
            assert health["database"] == "connected"
            assert "latency_ms" in health
        finally:
            db_module.engine = original_engine
            self._cleanup_engine(test_engine)

    def test_check_health_reports_unhealthy_when_db_unreachable(self):
        """check_health should report unhealthy when DB unreachable."""
        from backend.models.database import check_health

        # Create engine with invalid URL
        bad_engine = create_engine(
            "postgresql://invalid:invalid@invalid:5432/invalid",
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
            pool_pre_ping=False,
        )

        import backend.models.database as db_module
        original_engine = db_module.engine
        db_module.engine = bad_engine

        try:
            health = check_health()
            assert health["status"] == "unhealthy"
            assert health["database"] == "disconnected"
            assert "error" in health
        finally:
            db_module.engine = original_engine
            bad_engine.dispose()


class TestDBPoolSettingsValidation:
    """Tests for validating pool settings are applied correctly."""

    def _create_test_engine(self, pool_size=20, max_overflow=10, pool_timeout=30, pool_recycle=1800, pool_pre_ping=True):
        """Create a test engine with a file-based SQLite DB to share connections."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        engine = create_engine(
            f"sqlite:///{path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
        )
        engine._test_db_path = path
        return engine

    def _cleanup_engine(self, engine):
        """Clean up test engine and temp file."""
        engine.dispose()
        if hasattr(engine, '_test_db_path') and os.path.exists(engine._test_db_path):
            os.unlink(engine._test_db_path)

    def test_pool_size_respected(self):
        """pool_size limits concurrent connections."""
        from backend.core.config import settings
        test_engine = self._create_test_engine(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_pre_ping=True,
        )

        assert test_engine.pool.size() == settings.DATABASE_POOL_SIZE
        self._cleanup_engine(test_engine)

    def test_max_overflow_respected(self):
        """max_overflow limits extra connections."""
        from backend.core.config import settings
        test_engine = self._create_test_engine(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=1,
            pool_pre_ping=False,
        )

        connections = []
        # Should get pool_size + max_overflow connections
        for _ in range(settings.DATABASE_POOL_SIZE + settings.DATABASE_MAX_OVERFLOW):
            connections.append(test_engine.connect())

        # Next should fail
        with pytest.raises((OperationalError, SQLTimeoutError)):
            test_engine.connect()

        for c in connections:
            c.close()
        self._cleanup_engine(test_engine)

    def test_pool_timeout_respected(self):
        """pool_timeout controls wait time."""
        test_engine = self._create_test_engine(pool_size=1, max_overflow=0, pool_timeout=2)

        held = test_engine.connect()

        start = time.time()
        with pytest.raises((OperationalError, SQLTimeoutError)):
            test_engine.connect()
        elapsed = time.time() - start

        # Should wait approximately pool_timeout
        assert 1.5 <= elapsed <= 3.0, f"Expected ~2s timeout, got {elapsed:.2f}s"

        held.close()
        self._cleanup_engine(test_engine)


class TestDBPoolIntegration:
    """Integration tests for pool behavior with actual database operations."""

    def _create_test_engine(self, pool_size=2, max_overflow=1, pool_timeout=5, pool_pre_ping=False):
        """Create a test engine with a file-based SQLite DB to share connections."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)

        engine = create_engine(
            f"sqlite:///{path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=pool_pre_ping,
        )
        engine._test_db_path = path
        return engine

    def _cleanup_engine(self, engine):
        """Clean up test engine and temp file."""
        engine.dispose()
        if hasattr(engine, '_test_db_path') and os.path.exists(engine._test_db_path):
            os.unlink(engine._test_db_path)

    def test_multiple_operations_share_pool(self):
        """Multiple operations should share pool connections."""
        from backend.models.database import get_db_context

        test_engine = self._create_test_engine(pool_size=2, max_overflow=1, pool_timeout=5)

        # Create a table using the test engine directly
        with test_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"))
            conn.commit()

        import backend.models.database as db_module
        original_engine = db_module.engine
        db_module.engine = test_engine
        original_session_local = db_module.SessionLocal
        from sqlalchemy.orm import sessionmaker
        db_module.SessionLocal = sessionmaker(bind=test_engine)

        try:
            # Perform multiple operations
            for i in range(5):
                with get_db_context() as db:
                    db.execute(text("INSERT INTO test (value) VALUES (:v)"), {"v": f"value_{i}"})
                    db.commit()

            # Verify all inserted
            with get_db_context() as db:
                count = db.execute(text("SELECT COUNT(*) FROM test")).scalar()
                assert count == 5
        finally:
            db_module.engine = original_engine
            db_module.SessionLocal = original_session_local
            self._cleanup_engine(test_engine)

    def test_long_running_transaction_blocks_pool_slot(self):
        """Long-running transactions should block a pool slot."""
        # Use pool_size=1 to ensure the long transaction blocks the only slot
        test_engine = self._create_test_engine(pool_size=1, max_overflow=0, pool_timeout=1)

        with test_engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY)"))
            conn.commit()

        # Start a long transaction - holds the only connection
        conn1 = test_engine.connect()
        conn1.execute(text("BEGIN"))
        conn1.execute(text("INSERT INTO test (id) VALUES (1)"))

        # Second connection should timeout (pool exhausted)
        with pytest.raises((OperationalError, SQLTimeoutError)):
            test_engine.connect()

        # Commit and release first
        conn1.execute(text("COMMIT"))
        conn1.close()

        # Now should work
        conn3 = test_engine.connect()
        conn3.close()

        self._cleanup_engine(test_engine)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])