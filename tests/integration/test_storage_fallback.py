# tests/integration/test_storage_fallback.py
"""
Tests for Storage Service fallback behavior.

Verifies:
1. When S3 credentials missing → local backend used
2. When S3 credentials are insecure defaults → local backend used
3. When S3 init fails → local backend used
4. Both backends provide same interface
5. backend_name property reports correct backend
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import io
import os
from pathlib import Path


class TestStorageServiceFallback:
    """Tests for StorageService fallback selection logic."""

    def test_no_credentials_uses_local_backend(self):
        """When AWS credentials not set, StorageService uses LocalBackend."""
        with patch.dict(os.environ, {}, clear=True):
            for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_ENDPOINT"]:
                os.environ.pop(key, None)

            import importlib
            import backend.services.storage_service as storage_module
            importlib.reload(storage_module)

            service = storage_module.StorageService()
            assert service.backend_name == "local"
            assert isinstance(service._backend, storage_module._LocalBackend)

    def test_insecure_minio_defaults_uses_local_backend(self):
        """When MinIO default credentials used, StorageService refuses S3 and uses LocalBackend."""
        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "minioadmin",
            "AWS_SECRET_ACCESS_KEY": "minioadmin",
        }, clear=True):
            import importlib
            import backend.services.storage_service as storage_module
            importlib.reload(storage_module)

            service = storage_module.StorageService()
            assert service.backend_name == "local"
            assert isinstance(service._backend, storage_module._LocalBackend)

    def test_s3_init_failure_falls_back_to_local(self):
        """When S3 client initialization fails, StorageService falls back to LocalBackend."""
        with patch.dict(os.environ, {
            "AWS_ACCESS_KEY_ID": "valid_key",
            "AWS_SECRET_ACCESS_KEY": "valid_secret",
        }, clear=True):
            with patch("backend.services.storage_service._S3Backend") as mock_s3:
                mock_s3.side_effect = Exception("Connection refused")

                import importlib
                import backend.services.storage_service as storage_module
                importlib.reload(storage_module)

                service = storage_module.StorageService()
                assert service.backend_name == "local"
                assert isinstance(service._backend, storage_module._LocalBackend)


class TestLocalBackendWithMonkeyPatch:
    """Tests for LocalBackend using monkeypatch to override module constants."""

    def _create_local_backend(self, monkeypatch, tmp_path, base_url="http://localhost:8000"):
        """Helper to create LocalBackend with patched module constants."""
        # Patch the module constants BEFORE importing/reloading
        import backend.services.storage_service as storage_module

        # Directly modify the module attributes (they're used by _LocalBackend.__init__)
        monkeypatch.setattr(storage_module, "_LOCAL_ROOT", tmp_path)
        monkeypatch.setattr(storage_module, "_APP_BASE_URL", base_url)

        # Now create backend directly - it will use the patched module attributes
        backend = storage_module._LocalBackend()
        return backend, storage_module

    def test_upload_file_creates_file_and_returns_url(self, monkeypatch, tmp_path):
        """LocalBackend uploads file and returns URL."""
        backend, storage_module = self._create_local_backend(monkeypatch, tmp_path)
        file_obj = io.BytesIO(b"test content")

        url = backend.upload_file(file_obj, "test.txt", "text/plain")

        assert url is not None
        assert "test.txt" in url or "api/v1/files" in url

        # Verify file was created
        saved_file = tmp_path / "test.txt"
        assert saved_file.exists()
        assert saved_file.read_bytes() == b"test content"

    def test_upload_file_failure_returns_none(self, monkeypatch, tmp_path):
        """Upload failure returns None, not exception."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        class FailingFile:
            def read(self, *args, **kwargs):
                raise OSError("Disk full")

        url = backend.upload_file(FailingFile(), "fail.txt")
        assert url is None

    def test_generate_presigned_url_existing_file(self, monkeypatch, tmp_path):
        """LocalBackend returns URL for existing file."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        # Create a test file directly in the backend's root
        test_file = tmp_path / "existing.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        url = backend.generate_presigned_url("existing.txt")
        assert url is not None
        assert "existing.txt" in url

    def test_generate_presigned_url_missing_file(self, monkeypatch, tmp_path):
        """LocalBackend returns None for missing file."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        url = backend.generate_presigned_url("missing.txt")
        assert url is None

    def test_delete_file_existing(self, monkeypatch, tmp_path):
        """LocalBackend deletes existing file."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        # Create a test file
        test_file = tmp_path / "to_delete.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        result = backend.delete_file("to_delete.txt")
        assert result is True
        assert not test_file.exists()

    def test_delete_file_nonexistent(self, monkeypatch, tmp_path):
        """LocalBackend handles deleting non-existing file gracefully."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        result = backend.delete_file("nonexistent.txt")
        assert result is True

    def test_list_files(self, monkeypatch, tmp_path):
        """LocalBackend lists files with S3-compatible dict format."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)

        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "subdir").mkdir(exist_ok=True)
        (tmp_path / "subdir" / "file2.txt").write_text("content2")

        files = backend.list_files("")

        assert isinstance(files, list)
        assert len(files) == 2
        for f in files:
            assert "Key" in f
            assert "Size" in f
            assert "LastModified" in f

    def test_local_backend_creates_directories(self, monkeypatch, tmp_path):
        """LocalBackend creates parent directories on upload."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path)
        file_obj = io.BytesIO(b"deep content")

        url = backend.upload_file(file_obj, "deep/nested/path/file.txt")

        assert url is not None
        saved = tmp_path / "deep/nested/path/file.txt"
        assert saved.exists()
        assert saved.read_bytes() == b"deep content"

    def test_local_backend_public_url_format(self, monkeypatch, tmp_path):
        """LocalBackend generates correct API download URLs."""
        backend, _ = self._create_local_backend(monkeypatch, tmp_path, "http://localhost:8000")

        # Standard file path: files/user_id/filename (3+ parts -> uses download endpoint)
        url = backend._public_url("files/user123/document.pdf")
        assert url == "http://localhost:8000/api/v1/files/download/user123/document.pdf"

        # Path with exactly 3 parts also uses download endpoint
        # "other/path/file.txt" -> parts = ("other", "path", "file.txt") -> user_id="path", filename="file.txt"
        url = backend._public_url("other/path/file.txt")
        assert url == "http://localhost:8000/api/v1/files/download/path/file.txt"

        # Path with fewer than 3 parts uses local endpoint
        url = backend._public_url("single.txt")
        assert url == "http://localhost:8000/api/v1/files/local/single.txt"


