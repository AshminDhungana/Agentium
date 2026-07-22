# Structured Response Envelope — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard 2-3 line truncation in the REST/SSE chat path with a typed event envelope (ack, summary, detail, complete) for per-channel delivery.

**Architecture:** Three independent changes: (1) persona hint + config flag, (2) envelope emission in `chat.py` replaces the truncation block, (3) voice bridge `_stream_chat()` adapts to the new event types. No changes to the WebSocket path or channel_manager internals — the WebSocket path already streams freely, and external channel adapters already handle chunking.

**Tech Stack:** Python 3.11+, FastAPI, SSE, JSON

**Spec:** `docs/superpowers/specs/2026-07-22-structured-response-envelope-design.md`

**Reference:** Existing `_stream_response()` at `backend/api/routes/chat.py:475-677`. Existing `_stream_chat()` at `voice-bridge/main.py:893-933`. Existing SSE event parsing handles `content`, `done`, `complete` types only — all other types silently ignored.

---

### Task 1: Config Flag + Persona Summary Hint

**Files:**
- Modify: `backend/core/config.py` (add settings field)
- Modify: `backend/core/persona.py` (add summary-first hint to build_system_prompt)

**Interfaces:**
- Consumes: `get_settings()` from `backend.core.config`
- Produces: `RESPONSE_DELIVERY_ENVELOPE` env var (default `true`), persona hint injected into system prompt at line 136

- [ ] **Step 1: Add RESPONSE_DELIVERY_ENVELOPE to Settings**

In `backend/core/config.py`, add the field after `VISION_ENABLED` (line 220):

```python
    RESPONSE_DELIVERY_ENVELOPE: bool = Field(
        default=True,
        env="RESPONSE_DELIVERY_ENVELOPE",
        description=(
            "Emit structured response envelope (ack/summary/detail/complete) "
            "instead of raw content events. Set to false for legacy behavior."
        ),
    )
```

- [ ] **Step 2: Add summary-first hint to build_system_prompt**

In `backend/core/persona.py`, modify the style_bits section (lines 130-137) to append the summary hint when the envelope feature is active:

```python
    style_bits = []
    comm = sovereign.get("communication_style")
    if comm:
        style_bits.append(str(comm))
    if channel == "voice":
        style_bits.append(VOICE_ADAPTATION)
    # Summary-first hint for response envelope (non-voice channels)
    if channel != "voice":
        from backend.core.config import get_settings
        if get_settings().RESPONSE_DELIVERY_ENVELOPE:
            style_bits.append(
                "Start responses with a concise standalone summary "
                "(1-3 sentences) that can stand alone as the full answer, "
                "then provide detail."
            )
    if style_bits:
        parts.append("# Communication Style\n" + "\n".join(f"- {s}" for s in style_bits))
```

- [ ] **Step 3: Verify tests still pass**

