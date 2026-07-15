import pytest
from pathlib import Path
from tempfile import mkdtemp


@pytest.fixture
def no_minio_creds(monkeypatch):
    import backend.services.storage_service as ss

    monkeypatch.setattr(ss, "_ACCESS_KEY", "")
    monkeypatch.setattr(ss, "_SECRET_KEY", "")
    monkeypatch.setattr(ss, "_LOCAL_ROOT", Path(mkdtemp()))
    return ss


def test_local_fallback_without_creds(no_minio_creds):
    backend = no_minio_creds.StorageService._init_backend()
    assert backend.name == "local"