class TestS3BackendBehavior:
    """Tests specific to S3Backend behavior (with mocked boto3)."""

    def test_s3_backend_upload_returns_presigned_url(self, monkeypatch):
        """S3Backend returns proper S3 URL on upload."""
        # Patch boto3 where it's actually imported (inside _S3Backend.__init__)
        with patch("boto3.client") as mock_client:
            mock_s3 = MagicMock()
            mock_client.return_value = mock_s3

            # Set env vars before reload
            monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
            monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
            monkeypatch.setenv("S3_ENDPOINT", "http://minio:9000")
            monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

            import importlib
            import backend.services.storage_service as storage_module
            importlib.reload(storage_module)

            backend = storage_module._S3Backend()
            file_obj = io.BytesIO(b"test")

            url = backend.upload_file(file_obj, "test.txt")

            assert url is not None
            assert "test-bucket" in url
            assert "test.txt" in url
            mock_s3.upload_fileobj.assert_called_once()

    def test_s3_backend_presigned_url(self, monkeypatch):
        """S3Backend generates presigned URLs."""
        # Patch boto3 where it's actually imported (inside _S3Backend.__init__)
        with patch("boto3.client") as mock_client:
            mock_s3 = MagicMock()
            mock_s3.generate_presigned_url.return_value = "https://presigned.url/test.txt"
            mock_client.return_value = mock_s3

            monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
            monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")

            import importlib
            import backend.services.storage_service as storage_module
            importlib.reload(storage_module)

            backend = storage_module._S3Backend()
            url = backend.generate_presigned_url("test.txt", 3600)

            assert url == "https://presigned.url/test.txt"
            mock_s3.generate_presigned_url.assert_called_once()


class TestStorageServiceIntegration:
    """Integration tests for StorageService facade."""

    def test_storage_service_delegates_to_backend(self):
        """StorageService delegates all calls to active backend."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import backend.services.storage_service as storage_module
            importlib.reload(storage_module)

            service = storage_module.StorageService()

            # Mock the backend to verify delegation
            mock_backend = MagicMock()
            mock_backend.upload_file.return_value = "http://test.url"
            mock_backend.generate_presigned_url.return_value = "http://presigned.url"
            mock_backend.delete_file.return_value = True
            mock_backend.list_files.return_value = [{"Key": "test.txt"}]
            service._backend = mock_backend

            # Test all public methods
            file_obj = io.BytesIO(b"test")

            assert service.upload_file(file_obj, "test.txt") == "http://test.url"
            mock_backend.upload_file.assert_called_once_with(file_obj, "test.txt", "application/octet-stream")

            assert service.generate_presigned_url("test.txt", 7200) == "http://presigned.url"
            mock_backend.generate_presigned_url.assert_called_once_with("test.txt", 7200)

            assert service.delete_file("test.txt") is True
            mock_backend.delete_file.assert_called_once_with("test.txt")

            assert service.list_files("prefix/") == [{"Key": "test.txt"}]
            mock_backend.list_files.assert_called_once_with("prefix/")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])