Run: `pytest backend/tests/test_constitution_persona.py -v`
Expected: all tests pass (the hint is appended to the persona but doesn't change any existing behavior)

- [ ] **Step 4: Commit**

```bash
git add backend/core/config.py backend/core/persona.py
git commit -m "feat: add RESPONSE_DELIVERY_ENVELOPE config and summary-first persona hint"
```

---

### Task 2: Envelope Emission in chat.py

**Files:**
- Modify: `backend/api/routes/chat.py` (lines 567-591 — replace streaming + truncation)
- Test: `backend/tests/integration/test_provider_mock_wiring.py` (extend existing streaming test)

**Interfaces:**
- Consumes: `RESPONSE_DELIVERY_ENVELOPE` from settings, `stream_generate()` from provider
- Produces: SSE events of type `ack` (immediate), `summary` + `detail` (after generation) + `complete`; or legacy `content` events when envelope is disabled

- [ ] **Step 1: Write the integration test**

Add to `backend/tests/integration/test_provider_mock_wiring.py` after the existing streaming tests. Model it after `test_chat_service_forwards_on_delta` (line 617) which already exercises the streaming path:

```python
@pytest.mark.asyncio
async def test_stream_response_emits_envelope_events(db_session, mock_provider):
    """_stream_response emits ack/summary/detail/complete when envelope is enabled.

    Uses the same mock_provider fixture as test_chat_service_forwards_on_delta.
    The mock provider returns canned text; we verify the SSE event sequence.
    """
    from backend.api.routes.chat import _stream_response
    from backend.models.entities.chat_message import ChatMessage as ChatMsg
    from backend.core.config import get_settings

    # Ensure envelope is enabled
    settings = get_settings()
    assert settings.RESPONSE_DELIVERY_ENVELOPE is True

    chat_msg = ChatMsg(message="test envelope", voice_persona=None)
    events = []
    async for raw_event in _stream_response("00001", chat_msg):
        events.append(json.loads(raw_event[len("data: "):].strip()))

    # Event sequence must be: ack → summary → part_end → (detail → part_end?) → complete → done
    assert len(events) >= 3, f"Expected at least 3 events, got {len(events)}"
    assert events[0]["type"] == "ack", f"First event should be ack, got {events[0]['type']}"
    assert events[0]["stream_id"] is not None

    # Find the terminal event types in order
    types = [e["type"] for e in events]
    assert "summary" in types, "Expected a summary event"
    assert "complete" in types, "Expected a complete event"
    assert "done" in types or types[-1] == "done", "Expected a done event at the end"

    # Verify ack has content
    assert events[0].get("content"), "ack should have content"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py::test_stream_response_emits_envelope_events -v`
Expected: FAIL (envelope emission not yet implemented)

- [ ] **Step 3: Modify _stream_response() to emit envelope events**

Replace lines 567-591 in `backend/api/routes/chat.py`. The key change:

```python
        from backend.core.config import get_settings
        use_envelope = get_settings().RESPONSE_DELIVERY_ENVELOPE
        stream_id = str(uuid.uuid4()) if use_envelope else None

        # Emit ack immediately if envelope is enabled
        if use_envelope:
            yield f"data: {json.dumps({'type': 'ack', 'stream_id': stream_id, 'seq': 1, 'content': 'Processing your request...'})}\n\n"

        full_response: list[str] = []
        seq = 2 if use_envelope else 0
        async for chunk in provider.stream_generate(full_prompt, enriched_message):
            full_response.append(chunk)
            if not use_envelope:
                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        full_text = "".join(full_response)
        task_info = await ChatService.analyze_for_task(head, chat_msg.message, full_text, db)

        if use_envelope:
            # ── Envelope emission (replaces 3-line truncation) ──────────────
            if task_info.get("created", False):
                # Task-created responses: send as summary, no detail
                yield f"data: {json.dumps({'type': 'summary', 'stream_id': stream_id, 'seq': seq, 'content': full_text})}\n\n"; seq += 1
                yield f"data: {json.dumps({'type': 'part_end', 'stream_id': stream_id, 'seq': seq, 'part': 'summary'})}\n\n"; seq += 1
            else:
                # Split into summary + detail
                non_empty_lines = [ln for ln in full_text.split("\n") if ln.strip()]
                if len(non_empty_lines) <= 3:
                    summary_text = full_text
                    detail_text = ""
                else:
                    # First paragraph boundary or 3 lines
                    boundary = full_text.find("\n\n")
                    if boundary == -1 or boundary == 0:
                        summary_text = "\n".join(non_empty_lines[:3])
                        detail_text = "\n".join(non_empty_lines[3:])
                    else:
                        summary_text = full_text[:boundary].strip()
                        detail_text = full_text[boundary:].strip()
                        # Ensure summary is at most 3 lines
                        summary_lines = [ln for ln in summary_text.split("\n") if ln.strip()]
                        if len(summary_lines) > 3:
                            summary_text = "\n".join(summary_lines[:3])
                            detail_text = "\n".join(summary_lines[3:]) + "\n" + detail_text

                yield f"data: {json.dumps({'type': 'summary', 'stream_id': stream_id, 'seq': seq, 'content': summary_text})}\n\n"; seq += 1
                yield f"data: {json.dumps({'type': 'part_end', 'stream_id': stream_id, 'seq': seq, 'part': 'summary'})}\n\n"; seq += 1
                if detail_text:
                    yield f"data: {json.dumps({'type': 'detail', 'stream_id': stream_id, 'seq': seq, 'content': detail_text})}\n\n"; seq += 1
                    yield f"data: {json.dumps({'type': 'part_end', 'stream_id': stream_id, 'seq': seq, 'part': 'detail'})}\n\n"; seq += 1
        else:
            # ── Legacy 3-line truncation (unchanged) ────────────────────────
            if not task_info.get("created", False):
                original_length = len(full_text)
                non_empty_lines = [ln for ln in full_text.split("\n") if ln.strip()]
                if len(non_empty_lines) > 3:
                    full_text = "\n".join(non_empty_lines[:3])
                    logger.debug(
                        f"[chat.py] Response truncated for 2-3 line policy: "
                        f"{original_length} chars → {len(full_text)} chars"
                    )
        # ── end envelope / truncation ─────────────────────────────────────────
```

- [ ] **Step 4: Update the complete event emission**

The existing `complete` event at line 591 should still emit after the envelope, but now carries the full text in `content` instead of empty string when envelope is enabled:

```python
        message_id = str(uuid.uuid4())

        yield f"data: {json.dumps({'type': 'complete', 'stream_id': stream_id, 'seq': seq if use_envelope else 0, 'content': full_text, 'message_id': message_id, 'metadata': {'agent_id': agent_id, 'model': model_name, 'task_created': task_info['created'], 'task_id': task_info.get('task_id'), 'card': None}})}\n\n"
```

Note: The existing `full_text` following line 593 and the persistence at 613-632 must still use the **full** `full_text` (not the summary-only text), because the DB stores the complete response. The `full_text` variable is never truncated in envelope mode — the split only affects what's sent over SSE.

- [ ] **Step 5: Update the broadcast_payload to pass envelope parts**

In the broadcast_payload dict (lines 643-646), include the summary/detail split so external channel adapters can use structured delivery:

```python
        if sovereign_user and use_envelope:
            broadcast_payload = {
                "user_id": sovereign_user.id,
                "content": full_text,
                "summary": summary_text if not task_info.get("created", False) else full_text,
                "detail": detail_text if not task_info.get("created", False) else "",
            }
        elif sovereign_user:
            broadcast_payload = {
                "user_id": sovereign_user.id,
                "content": full_text,
            }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest backend/tests/integration/test_provider_mock_wiring.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/api/routes/chat.py backend/tests/integration/test_provider_mock_wiring.py
git commit -m "feat: replace 3-line truncation with structured response envelope"
```

---

### Task 3: Voice Bridge _stream_chat() Envelope Support

**Files:**
- Modify: `voice-bridge/main.py` (lines 913-929 — SSE event parsing)
- Modify: `voice-bridge/tests/test_session.py` (extend existing streaming tests)

**Interfaces:**
- Consumes: SSE events of type `ack`, `summary`, `detail`, `complete`, `error`, `part_end`
- Produces: yields text to caller (for TTS), ignores unknown event types

- [ ] **Step 1: Write failing test**

In `voice-bridge/tests/test_session.py`, add a test for envelope events:

```python
@pytest.mark.asyncio
async def test_stream_chat_handles_envelope_events():
    """_stream_chat yields summary+detail from envelope events, ignores ack."""
    from voice_bridge_main import _stream_chat

    envelope_events = [
        "data: " + json.dumps({"type": "ack", "stream_id": "s1", "seq": 1, "content": "Thinking..."}),
        "data: " + json.dumps({"type": "summary", "stream_id": "s1", "seq": 2, "content": "Battery at 42%."}),
        "data: " + json.dumps({"type": "part_end", "stream_id": "s1", "seq": 3, "part": "summary"}),
        "data: " + json.dumps({"type": "detail", "stream_id": "s1", "seq": 4, "content": "Discharging at 5%/h."}),
        "data: " + json.dumps({"type": "part_end", "stream_id": "s1", "seq": 5, "part": "detail"}),
        "data: " + json.dumps({"type": "complete", "stream_id": "s1", "seq": 6, "content": "Battery at 42%. Discharging at 5%/h."}),
    ]
    sse_data = "\n\n".join(envelope_events) + "\n\n"

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.__iter__.return_value = [sse_data.encode()]
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        results = [chunk async for chunk in _stream_chat("battery?")]

    # Should yield summary and detail content, not ack
    assert "Battery at 42%" in results
    assert "Discharging at 5%/h" in results
    # Should not contain "Thinking..."
    assert all("Thinking..." not in r for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest voice-bridge/tests/test_session.py::test_stream_chat_handles_envelope_events -v`
Expected: FAIL (current code only handles `content` and `done`/`complete` types)

- [ ] **Step 3: Update _stream_chat event parsing**

In `voice-bridge/main.py`, replace the event parsing block (lines 925-928):

```python
            evt = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        evt_type = evt.get("type")
        if evt_type == "ack":
            # Acknowledgment — ignore (backend handles timing)
            continue
        if evt_type == "summary" and evt.get("content"):
            yield evt["content"]
        elif evt_type == "detail" and evt.get("content"):
            yield evt["content"]
        elif evt_type == "content" and evt.get("content"):
            yield evt["content"]
        elif evt_type == "part_end":
            # Part boundary — yield newline for sentence separation
            yield "\n"
        elif evt_type in ("complete", "done"):
            yield ""  # signal terminal
            break
        elif evt_type == "error":
            logger.error(f"[voice] Stream error: {evt.get('error')}")
            break
        # All other event types (thinking, etc.) silently ignored
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest voice-bridge/tests/test_session.py -v`
Expected: all tests pass (existing test_stream_chat_yields_sentences still works with legacy `content` events, new test passes with envelope events)

- [ ] **Step 5: Commit**

```bash
git add voice-bridge/main.py voice-bridge/tests/test_session.py
git commit -m "feat: handle structured response envelope events in voice bridge"
```

---

### Task 4: External Channel Delivery (Summary/Detail)

**Files:**
- Modify: `backend/api/routes/chat.py` (broadcast_payload — already updated in Task 2 Step 5)
- Modify: `backend/services/channel_manager.py` (receive structured payload)

**Interfaces:**
- Consumes: `broadcast_payload` dict with optional `summary`/`detail` keys (from Task 2)
- Produces: `broadcast_to_channels()` passes summary as the primary content, detail as secondary

- [ ] **Step 1: Write a unit test for broadcast_to_channels with envelope payload**

Add to an existing test file or create `backend/tests/unit/test_channel_manager_envelope.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_broadcast_to_channels_uses_summary_when_available(db_session):
    """When broadcast payload includes summary, it's used as primary content."""
    from backend.services.channel_manager import ChannelManager

    payload = {
        "user_id": 1,
        "content": "Full text here. More details.",
        "summary": "Full text here.",
        "detail": "More details.",
    }

    with patch.object(ChannelManager, "_send_to_channel", new=AsyncMock()) as mock_send:
        await ChannelManager.broadcast_to_channels(
            user_id=payload["user_id"],
            content=payload["summary"],
            db=db_session,
            detail=payload.get("detail", ""),
        )
        mock_send.assert_called_once()
        call_content = mock_send.call_args[1].get("content", "")
        assert call_content == payload["summary"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_channel_manager_envelope.py -v`
Expected: FAIL (broadcast_to_channels does not accept `detail` parameter)

- [ ] **Step 3: Update broadcast_to_channels signature**

In `backend/services/channel_manager.py`, modify `broadcast_to_channels` to accept an optional `detail` parameter and pass it through to adapters:

```python
    @staticmethod
    async def broadcast_to_channels(
        user_id: str,
        content: str,
        db: Session,
        detail: str = "",
    ) -> None:
```

The method signature change is additive (default `detail=""`), so existing callers (line 667 in chat.py and any other callers) continue to work unchanged. The `detail` string is available for adapters that want to use it for follow-up delivery.

- [ ] **Step 4: Update call site in chat.py**

The broadcast call at line 666-670 in `chat.py` passes `detail` when available:

```python
                    await ChannelManager.broadcast_to_channels(
                        user_id=broadcast_payload["user_id"],
                        content=broadcast_payload.get("summary", broadcast_payload["content"]),
                        db=broadcast_db,
                        detail=broadcast_payload.get("detail", ""),
                    )
```

- [ ] **Step 5: Run tests**

Run: `pytest backend/tests/unit/test_channel_manager_envelope.py backend/tests/integration/test_provider_mock_wiring.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/channel_manager.py backend/api/routes/chat.py backend/tests/unit/test_channel_manager_envelope.py
git commit -m "feat: pass structured envelope parts to external channel delivery"
```

---

## Rollback

If any task causes issues:
- **Task 1**: Set `RESPONSE_DELIVERY_ENVELOPE=false` in environment — persona hint suppresses itself
- **Task 2**: Set `RESPONSE_DELIVERY_ENVELOPE=false` — falls back to legacy 3-line truncation
- **Task 3**: Voice bridge continues to handle `content` events (legacy mode) — no rollback needed
- **Task 4**: Fallback `detail=""` default means existing callers are unaffected
