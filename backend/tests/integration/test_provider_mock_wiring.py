# backend/tests/integration/test_provider_mock_wiring.py
import json
from http.server import BaseHTTPRequestHandler
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
        # The base class starts serve_forever in a daemon thread but does not
        # guarantee the socket is accepting by the time the caller connects.
        # The Anthropic SDK does not retry connection errors, so a race there
        # caused intermittent 401/connection failures. Poll until ready.
        self._wait_until_ready()

    def _wait_until_ready(self, timeout: float = 5.0):
        import socket
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.02)
        raise RuntimeError(
            f"ExtendedFakeProviderServer did not start on port {self.port}"
        )

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
                # Only the branches we serve ourselves drain the body. The
                # delegated base handler does its OWN body read, so draining
                # here first would consume the bytes it waits for and hang.
                if self.path == "/v1/messages":
                    self._drain()
                    # Honor the same injected-failure queue + hit counters the
                    # base handler uses (set_next / status_counts) so Anthropic
                    # exercises the identical resilience paths as the
                    # OpenAI-compatible providers. A queued (or default) non-200
                    # spec returns that status; otherwise serve the anthropic body.
                    with server._lock:
                        server._hits += 1
                        spec = (
                            server._queue.pop(0)
                            if server._queue
                            else server._default
                        )
                        status = spec.get("status", 200)
                        server._status_counts[status] = (
                            server._status_counts.get(status, 0) + 1
                        )
                        if status == 200:
                            body = json.dumps(server._anthropic_body).encode()
                        else:
                            err = spec.get("body") or {"error": "mock error"}
                            body = json.dumps(err).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/v1/chat/completions" and server._sse_queue:
                    self._drain()
                    with server._lock:
                        chunks = server._sse_queue
                        server._sse_queue = []
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    # HTTPServer speaks HTTP/1.0; without a Content-Length the
                    # client relies on connection close to detect end-of-stream.
                    self.send_header("Connection", "close")
                    self.close_connection = True
                    self.end_headers()
                    for ch in chunks:
                        self.wfile.write(f"data: {json.dumps(ch)}\n\n".encode())
                        self.wfile.flush()
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    return
                base_handler.do_POST(self)

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
import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.services.model_provider import ModelService
from backend.core.tool_registry import tool_registry
from backend.models.entities import Agent


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


@pytest.fixture(scope="module")
def seeded_once():
    """Run genesis at most ONCE for this module and reuse it across every
    parametrized provider case.

    The shared ``seeded_db`` fixture is function-scoped and re-runs the full
    genesis protocol per test (17x here), which is heavy and flaky. These
    wiring tests only need agent ``10003`` to exist and be committed so the
    ModelService/LLMClient (which open their own DB sessions) can load it.
    We commit genesis to the real test DB once, yield a committed session for
    querying, and leave the seeded rows in place for the whole module.
    """
    from backend.services.initialization_service import InitializationService
    from backend.models.entities.agents import Agent as _Agent, AgentType, AgentStatus
    from backend.models.entities.user import User

    eng = create_engine(os.getenv("DATABASE_URL"), poolclass=NullPool, pool_pre_ping=True)
    session = sessionmaker(bind=eng)()

    admin = session.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_active=True,
            is_pending=False,
            is_admin=True,
        )
        session.add(admin)
        session.commit()

    init_service = InitializationService(db=session)
    if not init_service.is_system_initialized():
        init_service._has_any_active_api_key = lambda: True
        asyncio.get_event_loop().run_until_complete(
            init_service.run_genesis_protocol(force=True, country_name="TestNation")
        )
        session.commit()

    if not session.query(_Agent).filter_by(agentium_id="10003").first():
        session.add(
            _Agent(
                agentium_id="10003",
                name="Admin User Agent",
                agent_type=AgentType.COUNCIL_MEMBER,
                status=AgentStatus.ACTIVE,
            )
        )
        session.commit()

    try:
        yield session
    finally:
        session.close()
        eng.dispose()


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


