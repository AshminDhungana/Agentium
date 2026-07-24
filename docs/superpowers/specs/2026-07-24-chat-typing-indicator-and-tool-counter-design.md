# Chat Typing Indicator & Tool Counter Design

**Date:** 2026-07-24
**Status:** Draft
**Domain:** project
**Tags:** chat, ui, frontend, websocket, typing-indicator, tool-counter

## Overview

Replace the current shimmer-bar typing indicator with animated three-dot bouncing dots and add a real-time running tool-use counter (+1 → +2 → +3) inside the chat bubble, making the chat feel more engaging and transparent about what the agent is doing.

## Current State

- `TypingIndicator.tsx` renders either 3 shimmer bars (default) or an italic "Thinking…" label (when `thinking=true`)
- `type: "message_start"` WS payload sends `thinking: true/false` — no tool-use data
- No tool-use visibility exists; the frontend sees a pause in text deltas during tool execution with no indication of activity

## Design Decisions

### Approach Chosen: New `tool_progress` WS Event (A)

A new WebSocket event type `tool_progress` is fired each time a batch of tool calls begins executing. The frontend uses the `tool_count` field to display a running counter.

**Alternatives rejected:**
- B: Static count in `message_start` — no live +1 → +2 → +3 progression
- C: Count only in `message_end` — not real-time, defeats the engagement goal

### Position: Inline After Dots Inside Bubble

```
┌──────────────────────────────┐
│ ● ● ●  +2                   │
└──────────────────────────────┘
```

Based on research — Chat bots show status where the user is looking (inside the bubble). Keeps the counter proximate to the typing indicator without adding extra rows or cluttering the avatar area.

## Backend Changes

### New Callback: `on_tool_start`

A new async callback threaded through the same pass-through chain as `on_delta`:

```
websocket.py  →  chat_service.py  →  llm_client.py  →  model_provider.py
```

**Signature:** `Callable[[List[Dict], int], Awaitable[None]]` — receives the list of tool calls about to execute and the cumulative count so far.

### Injection Points (3)

In `model_provider.py`:

1. **OpenAI blocking path** (~line 977) — right before `asyncio.gather()` in the blocking tool-call branch
2. **OpenAI streaming path** (~line 1042) — right before `asyncio.gather()` in the streaming tool-call branch
3. **Anthropic blocking path** (~line 1415) — right before `asyncio.gather()` in the Anthropic tool-call branch

### New WS Message Type

```python
async def on_tool_start(tool_calls: List[Dict], cumulative: int, sid: str = stream_id) -> None:
    await websocket.send_json({
        "type":        "tool_progress",
        "stream_id":   sid,
        "tool_count":  cumulative,
    })
```

The cumulative count is tracked in a closure variable across all iterations of the agentic loop so subsequent tool-call turns increment correctly.

### Pass-Through Updates

Three files need the new parameter threaded through:

- `chat_service.py` — `process_message()` passes `on_tool_start` to `llm_client.generate_with_tools()`
- `llm_client.py` — `generate_with_tools()` passes it to `ModelService.generate_with_agent_tools()`
- `model_provider.py` — `generate_with_agent_tools()` passes it to `provider.generate_with_tools()`

All default to `None` to avoid breaking existing callers.

## Frontend Changes

### TypingIndicator Component

Replace `.shimmer` + `.bar` elements with three `.dot` elements using a bouncing animation.

**Animation:**

```css
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
  animation: dot-bounce 1.4s ease-in-out infinite;
}
.dot:nth-child(1) { animation-delay: 0s; }
.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
  40% { transform: translateY(-6px); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .dot { animation: dot-pulse 1.5s ease-in-out infinite; }
  .dot:nth-child(2) { animation-delay: 0.3s; }
  .dot:nth-child(3) { animation-delay: 0.6s; }
}

@keyframes dot-pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.7; }
}
```

**Props:**

```typescript
interface TypingIndicatorProps {
  thinking?: boolean;
  toolCount?: number;
}
```

**Behavior:**

