# Chat Typing Indicator & Tool Counter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the shimmer-bar typing indicator with animated bouncing dots and add a real-time running tool-use counter (+1 → +2 → +3) inside the chat bubble.

**Architecture:** A new `on_tool_start` async callback threads through the generation pipeline (websocket → chat_service → llm_client → model_provider), firing before tool execution. The websocket handler sends `tool_progress` WS events. The frontend tracks a running count and displays it inline after the three dots.

**Tech Stack:** Python/FastAPI (backend), TypeScript/React/Zustand (frontend), Vitest (frontend tests), Pytest (backend tests)

## Global Constraints

- All existing tests must pass without modification
- `on_tool_start` defaults to `None` everywhere — existing callers unaffected
- No chatStore (Zustand) changes — `toolCount` is local ChatPage state
- Reduced-motion fallback uses opacity pulse, not translateY
- Tool names, duration, per-tool status are out of scope

---

### Task 1: Backend — Add `on_tool_start` callback to both provider `generate_with_tools()` methods

**Files:**
- Modify: `backend/services/model_provider.py` — `OpenAICompatibleProvider.generate_with_tools()` signature + 2 injection points
- Modify: `backend/services/model_provider.py` — `AnthropicProvider.generate_with_tools()` signature + 1 injection point
- Modify: `backend/services/model_provider.py` — `ModelService.generate_with_agent_tools()` signature + pass-through

**Interfaces:**
- Consumes: `on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]]` — receives list of tool calls and cumulative count
- Produces: `result["tool_count"]` key in the returned dict

- [ ] **Step 1: Add `on_tool_start` param to `OpenAICompatibleProvider.generate_with_tools()`**

```python
# line 826: add on_tool_start parameter
async def generate_with_tools(
    self,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_executor: Callable,
    max_iterations: int = 10,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
    **kwargs,
) -> Dict[str, Any]:
```

- [ ] **Step 2: Add cumulative counter + inject `on_tool_start` at both OpenAI tool-call points**

Add a counter variable before the loop:

```python
# line 878, after loop_finish_reason assignment
_tool_call_counter = 0
```

**Blocking path (~line 977)** — right before `asyncio.gather`:

```python
                    if finish_reason == "tool_calls" and norm_tool_calls:
                        _tool_call_counter += len(norm_tool_calls)
                        if on_tool_start is not None:
                            await on_tool_start(norm_tool_calls, _tool_call_counter)
                        # Execute ALL tool calls in this response in parallel
                        results = await asyncio.gather(
```

**Streaming path (~line 1042)** — right before `asyncio.gather`:

```python
                    if finish_reason == "tool_calls" and msg_tool_calls:
                        _tool_call_counter += len(msg_tool_calls)
                        if on_tool_start is not None:
                            await on_tool_start(msg_tool_calls, _tool_call_counter)
                        # Execute ALL tool calls in this response in parallel,
                        # mirroring the blocking branch exactly.
                        results = await asyncio.gather(
```

- [ ] **Step 3: Add `on_tool_start` param to `AnthropicProvider.generate_with_tools()`**

```python
# line 1249: add on_tool_start parameter
async def generate_with_tools(
    self,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_executor: Callable,
    max_iterations: int = 10,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
    **kwargs,
) -> Dict[str, Any]:
```

- [ ] **Step 4: Add cumulative counter + inject at Anthropic tool-call point (~line 1415)**

```python
# line 1299, after loop_finish_reason assignment
_tool_call_counter = 0
```

```python
                if response.stop_reason == "tool_use":
                    tool_blocks = [b for b in response.content if b.type == "tool_use"]
                    _tool_call_counter += len(tool_blocks)
                    if on_tool_start is not None:
                        await on_tool_start(
                            [{"name": b.name, "id": b.id, "input": b.input} for b in tool_blocks],
                            _tool_call_counter,
                        )
                    # Execute all tool calls in parallel
                    results = await asyncio.gather(
```

- [ ] **Step 5: Add `on_tool_start` param to `ModelService.generate_with_agent_tools()` and pass through**

```python
# line 1701: add on_tool_start parameter
on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
cancel_event: Optional[asyncio.Event] = None,
on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
```

