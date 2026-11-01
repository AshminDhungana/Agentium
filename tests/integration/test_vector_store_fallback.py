# tests/integration/test_vector_store_fallback.py
"""
Tests for Vector Store fallback behavior.

Verifies:
1. When CHROMA_HOST not set → local persistent client used
2. When CHROMA_HOST set → HTTP client with retry logic (3 attempts, exponential backoff)
3. When HTTP connection fails after retries → RuntimeError raised (no fallback to local)
4. Health check returns correct status for both modes
5. Retry logic uses exponential backoff (2^attempt seconds)
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import time
import os
from pathlib import Path


class TestVectorStoreLocalMode:
    """Tests for local persistent client mode (development/CI)."""

    def test_local_mode_when_chroma_host_not_set(self, monkeypatch, tmp_path):
        """When CHROMA_HOST is not set, VectorStore uses local PersistentClient."""
        # Ensure CHROMA_HOST is not set
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()
        client = store.client

        # Should be a PersistentClient
        assert store._host is None
        # Verify the persist directory was created
        assert (tmp_path / "chroma_data").exists()

    def test_local_mode_health_check(self, monkeypatch, tmp_path):
        """Health check returns healthy status in local mode."""
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()
        # Access client to trigger initialization
        _ = store.client

        health = store.health_check()

        assert health["status"] == "healthy"
        assert health["mode"] == "local"
        assert health["persist_directory"] == str(tmp_path / "chroma_data")
        assert "heartbeat" in health
        assert isinstance(health["collections"], list)


class TestVectorStoreHTTPMode:
    """Tests for HTTP client mode (production)."""

    def test_http_mode_when_chroma_host_set(self, monkeypatch):
        """When CHROMA_HOST is set, VectorStore uses HttpClient."""
        monkeypatch.setenv("CHROMA_HOST", "chromadb")
        monkeypatch.setenv("CHROMA_PORT", "8000")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()
        assert store._host == "chromadb"
        assert store._port == 8000

    def test_http_mode_connection_retry_logic(self, monkeypatch):
        """HTTP mode retries 3 times with exponential backoff on connection failure."""
        monkeypatch.setenv("CHROMA_HOST", "chromadb")
        monkeypatch.setenv("CHROMA_PORT", "8000")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()

        # Mock chromadb and httpx to simulate connection failures
        with patch.object(store, '_get_chromadb') as mock_get_chromadb, \
             patch.object(store, '_get_httpx') as mock_get_httpx, \
             patch.object(store, '_patch_http_timeouts'):

            mock_chromadb = MagicMock()
            mock_httpx = MagicMock()
            mock_get_chromadb.return_value = mock_chromadb
            mock_get_httpx.return_value = mock_httpx

            # Simulate TransportError on all 3 attempts
            mock_httpx.TransportError = Exception
            mock_chromadb.HttpClient.side_effect = mock_httpx.TransportError("Connection refused")

            # Time the retry attempts
            start = time.time()
            with pytest.raises(RuntimeError) as exc_info:
                store.initialize()
            elapsed = time.time() - start

            # Should have retried 3 times
            assert mock_chromadb.HttpClient.call_count == 3
            # Should have exponential backoff: 2^0 + 2^1 + 2^2 = 1 + 2 + 4 = 7 seconds minimum
            # Allow some margin for execution time
            assert elapsed >= 6.5, f"Expected ~7s for retries, got {elapsed:.2f}s"
            assert "Cannot connect to ChromaDB at chromadb:8000 after 3 attempts" in str(exc_info.value)

    def test_http_mode_success_on_second_attempt(self, monkeypatch):
        """HTTP mode succeeds on retry and doesn't retry further."""
        monkeypatch.setenv("CHROMA_HOST", "chromadb")
        monkeypatch.setenv("CHROMA_PORT", "8000")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()

        # Patch at module level where the methods are defined
        with patch.object(vs_module.VectorStore, '_get_chromadb') as mock_get_chromadb, \
             patch.object(vs_module.VectorStore, '_get_httpx') as mock_get_httpx, \
             patch.object(vs_module.VectorStore, '_patch_http_timeouts'), \
             patch('time.sleep') as mock_sleep:

            mock_chromadb = MagicMock()
            mock_httpx = MagicMock()
            mock_get_chromadb.return_value = mock_chromadb
            mock_get_httpx.return_value = mock_httpx
            mock_httpx.TransportError = Exception

            # First attempt fails, second succeeds
            mock_client = MagicMock()
            mock_client.heartbeat.return_value = 12345
            mock_chromadb.HttpClient.side_effect = [
                mock_httpx.TransportError("Connection refused"),
                mock_client,
            ]

            client = store.initialize()

            # Verify client is returned and is the mock we provided
            assert client is not None
            assert hasattr(client, 'heartbeat')
            assert mock_chromadb.HttpClient.call_count == 2
            # Should have slept once (after first failure)
            assert mock_sleep.call_count == 1
            # Sleep should be 2^0 = 1 second
            mock_sleep.assert_called_with(1)

    def test_http_mode_health_check(self, monkeypatch):
        """Health check returns correct status in HTTP mode."""
        monkeypatch.setenv("CHROMA_HOST", "chromadb")
        monkeypatch.setenv("CHROMA_PORT", "8000")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()

        with patch.object(store, '_get_chromadb') as mock_get_chromadb, \
             patch.object(store, '_get_httpx') as mock_get_httpx, \
             patch.object(store, '_patch_http_timeouts'):

            mock_chromadb = MagicMock()
            mock_httpx = MagicMock()
            mock_get_chromadb.return_value = mock_chromadb
            mock_get_httpx.return_value = mock_httpx

            mock_client = MagicMock()
            mock_client.heartbeat.return_value = 12345
            mock_chromadb.HttpClient.return_value = mock_client

            _ = store.client  # Initialize

            health = store.health_check()

            assert health["status"] == "healthy"
            assert health["mode"] == "http"
            assert health["host"] == "chromadb"
            assert health["heartbeat"] == 12345