| `thinking` | `toolCount` | Renders |
|---|---|---|
| any | 0 or undefined | Three bouncing dots only |
| any | > 0 | Dots + inline `+N` (e.g. `+2`) |

The `thinking` prop is preserved as an informational flag (the server still sends it in `message_start`) but both modes render identically — bouncing dots. The "Thinking…" label and shimmer bars are removed entirely. Clients that don't pass `thinking` work fine; it's a no-op visually. The `toolCount` takes visual priority when > 0.

**Counter visual:** A `<span className="tool-count">+2</span>` rendered immediately after the dots, styled with the same color/weight as the bubble text. Small scale animation (1.0 → 1.15 → 1.0 over 200ms) when the number changes.

### ChatPage WS Handler

New state: `const [toolCount, setToolCount] = useState(0);`

```typescript
// In the WS subscriber useEffect:

if (msg.type === 'message_start') {
  useChatStore.getState().beginStream(...);
  setIsThinking(Boolean((msg as any).thinking));
  setToolCount(0);                   // reset counter
  return;
}

if (msg.type === 'tool_progress') {
  setToolCount(msg.tool_count as number);  // update running count
  return;
}

if (msg.type === 'message_delta') {
  useChatStore.getState().appendDelta(...);
  setIsAwaitingReply(false);
  setIsThinking(false);
  setToolCount(0);                   // clear — text streaming has begun
  return;
}

if (msg.type === 'message_end') {
  useChatStore.getState().endStream(...);
  setIsAwaitingReply(false);
  setIsThinking(false);
  setToolCount(0);
  return;
}
```

Pass to TypingIndicator:

```tsx
<TypingIndicator thinking={isThinking} toolCount={toolCount} />
```

### Rendering Logic

The TypingIndicator is shown in two places (both need the `toolCount` prop):

1. **Inside streaming placeholder bubble** (~line 1184):
   ```tsx
   {isAwaitingReply && message.status === 'streaming' && !message.content ? (
     <TypingIndicator thinking={isThinking} toolCount={toolCount} />
   ) : ( ... ) }
   ```

2. **Standalone bubble** (~line 1242) — legacy non-streaming path:
   ```tsx
   {isAwaitingReply && !activeStreamId && (
     <TypingIndicator thinking={isThinking} toolCount={toolCount} />
   )}
   ```

### Cleanup on WS Disconnect

The existing connection-drop effect (~line 289) must also reset `toolCount`:

```typescript
useEffect(() => {
    if (connectionPhase !== 'active') {
        if (activeStreamId) useChatStore.getState().resetStream();
        setIsAwaitingReply(false);
        setToolCount(0);   // reset tool counter on disconnect
    }
}, [connectionPhase, activeStreamId]);
```

### CSS Module Rewrite

`TypingIndicator.module.css` is substantially rewritten:
- Remove `.shimmer`, `.bar`, `.shimmer-sweep` keyframes, `.thinkingLabel`
- Add `.dot`, `.dot:nth-child(N)`, `@keyframes dot-bounce`, `@keyframes dot-pulse`, `.toolCount`

## No chatStore Changes

`toolCount` is local UI state in ChatPage — it's reset on every `message_start` and never persisted. No changes to the Zustand store.

## Testing

### Backend

- Unit test: `on_tool_start` fires with `cumulative=1` on first tool-call turn, `cumulative=2` on second
- Unit test: `on_tool_start` is `None`-safe (defaults to no-op)
- Integration: extend `test_ws_stream.py` to assert `tool_progress` events arrive between `message_start` and `message_end`

### Frontend

- **TypingIndicator.test.tsx:** Verify 3 `.dot` elements render (not bars), verify `+N` text appears when `toolCount > 0`, verify `+N` hidden when `toolCount` is 0 or undefined
- **ChatPage.typing.test.tsx:** Update existing tests to match new dot structure

## Out of Scope

- Tool names or descriptions (future enhancement)
- Tool execution duration
- Per-tool status (success/failure)
- Collapsible tool-call log
