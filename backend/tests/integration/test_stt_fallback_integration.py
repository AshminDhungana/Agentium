"""Integration: whisper.cpp unavailable -> OpenAI Whisper leg of the chain.

Drives the REAL OpenAI SDK through AudioService.transcribe against
a FakeProviderServer (inlined from test_provider_resilience.py), with the
local whisper.cpp leg disabled by patching is_available() -> False.
"""
import uuid
import threading
import json
import os
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.services.audio_service import AudioService
from backend.services.whisper_cpp_service import get_whisper_cpp_service
from backend.core.security import encrypt_api_key
from backend.models.entities.user_config import (
    UserModelConfig,
    ProviderType,
    ConnectionStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Inlined FakeProviderServer and helpers (from test_provider_resilience.py)
# ─────────────────────────────────────────────────────────────────────────────

OPENAI_COMPLETION = {
    "id": "chatcmplt-test",
    "object": "chat.completion",
    "created": 1,
    "model": "fake",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

OPENAI_TRANSCRIPTION = {
    "text": "ok"
}


class FakeProviderServer:
    """A threaded OpenAI-compatible HTTP server returning configurable responses."""

    def __init__(self, default_status=200, default_headers=None, default_body=None):
        self._default = {
            "status": default_status,
            "headers": default_headers or {},
            "body": default_body or OPENAI_COMPLETION,
        }
        self._queue = []  # list of {"status","headers","body"}
        self._lock = threading.Lock()
        self._hits = 0
        self._status_counts = {}  # status_code -> hit count
        handler = self._make_handler()
        self._httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        t.start()

    def _make_handler(self):
        server = self

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    body = self.rfile.read(length)
                else:
                    body = b""
                with server._lock:
                    server._hits += 1
                    used_queue = bool(server._queue)
                    spec = server._queue.pop(0) if server._queue else server._default
                    server._status_counts[spec["status"]] = (
                        server._status_counts.get(spec["status"], 0) + 1
                    )

                # Different response format for audio transcription endpoint
                path = self.path
                # Use path-appropriate default body if using default spec (not queued response)
                if path.endswith("/audio/transcriptions"):
                    if used_queue:
                        body_resp = spec.get("body", OPENAI_TRANSCRIPTION)
                    else:
                        body_resp = OPENAI_TRANSCRIPTION
                    payload = json.dumps(body_resp).encode()
                else:
                    if used_queue:
                        body_resp = spec.get("body", OPENAI_COMPLETION)
                    else:
                        body_resp = OPENAI_COMPLETION
                    payload = json.dumps(body_resp).encode()

                status = spec.get("status", 200)
                headers = spec.get("headers", {})
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, str(v))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return _H

    def set_next(self, status=200, headers=None, body=None):
        with self._lock:
            self._queue.append(
                {
                    "status": status,
                    "headers": headers or {},
                    "body": body or OPENAI_COMPLETION,
                }
            )

    def hits(self):
        with self._lock:
            return self._hits

    def status_counts(self):
        with self._lock:
            return dict(self._status_counts)

    def shutdown(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def make_fake_config(
    base_url: str,
    *,
    rpm: int = 100000,
    status: ConnectionStatus = ConnectionStatus.ACTIVE,
):
    """Create + TOP-LEVEL commit a UserModelConfig pointing at a FakeProviderServer.

    Uses its own NullPool engine because ModelService.get_provider() opens its
    OWN db session (get_db_context) — a savepoint commit on the test's
    db_session is invisible to it until the outer transaction commits.
    rpm is stored in the `requests_per_minute` column (renamed away from the
    old `rate_limit` column — see user_config.py and migration 003).
    """
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://agentium:agentium@localhost:5432/agentium_test",
    )
    eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    cfg = UserModelConfig(
        user_id="sovereign",
        provider=ProviderType.OPENAI,
        config_name=f"fake-{uuid.uuid4().hex[:8]}",
        api_key_encrypted=encrypt_api_key("sk-test"),
        api_key_masked="sk-test",
        default_model="fake",
        status=status,
        api_base_url=base_url,
        requests_per_minute=rpm,  # column is `requests_per_minute` (was `rate_limit`)
        is_active=True,
        priority=1,
    )
    s.add(cfg)
    s.commit()
    s.refresh(cfg)
    s.close()
    eng.dispose()
    return cfg


def _delete_fake_configs(ids):
    """Soft-deactivate configs committed by make_fake_config."""
    if not ids:
        return
    database_url = os.getenv("DATABASE_URL")
    eng = create_engine(database_url, poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    s.query(UserModelConfig).filter(UserModelConfig.id.in_(ids)).update(
        {
            UserModelConfig.is_active: False,
            UserModelConfig.status: ConnectionStatus.ERROR,
        },
        synchronize_session=False,
    )
    s.commit()
    s.close()
    eng.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestWhisperDownFallsBackToOpenAI:
    async def test_openai_leg_used_when_whisper_unavailable(self, seeded_db: Session, monkeypatch):
        srv = FakeProviderServer(default_status=200)
        created = []
        try:
            cfg = make_fake_config(srv.base_url, rpm=100000)
            created.append(str(cfg.id))

            # Disable the local whisper.cpp leg so the chain must use OpenAI.
            monkeypatch.setattr(
                get_whisper_cpp_service(), "is_available", lambda: False
            )
            # Bypass the DB lookup for the OpenAI key (provider enum case mismatch).
            monkeypatch.setattr(
                AudioService, "_get_openai_api_key", lambda self, db, user_id: "sk-test"
            )
            # Make the OpenAI client point at the fake server (not real API).
            monkeypatch.setattr(
                AudioService,
                "_get_openai_client",
                lambda self, api_key: __import__("openai").OpenAI(
                    api_key=api_key, base_url=srv.base_url
                ),
            )

            svc = AudioService()
            text = await svc.transcribe(
                db=seeded_db, user_id="sovereign",
                audio_bytes=b"RIFF....", language="en",
            )
            assert text == "ok"  # FakeProviderServer returns "ok"
            assert srv.hits() >= 1
        finally:
            srv.shutdown()
            _delete_fake_configs(created)