class TestVectorStoreFallbackBehavior:
    """Tests for the fallback/no-fallback behavior between modes."""

    def test_no_automatic_fallback_from_http_to_local(self, monkeypatch):
        """
        When CHROMA_HOST is set but connection fails, NO automatic fallback to local mode.
        Raises RuntimeError instead.
        """
        monkeypatch.setenv("CHROMA_HOST", "unreachable-host")
        monkeypatch.setenv("CHROMA_PORT", "8000")
        # Set a local persist dir - should NOT be used when CHROMA_HOST is set
        monkeypatch.setenv("CHROMA_PERSIST_DIR", "/tmp/should_not_be_used")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()

        with patch.object(store, '_get_chromadb') as mock_get_chromadb, \
             patch.object(store, '_get_httpx') as mock_get_httpx, \
             patch.object(store, '_patch_http_timeouts'):

            mock_chromadb = MagicMock()
            mock_httpx = MagicMock()
            mock_get_chromadb.return_value = mock_chromadb
            mock_get_httpx.return_value = mock_httpx
            mock_httpx.TransportError = Exception
            mock_chromadb.HttpClient.side_effect = mock_httpx.TransportError("Connection refused")

            with pytest.raises(RuntimeError) as exc_info:
                store.initialize()

            # Should NOT have fallen back to PersistentClient
            mock_chromadb.PersistentClient.assert_not_called()
            assert "Cannot connect to ChromaDB at unreachable-host:8000 after 3 attempts" in str(exc_info.value)

    def test_explicit_local_mode_when_host_unset(self, monkeypatch, tmp_path):
        """Explicitly using local mode when CHROMA_HOST is unset works correctly."""
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()
        client = store.client

        # Should use PersistentClient - verify by checking host is None and client has expected methods
        assert store._host is None
        assert hasattr(client, 'get_or_create_collection')
        assert hasattr(client, 'heartbeat')


class TestVectorStoreSingleton:
    """Tests for the module-level singleton pattern."""

    def test_get_vector_store_returns_singleton(self, monkeypatch, tmp_path):
        """get_vector_store() returns the same instance on multiple calls."""
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        # Reset the module-level singleton
        vs_module._vector_store = None

        store1 = vs_module.get_vector_store()
        store2 = vs_module.get_vector_store()

        assert store1 is store2

    def test_module_getattr_vector_store(self, monkeypatch, tmp_path):
        """Module __getattr__ returns the singleton vector_store."""
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        # Reset the module-level singleton
        vs_module._vector_store = None

        # Access via module attribute
        store = vs_module.vector_store

        assert store is not None
        assert isinstance(store, vs_module.VectorStore)


class TestVectorDBContextManager:
    """Tests for the vector_db_session context manager."""

    def test_vector_db_session_context_manager(self, monkeypatch, tmp_path):
        """vector_db_session yields a VectorStore instance."""
        monkeypatch.delenv("CHROMA_HOST", raising=False)
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma_data"))

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        # Reset the module-level singleton
        vs_module._vector_store = None

        with vs_module.vector_db_session() as store:
            assert isinstance(store, vs_module.VectorStore)
            assert store is vs_module.get_vector_store()


class TestVectorStoreRetryTiming:
    """Tests for precise retry timing behavior."""

    def test_retry_backoff_timing(self, monkeypatch):
        """Retry backoff follows 2^attempt pattern: 1s, 2s, 4s."""
        monkeypatch.setenv("CHROMA_HOST", "chromadb")
        monkeypatch.setenv("CHROMA_PORT", "8000")

        import importlib
        import backend.core.vector_store as vs_module
        importlib.reload(vs_module)

        store = vs_module.VectorStore()

        with patch.object(store, '_get_chromadb') as mock_get_chromadb, \
             patch.object(store, '_get_httpx') as mock_get_httpx, \
             patch.object(store, '_patch_http_timeouts'), \
             patch('time.sleep') as mock_sleep:

            mock_chromadb = MagicMock()
            mock_httpx = MagicMock()
            mock_get_chromadb.return_value = mock_chromadb
            mock_get_httpx.return_value = mock_httpx
            mock_httpx.TransportError = Exception
            mock_chromadb.HttpClient.side_effect = mock_httpx.TransportError("Connection refused")

            with pytest.raises(RuntimeError):
                store.initialize()

            # Verify sleep was called with exponential backoff: 1, 2, 4
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls == [1, 2, 4], f"Expected [1, 2, 4], got {sleep_calls}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])