```python
# line 1820: pass on_tool_start to provider.generate_with_tools
result = await provider.generate_with_tools(
    system_prompt=system_prompt,
    messages=messages,
    tools=tools,
    tool_executor=tool_executor,
    max_iterations=max_tool_iterations,
    agentium_id=agent_id,
    on_delta=on_delta,
    on_tool_start=on_tool_start,
    cancel_event=run_event,
```

- [ ] **Step 6: Run existing tests to verify nothing broke**

```bash
pytest backend/tests/unit/test_provider_system_message.py backend/tests/unit/test_agent_loop_thinking.py -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/services/model_provider.py
git commit -m "feat(backend): add on_tool_start callback to provider generation loop"
```

---

### Task 2: Backend — Thread `on_tool_start` through LLMClient and chat_service

**Files:**
- Modify: `backend/core/llm_client.py` — `generate_with_tools()` signature + pass-through
- Modify: `backend/services/chat_service.py` — `process_message()` call to `llm_client.generate_with_tools()`

**Interfaces:**
- Consumes: `on_tool_start` from `chat_service.py` (passed in by websocket handler)
- Produces: threaded through to `ModelService.generate_with_agent_tools()`

- [ ] **Step 1: Add `on_tool_start` param to `LLMClient.generate_with_tools()` and pass through**

```python
# line 364: add parameter
on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
cancel_event: Optional[asyncio.Event] = None,
on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
```

```python
# line 410: pass to ModelService.generate_with_agent_tools
history=history,
on_delta=on_delta,
on_tool_start=on_tool_start,
cancel_event=cancel_event,
```

- [ ] **Step 2: Pass `on_tool_start` in `chat_service.py`**

```python
# line 426: add on_tool_start=on_tool_start to the call
on_delta=on_delta,
on_tool_start=on_tool_start,
cancel_event=cancel_event,
```

Also update the function signature of `process_message()` to accept `on_tool_start`:

```python
async def process_message(
    head,
    message: str,
    db,
    extra_metadata: Optional[dict] = None,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
) -> Dict[str, Any]:
```

- [ ] **Step 3: Run existing tests**

```bash
pytest backend/tests/unit/ -v -x
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add backend/core/llm_client.py backend/services/chat_service.py
git commit -m "feat(backend): thread on_tool_start through LLMClient and chat_service"
```

---

### Task 3: Backend — Define `on_tool_start` callback in websocket.py

**Files:**
- Modify: `backend/api/routes/websocket.py` — define `on_tool_start` closure alongside `on_delta`, pass to `ChatService.process_message()`

**Interfaces:**
- Produces: WS message `{"type": "tool_progress", "stream_id": "...", "tool_count": N}`

- [ ] **Step 1: Add `on_tool_start` closure after the existing `on_delta` definition**

```python
# After line 661 (end of on_delta closure)
_tool_call_counter = 0

async def on_tool_start(
    tool_calls: List[Dict],
    cumulative: int,
    sid: str = stream_id,
) -> None:
    nonlocal _tool_call_counter
    await websocket.send_json({
        "type":        "tool_progress",
        "stream_id":   sid,
        "tool_count":  cumulative,
    })
```

Import `List` and `Dict` at the top of the file if not already imported.

- [ ] **Step 2: Pass `on_tool_start` to `ChatService.process_message()`**

```python
# line 684-686
response = await ChatService.process_message(
    gen_head, msg, gen_db,
    extra_metadata=meta,
    on_delta=on_delta,
    on_tool_start=on_tool_start,
    cancel_event=cevent,
)
```

- [ ] **Step 3: Run integration test**

```bash
pytest backend/tests/integration/test_ws_stream.py -v
```

Expected: pass

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "feat(backend): define on_tool_start WS callback in websocket handler"
```

---

### Task 4: Frontend — Rewrite TypingIndicator component

**Files:**
- Modify: `frontend/src/components/chat/TypingIndicator.tsx`
- Modify: `frontend/src/components/chat/TypingIndicator.module.css`

**Interfaces:**
- Produces: `TypingIndicatorProps { thinking?: boolean; toolCount?: number }`
- Consumes: rendered by ChatPage with `toolCount` from WS events

- [ ] **Step 1: Rewrite `TypingIndicator.tsx`**

```tsx
import styles from './TypingIndicator.module.css';

