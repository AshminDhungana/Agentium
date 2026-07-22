# Structured Response Envelope

Replace the hard 2-3 line truncation (chat.py:577-587) with a typed-part
response envelope that delivers the right view of each AI response to every
channel — summary for voice/TTS, full text for dashboard, chunked blocks for
external messaging platforms.

## Current State

The REST/SSE path (`POST /api/v1/chat/send`, `_stream_response()` in
chat.py) enforces a post-generation truncation: after the LLM finishes, any
non-task response is cut to at most 3 non-empty lines. This affects the voice
bridge (which uses this path) and HTTP/SSE clients.

The WebSocket path (`/ws/chat`, websocket.py) streams freely via
`message_start` / `message_delta` / `message_end` with no truncation — but has
no structured envelope.

The voice bridge (`voice-bridge/main.py`) receives the truncated SSE stream,
buffers content, and flushes at sentence boundaries for TTS. Truncation makes
spoken responses feel abrupt.

External channels (`channel_manager.py`) receive the full (untruncated)
response and split by platform character limits only.

Two layers push brevity: the Constitution/communication_style says "be
concise," and the code enforces 3-line truncation on top of that.

## Core Concept

The response envelope replaces the flat truncated output with a sequence of
typed SSE events. Each event carries a `type` discriminant, a `seq` number,
and a `part` identifier. The LLM generates freely (one generation, one full
response). The delivery layer splits the response into parts (summary +
detail) and emits them as sequential envelope events. Each channel adapter
consumes the parts relevant to its renderer.

```
Before: LLM → full text → [3-line guillotine] → delivered to all channels
After:  LLM → full text → Envelope (summary + detail parts) →
         ├─ Dashboard: full streaming (unchanged WebSocket path)
         ├─ Voice: summary → fast TTS, detail → queued follow-up
         └─ External channels: summary → immediate, detail → paced blocks
```

## Envelope Protocol (REST/SSE Path)

### Wire Format

Events are SSE `data:` lines, one JSON object per event, separated by `\n\n`:

```
data: {"type":"ack","stream_id":"<uuid>","seq":1,"content":"Checking..."}
data: {"type":"summary","stream_id":"<uuid>","seq":2,"content":"Battery at 42%."}
data: {"type":"detail","stream_id":"<uuid>","seq":3,"content":"Discharging 5%/h."}
data: {"type":"part_end","stream_id":"<uuid>","seq":4,"part":"summary"}
data: {"type":"part_end","stream_id":"<uuid>","seq":5,"part":"detail"}
data: {"type":"complete","stream_id":"<uuid>","seq":6,"content":"","usage":{...}}
```

### Event Types

| Type | When | Required fields | Payload |
|------|------|-----------------|---------|
| `ack` | Before LLM generation starts | `stream_id`,`seq`,`content` | Human-readable acknowledgement ("Checking battery status…") |
| `thinking` | During LLM generation (optional) | `stream_id`,`seq` | No payload — signals "working on it" |
| `summary` | Content of the summary part | `stream_id`,`seq`,`content` | Concise 1-3 sentence summary |
| `detail` | Content of the detail part | `stream_id`,`seq`,`content` | Full elaboration text |
| `part_end` | Marks end of a named part | `stream_id`,`seq`,`part` | `part` = `"summary"` or `"detail"` |
| `error` | Unrecoverable mid-stream error | `stream_id`,`seq`,`error`,`retryable` | Human-readable error message + boolean |
| `complete` | Stream finished normally | `stream_id`,`seq`,`content`,`usage` | Final assembled text + token usage metadata |

### Sequence Numbers

Every event carries a monotonically increasing `seq` (per stream_id). Consumers
detect gaps: if event seq=5 arrives but seq=4 never did, a gap occurred.
Consumers MAY request replay for a given `stream_id` via a separate replay
endpoint (future). On gap, consumers SHOULD continue rendering (partial
content is better than stuck) and log the gap.

### Lifecycle States

The consumer tracks one lifecycle state per `stream_id`:

| State | Entered by | Meaning |
|-------|-----------|---------|
| `processing` | `ack` | Request accepted, LLM generating |
| `awaiting_detail` | `part_end` with `part="summary"` | Summary delivered, detail pending |
| `complete` | `complete` | Finished successfully |
| `error` | `error` | Unrecoverable failure |
| `cancelled` | (client abort signal) | User stopped generation |

### Error Handling

Mid-stream errors (rate limit, context overflow, provider failure) are
delivered as in-band `error` events — not as HTTP status codes (which were
already sent as 200):

```
data: {"type":"error","stream_id":"<uuid>","seq":7,
       "error":"Upstream rate limit exceeded","retryable":true}
```

