"""Integration tests for user avatar upload/remove."""
import io
from unittest.mock import MagicMock

import pytest

from backend.api.routes import users as users_module


@pytest.fixture
def patched_storage(monkeypatch):
    upload = MagicMock(return_value="https://storage.test/avatars/u1/abc.png")
    delete = MagicMock(return_value=True)
    monkeypatch.setattr(users_module.storage_service, "upload_file", upload)
    monkeypatch.setattr(users_module.storage_service, "delete_file", delete)
    return upload, delete


def _png_bytes() -> bytes:
    # Minimal valid PNG (1x1) — starts with the real PNG magic bytes.
    return (
        b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"
        b"\x00\x00\x00\x0d\x49\x48\x44\x52"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    )


def test_upload_sets_avatar_url(client, seeded_db, auth_headers, patched_storage):
    upload, _ = patched_storage
    resp = client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["avatar_url"].startswith("https://storage.test/")
    assert upload.called


def test_upload_rejects_bad_type(client, seeded_db, auth_headers, patched_storage):
    # A .png extension but PDF magic bytes -> magic-byte mismatch (400).
    resp = client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic.png", io.BytesIO(b"%PDF-1.4 fake"), "image/png")},
    )
    assert resp.status_code == 400


def test_upload_rejects_oversize(client, seeded_db, auth_headers, patched_storage):
    big = _png_bytes() + b"\x00" * (5 * 1024 * 1024 + 10)
    resp = client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic.png", io.BytesIO(big), "image/png")},
    )
    assert resp.status_code == 413


def test_replace_deletes_old_object(client, seeded_db, auth_headers, patched_storage):
    upload, delete = patched_storage
    client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    # Second upload should trigger a delete of the previous object.
    upload.return_value = "https://storage.test/avatars/u1/def.png"
    client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic2.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert delete.called


def test_remove_clears_avatar(client, seeded_db, auth_headers, patched_storage):
    upload, delete = patched_storage
    client.post(
        "/api/v1/users/me/avatar",
        headers=auth_headers,
        files={"file": ("pic.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    resp = client.delete("/api/v1/users/me/avatar", headers=auth_headers)
    assert resp.status_code == 204
    assert delete.called


def test_unauthenticated_rejected(client, seeded_db, patched_storage):
    resp = client.post(
        "/api/v1/users/me/avatar",
        files={"file": ("pic.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert resp.status_code == 401
