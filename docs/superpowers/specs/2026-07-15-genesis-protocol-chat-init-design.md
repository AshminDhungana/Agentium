# Genesis Protocol & Chat Initialization — Design

**Date:** 2026-07-15
**Status:** Approved (design)
**Scope:** Frontend WebSocket status model + Chat header + backend genesis-status fail-fast

## Problem

After a user logs in, opens the Models page, and adds an API key, the Genesis
Protocol runs and the chat page should switch to "Active". Two user-visible
symptoms, plus a cluster of latent bugs, were reported:

1. **Slow / refresh-required activation.** After the key is added, the chat page
   takes a long time to become active, and the whole site must be refreshed
   before the status flips to "Active".
2. **Ugly "System is initializing" notice.** The notice renders multiple
   duplicated indicators and shows the initializing message in red like a
   failure.
3. General claim of "many problems" with the genesis protocol.

An end-to-end trace found **10 distinct problems (P1–P10)**, all rooted in a
single structural flaw: **there is no single source of truth for connection /
genesis status.** Status is smeared across `isConnected`, `isConnecting`,
`error`, `_genesisPollActive`, and `_genesisWaitingForApiKey`, which overlap and
can be set into mutually contradictory combinations.

## Root-Cause Catalogue

| # | Problem | Root cause & evidence |
|---|---------|----------------------|
| P1 | Must refresh to go Active | On poll `complete`, `_pollGenesisStatus` calls `connect()` exactly once (`websocketStore.ts:429-434`); a 1s reconnect debounce (`MIN_CONNECT_INTERVAL_MS`, `:480-484`) silently swallows it with no retry. Store left stuck; only a full-page refresh recovers. |
| P2 | Duplicate indicators | Three indicators render at once: subtitle "Initializing…" (`ChatPage.tsx:889`), red error banner (`:912-914`), and "Connecting…" spinner (`:921-925`). |
| P3 | Silent "waiting for key" trap | Only `notifyApiKeyAdded()` (`ModelsPage.tsx:163`) can exit `_genesisWaitingForApiKey` (`websocketStore.ts:467-470, 581-589`). If missed, permanent stall until refresh. |
| P4 | Dead genesis-trigger code | `useModelConfigs.ts` clears `sessionStorage['genesis_check_done']` and comments reference a `useGenesisCheck` hook that **does not exist**. Genesis actually fires from the backend (`trigger_genesis_if_needed`). Dead + misleading. |
| P5 | Transient `not_started` kills poll | Poll `not_started` branch (`websocketStore.ts:436-442`) re-arms `_genesisWaitingForApiKey` and stops polling. A transient response (DB read lag after key commit) permanently silences the client. |
| P6 | Reconnect button hidden | Button gated on `!isConnected && !isConnecting` (`ChatPage.tsx:915-920`), but `isConnecting` is forced `true` throughout genesis — no in-app escape. |
| P7 | No reconnect fallback | Single `connect()` on completion, no watchdog/retry (`websocketStore.ts:429-434`). |
| P8 | Initializing shown as error (red) | Progress message pushed into `error` state (`websocketStore.ts:576-579, 655-657`), rendered `text-red-600` (`ChatPage.tsx:912-914`). |
| P9 | Failed genesis polls 5 min | `/ws/genesis-status` (`websocket.py:642-654`) cannot report failure — a crashed genesis (`initialization_service.py:1169-1179`) only logs + broadcasts to already-connected clients. Failure reads as `running` forever. |
| P10 | "Connecting…" leaks pre-key | `system_not_ready` and 1013 branches never clear `isConnecting`, so a perpetual "Connecting…" shows even before any key is added. |

## Approach (Chosen)

**Approach A — Single `connectionPhase` enum state machine.** Replace the
overlapping booleans with one explicit phase field that is the sole source of
truth. This makes illegal states unrepresentable and structurally prevents the
whole symptom class from recurring.

Rejected alternatives:
- **B — Keep booleans + a `deriveStatus()` selector.** Smaller diff but leaves
  the contradictory source-of-truth fields intact.
- **C — XState.** New dependency, overkill for ~6 states, doesn't match the
  existing Zustand pattern.

## Design

### 1. Phase state machine (frontend `websocketStore.ts`)

Add one field as the single source of truth:

```ts
type ConnectionPhase =
  | 'offline'          // no socket, nothing in progress
  | 'connecting'       // WS handshake in flight
  | 'waiting_for_key'  // server said not_ready, genesis_triggered=false
  | 'genesis_running'  // genesis in progress; polling /ws/genesis-status
  | 'genesis_failed'   // backend reported failure (P9)
  | 'active';          // system message received, chat live
```

Rules:
- `connectionPhase` is the **only** field `ChatPage` reads to choose the
  header/indicator.
- `isConnected` / `isConnecting` become **derived getters**
  (`phase === 'active'` / `phase === 'connecting'`). Kept for backward
  compatibility so existing `useWebSocketStore` consumers don't break; nothing
  sets them directly anymore. This keeps the blast radius inside the store + the
  ChatPage header.
- `error` reverts to **real failures only** (network error, auth failure,
  genesis-failed reason). Genesis *progress* never touches `error`.
- `_genesisWaitingForApiKey` and `_genesisPollActive` are absorbed into the phase
  (`waiting_for_key` / `genesis_running`), eliminating contradictory flags.

Transition table (single reducer-like place in the store):

