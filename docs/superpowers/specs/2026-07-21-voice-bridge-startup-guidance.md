# Voice Bridge — Startup Guidance Messages

**Date:** 2026-07-21
**Status:** Approved design
**Domain:** voice-bridge

## Problem

When a user installs the Agentium Voice Bridge and runs it for the first time,
the bridge starts silently and only responds *after* a wake word is spoken and
a backend query fails. There is no acknowledgment that the bridge is working,
and no guidance when the bridge cannot proceed because no API key has been
configured.

## States

The bridge is always in exactly one of three states:

```
STARTUP
  ├─ Startup counter % 5 == 0?
  │    → speak "Welcome back, voice is ready."
  │
  ├─ VOICE_TOKEN empty?
  │    → speak "Please add an API key in the Agentium dashboard to start using voice."
  │    → WAITING state (WS server alive, voice loop paused on asyncio.Event)
  │
  └─ VOICE_TOKEN present?
       → READY state (voice loop + WS server both running — existing behavior)
```

Transitions:
- `STARTUP → WAITING` when no token
- `WAITING → READY` when `set_token` arrives via local WS
- `STARTUP → READY` when token already present

## Design

### 1. Startup Counter File

A sentinel file at `~/.agentium/.voice-startup-count` containing a single
decimal integer (the number of times the bridge has started).

- On startup, read the file. If absent, treat as count = 0.
- Increment count.
- If count == 1 (first ever run) or count % 5 == 0: speak the welcome message.
- Write the updated count back to the file.

No other state is stored in this file.

### 2. Guidance Messages

All messages are spoken via the existing `speak()` / TTS path. If TTS is not
available, the text is logged as a fallback (identical to the existing
`_speak_fallback` pattern).

| Condition | Utterance |
|---|---|
| First run + token present | "Welcome back, voice is ready." |
| First run + no token | "Welcome back, voice is ready. Please add an API key in the Agentium dashboard to start using voice." |
| Subsequent, every 5th run + token present | "Welcome back, voice is ready." |
| Subsequent, every 5th run + no token | "Welcome back, voice is ready. Please add an API key in the Agentium dashboard to start using voice." |
| Subsequent, non-5th-run + no token | "Please add an API key in the Agentium dashboard to start using voice." |

The welcome and guidance messages are combined into a single utterance when
both conditions trigger, so the user hears one coherent sentence rather than
two separate announcements.

### 3. Token-Wait Event

A module-level `asyncio.Event` (`_token_ready`) gates the voice loop:

- **At startup in `_main()`**: if `VOICE_TOKEN` is present, set `_token_ready`
  immediately. If absent, leave it unset.
- **In `_run_voice_loop_once()`**: at the top (before any mic logic), await
  `_token_ready.wait()`. The supervisor wrapping this coroutine keeps the
  subsystem alive but the wait blocks until the event fires.
- **In the WS `_ws_handler`**: when a `{"type": "set_token", "token": "..."}`
  message arrives, after the existing `_set_voice_token()` call, also call
  `_token_ready.set()`. This unblocks the voice loop.

### 4. Speaking Location

All startup speech happens in `_main()`, **before** `asyncio.gather()` launches
the three supervisors (ws-server, voice-loop, backend-ws). This ensures:

- TTS / `speak()` is importable (no heavy deps needed at this point — `pyttsx3`
  init is lazy and inside `_get_tts()`).
- If `speak()` fails (TTS not installed), the text is still logged so the user
  can see it in the bridge log.

### 5. Files Changed

Only one file is modified:

**`voice-bridge/main.py`**

Additions:
- Module-level `_token_ready: asyncio.Event = None` (initialized in `_main()`)
- `_maybe_speak_startup_messages()` — reads counter file, speaks
  welcome/guidance combination, writes counter back
- In `_main()`, call `_maybe_speak_startup_messages()` before `asyncio.gather()`
- In `_main()`, set or leave `_token_ready` based on token presence
- In `_ws_handler` `set_token` branch, add `_token_ready.set()`
- In `_run_voice_loop_once`, add `await _token_ready.wait()` at the top

No backend changes, no new files, no new dependencies.

## Out of Scope

- No changes to the wake-word detection, session management, STT, TTS, or
  browser sync logic.
- No backend changes (the guidance is purely a host-side UX improvement).
- No UI changes (the desktop HUD is unaffected).
- No changes to the install scripts or Docker services.