export function TypingIndicator({ thinking = false, toolCount }: { thinking?: boolean; toolCount?: number }) {
    return (
        <div data-testid="typing-indicator" aria-hidden className={styles.container}>
            <span className={styles.dot} />
            <span className={styles.dot} />
            <span className={styles.dot} />
            {toolCount != null && toolCount > 0 && (
                <span className={styles.toolCount} key={toolCount}>
                    +{toolCount}
                </span>
            )}
        </div>
    );
}
```

- [ ] **Step 2: Rewrite `TypingIndicator.module.css`**

```css
.container {
  display: flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
  animation: dot-bounce 1.4s ease-in-out infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.18s;
}

.dot:nth-child(3) {
  animation-delay: 0.36s;
}

@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
  40% { transform: translateY(-6px); opacity: 1; }
}

.toolCount {
  font-size: 0.75rem;
  font-weight: 500;
  opacity: 0.7;
  margin-left: 2px;
  animation: count-pop 0.2s ease-out;
}

@keyframes count-pop {
  0% { transform: scale(1); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .dot {
    animation: dot-pulse 1.5s ease-in-out infinite;
  }
  .dot:nth-child(2) { animation-delay: 0.3s; }
  .dot:nth-child(3) { animation-delay: 0.6s; }
  .toolCount { animation: none; }
}

@keyframes dot-pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.7; }
}
```

- [ ] **Step 3: Run existing frontend tests to verify no regressions**

```bash
cd frontend && npx vitest run src/components/chat/TypingIndicator.test.tsx src/pages/ChatPage.typing.test.tsx
```

Expected: tests may fail since we changed the structure — that's expected

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/chat/TypingIndicator.tsx frontend/src/components/chat/TypingIndicator.module.css
git commit -m "feat(chat): replace shimmer bars with bouncing dots and add toolCount support"
```

---

### Task 5: Frontend — Update ChatPage WS handler and rendering

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`

**Interfaces:**
- Consumes: `tool_progress` WS events
- Produces: `toolCount` state passed to `TypingIndicator`

- [ ] **Step 1: Add `toolCount` state**

```typescript
// near line 160, alongside isAwaitingReply/isThinking
const [toolCount, setToolCount] = useState(0);
```

- [ ] **Step 2: Handle `tool_progress` in WS subscriber**

Add handler right after `message_start` handling (~line 318):

```typescript
            if (msg.type === 'tool_progress') {
                setToolCount(msg.tool_count as number);
                return;
            }
```

- [ ] **Step 3: Reset `toolCount` on `message_start`, `message_delta`, `message_end`**

```typescript
// In message_start handler:
setToolCount(0);

// Already there in message_delta: setToolCount(0);
// Already there in message_end: setToolCount(0);
```

- [ ] **Step 4: Add `setToolCount(0)` to WS disconnect cleanup effect**

```typescript
// ~line 289
useEffect(() => {
    if (connectionPhase !== 'active') {
        if (activeStreamId) useChatStore.getState().resetStream();
        setIsAwaitingReply(false);
        setToolCount(0);
    }
}, [connectionPhase, activeStreamId]);
```

- [ ] **Step 5: Pass `toolCount` to both TypingIndicator instances**

Inside streaming placeholder bubble (~line 1184):
```tsx
<TypingIndicator thinking={isThinking} toolCount={toolCount} />
```

Standalone bubble (~line 1248):
```tsx
<TypingIndicator thinking={isThinking} toolCount={toolCount} />
```

- [ ] **Step 6: Build to verify compilation**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no type errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(chat): add toolCount state and handle tool_progress WS events"
```

---

### Task 6: Frontend — Update tests

**Files:**
- Modify: `frontend/src/pages/ChatPage.typing.test.tsx`

- [ ] **Step 1: Update TypingIndicator rendering tests**

Replace the existing tests with:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useChatStore } from '@/store/chatStore';
import { TypingIndicator } from '@/components/chat/TypingIndicator';