OPENAI_TOOL_CALL = {
    "id": "chatcmplt-tool",
    "object": "chat.completion",
    "created": 1,
    "model": "fake",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_time", "arguments": "{}"},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

ANTHROPIC_TOOL_CALL = {
    "id": "msg_tool",
    "type": "message",
    "role": "assistant",
    "model": "fake",
    "content": [
        {"type": "tool_use", "id": "tu_1", "name": "get_time", "input": {}}
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


@pytest.mark.integration
class TestProviderHappyPath:
    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_happy_path_wiring(self, provider, path, seeded_once):
        seeded_db = seeded_once
        if path == "anthropic":
            srv = ExtendedFakeProviderServer(anthropic_body=ANTHROPIC_OK)
        else:
            srv = ExtendedFakeProviderServer()
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            assert agent is not None

            # 1) test_connection
            conn = await ModelService.test_connection(cfg)
            assert conn["success"] is True
            assert conn["model"] == "fake"

            # 2) non-stream generate
            client = LLMClient()
            res = await client.generate(agent, "hello", config_id=str(cfg.id))
            assert res["content"] == "ok"
            assert res["model"] == "fake"
            assert res["tokens_used"] >= 0

            # 3) streaming / content generation
            # OpenAI-compatible providers exercise the real SSE streaming path
            # against the mock. Anthropic streaming is out of scope for this
            # suite (the mock serves the non-stream /v1/messages route), so for
            # the anthropic path we verify content via the non-stream generate.
            if path == "anthropic":
                provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
                content = await provider_obj.generate("sys", "hello")
                assert content["content"] == "ok"
            else:
                srv.set_stream(SSE_CHUNKS)
                provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
                chunks = []
                async for c in provider_obj.stream_generate("sys", "hello"):
                    chunks.append(c)
                assert "".join(chunks) == "hello"

            # 4) tool-calling
            if path == "anthropic":
                srv._anthropic_body = ANTHROPIC_TOOL_CALL
            else:
                srv.set_next(200, None, OPENAI_TOOL_CALL)
            provider_obj = await ModelService.get_provider("sovereign", str(cfg.id))
            async def executor(name, args):
                return "done"
            result = await provider_obj.generate_with_tools(
                system_prompt="sys",
                messages=[{"role": "user", "content": "use a tool"}],
                tools=[{"type": "function", "function": {"name": "get_time", "parameters": {}}}],
                tool_executor=executor,
                agentium_id="10003",
            )
            assert "content" in result
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()


from backend.services.api_key_manager import api_key_manager


# LOCAL is a keyless self-hosted endpoint: LocalProvider deliberately tolerates
# a flaky/unauthorized local server by returning empty content instead of
# raising, so the "dead API key -> rotate to fallback" semantics do not apply.
# It is still covered by the 429/500 retry tests and the happy path.
rotation_cases = [(p, path) for (p, path) in provider_cases if p != ProviderType.LOCAL]


@pytest.mark.integration
class TestProviderResilience:
    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_429_retries_then_succeeds(self, provider, path, seeded_once):
        seeded_db = seeded_once
        srv = ExtendedFakeProviderServer()
        # First call 429, then 200 on retry.
        srv.set_next(429, None, {"error": "rate limited"})
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=1)
            res = await client.generate(agent, "hi", config_id=str(cfg.id))
            assert res["content"] == "ok"
            counts = srv.status_counts()
            assert counts.get(429, 0) >= 1
            assert counts.get(200, 0) >= 1
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()

    @pytest.mark.parametrize("provider,path", provider_cases)
    async def test_500_retries_then_succeeds(self, provider, path, seeded_once):
        seeded_db = seeded_once
        srv = ExtendedFakeProviderServer()
        srv.set_next(500, None, {"error": "boom"})
        cfg = make_mock_config(provider, srv.base_url)
        created_ids = [str(cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=1)
            res = await client.generate(agent, "hi", config_id=str(cfg.id))
            assert res["content"] == "ok"
        finally:
            srv.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()

    @pytest.mark.parametrize("provider,path", rotation_cases)
    async def test_401_rotates_without_retry(self, provider, path, seeded_once):
        seeded_db = seeded_once
        dead = ExtendedFakeProviderServer(default_status=401,
                                          default_body={"error": "unauthorized"})
        good = ExtendedFakeProviderServer(default_status=200)
        dead_cfg = make_mock_config(provider, dead.base_url)
        good_cfg = make_mock_config(provider, good.base_url)
        created_ids = [str(dead_cfg.id), str(good_cfg.id)]
        try:
            agent = seeded_db.query(Agent).filter_by(agentium_id="10003").first()
            client = LLMClient(max_retries=2)
            res = await client.generate(
                agent, "hi",
                config_id=str(dead_cfg.id),
                fallback_configs=[str(good_cfg.id)],
            )
            assert res["content"] == "ok"
            # Dead key hit exactly once (permanent failure => no retry),
            # fallback hit exactly once.
            assert dead.status_counts().get(401, 0) == 1
            assert good.status_counts().get(200, 0) == 1
        finally:
            dead.shutdown()
            good.shutdown()
            _delete_fake_configs(created_ids)
            reset_resilience()


async def _make_streaming_openai_provider(on_delta=None, cancel_event=None):
    from backend.services.model_provider import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    cfg = MagicMock()
    cfg.id = "cfg-stream"; cfg.provider = "openai"; cfg.default_model = "gpt-test"
    cfg.timeout_seconds = 30; cfg.max_concurrent_requests = 10; cfg.requests_per_minute = 60
    cfg.max_tokens = 512; cfg.temperature = 0.7; cfg.top_p = 1.0
    provider.config = cfg; provider.api_key = "x"

    class _Delta:
        def __init__(self, content): self.content = content
    class _Choice:
        def __init__(self, content): self.delta = _Delta(content); self.finish_reason = None
    class _Chunk:
        def __init__(self, content, finish_reason=None, usage=None):
            self.choices = [_Choice(content)]; self.finish_reason = finish_reason
            self.usage = usage; self.model = "gpt-test"
    async def _gen():
        yield _Chunk("Hello "); yield _Chunk("world")
    class _StreamResp:
        def __aiter__(self): return _gen().__aiter__()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_StreamResp())
    provider._client = client
    return provider

async def test_generate_with_tools_streams_final_turn():
    provider = await _make_streaming_openai_provider()
    chunks = []
    async def on_delta(text): chunks.append(text)
    result = await provider.generate_with_tools(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
        tools=[], tool_executor=None, on_delta=on_delta)
    assert chunks == ["Hello ", "world"]
    assert result["content"] == "Hello world"
    assert result["finish_reason"] == "stop"
    assert result["tokens_used"] >= 0

async def test_generate_with_tools_no_delta_is_blocking_shape():
    provider = await _make_streaming_openai_provider()
    result = await provider.generate_with_tools(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
        tools=[], tool_executor=None, on_delta=None)
    assert isinstance(result["content"], str)

async def test_generate_with_tools_cancel_stops_stream():
    provider = await _make_streaming_openai_provider()
    ev = asyncio.Event(); chunks = []
    async def on_delta(text):
        chunks.append(text)
        if len(chunks) >= 1: ev.set()
    result = await provider.generate_with_tools(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
        tools=[], tool_executor=None, on_delta=on_delta, cancel_event=ev)
    assert result["finish_reason"] == "stopped_by_user"
    assert "Hello " in result["content"]

async def _make_streaming_anthropic_provider():
    from backend.services.model_provider import AnthropicProvider
    provider = AnthropicProvider.__new__(AnthropicProvider)
    cfg = MagicMock()
    cfg.id = "cfg-anthropic"; cfg.provider = "anthropic"; cfg.default_model = "claude-test"
    cfg.timeout_seconds = 30; cfg.max_concurrent_requests = 10; cfg.requests_per_minute = 60
    cfg.max_tokens = 512; cfg.temperature = 0.7
    provider.config = cfg; provider.api_key = "x"

    class _TextDelta:
        def __init__(self, text):
            self.type = "content_block_delta"
            self.delta = MagicMock(); self.delta.text = text
    class _MsgDelta:
        def __init__(self):
            self.type = "message_delta"
            self.usage = MagicMock(); self.usage.output_tokens = 4
    async def _gen():
        yield _TextDelta("Hi "); yield _TextDelta("there"); yield _MsgDelta()
    class _StreamResp:
        def __aiter__(self): return _gen().__aiter__()
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_StreamResp())
    provider._client = client
    return provider

async def test_anthropic_generate_with_tools_streams_final_turn():
    provider = await _make_streaming_anthropic_provider()
    chunks = []
    async def on_delta(text): chunks.append(text)
    result = await provider.generate_with_tools(
        system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
        tools=[], tool_executor=None, on_delta=on_delta)
    assert "".join(chunks) == "Hi there"
    assert result["content"] == "Hi there"
    assert result["finish_reason"] == "stop"

async def test_llm_client_forwards_on_delta(monkeypatch):
    from backend.core.llm_client import LLMClient
    from backend.services import model_provider as mp

    captured = {}
    async def fake_gen_with_agent_tools(**kwargs):
        captured["on_delta"] = kwargs.get("on_delta")
        captured["cancel_event"] = kwargs.get("cancel_event")
        provider = await _make_streaming_openai_provider(
            on_delta=kwargs.get("on_delta"), cancel_event=kwargs.get("cancel_event"))
        return await provider.generate_with_tools(
            system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
            tools=[], tool_executor=None,
            on_delta=kwargs.get("on_delta"), cancel_event=kwargs.get("cancel_event"))
    monkeypatch.setattr(mp.ModelService, "generate_with_agent_tools", staticmethod(fake_gen_with_agent_tools))

    async def on_delta(t): pass
    client = LLMClient.__new__(LLMClient)
    client.max_retries = 0
    client.MAX_FALLBACK_CONFIGS = 0
    await client.generate_with_tools(
        agent=MagicMock(agentium_id="0xxxx"), user_message="hi",
        db=None, config_id="cfg-stream", on_delta=on_delta)
    assert captured["on_delta"] is on_delta
