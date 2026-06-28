"""
Unit tests for backend.core.dependencies — @with_db_session decorator.

These tests mock `get_db_context` so no real database is required.
Coverage targets: decorator correctly handles session injection for
sync/async, instance/class/static methods, and both "db provided" and
"session created" paths.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, sentinel

from backend.core.dependencies import with_db_session, with_new_db_session


class TestWithDbSession:
    """Tests for the @with_db_session decorator."""

    # ── Sync ─────────────────────────────────────────────────────────────

    def test_sync_passes_existing_session(self):
        """If caller passes a real Session, decorator is a no-op."""
        existing = MagicMock(name="existing_session")

        @with_db_session
        def handle(data: str, db=None):
            return (data, db)

        result = handle("payload", db=existing)
        assert result == ("payload", existing)

    def test_sync_creates_new_session(self):
        """If 'db' is omitted, decorator creates a fresh session."""
        mock_ctx = MagicMock()
        mock_session = MagicMock(name="new_session")
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        @with_db_session
        def handle(data: str, db=None):
            return (data, db)

        with patch("backend.core.dependencies.get_db_context", return_value=mock_ctx):
            result = handle("payload")

        assert result == ("payload", mock_session)
        mock_ctx.__enter__.assert_called_once()

    def test_sync_method_on_instance(self):
        """Decorator handles 'self' correctly on instance methods."""
        mock_ctx = MagicMock()
        mock_session = MagicMock(name="new_session")
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        class Service:
            @with_db_session
            def do_thing(self, Show, db=None):
                return Show

        with patch("backend.core.dependencies.get_db_context", return_value=mock_ctx):
            got = Service().do_thing(42)

        assert got == 42
        mock_ctx.__enter__.assert_called_once()

    def test_classmethod_decorated(self):
        """Decorator works on classmethods."""
        mock_ctx = MagicMock()
        mock_session = MagicMock(name="new_session")
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        class Store:
            @classmethod
            @with_db_session
            def find(cls, item_id: int, db=None):
                return (item_id, db)

        with patch("backend.core.dependencies.get_db_context", return_value=mock_ctx):
            got = Store.find(99)

        assert got == (99, mock_session)

    # ── Async ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_async_passes_existing_session(self):
        existing = MagicMock(name="existing_session")

        @with_db_session
        async def handle(data: str, db=None):
            return (data, db)

        result = await handle("payload", db=existing)
        assert result == ("payload", existing)

    @pytest.mark.asyncio
    async def test_async_creates_new_session(self):
        mock_ctx = MagicMock()
        mock_session = MagicMock(name="new_session")
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        @with_db_session
        async def handle(data: str, db=None):
            return (data, db)

        with patch("backend.core.dependencies.get_db_context", return_value=mock_ctx):
            result = await handle("payload")

        assert result == ("payload", mock_session)
        mock_ctx.__enter__.assert_called_once()

    # ── Function without 'db' param ──────────────────────────────────────

    def test_function_without_db_param_skipped(self):
        """If the function doesn't accept a 'db' param, decorator is a no-op."""

        @with_db_session
        def plain(a, b):
            return a + b

        assert plain(1, 2) == 3

    # ── @with_new_db_session ─────────────────────────────────────────────

    def test_with_new_db_session_always_creates_new(self):
        """with_new_db_session ignores caller-provided 'db'."""
        mock_ctx = MagicMock()
        mock_session = MagicMock(name="forced_session")
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        @with_new_db_session
        def isolate(user, db=None):
            return (user, db)

        existing = MagicMock(name="existing_session")

        with patch("backend.core.dependencies.get_db_context", return_value=mock_ctx):
            result = isolate("u1", db=existing)

        assert result == ("u1", mock_session)