describe('ChatPage streaming polish', () => {
    beforeEach(() => {
        useChatStore.setState({ messages: [], activeStreamId: null, currentStreamingMessage: '' });
    });

    it('shows typing indicator for an empty streaming placeholder while awaiting', () => {
        useChatStore.getState().beginStream('s1', 'head_of_council');
        const m = useChatStore.getState().messages[0];
        expect(m.status).toBe('streaming');
        expect(m.content).toBe('');
    });

    it('renders three bouncing dots with the expected test id', () => {
        const { container } = render(<TypingIndicator />);
        const indicator = screen.getByTestId('typing-indicator');
        expect(indicator).toBeTruthy();
        expect(indicator.getAttribute('aria-hidden')).toBe('true');
        expect(container.querySelectorAll('span.dot').length).toBe(3);
    });

    it('shows +N count when toolCount > 0', () => {
        const { container } = render(<TypingIndicator toolCount={2} />);
        expect(container.textContent).toContain('+2');
    });

    it('hides +N count when toolCount is 0', () => {
        const { container } = render(<TypingIndicator toolCount={0} />);
        expect(container.textContent).not.toContain('+');
    });

    it('hides +N count when toolCount is undefined', () => {
        const { container } = render(<TypingIndicator />);
        expect(container.textContent).not.toContain('+');
    });

    it('thinking prop is a no-op visually (same dots, no label)', () => {
        const { container: t1 } = render(<TypingIndicator />);
        const { container: t2 } = render(<TypingIndicator thinking />);
        expect(t1.querySelectorAll('span.dot').length).toBe(3);
        expect(t2.querySelectorAll('span.dot').length).toBe(3);
    });
});
```

- [ ] **Step 2: Run tests**

```bash
cd frontend && npx vitest run src/pages/ChatPage.typing.test.tsx
```

Expected: all 7 tests pass

- [ ] **Step 3: Remove the old `thinking=true` test that checked for 'Thinking…' text (replaced by the last test above)**

- [ ] **Step 4: Run full frontend test suite**

```bash
cd frontend && npx vitest run
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.typing.test.tsx
git commit -m "test(chat): update typing indicator tests for bouncing dots and toolCount"
```

---

### Task 7: Backend — Add `on_tool_start` unit tests

**Files:**
- Create: `backend/tests/unit/test_on_tool_start.py`

- [ ] **Step 1: Write unit tests for `on_tool_start` callback**

```python
"""Tests for the on_tool_start callback in the generation pipeline."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List


@pytest.mark.asyncio
async def test_on_tool_start_fires_with_cumulative_count():
    """on_tool_start receives cumulative count across multiple tool-call turns."""
    from backend.services.model_provider import OpenAICompatibleProvider

    on_tool_start = AsyncMock()
    tool_executor = AsyncMock(return_value="ok")

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.config = MagicMock()
    provider.config.id = "test"
    provider.config.provider = "openai"
    provider.config.default_model = "gpt-4o"
    provider.config.max_tokens = 1000
    provider.config.temperature = 0.7
    provider.config.timeout_seconds = 30
    provider.config.max_concurrent_requests = 10
    provider.config.requests_per_minute = 60
    provider.api_key = "sk-test"
    provider.base_url = None

    # Build a mock client that returns two tool-call turns then a text turn
    mock_client = MagicMock()

    async def _fake_create(**kwargs):
        msg = MagicMock()
        if kwargs.get("stream"):

            class FakeChunk:
                def __init__(self):
                    self.choices = []
                    self.usage = None

            async def _iter():
                # First turn: tool calls (2 tools)
                chunk1 = FakeChunk()
                choice1 = MagicMock()
                choice1.delta = MagicMock()
                choice1.delta.content = None
                choice1.delta.tool_calls = [
                    MagicMock(index=0, id="call_1", function=MagicMock(name="search", arguments='{"q":"a"}')),
                    MagicMock(index=1, id="call_2", function=MagicMock(name="read", arguments='{"f":"b"}')),
                ]
                choice1.finish_reason = "tool_calls"
                chunk1.choices = [choice1]
                yield chunk1

                # Second turn: tool calls (1 tool)
                chunk2 = FakeChunk()
                choice2 = MagicMock()
                choice2.delta = MagicMock()
                choice2.delta.content = None
                choice2.delta.tool_calls = [
                    MagicMock(index=0, id="call_3", function=MagicMock(name="write", arguments='{"f":"c"}')),
                ]
                choice2.finish_reason = "tool_calls"
                chunk2.choices = [choice2]
                yield chunk2

                # Third turn: final text
                chunk3 = FakeChunk()
                choice3 = MagicMock()
                choice3.delta = MagicMock()
                choice3.delta.content = "Done"
                choice3.delta.tool_calls = None
                choice3.finish_reason = "stop"
                chunk3.choices = [choice3]
                yield chunk3

            return _iter()
        else:
            # blocking path — not used in this test because we test streaming
            msg.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None), finish_reason="stop")]
            return msg

    mock_client.chat.completions.create = _fake_create
    provider._client = mock_client

    with patch("backend.services.model_provider.provider_rate_limiter"):
        with patch("backend.services.model_provider._record_provider_headers", AsyncMock()):
            result = await provider.generate_with_tools(
                system_prompt="Be helpful.",
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}],
                tool_executor=tool_executor,
                max_iterations=5,
                on_delta=None,
                on_tool_start=on_tool_start,
            )

    # on_tool_start should have been called twice:
    #   call 1: cumulative=2 (2 tools in first turn)
    #   call 2: cumulative=3 (1 more tool in second turn)
    assert on_tool_start.call_count == 2
    assert on_tool_start.await_args_list[0][0][1] == 2
    assert on_tool_start.await_args_list[1][0][1] == 3
    assert result["content"] == "Done"


@pytest.mark.asyncio
async def test_on_tool_start_none_is_safe():
    """on_tool_start=None does not crash the generation loop."""
    from backend.services.model_provider import OpenAICompatibleProvider

    tool_executor = AsyncMock(return_value="ok")

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.config = MagicMock()
    provider.config.id = "test"
    provider.config.provider = "openai"
    provider.config.default_model = "gpt-4o"
    provider.config.max_tokens = 1000
    provider.config.temperature = 0.7
    provider.config.timeout_seconds = 30
    provider.config.max_concurrent_requests = 10
    provider.config.requests_per_minute = 60
    provider.api_key = "sk-test"
    provider.base_url = None

    mock_client = MagicMock()

    async def _fake_create(**kwargs):
        msg = MagicMock()
        msg.choices = [MagicMock(message=MagicMock(content="Hello", tool_calls=None), finish_reason="stop")]
        return msg

    mock_client.chat.completions.create = _fake_create
    provider._client = mock_client

    with patch("backend.services.model_provider.provider_rate_limiter"):
        result = await provider.generate_with_tools(
            system_prompt="Be helpful.",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            tool_executor=tool_executor,
            max_iterations=5,
            on_delta=None,
            on_tool_start=None,
        )

    assert result["content"] == "Hello"
```

- [ ] **Step 2: Run the new tests**

```bash
pytest backend/tests/unit/test_on_tool_start.py -v
```

Expected: both tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_on_tool_start.py
git commit -m "test(backend): add unit tests for on_tool_start callback"
```

---

### Task 8: Backend — Update integration test for `tool_progress` events

**Files:**
- Modify: `backend/tests/integration/test_ws_stream.py`

- [ ] **Step 1: Update `fake_process_message` to simulate tool calls and verify `tool_progress` events**

```python
async def fake_process_message(head, message, db, **kwargs):
    on_delta = kwargs.get("on_delta")
    cancel_event = kwargs.get("cancel_event")
    on_tool_start = kwargs.get("on_tool_start")
    assert on_delta is not None and cancel_event is not None

    # Simulate a tool call phase before streaming text
    if on_tool_start is not None:
        await on_tool_start([{"name": "search", "id": "tc_1"}], 1)

    await on_delta("Hello ")
    await on_delta("world")
    return {
        "content": "Hello world", "model": "m", "tokens_used": 2,
        "task_created": False, "task_id": None, "agent_spawned": None,
        "reincarnated": False, "finish_reason": "stop", "metadata": {},
    }
```

- [ ] **Step 2: Add assertion for `tool_progress` event in the integration test**

```python
    assert "tool_progress" in types, f"expected tool_progress in {types}"
    tp_idx = types.index("tool_progress")
    start_idx = types.index("message_start")
    delta_idx = types.index("message_delta")
    assert start_idx < tp_idx < delta_idx, \
        f"tool_progress should be after message_start but before message_delta: {types}"
```

- [ ] **Step 3: Run integration test**

```bash
pytest backend/tests/integration/test_ws_stream.py -v
```

Expected: passes

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_ws_stream.py
git commit -m "test(backend): verify tool_progress WS events in integration test"
```