Characteristics:
- The `error` event is **terminal** — no further events follow for that
  `stream_id`.
- `retryable: true` means the consumer MAY retry with exponential backoff.
- `retryable: false` means the error is permanent (content filter, auth, bad
  request) — do not retry.
- The consumer preserves any partial content already received (the summary
  is still valid) and marks the message as interrupted.
- The `ack` event is always emitted synchronously before any LLM call, so
  the client always gets an acknowledgement even if the LLM call fails
  immediately.

### Compatibility

The envelope format is additive. Existing SSE clients that parse
`{"type":"content"}` or `{"type":"complete"}` will continue to work — they
will see `summary`/`detail` as unknown event types and silently ignore them
(SSE clients MUST ignore unknown event types per spec). A
backward-compatibility mode (`envelope: false`) emits the legacy format.

## Summary/Detail Split

The split is performed at the **delivery layer** after the LLM finishes
generating, not at generation time. This keeps the AI prompt unchanged and
works with any provider.

### Split Algorithm

```
split_response(full_text):
    1. Strip trailing whitespace
    2. Find first paragraph boundary (double newline) or 3-line mark
    3. Lines before boundary = summary (1-3 lines, ~50-100 words)
    4. Lines after boundary = detail (everything else)
    5. If total text <= 3 lines → summary = full text, detail = empty
    6. If no paragraph boundary found → first 3 lines = summary
    7. If total text <= 1 line and no boundary → summary = full text, detail = empty
```

### Persona Hint

One line added to the Constitution `communication_style`:

> "Start responses with a concise standalone summary (1-3 sentences) that can
> stand alone as the full answer, then provide detail."

This improves the heuristic's accuracy without structured output overhead.
The heuristic still works correctly without this hint — the hint just makes
the split more natural.

### Edge Cases

| Input | Summary | Detail |
|-------|---------|--------|
| "Yes, it's ready." | "Yes, it's ready." | (empty) |
| 1-line answer | Same as full text | (empty) |
| 2-line answer | Same as full text | (empty) |
| Multi-paragraph | First paragraph (≤3 lines) | Remaining paragraphs |
| Code block first | First 3 lines or paragraph break | Rest of code + explanation |
| Tool-only response (task created) | Full text (no split) | (empty — already handled by task_info check) |
| Empty response | (empty) | (empty) |

## Per-Channel Delivery

### Dashboard (WebSocket Path)

**No change.** The WebSocket path continues to stream raw text deltas via
`message_start` / `message_delta` / `message_end`. The dashboard gets the
full response token-by-token with no envelope indirection — this path was
already working well and does not have the truncation problem.

### Voice Bridge (REST/SSE Path)

The voice bridge (`_stream_chat()`) currently parses `{"type":"content"}`
SSE events from the REST endpoint. With the envelope:

| Envelope event | Voice bridge action |
|----------------|---------------------|
| `ack` | Play cached filler audio (~100ms "mm-hmm" file), transition to `thinking` state |
| `thinking` | Send voice_state "thinking" to overlay |
| `summary` | Accumulate into buffer; flush completed sentences to TTS immediately |
| `part_end` ("summary") | Brief natural pause (~300ms breath gap) |
| `detail` | Queue in buffer; continue sentence-flushing to TTS from queue |
| `error` | Play error tone, send voice_state "error" |
| `complete` | Finalize, send voice_state "idle" |

Key behavioral changes:
- **Time-to-first-audio** drops from "wait for sentence boundary in truncated
  text" to "begin speaking summary within 200ms of first summary chunk."
- The `ack` filler audio eliminates dead air during LLM generation entirely
  (proven pattern from Vapi / AssemblyAI / Rime research).
- Sentence-boundary chunking continues to use the existing `. ! ?` flush
  logic — no change needed.
- If the user barges in during `detail` streaming, the detail queue is
  flushed (existing barge-in logic unchanged). The summary is already spoken.

### External Channels (WhatsApp, Telegram, Discord, Slack, etc.)

The trigger point is `ChannelManager.broadcast_to_channels()`. Currently
receives the full text. With the envelope, the adapter receives structured
parts:

| Channel | Summary | Detail | Pacing |
|---------|---------|--------|--------|
| WhatsApp | Sent as first message | Follow-up messages with 800-2500ms natural delay | Coalesce blocks < 3 lines |
| Telegram | Sent immediately | Edits same message with progressive text (preview streaming) | 300ms edit throttle |
| Discord | Sent as first message | Follow-up with 2000-char chunks, 17-line cap | No extra delay |
| Slack | Sent as first block | Blocks appended via chat.update | 400ms edit throttle |
| Signal | Sent as first message | Follow-up messages with 500ms throttle | Coalesce blocks < 3 lines |
| SMS/Email | Summary only | Detail never sent (channel constraint) | N/A |

