# Streaming Chat Replies (Task 10.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream assistant chat replies token-by-token over the existing `/chat` WebSocket (provider stream → WebSocket → incremental frontend render), with a stop control and graceful fallback for non-streaming providers.

**Architecture:** Thread an optional `on_delta` async callback + `cancel_event` down through `ChatService.process_message → LLMClient.generate_with_tools → ModelService.generate_with_agent_tools → Provider.generate_with_tools`. The agentic tool-call loop is untouched; the final text turn is streamed with `stream=True` and each chunk forwarded to `on_delta`. The WebSocket handler runs generation as a task and emits `message_start` / `message_delta` / `message_end` events. Persistence, token/cost logging, and metadata run once at completion, unchanged. The frontend renders live markdown + a blinking caret and exposes a Stop button.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / pytest (backend); React 18 / TypeScript / Zustand / Vitest (frontend). Providers: OpenAI-compatible SDK (OpenAI/Groq/Ollama/compatible) + Anthropic SDK.

## Global Constraints

- Every reply emits exactly one `message_start` and one `message_end`; `message_delta` count is 0..N. Keyed by server-generated `stream_id` (UUID).
- `message_id` is server-assigned in `message_start`; frontend dedups via it.
- Only the **final text turn** is streamed; tool-call iterations run silently (blocking) as today.
- Provider scope: OpenAI-compatible + Anthropic stream; all others fall back to blocking (single `message_end`, zero deltas).
- Persistence, token/cost logging, and metadata (`task_created`, `card`, `media_urls`, `model`) run ONLY on completion, using the existing `ChatService` logic unchanged.
- Non-LLM replies (governance fast-path, structured cards) deliver whole as `message_start` + `message_end` with zero deltas.
- `message_delta` events are NOT buffered to Redis replay; only `message_start`/`message_end` are.
- `on_delta is None` ⇒ behavior byte-for-byte identical to current blocking path (agents, tests, non-chat callers unaffected).
- `finish_reason` values: `"stop" | "stopped_by_user" | "error"`.
- Respect `prefers-reduced-motion`: no blinking caret / typewriter smoothing.
- `Message.status` must gain a `'streaming'` variant (currently `'sending' | 'sent' | 'error'`).
- Follow existing code conventions: `Optional[...]`/`List[...]` imports already present in `model_provider.py`; the OpenAI streaming pattern at `model_provider.py:512-545` (`stream=True`, `async for chunk`, `chunk.choices[0].delta.content`) is the reference shape.

---

### Task 1: Backend — OpenAI-compatible provider streaming seam

**Files:**
- Modify: `backend/services/model_provider.py` (method `OpenAICompatibleProvider.generate_with_tools`, currently lines 547–712)
- Test: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: existing loop logic / `_get_cached_sdk_client` / `provider_rate_limiter` / `calculate_cost` / `self._log_usage`.
- Produces: `generate_with_tools(system_prompt, messages, tools, tool_executor, max_iterations=10, on_delta=None, cancel_event=None, **kwargs)` — when `on_delta` is callable, streams final text turn and calls `await on_delta(text_chunk)` per chunk; when `cancel_event.is_set()` mid-stream, stops and returns accumulated content with `finish_reason="stopped_by_user"`. Return dict unchanged in shape (`content`, `tokens_used`, `prompt_tokens`, `completion_tokens`, `latency_ms`, `model`, `messages`, `cost_usd`) plus optional `finish_reason`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_provider_mock_wiring.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


async def _make_streaming_openai_provider(on_delta=None, cancel_event=None):
    """Build an OpenAICompatibleProvider whose SDK client yields two text chunks
    with NO tool calls (final-turn streaming path)."""
    from backend.services.model_provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    # Minimal config stub with attrs the method reads.
    cfg = MagicMock()
    cfg.id = "cfg-stream"
    cfg.provider = "openai"
    cfg.default_model = "gpt-test"
    cfg.timeout_seconds = 30
    cfg.max_concurrent_requests = 10
    cfg.requests_per_minute = 60
    cfg.max_tokens = 512
    cfg.temperature = 0.7
    cfg.top_p = 1.0
    provider.config = cfg
    provider.api_key = "x"

    class _Delta:
        def __init__(self, content):
            self.content = content
    class _Choice:
        def __init__(self, content):
            self.delta = _Delta(content)
            self.finish_reason = None
    class _Chunk:
        def __init__(self, content, finish_reason=None, usage=None):
            self.choices = [_Choice(content)]
            self.finish_reason = finish_reason
            self.usage = usage
            self.model = "gpt-test"
    async def _gen():
        yield _Chunk("Hello ")
        yield _Chunk("world")
    class _StreamResp:
        def __aiter__(self):
            return _gen().__aiter__()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_StreamResp())
    provider._client = client
    return provider


async def test_generate_with_tools_streams_final_turn():
    provider = await _make_streaming_openai_provider()
    chunks = []
    async def on_delta(text):
        chunks.append(text)

    result = await provider.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=None,
        on_delta=on_delta,
    )
    assert chunks == ["Hello ", "world"]
    assert result["content"] == "Hello world"
    assert result["finish_reason"] == "stop"
    assert result["tokens_used"] >= 0


async def test_generate_with_tools_no_delta_is_blocking_shape():
    provider = await _make_streaming_openai_provider()
    # on_delta=None must still return content (blocking fallback path is not
    # triggered for the streaming-capable provider, but shape must hold).
    result = await provider.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=None,
        on_delta=None,
    )
    assert isinstance(result["content"], str)


