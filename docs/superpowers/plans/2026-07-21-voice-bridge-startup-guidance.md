# Voice Bridge Startup Guidance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add startup guidance messages and token-wait state to the voice bridge.

**Architecture:** A single module-level `asyncio.Event` gates the voice loop. A startup counter file tracks how many times the bridge has launched. The existing WS `set_token` handler unblocks the event when a token arrives.

**Tech Stack:** Python 3.10+, asyncio, pyttsx3, existing voice-bridge infrastructure.

## Global Constraints

- Only modify `voice-bridge/main.py`. No new files, no new dependencies, no backend changes.
- All startup speech happens in `_main()` before `asyncio.gather()`, not inside a supervisor.
- The welcome message replays every 5 bridge restarts (counter file at `~/.agentium/.voice-startup-count`).

---

### Task 1: Startup Counter + Speech Function

**Files:**
- Modify: `voice-bridge/main.py` — add `_maybe_speak_startup_messages()` after the existing config block (around line 155)

**Interfaces:**
- Consumes: module globals `VOICE_TOKEN`, `speak()` function, `logger`
- Produces: `_maybe_speak_startup_messages()` — called from `_main()`, reads/writes `~/.agentium/.voice-startup-count`, speaks welcome/guidance

- [ ] **Step 1: Write the failing test**

Create `voice-bridge/tests/test_startup_guidance.py`:

```python
"""Tests for voice-bridge startup guidance messages."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import main as bridge


def test_first_run_speaks_welcome():
    """Counter file absent → welcome spoken, counter written as 1."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert mock_speak.called
            text = " ".join(c.args[0] for c in mock_speak.call_args_list)
            assert "Welcome back" in text
        assert bridge._COUNTER_PATH.read_text().strip() == "1"


def test_second_run_skips_welcome():
    """Counter = 1 → no welcome, counter incremented to 2."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("1")
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert not mock_speak.called
        assert bridge._COUNTER_PATH.read_text().strip() == "2"


def test_fifth_run_speaks_welcome():
    """Counter = 4 (5th run) → welcome spoken."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("4")
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert mock_speak.called
            assert "Welcome back" in mock_speak.call_args[0][0]


def test_no_token_speaks_guidance():
    """VOICE_TOKEN empty → guidance spoken."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("2")
        with patch.object(bridge, "VOICE_TOKEN", ""):
            with patch.object(bridge, "speak") as mock_speak:
                asyncio.run(bridge._maybe_speak_startup_messages())
                assert mock_speak.called
                assert "API key" in mock_speak.call_args[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd voice-bridge && python -m pytest tests/test_startup_guidance.py -v`
Expected: ImportError or AttributeError (function not defined)

- [ ] **Step 3: Add `_COUNTER_PATH` and `_maybe_speak_startup_messages()` to `main.py`**

Add after the config block (after line 155, before the optional dependency guards):

```python
# ── Startup counter ──────────────────────────────────────────────────────────
_COUNTER_PATH = Path.home() / ".agentium" / ".voice-startup-count"


async def _maybe_speak_startup_messages() -> None:
    """Read/increment startup counter, speak welcome (every 5 runs) and/or
    guidance (no token). Called once from _main() before asyncio.gather()."""
    count = 0
    try:
        if _COUNTER_PATH.is_file():
            count = int(_COUNTER_PATH.read_text().strip())
    except (ValueError, OSError):
        pass
    count += 1
    try:
        _COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _COUNTER_PATH.write_text(str(count))
    except OSError as exc:
        logger.warning("[bridge] Could not write startup counter: %s", exc)

    parts: list[str] = []
    if count == 1 or count % 5 == 0:
        parts.append("Welcome back, voice is ready.")
    if not VOICE_TOKEN:
        parts.append("Please add an API key in the Agentium dashboard to start using voice.")

    if parts:
        text = " ".join(parts)
        logger.info("[bridge] Startup guidance: %s", text)
        try:
            await speak(text)
        except Exception as exc:
            logger.warning("[WARN] Could not speak startup guidance: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd voice-bridge && python -m pytest tests/test_startup_guidance.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add voice-bridge/main.py voice-bridge/tests/test_startup_guidance.py
git commit -m "feat(voice-bridge): add startup counter and guidance speech function"
```

---

### Task 2: Token-Wait Event + Wiring

**Files:**
- Modify: `voice-bridge/main.py` — add `_token_ready` event, wire into `_main()`, `_run_voice_loop_once()`, `_ws_handler()`

