# Fix Genesis Setup Sequence Ordering (todo §4.1)

- **Date:** 2026-07-19
- **Priority:** P1
- **Status:** approved

## Problem

On a fresh install the nation-naming popup renders before the Head of Council
is "active" in the UI, and no Head reply appears in the chat immediately after
the name is submitted. The documented correct order is:

> API key added → Head of Council connects → welcome message → nation-naming
> popup appears → reply is given after naming.

## Root cause

The chat WebSocket is gated on Head `00001` existing **and being committed**.
In `backend/services/initialization_service.py::run_genesis_protocol` the entire
protocol — Head, Council, Lead, constitution, the naming prompt, and the reply —
runs inside a single transaction that only commits at the very end (line 576).
The WS handshake's `authenticate()` (`backend/api/routes/websocket.py:142`)
queries Head in a *separate* DB session, so it cannot see the uncommitted Head
and closes the socket with `1013` ("Genesis in progress").

Because no socket can connect until genesis fully completes, the frontend never
opens the live chat until `genesis-status` returns `complete`
(`frontend/src/store/websocketStore.ts` `_pollGenesisStatus`). During the whole
naming step the socket is dead and the dashboard is only *polling*:

1. **Popup before Head active** — `GenesisNameModal` renders the instant the
   poll sees `awaiting_name` (`websocketStore.ts:504`), i.e. over a
   disconnected chat. Head is not yet "active" in the UI.
2. **No live reply after naming** — the reply from
   `_notify_country_name_decision` (`initialization_service.py:514`) is
   broadcast while still no socket is connected, so it is lost. It only returns
   via the post-`complete` `_replay_genesis_welcome` + ChatPage history reload,
   which is fragile and delayed.

Both symptoms share this single root cause (and the same one as the
"Genesis doesn't run after API key is added" report: the chat never comes alive
during genesis).

## Fix

### Backend — commit structural agents early
In `run_genesis_protocol`, add `self.db.commit()` immediately after the default
Lead is created (step 2b) and **before** `_prompt_for_country_name` (step 3).
Head / Council / Lead then become visible to the WS handshake's separate
session, so the chat can connect during the naming step.

- A failure *before* this commit still rolls back the whole transaction and
  leaves `is_system_initialized()` False, so genesis can be retried cleanly.
- The existing independent welcome-message commit
  (`_persist_head_message`, own session) already accepts the small
  partial-state risk for steps after the commit; nothing new is introduced.

In the `TESTING` environment keep the existing flush-only behavior (no commit)
so test fixtures' savepoints still roll back.

### Frontend — connect the live socket when naming starts
In `websocketStore.ts` `_pollGenesisStatus`: when `data.status === 'awaiting_name'`,
call `_connectNow()` (it is a no-op if the socket is already open/connecting).
This opens the live chat behind the modal so Head is "active" before the popup
is shown to the user.

### Frontend — stop phase regression during naming
In `connectionPhase.ts` `nextPhase`, handle a `poll` event with status
`awaiting_name`: if the current phase is already `active` or `connecting`,
preserve it (return `current`) instead of falling through to `genesis_running`.
Without this, each subsequent `awaiting_name` poll would regress the phase and
could tear down the just-opened socket.

The post-naming reply is then delivered live on the open socket. The backend's
`_replay_genesis_welcome` re-broadcasts the same persisted `message_id` after
`complete`; ChatPage's existing `message_id` dedup (`ChatPage.tsx:337`) prevents
a duplicate.

## Acceptance criteria

- On a fresh install the sequence occurs in the documented order every time.
- The nation-naming popup only renders once the chat/Head is confirmed active.
- Submitting the nation name always produces a visible Head reply in the chat
  (delivered live on the open socket).

## Tests

- Backend unit test: `run_genesis_protocol` commits the transaction (Head
  visible) before it reaches the country-name prompt; a pre-prompt failure still
  rolls back.
- Frontend store test: a poll reporting `awaiting_name` transitions the store to
  connect (or keeps it connected) without regressing `active` → `genesis_running`.