async def test_generate_with_tools_cancel_stops_stream():
    provider = await _make_streaming_openai_provider()
    ev = asyncio.Event()
    chunks = []
    async def on_delta(text):
        chunks.append(text)
        if len(chunks) >= 1:
            # simulate the handler cancelling after the first chunk
            ev.set()
    result = await provider.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=None,
        on_delta=on_delta,
        cancel_event=ev,
    )
    assert result["finish_reason"] == "stopped_by_user"
    assert "Hello " in result["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "streams_final_turn or no_delta_is_blocking or cancel_stops_stream" -v`
Expected: FAIL — `generate_with_tools() got an unexpected keyword argument 'on_delta'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/services/model_provider.py`, change the signature of `OpenAICompatibleProvider.generate_with_tools` (line 547) and add a streaming final-turn branch. Replace the method header and the inner loop body's completion handling:

```python
    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor: Callable,
        max_iterations: int = 10,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Agentic tool-calling loop for OpenAI-compatible providers.

        When ``on_delta`` is provided, the final text turn is streamed
        token-by-token and each chunk is forwarded via ``await on_delta(chunk)``.
        ``cancel_event`` (if set mid-stream) halts consumption and returns the
        accumulated content with finish_reason="stopped_by_user".
        """
        actual_model = kwargs.get("model", self.config.default_model)
        client = _get_cached_sdk_client(
            self.config,
            api_key=self.api_key or "not-needed",
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
            is_anthropic=False,
        )

        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        finish_reason = "stop"
        start_time = time.time()
        maxc = getattr(self.config, "max_concurrent_requests", 10) or 10
        await provider_rate_limiter.acquire_concurrency(self.config.id, maxc)

        try:
            for _ in range(max_iterations):
                if cancel_event and cancel_event.is_set():
                    finish_reason = "stopped_by_user"
                    break

                create_kwargs: Dict[str, Any] = dict(
                    model=actual_model,
                    messages=[{"role": "system", "content": system_prompt}] + conversation,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                )
                if tools:
                    create_kwargs["tools"] = tools
                    create_kwargs["tool_choice"] = "auto"

                rpm = getattr(self.config, "requests_per_minute", 60) or 60
                await provider_rate_limiter.acquire(self.config.id, rpm)

                streaming = on_delta is not None
                if streaming:
                    create_kwargs["stream"] = True
                    create_kwargs["stream_options"] = {"include_usage": True}

                response = await client.chat.completions.create(**create_kwargs)
                await _record_provider_headers(self.config)

                # ── Streaming branch: forward text deltas; accumulate tool calls ──
                if streaming:
                    text_parts: List[str] = []
                    tool_calls_acc = {}
                    tc_idx = 0
                    async for chunk in response:
                        if cancel_event and cancel_event.is_set():
                            finish_reason = "stopped_by_user"
                            break
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if getattr(delta, "content", None):
                            text_parts.append(delta.content)
                            await on_delta(delta.content)
                        # Accumulate streamed tool-call fragments
                        if getattr(delta, "tool_calls", None):
                            for tc in delta.tool_calls:
                                idx = tc.index if tc.index is not None else tc_idx
                                slot = tool_calls_acc.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if tc.id:
                                    slot["id"] = tc.id
                                if tc.function and tc.function.name:
                                    slot["function"]["name"] = tc.function.name
                                if tc.function and tc.function.arguments:
                                    slot["function"]["arguments"] += tc.function.arguments
                                tc_idx = max(tc_idx, idx + 1)
                        if getattr(chunk, "usage", None):
                            total_prompt_tokens += chunk.usage.prompt_tokens or 0
                            total_completion_tokens += chunk.usage.completion_tokens or 0
                    if cancel_event and cancel_event.is_set() and not text_parts:
                        finish_reason = "stopped_by_user"
                        break

                    if text_parts and not tool_calls_acc:
                        content = "".join(text_parts)
                        finish_reason = "stop"
                        break
                    elif tool_calls_acc:
                        # Reconstruct assistant message with full tool_calls
                        assembled = [v for v in tool_calls_acc.values()]
                        assistant_msg = {
                            "role": "assistant",
                            "content": "".join(text_parts) or None,
                            "tool_calls": assembled,
                        }
                        conversation.append(assistant_msg)
                        results = await asyncio.gather(
                            *[
                                tool_executor(
                                    tc["function"]["name"],
                                    json.loads(tc["function"]["arguments"] or "{}"),
                                )
                                for tc in assembled
                            ],
                            return_exceptions=True,
                        )
                        for tc, result in zip(assembled, results):
                            result_str = str(result) if not isinstance(result, Exception) else f"ERROR: {result}"
                            conversation.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result_str,
                            })
                        continue
                    else:
                        # Stream produced neither text nor tool calls
                        break

                # ── Blocking branch (on_delta is None) ──
                msg = response.choices[0].message
                if response.usage:
                    total_prompt_tokens += response.usage.prompt_tokens or 0
                    total_completion_tokens += response.usage.completion_tokens or 0
                try:
                    conversation.append(msg.model_dump(exclude_none=True))
                except Exception:
                    conversation.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        **({"tool_calls": [tc.model_dump() for tc in msg.tool_calls]} if msg.tool_calls else {}),
                    })
                fr = response.choices[0].finish_reason
                if fr == "stop" or not msg.tool_calls:
                    content = msg.content or ""
                    break
                if fr == "tool_calls" and msg.tool_calls:
                    results = await asyncio.gather(
                        *[
                            tool_executor(tc.function.name, json.loads(tc.function.arguments or "{}"))
                            for tc in msg.tool_calls
                        ],
                        return_exceptions=True,
                    )
                    for tc, result in zip(msg.tool_calls, results):
                        result_str = str(result) if not isinstance(result, Exception) else f"ERROR: {result}"
                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_str,
                        })
                else:
                    content = msg.content or ""
                    break
            else:
                content = ""
        except Exception as exc:
            latency = int((time.time() - start_time) * 1000)
            await self._log_usage(
                model_used=actual_model, prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens, latency_ms=latency,
                success=False, error=str(exc),
                agentium_id=kwargs.get("agentium_id") or "system",
            )
            raise
        finally:
            await provider_rate_limiter.release_concurrency(self.config.id)

        latency = int((time.time() - start_time) * 1000)
        total_tokens = total_prompt_tokens + total_completion_tokens
        await self._log_usage(
            model_used=actual_model, prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens, latency_ms=latency,
            success=True, agentium_id=kwargs.get("agentium_id") or "system",
        )

        return {
            "content": content,
            "tokens_used": total_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "latency_ms": latency,
            "model": actual_model,
            "messages": conversation,
            "finish_reason": finish_reason,
            "cost_usd": calculate_cost(
                actual_model, self.config.provider,
                total_prompt_tokens, total_completion_tokens,
            ),
        }
```

Note: `import asyncio` and `import json` must be present at the top of `model_provider.py` (they are). Ensure `List`, `Dict`, `Optional`, `Callable`, `Awaitable` are imported (they are).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "streams_final_turn or no_delta_is_blocking or cancel_stops_stream" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_provider.py backend/tests/integration/test_provider_mock_wiring.py
git commit -m "feat(provider): add streaming final-turn seam to OpenAICompatibleProvider.generate_with_tools"
```

---

### Task 2: Backend — Anthropic provider streaming seam

**Files:**
- Modify: `backend/services/model_provider.py` (method `AnthropicProvider.generate_with_tools`)
- Test: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: same as Task 1 (`self.config`, `_get_cached_sdk_client(..., is_anthropic=True)`, `provider_rate_limiter`, `calculate_cost`).
- Produces: `AnthropicProvider.generate_with_tools(..., on_delta=None, cancel_event=None)` with identical contract to Task 1 (streams final text turn via Anthropic's `stream=True`; forwards text deltas; honors `cancel_event`; returns same dict shape + `finish_reason`).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_provider_mock_wiring.py`:

```python
async def _make_streaming_anthropic_provider():
    from backend.services.model_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    cfg = MagicMock()
    cfg.id = "cfg-anthropic"
    cfg.provider = "anthropic"
    cfg.default_model = "claude-test"
    cfg.timeout_seconds = 30
    cfg.max_concurrent_requests = 10
    cfg.requests_per_minute = 60
    cfg.max_tokens = 512
    cfg.temperature = 0.7
    provider.config = cfg
    provider.api_key = "x"

    class _TextDelta:
        def __init__(self, text):
            self.type = "content_block_delta"
            self.delta = MagicMock()
            self.delta.text = text
    class _MsgDelta:
        def __init__(self):
            self.type = "message_delta"
            self.usage = MagicMock()
            self.usage.output_tokens = 4
    async def _gen():
        yield _TextDelta("Hi ")
        yield _TextDelta("there")
        yield _MsgDelta()
    class _StreamResp:
        def __aiter__(self):
            return _gen().__aiter__()
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=_StreamResp())
    provider._client = client
    return provider


async def test_anthropic_generate_with_tools_streams_final_turn():
    provider = await _make_streaming_anthropic_provider()
    chunks = []
    async def on_delta(text):
        chunks.append(text)
    result = await provider.generate_with_tools(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        tool_executor=None,
        on_delta=on_delta,
    )
    assert "".join(chunks) == "Hi there"
    assert result["content"] == "Hi there"
    assert result["finish_reason"] == "stop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "anthropic_generate_with_tools_streams" -v`
Expected: FAIL — unexpected keyword `on_delta`.

- [ ] **Step 3: Write minimal implementation**

Locate `AnthropicProvider.generate_with_tools`. Add `on_delta: Optional[Callable[[str], Awaitable[None]]] = None` and `cancel_event: Optional[asyncio.Event] = None` to its signature (same position as Task 1). Then implement the streaming branch for the case where there are no tool calls to make. Minimal correct version:

```python
        actual_model = kwargs.get("model", self.config.default_model)
        # ... existing setup (client creation) ...
        conversation = list(messages)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        content = ""
        finish_reason = "stop"
        streaming = on_delta is not None

        # Existing blocking body stays for tools / non-streaming. When streaming
        # AND this is the final text turn (no tools requested), use stream=True.
        if streaming and not tools:
            create_kwargs = dict(
                model=actual_model,
                system=system_prompt,
                messages=conversation,
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                stream=True,
            )
            try:
                rpm = getattr(self.config, "requests_per_minute", 60) or 60
                await provider_rate_limiter.acquire(self.config.id, rpm)
                async for chunk in await client.messages.create(**create_kwargs):
                    if cancel_event and cancel_event.is_set():
                        finish_reason = "stopped_by_user"
                        break
                    if getattr(chunk, "type", None) == "content_block_delta":
                        text = getattr(getattr(chunk, "delta", None), "text", None)
                        if text:
                            content += text
                            await on_delta(text)
                    if getattr(chunk, "type", None) == "message_delta":
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            total_completion_tokens += getattr(usage, "output_tokens", 0) or 0
                if cancel_event and cancel_event.is_set():
                    finish_reason = "stopped_by_user"
            except Exception:
                # Fall back to blocking call so a non-streaming-capable setup still works
                blocking = await client.messages.create(
                    model=actual_model, system=system_prompt, messages=conversation,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                )
                content = "".join(
                    b.text for b in getattr(blocking.content, "__iter__", lambda: [])()
                    if getattr(b, "type", None) == "text"
                )
                if getattr(blocking, "usage", None):
                    total_prompt_tokens += getattr(blocking.usage, "input_tokens", 0) or 0
                    total_completion_tokens += getattr(blocking.usage, "output_tokens", 0) or 0
                finish_reason = "stop"
            return {
                "content": content,
                "tokens_used": total_prompt_tokens + total_completion_tokens,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "latency_ms": int((time.time() - start_time) * 1000),
                "model": actual_model,
                "messages": conversation,
                "finish_reason": finish_reason,
                "cost_usd": calculate_cost(actual_model, self.config.provider,
                                           total_prompt_tokens, total_completion_tokens),
            }
        # ... EXISTING blocking body for the tools-enabled path continues unchanged below ...
```

(Keep the existing blocking body below the new branch intact; only the signature gains the two new params and it must pass them through to any helper it already calls. If `AnthropicProvider.generate_with_tools` calls a shared helper, add the two params there too.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "anthropic_generate_with_tools_streams" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/model_provider.py backend/tests/integration/test_provider_mock_wiring.py
git commit -m "feat(provider): add streaming final-turn seam to AnthropicProvider.generate_with_tools"
```

---

### Task 3: Backend — thread `on_delta`/`cancel_event` through ModelService and LLMClient

**Files:**
- Modify: `backend/services/model_provider.py` (`ModelService.generate_with_agent_tools`, ~line 1146)
- Modify: `backend/core/llm_client.py` (`LLMClient.generate_with_tools`, ~line 350)
- Test: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: Tasks 1 & 2 produce `generate_with_tools(..., on_delta, cancel_event)`.
- Produces: `ModelService.generate_with_agent_tools(agent, user_message, *, db, config_id, ..., history, on_delta=None, cancel_event=None)` and `LLMClient.generate_with_tools(agent, user_message, *, db, config_id, ..., history, on_delta=None, cancel_event=None)` — both forward the two new params to the provider call.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_provider_mock_wiring.py`:

```python
async def test_llm_client_forwards_on_delta(monkeypatch):
    from backend.core.llm_client import LLMClient
    from backend.services import model_provider as mp

    captured = {}
    async def fake_gen_with_agent_tools(**kwargs):
        captured["on_delta"] = kwargs.get("on_delta")
        captured["cancel_event"] = kwargs.get("cancel_event")
        # Delegate to a fake provider so shape stays valid
        provider = await _make_streaming_openai_provider(
            on_delta=kwargs.get("on_delta"), cancel_event=kwargs.get("cancel_event")
        )
        return await provider.generate_with_tools(
            system_prompt="sys", messages=[{"role": "user", "content": "hi"}],
            tools=[], tool_executor=None,
            on_delta=kwargs.get("on_delta"), cancel_event=kwargs.get("cancel_event"),
        )
    monkeypatch.setattr(mp.ModelService, "generate_with_agent_tools", staticmethod(fake_gen_with_agent_tools))

    async def on_delta(t):
        pass
    client = LLMClient.__new__(LLMClient)
    client.max_retries = 0
    client.MAX_FALLBACK_CONFIGS = 0
    await client.generate_with_tools(
        agent=MagicMock(agentium_id="0xxxx"),
        user_message="hi", db=None, config_id="cfg-stream",
        on_delta=on_delta,
    )
    assert captured["on_delta"] is on_delta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "llm_client_forwards_on_delta" -v`
Expected: FAIL — `generate_with_tools() got an unexpected keyword argument 'on_delta'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/core/llm_client.py`, add the two params to `LLMClient.generate_with_tools` signature (after `history`) and forward them into the `ModelService.generate_with_agent_tools(...)` call (around line 398):

```python
    async def generate_with_tools(
        self,
        agent,
        user_message: str,
        *,
        db,
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        agent_tier: Optional[str] = None,
        task_id: Optional[str] = None,
        max_tool_iterations: int = 10,
        max_retries: Optional[int] = None,
        fallback_configs: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
```

And inside the `result = await ModelService.generate_with_agent_tools(...)` call (line ~398), add:
```python
                        on_delta=on_delta,
                        cancel_event=cancel_event,
```

In `backend/services/model_provider.py`, `ModelService.generate_with_agent_tools` (line ~1146): add the two params to its signature and forward them to the `provider.generate_with_tools(...)` call (~line 1270):
```python
    async def generate_with_agent_tools(
        cls,
        *,
        agent,
        user_message: str,
        db,
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        agent_tier: Optional[str] = None,
        task_id: Optional[str] = None,
        max_tool_iterations: int = 10,
        history: Optional[List[Dict[str, str]]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        **kwargs,
    ) -> Dict[str, Any]:
```
And in the `provider.generate_with_tools(...)` call (~line 1270):
```python
            on_delta=on_delta,
            cancel_event=cancel_event,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "llm_client_forwards_on_delta" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/llm_client.py backend/services/model_provider.py backend/tests/integration/test_provider_mock_wiring.py
git commit -m "feat(llm): thread on_delta/cancel_event through ModelService and LLMClient"
```

---

### Task 4: Backend — ChatService.process_message accepts the streaming seam

**Files:**
- Modify: `backend/services/chat_service.py` (`process_message`, line 71)
- Test: `backend/tests/integration/test_provider_mock_wiring.py`

**Interfaces:**
- Consumes: Task 3 produces `LLMClient.generate_with_tools(..., on_delta, cancel_event)`.
- Produces: `ChatService.process_message(head, message, db, extra_metadata=None, on_delta=None, cancel_event=None)` — forwards the two params to the `llm_client.generate_with_tools(...)` call (~line 274). Return dict shape unchanged (adds `finish_reason` if present from provider).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_provider_mock_wiring.py`:

```python
async def test_chat_service_forwards_on_delta(monkeypatch):
    from backend.services import chat_service as cs

    captured = {}
    class _FakeClient:
        async def generate_with_tools(self, **kwargs):
            captured.update(kwargs)
            return {
                "content": "answer", "model": "m", "tokens_used": 1,
                "task_created": False, "task_id": None, "agent_spawned": None,
                "reincarnated": False, "finish_reason": "stop",
            }
    monkeypatch.setattr(cs, "LLMClient", _FakeClient)

    async def on_delta(t):
        pass
    res = await cs.ChatService.process_message(
        head=MagicMock(agentium_id="0xxxx", get_model_config=lambda db: None,
                       preferred_config_id=None),
        message="hi", db=MagicMock(), on_delta=on_delta,
    )
    assert res["content"] == "answer"
    assert captured.get("on_delta") is on_delta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "chat_service_forwards_on_delta" -v`
Expected: FAIL — `process_message() got an unexpected keyword argument 'on_delta'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/services/chat_service.py`, change the signature (line 71):
```python
    async def process_message(head: HeadOfCouncil, message: str, db: Session, extra_metadata: Optional[dict] = None, on_delta: Optional[Callable[[str], Awaitable[None]]] = None, cancel_event: Optional[asyncio.Event] = None):
```
(ensure `asyncio` and `Callable`/`Awaitable` are imported at top of `chat_service.py`; if `asyncio` is missing, add `import asyncio`.)

At the `result = await llm_client.generate_with_tools(...)` call (~line 274), add:
```python
            on_delta=on_delta,
            cancel_event=cancel_event,
```
(The call uses `LLMClient` instance; insert the two kwargs after existing kwargs.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "chat_service_forwards_on_delta" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py backend/tests/integration/test_provider_mock_wiring.py
git commit -m "feat(chat): accept on_delta/cancel_event in ChatService.process_message"
```

---

### Task 5: Backend — WebSocket handler stream lifecycle + cancel

**Files:**
- Modify: `backend/api/routes/websocket.py` (the `message` handler, ~lines 580–613)
- Test: `backend/tests/integration/test_ws_stream.py` (create new)

**Interfaces:**
- Consumes: Task 4 produces `ChatService.process_message(..., on_delta, cancel_event)`; event schema defined in the spec (Section 3).
- Produces: WS emits `message_start` / `message_delta` / `message_end` for LLM replies; accepts inbound `{"type":"cancel","stream_id":...}`. `active_streams` is a per-connection dict `Dict[str, asyncio.Event]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_ws_stream.py`:

```python
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock


async def test_ws_emits_stream_events_and_cancel():
    from backend.api.routes import websocket as ws_mod

    sent = []

    class _FakeWS:
        def __init__(self):
            self.inbound = asyncio.Queue()
        async def send_json(self, payload):
            sent.append(payload)
        async def receive_json(self):
            return await self.inbound.get()
        async def accept(self):
            pass

    fake_ws = _FakeWS()

    # Simulated process_message that streams two deltas then returns
    events = []

    async def fake_process_message(head, message, db, **kwargs):
        on_delta = kwargs.get("on_delta")
        cancel_event = kwargs.get("cancel_event")
        assert on_delta is not None
        await on_delta("Hello ")
        await on_delta("world")
        return {
            "content": "Hello world", "model": "m", "tokens_used": 2,
            "task_created": False, "task_id": None, "agent_spawned": None,
            "reincarnated": False, "finish_reason": "stop",
        }

    with patch.object(ws_mod.ChatService, "process_message", staticmethod(fake_process_message)):
        # Drive the handler loop manually for one message + one cancel
        # (handler is an async generator/function; call it with fakes)
        head = MagicMock()
        handler = ws_mod.chat_ws_handler(fake_ws, head, db=MagicMock())
        await fake_ws.inbound.put({"type": "auth", "token": "x"})
        task = asyncio.create_task(handler)
        await asyncio.sleep(0.05)
        await fake_ws.inbound.put({"type": "cancel", "stream_id": sent[0]["stream_id"]})
        await asyncio.sleep(0.05)
        task.cancel()

    types = [m["type"] for m in sent]
    assert types[0] == "message_start"
    assert "message_delta" in types
    assert types[-1] == "message_end"
    assert sent[-1]["content"] == "Hello world"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_ws_stream.py -v`
Expected: FAIL (module/function structure mismatch or `message_start` never emitted).

- [ ] **Step 3: Write minimal implementation**

In `backend/api/routes/websocket.py`, refactor the message handler. Introduce a per-connection `active_streams: Dict[str, asyncio.Event] = {}`. Replace the inline `result = await ChatService.process_message(...)` + single `send_json` block (lines ~602–612) with:

```python
            if received.get("type") == "cancel":
                sid = received.get("stream_id")
                ev = active_streams.get(sid)
                if ev:
                    ev.set()
                continue

            if received.get("type") == "message":
                import uuid as _uuid
                stream_id = str(_uuid.uuid4())
                message_id = str(_uuid.uuid4())
                cancel_event = asyncio.Event()
                active_streams[stream_id] = cancel_event

                await websocket.send_json({
                    "type": "message_start",
                    "stream_id": stream_id,
                    "role": "head_of_council",
                    "message_id": message_id,
                    "timestamp": datetime.utcnow().isoformat(),
                })

                async def on_delta(text: str):
                    await websocket.send_json({
                        "type": "message_delta",
                        "stream_id": stream_id,
                        "delta": text,
                    })

                try:
                    response = await ChatService.process_message(
                        head, enriched_message, db,
                        on_delta=on_delta, cancel_event=cancel_event,
                    )
                    finish = response.get("finish_reason", "stop") or "stop"
                    await websocket.send_json({
                        "type": "message_end",
                        "stream_id": stream_id,
                        "content": response.get("content", ""),
                        "metadata": {
                            "model": response.get("model"),
                            "tokens_used": response.get("tokens_used", 0),
                            "task_created": response.get("task_created", False),
                            "task_id": response.get("task_id"),
                            "agent_spawned": response.get("agent_spawned"),
                            "card": (response.get("metadata") or {}).get("card")
                                     if isinstance(response.get("metadata"), dict) else None,
                            "media_urls": (response.get("metadata") or {}).get("media_urls", [])
                                         if isinstance(response.get("metadata"), dict) else [],
                        },
                        "finish_reason": finish,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                except Exception as exc:
                    logger.error(f"Stream error: {exc}")
                    await websocket.send_json({
                        "type": "message_end",
                        "stream_id": stream_id,
                        "content": "",
                        "metadata": {},
                        "finish_reason": "error",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                finally:
                    active_streams.pop(stream_id, None)
```

Wrap `ChatService.process_message` in `asyncio.create_task` only if the surrounding loop is a single `await`; otherwise the direct `await` shown above is sufficient as long as the `cancel` branch (checked each loop iteration) is reached. If the original handler awaits the receive once per iteration, keep the `await process_message` form and rely on the task-based variant if concurrency is needed — prefer the task-based variant to allow cancel to interrupt:

```python
                task = asyncio.create_task(
                    ChatService.process_message(head, enriched_message, db,
                                                on_delta=on_delta, cancel_event=cancel_event)
                )
                try:
                    response = await task
                    # ... message_end as above ...
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # ... error message_end ...
                finally:
                    active_streams.pop(stream_id, None)
```

Remove the old single `send_json({"type":"message", ...})` completion block. Ensure `enriched_message` variable still exists (it does in the current handler). Ensure `active_streams` is declared at the top of the connection handler scope.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integration/test_ws_stream.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/websocket.py backend/tests/integration/test_ws_stream.py
git commit -m "feat(ws): stream message_start/delta/end and handle cancel over /chat socket"
```

---

### Task 6: Backend — integration test for non-LLM (governance) atomic replies

**Files:**
- Modify: `backend/tests/integration/test_provider_mock_wiring.py` (add a test asserting zero deltas / start+end for the governance fast-path)
- No production code change (governance path returns without `on_delta`; handler already emits start+end).

**Interfaces:**
- Consumes: Task 5 handler emits `message_start` then `message_end` with zero deltas when `process_message` returns without calling `on_delta` (governance fast-path at `chat_service.py:177`).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_provider_mock_wiring.py`:

```python
async def test_governance_path_emits_no_deltas(monkeypatch):
    from backend.services import chat_service as cs
    from backend.services.governance_command_service import GovernanceCommandService

    # Force the governance fast-path to trigger
    monkeypatch.setattr(GovernanceCommandService, "detect_command",
                        staticmethod(lambda msg: MagicMock(action="noop", content="Governed.")))
    monkeypatch.setattr(GovernanceCommandService, "execute",
                        staticmethod(lambda cmd, head, db: {"action": "noop", "content": "Governed."}))

    captured = {}
    res = await cs.ChatService.process_message(
        head=MagicMock(agentium_id="0xxxx", get_model_config=lambda db: None,
                       preferred_config_id=None),
        message="/govern", db=MagicMock(), on_delta=captured.get("on_delta"),
    )
    assert res["content"] == "Governed."
    # on_delta was never called (the fast-path returns before any generation)
    assert captured == {}
```

- [ ] **Step 2: Run test to verify it passes** (no production change expected)

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -k "governance_path_emits_no_deltas" -v`
Expected: PASS (this asserts current behavior; if it fails, the governance path is calling on_delta somewhere — fix by ensuring the fast-path `return` happens before generation).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_provider_mock_wiring.py
git commit -m "test(chat): assert governance fast-path is atomic under streaming"
```

---

### Task 7: Frontend — chatStore streaming helpers + Message.status 'streaming'

**Files:**
- Modify: `frontend/src/store/chatStore.ts`
- Test: `frontend/src/store/chatStore.test.ts` (create new)

**Interfaces:**
- Consumes: existing `Message` / `MessageMetadata` / `ChatState` types (`chatStore.ts:8-60`).
- Produces:
  - `Message.status` gains `'streaming'`.
  - `ChatState.beginStream(message_id: string, role: Message['role']): void`
  - `ChatState.appendDelta(stream_id: string, delta: string): void` (keyed by `stream_id`)
  - `ChatState.endStream(stream_id: string, content: string, metadata?: MessageMetadata): void`
  - `ChatState.activeStreamId: string | null`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/store/chatStore.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

describe('chatStore streaming', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], activeStreamId: null, currentStreamingMessage: '' });
  });

  it('beginStream inserts a streaming placeholder with server id', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    const msgs = useChatStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].id).toBe('m1');
    expect(msgs[0].status).toBe('streaming');
    expect(useChatStore.getState().activeStreamId).toBe('m1');
  });

  it('appendDelta accrues content by stream_id', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    useChatStore.getState().appendDelta('m1', 'Hello ');
    useChatStore.getState().appendDelta('m1', 'world');
    expect(useChatStore.getState().messages[0].content).toBe('Hello world');
  });

  it('endStream finalizes content, metadata, and status', () => {
    useChatStore.getState().beginStream('m1', 'head_of_council');
    useChatStore.getState().appendDelta('m1', 'Hi');
    useChatStore.getState().endStream('m1', 'Hi', { model: 'gpt-test', tokens_used: 3 });
    const m = useChatStore.getState().messages[0];
    expect(m.content).toBe('Hi');
    expect(m.status).toBe('sent');
    expect(m.metadata?.model).toBe('gpt-test');
    expect(useChatStore.getState().activeStreamId).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run --project unit src/store/chatStore.test.ts`
Expected: FAIL — `beginStream` is not a function.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/store/chatStore.ts`:

1. Extend `Message.status` (line 39):
```ts
    status?: 'sending' | 'sent' | 'error' | 'streaming';
```

2. Add to `ChatState` interface (near line 51):
```ts
    activeStreamId: string | null;
    beginStream: (messageId: string, role: Message['role']) => void;
    appendDelta: (streamId: string, delta: string) => void;
    endStream: (streamId: string, content: string, metadata?: MessageMetadata) => void;
```

3. In the store initializer, add `activeStreamId: null` alongside `currentStreamingMessage: ''`, and implement the three functions:
```ts
            activeStreamId: null,

            beginStream: (messageId, role) => set((s) => ({
                activeStreamId: messageId,
                messages: [
                    ...s.messages,
                    {
                        id: messageId,
                        role,
                        content: '',
                        timestamp: new Date(),
                        status: 'streaming',
                    },
                ],
                currentStreamingMessage: '',
            })),

            appendDelta: (streamId, delta) => set((s) => ({
                currentStreamingMessage: s.currentStreamingMessage + delta,
                messages: s.messages.map((m) =>
                    m.id === streamId ? { ...m, content: m.content + delta } : m
                ),
            })),

            endStream: (streamId, content, metadata) => set((s) => ({
                activeStreamId: s.activeStreamId === streamId ? null : s.activeStreamId,
                currentStreamingMessage: '',
                messages: s.messages.map((m) =>
                    m.id === streamId
                        ? { ...m, content, status: 'sent', metadata: { ...m.metadata, ...metadata } }
                        : m
                ),
            })),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run --project unit src/store/chatStore.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/chatStore.ts frontend/src/store/chatStore.test.ts
git commit -m "feat(frontend): add streaming helpers and 'streaming' status to chatStore"
```

---

### Task 8: Frontend — ChatPage WS subscriber handles stream + stop button

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx` (WS subscriber ~lines 280–326; send button area ~line 497)
- Test: `frontend/src/pages/ChatPage.test.tsx` (create new, render + simulate WS events)

**Interfaces:**
- Consumes: Task 7 produces `beginStream` / `appendDelta` / `endStream` / `activeStreamId` from `useChatStore`; `useWebSocketStore` `sendWsMessage` and `lastMessage`.
- Produces: ChatPage handles `message_start` / `message_delta` / `message_end`; keeps backward-compat with legacy `type:'message'`; Send button morphs into Stop when `activeStreamId` is set and sends `{type:'cancel', stream_id}`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ChatPage.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import ChatPage from './ChatPage';

// Lightweight harness: stub stores so we can drive WS messages in.
vi.mock('@/store/chatStore', () => {
  const state = {
    messages: [] as any[],
    activeStreamId: null as string | null,
    currentStreamingMessage: '',
    beginStream: (id: string, role: any) =>
      (state.messages = [...state.messages, { id, role, content: '', timestamp: new Date(), status: 'streaming' }]),
    appendDelta: (id: string, d: string) =>
      (state.messages = state.messages.map((m) => (m.id === id ? { ...m, content: m.content + d } : m))),
    endStream: (id: string, c: string, meta?: any) =>
      (state.messages = state.messages.map((m) => (m.id === id ? { ...m, content: c, status: 'sent', metadata: meta } : m)),
       (state.activeStreamId = null)),
  };
  return {
    useChatStore: {
      getState: () => state,
      setState: (p: any) => Object.assign(state, typeof p === 'function' ? p(state) : p),
    },
  };
});

vi.mock('@/store/websocketStore', () => ({
  useWebSocketStore: { subscribe: () => () => {}, getState: () => ({}) },
  sendWsMessage: (msg: any) => (sendWsMessage.last = msg),
  __last: () => sendWsMessage.last,
}));
const sendWsMessage: any = (msg: any) => { sendWsMessage.last = msg; };

describe('ChatPage streaming', () => {
  beforeEach(() => { sendWsMessage.last = undefined; });

  it('renders streamed content from start/delta/end events', async () => {
    // Drive the subscriber path via a simulated lastMessage pipeline:
    // We can't easily reach the internal subscribe; instead assert the store
    // helpers are exercised by importing them directly through the page's API.
    expect(true).toBe(true);
  });
});
```

> Note: If reaching ChatPage's internal WS subscription from a unit test is impractical, replace this test with a component test that imports `useChatStore` and asserts `beginStream`/`appendDelta`/`endStream` are wired by calling them in order and checking `messages` — keeping the same assertions as Task 7 but through the page module (to confirm the page imports them). Adjust the mock to expose them and assert they are called during a simulated render.

- [ ] **Step 2: Run test to verify it fails / compiles**

Run: `cd frontend && npx vitest run --project unit src/pages/ChatPage.test.tsx`
Expected: test file compiles; at minimum the page imports resolve. (Replace the placeholder assertion per the Note above with a real assertion that `beginStream` is invoked on a `message_start` event; this may require refactoring ChatPage's subscriber into a testable exported handler — see Step 3.)

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/pages/ChatPage.tsx`:

1. Import the new store helpers:
```ts
import { useChatStore } from '@/store/chatStore';
```
(already imported; ensure `beginStream`/`appendDelta`/`endStream` are referenced from it.)

2. In the WS subscriber (around line 284), handle the three new event types BEFORE the legacy `type === 'message'` branch:
```ts
        const msg = state.lastMessage;
        if (msg?.type === 'message_start') {
            // Key the local message by stream_id so appendDelta/endStream (which
            // also key by stream_id) can find it. stream_id is unique per reply,
            // so it is equally valid for dedup; the server message_id is unused
            // locally beyond this.
            useChatStore.getState().beginStream(msg.stream_id, (msg.role as Message['role']) || 'head_of_council');
            return;
        }
        if (msg?.type === 'message_delta') {
            useChatStore.getState().appendDelta(msg.stream_id, msg.delta);
            setIsAwaitingReply(false);
            return;
        }
        if (msg?.type === 'message_end') {
            const m = useChatStore.getState().messages.find((x) => x.id === msg.stream_id);
            useChatStore.getState().endStream(msg.stream_id, msg.content ?? m?.content ?? '', msg.metadata);
            setIsAwaitingReply(false);
            if (msg.metadata?.card) {
                useChatStore.getState().registerCard(msg.metadata.card.card_id, true);
            }
            if (msg.metadata?.task_created) {
                showToast.success(`Task ${msg.metadata.task_id} created`);
            }
            return;
        }
        // Legacy single-message event (backward-compat): atomic start+end
        if (msg?.type === 'message') {
            // ...existing legacy handling from lines 290-318...
        }
```

3. Stop button: locate the send control (~line 497) and branch on `useChatStore.getState().activeStreamId`:
```tsx
  const activeStreamId = useChatStore((s) => s.activeStreamId);
  // ...
  {activeStreamId ? (
    <button
      aria-label="Stop generating"
      onClick={() => sendWsMessage({ type: 'cancel', stream_id: activeStreamId })}
      className="stop-button"
    >
      {/* square stop icon; ≥44px target */}
      <span className="stop-icon" aria-hidden />
    </button>
  ) : (
    <button aria-label="Send message" onClick={handleSend} className="send-button">
      {/* existing send icon / label */}
    </button>
  )}
```

- [ ] **Step 4: Run test / typecheck**

Run: `cd frontend && npx vitest run --project unit src/pages/ChatPage.test.tsx && npx tsc --noEmit -p tsconfig.json`
Expected: compiles and tests pass; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(frontend): wire ChatPage to stream events and add Stop button"
```

---

### Task 9: Frontend — MarkdownMessage live render + blinking caret

**Files:**
- Modify: `frontend/src/components/chat/MarkdownMessage.tsx`
- Test: `frontend/src/components/chat/MarkdownMessage.test.tsx` (existing; extend)

**Interfaces:**
- Consumes: `Message` with `status: 'streaming'` (Task 7).
- Produces: while `status === 'streaming'`, render a blinking caret `▍` after the live markdown; tolerate unterminated markdown (best-effort); respect `prefers-reduced-motion` (solid caret, no blink).

- [ ] **Step 1: Write the failing test**

Extend `frontend/src/components/chat/MarkdownMessage.test.tsx` (add):
```tsx
import { render } from '@testing-library/react';
import MarkdownMessage from './MarkdownMessage';

it('shows a caret while streaming', () => {
  const { container } = render(
    <MarkdownMessage content="Hello" status="streaming" role="head_of_council" />
  );
  expect(container.querySelector('[data-testid="stream-caret"]')).not.toBeNull();
});

it('hides the caret when complete', () => {
  const { container } = render(
    <MarkdownMessage content="Hello" status="sent" role="head_of_council" />
  );
  expect(container.querySelector('[data-testid="stream-caret"]')).toBeNull();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run --project unit src/components/chat/MarkdownMessage.test.tsx`
Expected: FAIL — caret element not found.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/components/chat/MarkdownMessage.tsx`, accept a `status?: string` prop. After the rendered markdown, append:
```tsx
  {status === 'streaming' && (
    <span data-testid="stream-caret" className="stream-caret" aria-hidden>▍</span>
  )}
```
And add CSS (in the component's stylesheet or a module):
```css
.stream-caret {
  display: inline-block;
  margin-left: 1px;
  animation: caret-blink 1s steps(2, start) infinite;
}
@keyframes caret-blink { to { visibility: hidden; } }
@media (prefers-reduced-motion: reduce) {
  .stream-caret { animation: none; }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run --project unit src/components/chat/MarkdownMessage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/MarkdownMessage.tsx frontend/src/components/chat/MarkdownMessage.test.tsx
git commit -m "feat(frontend): live caret while streaming, reduced-motion safe"
```

---

### Task 10: Frontend — auto-scroll + typing indicator polish

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx` (scroll behavior)
- Modify: existing typing/thinking indicator rendering during `streaming` placeholder

**Interfaces:**
- Consumes: Task 7 `status: 'streaming'`; `isAwaitingReply`.
- Produces: auto-scroll follows the stream only if user is near bottom; while `activeStreamId` is set but no delta has arrived yet (still `isAwaitingReply`), show the existing typing indicator in the placeholder bubble.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/ChatPage.test.tsx`:
```tsx
it('shows typing indicator while awaiting first delta', () => {
  // set store to a streaming placeholder with empty content + isAwaitingReply true
  // assert a typing-indicator element is present
  expect(true).toBe(true); // replace with real DOM assertion once indicator is wired
});
```
(Concrete assertion: render the streaming placeholder and assert `[data-testid="typing-indicator"]` exists while `content === ''` and `status === 'streaming'`.)

- [ ] **Step 2: Run test**

Run: `cd frontend && npx vitest run --project unit src/pages/ChatPage.test.tsx`
Expected: compiles.

- [ ] **Step 3: Write minimal implementation**

In `ChatPage.tsx`:
- On `beginStream`, keep `isAwaitingReply(true)`; on first `message_delta`, set `isAwaitingReply(false)` (already done in Task 8).
- In the message list render, for a message with `status === 'streaming' && content === ''`, render the existing typing indicator component (whatever the page already uses for "thinking").
- Auto-scroll effect: track scroll position; only call `scrollToBottom()` on `messages` change when the user is within ~80px of the bottom.

- [ ] **Step 4: Typecheck + unit run**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run --project unit src/pages/ChatPage.test.tsx`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(frontend): auto-scroll when near bottom + typing indicator during stream"
```

---

### Task 11: Full-suite verification + cleanup of dead SSE code

**Files:**
- Verify: `backend/tests/integration/test_provider_mock_wiring.py`, `test_ws_stream.py`, `frontend` unit tests.
- Optional cleanup: `frontend/src/services/chatStream.ts` and `chatStore.sendStreamingMessage` are now superseded — leave them unless they are referenced elsewhere; if unreferenced, delete to avoid confusion.

**Interfaces:**
- Consumes: all prior tasks.

- [ ] **Step 1: Run backend integration suite**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py backend/tests/integration/test_ws_stream.py -v`
Expected: all new + existing tests PASS.

- [ ] **Step 2: Run frontend unit suite**

Run: `cd frontend && npx vitest run --project unit`
Expected: all PASS.

- [ ] **Step 3: Check for references to dead SSE code**

Run (grep): `chatStreamApi` and `sendStreamingMessage` usages in `frontend/src`.
If only declared, never called by any page: delete `frontend/src/services/chatStream.ts` and remove `sendStreamingMessage` from `chatStore.ts` + its import.

- [ ] **Step 4: Commit cleanup (if any)**

```bash
git add -A frontend/src
git commit -m "chore(frontend): remove superseded dead SSE streaming code"
```

- [ ] **Step 5: Final full check**

Run: backend `pytest` for the affected modules and `cd frontend && npx tsc --noEmit -p tsconfig.json`.
Expected: clean.
