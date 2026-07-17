# backend/tests/integration/test_provider_mock_wiring.py
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from backend.tests.integration.test_provider_resilience import FakeProviderServer


ANTHROPIC_OK = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "fake",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}

SSE_CHUNKS = [
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "he"}, "finish_reason": None}]},
    {"id": "c1", "object": "chat.completion.chunk", "model": "fake",
     "choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": "stop"}]},
]


class ExtendedFakeProviderServer(FakeProviderServer):
    def __init__(self, default_status=200, default_body=None, anthropic_body=None):
        super().__init__(default_status=default_status, default_body=default_body)
        self._anthropic_body = anthropic_body or ANTHROPIC_OK
        self._sse_queue = []
        self.messages_url = f"http://127.0.0.1:{self.port}/v1/messages"

    def set_stream(self, chunks):
        with self._lock:
            self._sse_queue = list(chunks)

    def _make_handler(self):
        server = self
        base_handler = super()._make_handler()

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _drain(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                if length:
                    self.rfile.read(length)

            def do_POST(self):
                self._drain()
                if self.path == "/v1/messages":
                    with server._lock:
                        body = json.dumps(server._anthropic_body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/v1/chat/completions" and server._sse_queue:
                    with server._lock:
                        chunks = server._sse_queue
                        server._sse_queue = []
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for ch in chunks:
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                base_handler(self)

        return _H


def test_extended_server_anthropic_route():
    srv = ExtendedFakeProviderServer()
    try:
        import urllib.request
        req = urllib.request.Request(
            srv.messages_url, data=b"{}", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        assert data["stop_reason"] == "end_turn"
        assert data["content"][0]["text"] == "ok"
    finally:
        srv.shutdown()


import pytest
import uuid
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.models.entities.user_config import (
    UserModelConfig, ProviderType, ConnectionStatus,
)
from backend.core.security import encrypt_api_key
from backend.tests.integration.test_provider_resilience import (
    make_fake_config, _delete_fake_configs,
)
from backend.services.provider_rate_limiter import provider_rate_limiter
from backend.core.llm_client import LLMClient


def make_mock_config(provider: ProviderType, base_url: str) -> UserModelConfig:
    """Committed UserModelConfig pointing at the mock; sets provider + local URL."""
    eng = create_engine(os.getenv("DATABASE_URL"), poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=eng)()
    cfg = UserModelConfig(
        user_id="sovereign",
        provider=provider,
        config_name=f"mock-{provider.value.lower()}-{uuid.uuid4().hex[:6]}",
        api_key_encrypted=encrypt_api_key("sk-test"),
        api_key_masked="sk-test",
        default_model="fake",
        status=ConnectionStatus.ACTIVE,
        is_active=True,
        requests_per_minute=100000,
        max_concurrent_requests=100,
        priority=1,
    )
    if provider == ProviderType.LOCAL:
        cfg.local_server_url = base_url
    else:
        cfg.api_base_url = base_url
    s.add(cfg)
    s.commit()
    s.refresh(cfg)
    s.close()
    eng.dispose()
    return cfg


def reset_resilience():
    """Clear circuit-breaker + rate-limiter local state between tests."""
    LLMClient._circuit_breakers.clear()
    provider_rate_limiter._local_sems.clear()
    provider_rate_limiter._last_headers.clear()


provider_cases = [
    (ProviderType.OPENAI, "openai_compat"),
    (ProviderType.ANTHROPIC, "anthropic"),
    (ProviderType.GEMINI, "openai_compat"),
    (ProviderType.GROQ, "openai_compat"),
    (ProviderType.MISTRAL, "openai_compat"),
    (ProviderType.TOGETHER, "openai_compat"),
    (ProviderType.COHERE, "openai_compat"),
    (ProviderType.FIREWORKS, "openai_compat"),
    (ProviderType.MOONSHOT, "openai_compat"),
    (ProviderType.DEEPSEEK, "openai_compat"),
    (ProviderType.AZURE_OPENAI, "openai_compat"),
    (ProviderType.QIANWEN, "openai_compat"),
    (ProviderType.ZHIPU, "openai_compat"),
    (ProviderType.AI21, "openai_compat"),
    (ProviderType.PERPLEXITY, "openai_compat"),
    (ProviderType.LOCAL, "openai_compat"),
    (ProviderType.CUSTOM, "openai_compat"),
]


def test_make_mock_config_committed():
    srv = ExtendedFakeProviderServer()
    cfg = make_mock_config(ProviderType.OPENAI, srv.base_url)
    try:
        assert cfg.id is not None
        assert cfg.provider == ProviderType.OPENAI
        assert cfg.api_base_url == srv.base_url
    finally:
        srv.shutdown()
        _delete_fake_configs([str(cfg.id)])
        reset_resilience()