| Event | New phase |
|-------|-----------|
| `connect()` starts | `connecting` |
| `system` msg received | `active` |
| `system_not_ready`, `genesis_triggered=false` | `waiting_for_key` |
| `system_not_ready`, `genesis_triggered=true` | `genesis_running` (start poll) |
| poll → `complete` | `connecting` (debounce-exempt reconnect) |
| poll → `failed` | `genesis_failed` |
| poll → `not_started` **after** key added | stay `genesis_running` (grace window) |
| `notifyApiKeyAdded()` | `connecting` (leave `waiting_for_key`) |
| socket closes / error | `offline` (or `genesis_failed` if terminal) |

### 2. Bug fixes mapped onto the machine

| # | Fix |
|---|-----|
| P1 | On poll `complete`: set phase `connecting` and reconnect via a **debounce-exempt** path (bypass `MIN_CONNECT_INTERVAL_MS` for genesis-completion reconnects; if still debounced, schedule a retry `setTimeout`). No transition may end in a dead state. |
| P2/P8/P10 | `ChatPage` renders **exactly one** indicator via `switch(phase)`. `genesis_running` → neutral blue "Initializing…" (not red). Red `error` text only for real-failure phases. `connecting` spinner only in `connecting`. |
| P3 | `waiting_for_key` exitable by both `notifyApiKeyAdded()` and the P7 watchdog — not solely one call site. |
| P5 | While phase is `genesis_running`, a `not_started` poll response does **not** re-arm `waiting_for_key`; treat as "keep polling" for a grace window of the first 5 attempts (~10s, covering DB read lag after key commit). Only after the grace window does a sustained `not_started` transition back to `waiting_for_key`. |
| P6 | Reconnect button visibility gated on `phase === 'offline' \|\| phase === 'genesis_failed'`. |
| P7 | After poll `complete` → `connecting`, add a bounded watchdog: if not `active` within ~5s, retry `connect()`. Removes total dependence on one call succeeding. |
| P9 | Backend `/ws/genesis-status` returns `{status:"failed", reason}` on failure; frontend poll → `failed` sets phase `genesis_failed`, shows real error + Retry. |
| P4 | Remove `useGenesisCheck` references, the `genesis_check_done` sessionStorage guard, and misleading comments in `useModelConfigs.ts`. Rely on the backend trigger + the new fail-fast signal. |

Happy-path data flow after fixes (no refresh, ever):
key saved → backend triggers genesis + `notifyApiKeyAdded()` → phase
`connecting` → server `system_not_ready(triggered=true)` → phase
`genesis_running`, poll starts → poll `complete` → phase `connecting`
(debounce-exempt) → `system` msg → phase `active`.

Error flow: genesis backend failure → poll `failed` → phase `genesis_failed` →
red error + Retry button (fresh `connect()`). Watchdog covers the
"reconnect didn't take" gap. The 5-minute give-up cap
(`GENESIS_POLL_MAX_ATTEMPTS`) stays as a final backstop but should rarely be hit.

### 3. Backend fail-fast (P9)

The genesis-status endpoint (`websocket.py:642-654`) currently infers status
only from "does Head 00001 exist + does a key exist" — it has no knowledge of
failure. Record genesis state in **Redis** (already a core dependency, shared
across workers so the worker that serves the poll sees state written by the
worker that ran genesis):

| Point in `_run_genesis` (`initialization_service.py`) | Redis write |
|---|---|
| task start (~line 1146) | `genesis:state = {phase:"running", started_at}` |
| success (~line 1149) | `genesis:state = {phase:"complete"}` |
| exception (~line 1170) | `genesis:state = {phase:"failed", reason, failed_at}` |

`genesis_status` endpoint resolves with this precedence:
1. Head 00001 exists → `complete` (authoritative; unchanged).
2. Redis `phase == "failed"` → `{status:"failed", reason}`.
3. key exists (Redis `running` or config present) → `running`.
4. else → `not_started`.

The Redis key carries a TTL (~1h) so a stale failure doesn't block a later
legitimate retry. `trigger_genesis_if_needed` overwrites it to `running` on each
new trigger, so a retry after failure works cleanly.

## Component Boundaries

- **`websocketStore.ts`** — owns `connectionPhase`, all transitions, polling, and
  the debounce-exempt reconnect + watchdog. Exposes derived `isConnected` /
  `isConnecting` getters. Single source of truth for status.
- **`ChatPage.tsx` header** — pure presentation: one `switch(phase)` → one
  indicator + conditional Reconnect/Retry button. Reads phase; sets nothing.
- **`useModelConfigs.ts`** — key save + `notifyApiKeyAdded()`; dead genesis-guard
  code removed.
- **`/ws/genesis-status` (backend)** — reports `complete | failed | running |
  not_started` from Head existence + Redis genesis state.
- **`_run_genesis` (backend)** — writes genesis lifecycle state to Redis.

## Testing

- **Backend (pytest, `backend/tests/`)** — unit-test `genesis_status` precedence
  for all four states across Head present/absent × Redis running/failed/absent.
  Failure path asserts `{status:"failed", reason}`.
- **Frontend (Vitest, `unit` project — already configured)** — unit-test the
  phase-machine transitions (reducer) covering every row of the transition table,
  including P1 (debounce-exempt reconnect), P5 (grace window), P9 (`failed`).
- **Manual reproduction** — two scenarios on a fresh instance:
  1. login → add valid key → chat flips to **Active without refresh**.
  2. login → add invalid/failing key → **`genesis_failed` + Retry** appears within
     seconds, not 5 minutes.

## Out of Scope

- No unrelated refactoring of `websocketStore` beyond the phase migration.
- No change to the genesis protocol's governance/voting logic itself.
- No new frontend state-management library.