**Interfaces:**
- Consumes: `_token_ready` asyncio.Event, `_maybe_speak_startup_messages()` from Task 1
- Produces: gated voice loop, WS-triggered resume

- [ ] **Step 1: Write the failing tests**

Add to `voice-bridge/tests/test_startup_guidance.py`:

```python
def test_token_ready_set_immediately_when_token_present():
    """VOICE_TOKEN present → _token_ready is set in _main()."""
    bridge._token_ready = asyncio.Event()
    with patch.object(bridge, "VOICE_TOKEN", "some-token"):
        with patch.object(bridge, "_maybe_speak_startup_messages"):
            with patch.object(bridge, "asyncio") as mock_asyncio:
                mock_asyncio.gather = MagicMock()
                if bridge.VOICE_TOKEN:
                    bridge._token_ready.set()
                assert bridge._token_ready.is_set()


def test_token_ready_unset_when_token_empty():
    """VOICE_TOKEN empty → _token_ready not set in _main()."""
    bridge._token_ready = asyncio.Event()
    with patch.object(bridge, "VOICE_TOKEN", ""):
        with patch.object(bridge, "_maybe_speak_startup_messages"):
            with patch.object(bridge, "asyncio") as mock_asyncio:
                mock_asyncio.gather = MagicMock()
                if not bridge.VOICE_TOKEN:
                    pass  # leave event unset
                assert not bridge._token_ready.is_set()


def test_ws_set_token_sets_event():
    """WS set_token message → _token_ready.set() called."""
    bridge._token_ready = asyncio.Event()
    def handle_set_token():
        bridge._set_voice_token("new-token")
        bridge._token_ready.set()
    handle_set_token()
    assert bridge._token_ready.is_set()
    assert bridge.VOICE_TOKEN == "new-token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd voice-bridge && python -m pytest tests/test_startup_guidance.py -v`
Expected: some tests fail (AttributeError for _token_ready or voice-loop wiring)

- [ ] **Step 3: Add `_token_ready` event**

Add at module level, after `_COUNTER_PATH` (after the code from Task 1):

```python
_token_ready: Optional["asyncio.Event"] = None
```

- [ ] **Step 4: Wire `_token_ready` into `_main()`**

Modify the `_main()` function. Find the existing startup log block (around line 1405–1420) and add after it, before the `asyncio.gather()`:

```python
async def _main() -> None:
    logger.info("=" * 60)
    # ... existing log lines stay untouched ...

    # ── Startup guidance + token gating ─────────────────────────────────────
    await _maybe_speak_startup_messages()
    global _token_ready
    _token_ready = asyncio.Event()
    if VOICE_TOKEN:
        _token_ready.set()

    # B5: each subsystem is supervised independently
    await asyncio.gather(
        _supervise("ws-server", _run_ws_server_once),
        _supervise("voice-loop", _run_voice_loop_once),
        _supervise("backend-ws", lambda: _run_backend_ws(ProactiveAnnouncer())),
    )
```

- [ ] **Step 5: Wire `_token_ready.wait()` into `_run_voice_loop_once()`**

Add at the very top of `_run_voice_loop_once()`, before the existing `logger.info("[bridge] Voice loop started")`:

```python
async def _run_voice_loop_once() -> None:
    # Wait for a voice token before starting the mic loop
    if _token_ready is not None:
        await _token_ready.wait()
    logger.info("[bridge] Voice loop started")
    # ... rest of existing function stays unchanged ...
```

- [ ] **Step 6: Wire `_token_ready.set()` into the WS handler**

In `_ws_handler()`, find the `set_token` branch (around line 926–930). After the existing `_set_voice_token(token)`, add a `_token_ready.set()` call:

```python
            if isinstance(msg, dict) and msg.get("type") == "set_token":
                token = msg.get("token")
                if token:
                    _set_voice_token(token)
                    if _token_ready is not None:
                        _token_ready.set()
                    await _broadcast({"type": "voice_token_set", "ts": time.time()})
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd voice-bridge && python -m pytest tests/test_startup_guidance.py -v`
Expected: all tests PASS

- [ ] **Step 8: Run existing tests to confirm no regressions**

Run: `cd voice-bridge && python -m pytest tests/ -v`
Expected: all existing tests still PASS

- [ ] **Step 9: Commit**

```bash
git add voice-bridge/main.py voice-bridge/tests/test_startup_guidance.py
git commit -m "feat(voice-bridge): add token-wait event and startup wiring"
```