No changes to `channel_manager.py` internals — the channel adapters already
handle chunking. The change is at the trigger point:
`broadcast_to_channels()` receives the structured envelope and the adapter
chooses what to deliver per its existing delivery strategy
(`all-or-abort` or `best-effort`).

### Humanized Pacing (Configuration)

Optional pacing config for external channels:

```yaml
response_delivery:
  pacing:
    mode: natural          # off | natural | custom
    natural_min_ms: 800
    natural_max_ms: 2500
    coalesce_min_lines: 3  # blocks shorter than this merge
```

When `mode: natural`, blocks are delivered with random delays between
`min_ms` and `max_ms`. Blocks shorter than `coalesce_min_lines` are merged
with the next block. The first block (summary) is always immediate.

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `backend/api/routes/chat.py` | Replace lines 577-587 (3-line truncation) with envelope emission logic in `_stream_response()`. Add `response_delivery_enabled` flag (default: `true`). |
| `backend/core/persona.py` or Constitution init | Add one-line persona hint about summary-first structure |
| `voice-bridge/main.py` | Update `_stream_chat()` to handle envelope events (`ack`, `thinking`, `summary`, `detail`, `part_end`, `error`, `complete`). Add `ack.wav` filler audio asset. |
| `backend/services/channel_manager.py` | Update `broadcast_to_channels()` to pass envelope parts. No adapter code changes (adapters already handle chunking). |
| Configuration | Add `response_delivery` section to config schema. |

### chat.py: _stream_response() Changes

Current flow:

```
1. Call provider.stream_generate() → yields text chunks
2. For each chunk: yield {"type":"content",...} via SSE (progressive)
3. Accumulate full_text from chunks
4. Task analysis on original message
5. If no task created: truncate full_text to 3 lines
6. Emit {"type":"complete",...}
```

New flow:

```
1. Emit {"type":"ack","stream_id":sid,"seq":1,"content":"<auto-ack>"} immediately
2. Call provider.stream_generate() → yields text chunks
3. Accumulate all chunks into full_text list (no SSE emission during gen)
4. After generation: run task analysis
5. Full text → split into summary + detail
6. Emit envelope from buffer:
   └─ If envelope=true: emit summary events → part_end → detail events → complete
   └─ If envelope=false: emit content events as before (legacy mode)
```

The buffer-and-replay approach is used because the summary boundary is not
known until the full text is available. The trade-off is losing progressive
content during generation — but the `ack` event (emitted immediately, before
generation) provides immediate feedback. For the voice bridge, the ack filler
audio plays during generation, and the summary arrives as a batch at the end
for immediate TTS. Total perceived time for voice:
generation + ack filler → same as current, but with ack masking the dead air.

### voice-bridge/main.py: _stream_chat() Changes

Current flow:

```
1. Parse {"type":"content"} SSE events
2. Accumulate into buffer
3. Flush completed sentences at . ! ? to TTS
4. On {"type":"complete"}: finalize
```

New flow:

```
1. On ack: play ack.wav, send {"voice_state": "thinking"}
2. On summary: accumulate, flush sentences to TTS
3. On part_end(part="summary"): brief 300ms pause
4. On detail: accumulate, continue TTS
5. On error: play error tone, send {"voice_state": "error"}
6. On complete: send {"voice_state": "idle"}
```

The sentence-flush logic (buffer + split at `. ! ?`) is unchanged — just
applied to both summary and detail parts separately.

### Config Schema

```yaml
response_delivery:
  enabled: true                    # master switch
  envelope: true                   # true=emit typed events, false=legacy format
  persona_summary_hint: true       # add summary-first hint to Constitution
  summary:
    max_lines: 3
  pacing:
    mode: natural                  # off | natural | custom
    natural_min_ms: 800
    natural_max_ms: 2500
    coalesce_min_lines: 3
```

## Rollout Plan

1. Add `response_delivery` config with `enabled: false` (zero behavior change)
2. Implement envelope emission in `chat.py` behind the flag
3. Add persona hint to Constitution (safe — just a preference, no constraint)
4. Update voice bridge `_stream_chat()` to handle envelope events
5. Test with voice bridge: verify TTFA improvement, ack audio, summary-first
6. Enable by default (`enabled: true`), keep legacy mode as fallback
7. Add pacing config to external channels (optional, behind flag)

## Open Questions

- Should the WebSocket path also adopt envelope events eventually? (Current
  design: no — dashboard streaming is already good.)
- Should the `ack` content be static or dynamically generated? (Static
  for now — a small set of canned acknowledgements based on intent.)
- Buffer size for the chunk rewind in chat.py? (The full response is
  already accumulated in `full_response` list — no additional buffer needed.)
