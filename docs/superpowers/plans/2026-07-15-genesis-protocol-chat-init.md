# Genesis Protocol & Chat Initialization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the overlapping WebSocket status booleans with a single `connectionPhase` state machine so chat activates without a page refresh, shows exactly one non-red "initializing" indicator, and surfaces genesis failures in seconds.

**Architecture:** A pure `nextPhase(current, event)` reducer in `src/store/connectionPhase.ts` is the single source of truth. `websocketStore.ts` holds `connectionPhase` and derives `isConnected`/`isConnecting` from it; `ChatPage.tsx` renders one `switch(phase)` indicator. The backend records genesis lifecycle state in Redis so `/ws/genesis-status` can report `failed`.

**Tech Stack:** React 18 + TypeScript + Zustand (frontend); Vitest v4 (`unit` project, jsdom) for frontend tests; FastAPI + SQLAlchemy + `redis.asyncio` (backend); pytest for backend tests.

## Global Constraints

- Single source of truth for status MUST be `connectionPhase`; `error` holds only real failures (never genesis progress). (Spec §1)
- `isConnected`/`isConnecting` remain as **derived** getters for backward compatibility; nothing sets them directly. (Spec §1)
- Reconnect after poll `complete` MUST bypass the 1s `MIN_CONNECT_INTERVAL_MS` debounce or retry on a timer — never end in a dead state. (Spec §2, P1)
- While phase is `genesis_running`, a transient `not_started` poll response MUST NOT re-arm the waiting state for the first 5 attempts (`GENESIS_GRACE_ATTEMPTS`). (Spec §2, P5)
- `_run_genesis` MUST write `genesis:state` to Redis (running → complete/failed) with a TTL (~1h). (Spec §3)
- `genesis_status` precedence: Head exists → `complete`; Redis `failed` → `failed`; key exists → `running`; else `not_started`. (Spec §3)
- Frontend test command: `cd frontend && npm test` (runs `vitest run --project unit`). Frontend typecheck/build: `cd frontend && npm run build` (`tsc && vite build`). Lint: `cd frontend && npm run lint`.
- Backend test command: `cd backend && pytest tests/unit/test_genesis_status.py -v` (pytest config in `backend/pytest.ini`, `testpaths = tests`).

---

## File Structure

- **Create `frontend/src/store/connectionPhase.ts`** — pure phase type, `PhaseEvent` union, `nextPhase()` reducer, derived predicates (`isActive`, `isConnectingPhase`, `canReconnect`, `isGenesisProgress`), and `phaseFromGenesisStatus()`. No React/store imports.
- **Create `frontend/src/store/connectionPhase.test.ts`** — unit tests for the reducer (Spec §3 transition table).
- **Modify `frontend/src/store/websocketStore.ts`** — add `connectionPhase` + `_genesisGraceCount` state; convert `_setConnected`/`_setConnecting` to derived getters; add `_transition(event)`/`_connectNow()`/`_genesisWatchdog()`; rewrite `connect`, `_pollGenesisStatus`, `system_not_ready`/`onclose` handlers to use the phase; remove `_genesisWaitingForApiKey`/`_genesisPollActive` writes in favor of phase.
- **Create `frontend/src/store/websocketStore.test.ts`** — store-level tests for P1/P5/P9 transitions via the public API.
- **Modify `frontend/src/services/websocketReplay.ts`** — `GenesisStatusResponse.status` union gains `'failed'`.
- **Modify `frontend/src/pages/ChatPage.tsx:198-925`** — replace boolean status block with `switch(connectionPhase)`; gate Reconnect button on `canReconnect(phase)`.
- **Modify `frontend/src/hooks/useModelConfigs.ts`** — remove dead `GENESIS_SESSION_KEY` + `useGenesisCheck` references/comments (P4).
- **Modify `frontend/vite.config.ts:50-55`** — add `'src/store/**/*.test.{ts,tsx}'` to the `unit` project `include`.
- **Modify `backend/services/initialization_service.py:1142-1181`** — write `genesis:state` to Redis at start/success/failure.
- **Modify `backend/api/routes/websocket.py:627-654`** — read Redis `genesis:state`, return `failed` when applicable; import `get_redis_client`.
- **Create `backend/tests/unit/test_genesis_status.py`** — pytest for the endpoint precedence.

---

### Task 1: Pure `connectionPhase` reducer + tests

**Files:**
- Create: `frontend/src/store/connectionPhase.ts`
- Test: `frontend/src/store/connectionPhase.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `ConnectionPhase`, `PhaseEvent`, `nextPhase(current, event, opts?)`, `isActive(phase)`, `isConnectingPhase(phase)`, `canReconnect(phase)`, `isGenesisProgress(phase)`, `phaseFromGenesisStatus(status, opts?)`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/store/connectionPhase.test.ts
import { describe, it, expect } from 'vitest';
import {
  nextPhase, isActive, isConnectingPhase, canReconnect, isGenesisProgress,
  phaseFromGenesisStatus, ConnectionPhase, PhaseEvent,
} from './connectionPhase';

describe('connectionPhase reducer', () => {
  it('connect start -> connecting', () => {
    expect(nextPhase('offline', { type: 'connect_start' })).toBe('connecting');
  });
  it('system message -> active', () => {
    expect(nextPhase('connecting', { type: 'system' })).toBe('active');
  });
  it('system_not_ready with key -> genesis_running', () => {
    expect(nextPhase('connecting', { type: 'system_not_ready', genesisTriggered: true })).toBe('genesis_running');
  });
  it('system_not_ready without key -> waiting_for_key', () => {
    expect(nextPhase('connecting', { type: 'system_not_ready', genesisTriggered: false })).toBe('waiting_for_key');
  });
  it('poll complete -> connecting', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'complete' })).toBe('connecting');
  });
  it('poll failed -> genesis_failed', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'failed' })).toBe('genesis_failed');
  });
  it('poll running stays genesis_running (P1/P5 path)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'running' })).toBe('genesis_running');
  });
  it('poll not_started within grace window stays genesis_running (P5)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'not_started' }, { graceCount: 2 })).toBe('genesis_running');
  });
  it('poll not_started after grace window -> waiting_for_key (P5)', () => {
    expect(nextPhase('genesis_running', { type: 'poll', status: 'not_started' }, { graceCount: 5 })).toBe('waiting_for_key');
  });
  it('notifyApiKeyAdded leaves waiting_for_key -> connecting', () => {
    expect(nextPhase('waiting_for_key', { type: 'notify_key_added' })).toBe('connecting');
  });
  it('socket close from genesis_running stays genesis_running (poll owns reconnect)', () => {
    expect(nextPhase('genesis_running', { type: 'socket_close', code: 1013 })).toBe('genesis_running');
  });
  it('socket close (1000) -> offline', () => {
    expect(nextPhase('active', { type: 'socket_close', code: 1000 })).toBe('offline');
  });
  it('socket close (4001) -> genesis_failed (terminal auth error)', () => {
    expect(nextPhase('connecting', { type: 'socket_close', code: 4001 })).toBe('genesis_failed');
  });
});

describe('derived predicates', () => {
  it('isActive', () => {
    expect(isActive('active')).toBe(true);
    expect(isActive('connecting')).toBe(false);
  });
  it('isConnectingPhase', () => {
    expect(isConnectingPhase('connecting')).toBe(true);
    expect(isConnectingPhase('genesis_running')).toBe(false);
  });
  it('canReconnect only in offline/genesis_failed', () => {
    expect(canReconnect('offline')).toBe(true);
    expect(canReconnect('genesis_failed')).toBe(true);
    expect(canReconnect('connecting')).toBe(false);
    expect(canReconnect('genesis_running')).toBe(false);
  });
  it('isGenesisProgress only in genesis_running', () => {
    expect(isGenesisProgress('genesis_running')).toBe(true);
    expect(isGenesisProgress('genesis_failed')).toBe(false);
  });
  it('phaseFromGenesisStatus maps statuses', () => {
    expect(phaseFromGenesisStatus('complete')).toBe('connecting');
    expect(phaseFromGenesisStatus('failed')).toBe('genesis_failed');
    expect(phaseFromGenesisStatus('running')).toBe('genesis_running');
    expect(phaseFromGenesisStatus('not_started')).toBe('genesis_running'); // grace handled by store
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/store/connectionPhase.test.ts`
Expected: FAIL — `connectionPhase.ts` does not exist / exports missing.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/store/connectionPhase.ts
export type ConnectionPhase =
  | 'offline'
  | 'connecting'
  | 'waiting_for_key'
  | 'genesis_running'
  | 'genesis_failed'
  | 'active';

export type PhaseEvent =
  | { type: 'connect_start' }
  | { type: 'system' }
  | { type: 'system_not_ready'; genesisTriggered: boolean }
  | { type: 'poll'; status: 'complete' | 'failed' | 'running' | 'not_started' }
  | { type: 'notify_key_added' }
  | { type: 'socket_close'; code: number };

export const GENESIS_GRACE_ATTEMPTS = 5;

export interface NextPhaseOpts {
  /** Number of consecutive not_started poll responses so far. */
  graceCount?: number;
}

export function nextPhase(
  current: ConnectionPhase,
  event: PhaseEvent,
  opts: NextPhaseOpts = {},
): ConnectionPhase {
  switch (event.type) {
    case 'connect_start':
      return 'connecting';
    case 'system':
      return 'active';
    case 'system_not_ready':
      return event.genesisTriggered ? 'genesis_running' : 'waiting_for_key';
    case 'poll':
      if (event.status === 'complete') return 'connecting';
      if (event.status === 'failed') return 'genesis_failed';
      if (event.status === 'not_started') {
        const grace = opts.graceCount ?? 0;
        return grace < GENESIS_GRACE_ATTEMPTS ? 'genesis_running' : 'waiting_for_key';
      }
      return 'genesis_running';
    case 'notify_key_added':
      return current === 'waiting_for_key' ? 'connecting' : current;
    case 'socket_close':
      if (event.code === 1013) return current === 'genesis_running' ? 'genesis_running' : current;
      if (event.code === 4001) return 'genesis_failed';
      // 1000 clean close / 1006 lost / default -> offline (reconnect path decides next).
      return 'offline';
  }
}

export function isActive(phase: ConnectionPhase): boolean {
  return phase === 'active';
}
export function isConnectingPhase(phase: ConnectionPhase): boolean {
  return phase === 'connecting';
}
export function isGenesisProgress(phase: ConnectionPhase): boolean {
  return phase === 'genesis_running';
}
export function canReconnect(phase: ConnectionPhase): boolean {
  return phase === 'offline' || phase === 'genesis_failed';
}

export function phaseFromGenesisStatus(
  status: 'complete' | 'failed' | 'running' | 'not_started',
): ConnectionPhase {
  switch (status) {
    case 'complete': return 'connecting';
    case 'failed': return 'genesis_failed';
    case 'running': return 'genesis_running';
    case 'not_started': return 'genesis_running'; // grace window handled by store
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/store/connectionPhase.test.ts`
Expected: PASS (all 22 assertions).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/connectionPhase.ts frontend/src/store/connectionPhase.test.ts
git commit -m "feat(ws): add pure connectionPhase state-machine reducer"
```

---

### Task 2: Wire `connectionPhase` into `websocketStore.ts`

**Files:**
- Modify: `frontend/src/store/websocketStore.ts` (type decls `:80-155`, initial state `:187-218`, setters `:219-237`, `connect` `:456-509`, `_pollGenesisStatus` `:398-453`, `onmessage` system_not_ready `:561-591`, `onclose` `:620-681`, derived getters)

**Interfaces:**
- Consumes: `nextPhase`, `phaseFromGenesisStatus`, `GENESIS_GRACE_ATTEMPTS`, `canReconnect`, `isActive`, `isConnectingPhase` from `./connectionPhase`.
- Produces: store now exposes `connectionPhase` (used by `ChatPage`), derived `isConnected`/`isConnecting`, and behaves per the Spec transition table.

- [ ] **Step 1: Add `connectionPhase` + `_genesisGraceCount` to the type and initial state, and convert setters to derived getters**

In the `WebSocketState` interface (near `:80-155`), replace:
```ts
    isConnected: boolean;
    isConnecting: boolean;
```
with:
```ts
    /** Single source of truth for connection/genesis status. */
    connectionPhase: ConnectionPhase;
    /** Derived for backward compat — do not set directly. */
    isConnected: boolean;
    isConnecting: boolean;
    /** Consecutive not_started poll responses while genesis_running (P5 grace). */
    _genesisGraceCount: number;
```
Add to the interface near `_genesisPollActive` removal area:
```ts
    /** Internal: advance the state machine. */
    _transition: (event: PhaseEvent) => void;
    /** Internal: connect() that bypasses MIN_CONNECT_INTERVAL_MS (P1). */
    _connectNow: () => void;
    /** Internal: watchdog fired after poll-complete reconnect didn't reach active (P7). */
    _genesisWatchdog: () => void;
```

In the store creation body (near `:187-218`), replace:
```ts
    isConnected: false,
    isConnecting: false,
```
with:
```ts
    connectionPhase: 'offline',
    isConnected: false,
    isConnecting: false,
    _genesisGraceCount: 0,
```
Remove the `_genesisWaitingForApiKey: false,` and `_genesisPollActive: false,` initial-state lines (`:213`, `:215`) — phase replaces them.

Replace the setter definitions (`:220-222`):
```ts
    _setConnected: (connected) => set({ isConnected: connected }),
    _setConnecting: (connecting) => set({ isConnecting: connecting }),
```
with derived getters + new internal actions:
```ts
    // isConnected / isConnecting are DERIVED from connectionPhase (Spec §1).
    get isConnected() { return get().connectionPhase === 'active'; },
    get isConnecting() { return get().connectionPhase === 'connecting'; },

    _transition: (event) => {
        const cur = get().connectionPhase;
        const next = nextPhase(cur, event, { graceCount: get()._genesisGraceCount });
        if (next === cur) {
            if (cur === 'genesis_running' && event.type === 'poll' && event.status === 'not_started') {
                set({ _genesisGraceCount: get()._genesisGraceCount + 1 });
            }
            return;
        }
        set({ connectionPhase: next, _genesisGraceCount: 0 });
    },

    _connectNow: () => {
        // P1: bypass the MIN_CONNECT_INTERVAL_MS debounce used by public connect().
        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING || s._ws?.readyState === WebSocket.OPEN) return;
        set({ connectionPhase: 'connecting', _isManualDisconnect: false, _connectionStable: false });
        get()._openSocket();
    },
```

> **Callers of the old `_setConnected`/`_setConnecting` must also change** (they are removed):
> - In `_startHeartbeat` pong-timeout branch (`:342-343`): replace `get()._setConnected(false); get()._setConnecting(false);` with `set({ connectionPhase: 'offline' });`.
> - In `disconnect` (`:708-709`): replace `get()._setConnected(false); get()._setConnecting(false);` with `set({ connectionPhase: 'offline' });`.
> - In the `system` message handler (`:527-528`): replace `get()._setConnected(true); get()._setConnecting(false);` with `get()._transition({ type: 'system' });`.
> - In the `onclose` code `4001` branch comment (`:629`) and `1000`/`1006`/`default` branches: the `_setConnecting(false)` calls are removed because phase is now the source of truth (the `_transition({type:'socket_close', code})` already sets `offline`/`genesis_failed`). Delete those standalone `get()._setConnecting(false);` lines in those branches.


    _connectNow: () => {
        // P1: bypass the MIN_CONNECT_INTERVAL_MS debounce used by public connect().
        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING || s._ws?.readyState === WebSocket.OPEN) return;
        set({ connectionPhase: 'connecting', _isManualDisconnect: false, _connectionStable: false });
        get()._openSocket();
    },
```

- [ ] **Step 2: Extract the socket-open body into `_openSocket()` and rewrite `connect()`**

Replace `connect: () => { ... }` (`:456-688`, the whole function through its closing `},`) so the public `connect()` applies the debounce and delegates to `_openSocket()`, and `_connectNow` (defined above) calls `_openSocket` directly. Concretely:

Change the top of `connect` (`:472-509`) so it no longer sets phase directly and instead checks the debounce then calls `_openSocket`:

```ts
    connect: () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            get()._setError('No access token — please login');
            set({ connectionPhase: 'genesis_failed' });
            return;
        }

        // Silent wait: stay put until notifyApiKeyAdded() (Spec §1, P3 escape hatch).
        if (get().connectionPhase === 'waiting_for_key') {
            logger.debug('[WebSocket] connect() suppressed — waiting for API key');
            return;
        }

        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING || s._ws?.readyState === WebSocket.OPEN) return;

        const now = Date.now();
        if (now - s._lastConnectTime < WS_CONFIG.MIN_CONNECT_INTERVAL_MS) {
            logger.debug('[WebSocket] connect() called too soon — debounced');
            return;
        }
        set({ _lastConnectTime: now });
        set({ connectionPhase: 'connecting', _isManualDisconnect: false, _connectionStable: false });
        get()._openSocket();
    },
```

Then rename the existing socket-construction function (the body from `:491-509` onward that creates `new WebSocket(wsUrl)` and assigns handlers) to `_openSocket: () => {` — i.e. replace `try { const ws = new WebSocket(wsUrl); ...` and its enclosing `connect` wrapper with a new method `get()._openSocket`. Inside `_openSocket`, where the old code did `get()._setConnecting(true); get()._setError(null);` (`:487-488`), DELETE those two lines (phase is already `connecting`; error cleared by transitions). Keep everything else (handlers) identical.

- [ ] **Step 3: Rewrite `_pollGenesisStatus` for P1/P5/P7**

Replace the `_pollGenesisStatus` body (`:398-453`) with:
```ts
    _pollGenesisStatus: (attempt: number = 0) => {
        if (attempt === 0) {
            if (get().connectionPhase === 'genesis_running') { /* already polling */ }
        }

        if (attempt >= WS_CONFIG.GENESIS_POLL_MAX_ATTEMPTS) {
            logger.error('[WebSocket] Genesis poll exceeded max attempts — giving up');
            get()._setError(
                'System initialization is taking longer than expected. ' +
                'Please refresh or contact support if this persists.'
            );
            set({ connectionPhase: 'genesis_failed', _genesisGraceCount: 0 });
            return;
        }

        const poll = async () => {
            try {
                const data = await websocketReplayApi.pollGenesisStatus();
                if (data.status === 'complete') {
                    logger.debug('[WebSocket] Genesis complete — reconnecting now (debounce-exempt)');
                    get()._setError(null);
                    set({ _genesisPollTimeout: null, _genesisGraceCount: 0 });
                    // P1: use _connectNow so a 1s debounce can't swallow the only reconnect.
                    get()._connectNow();
                    // P7: watchdog — if we're still not active shortly, retry.
                    get()._genesisWatchdog();
                    return;
                }
                if (data.status === 'failed') {
                    // P9: backend reported failure — surface it instead of polling forever.
                    logger.error('[WebSocket] Genesis failed:', (data as any).reason);
                    set({ _genesisPollTimeout: null, _genesisGraceCount: 0 });
                    get()._transition({ type: 'poll', status: 'failed' });
                    get()._setError((data as any).reason
                        ? `Genesis failed: ${(data as any).reason}`
                        : 'Genesis failed. Please check your API key and try again.');
                    return;
                }
                // running or not_started (grace handled inside _transition)
                get()._transition({ type: 'poll', status: data.status });
            } catch (err) {
                logger.warn('[WebSocket] Genesis status poll failed, will retry:', err);
                get()._transition({ type: 'poll', status: 'running' });
            }

            const t = setTimeout(() => get()._pollGenesisStatus(attempt + 1), WS_CONFIG.GENESIS_POLL_INTERVAL_MS);
            set({ _genesisPollTimeout: t });
        };

        poll();
    },

    _genesisWatchdog: () => {
        // P7: if poll-complete reconnect didn't reach 'active' within 5s, retry once.
        setTimeout(() => {
            if (get().connectionPhase === 'genesis_running' || get().connectionPhase === 'connecting') {
                logger.warn('[WebSocket] Genesis watchdog — reconnect did not settle, retrying');
                get()._connectNow();
                get()._genesisWatchdog();
            }
        }, 5000);
    },
```
Add `get _genesisPollTimeout` cleanup: ensure `_stopGenesisPoll` (`:282-286`) now clears the timeout only (no flag):
```ts
    _stopGenesisPoll: () => {
        const s = get();
        if (s._genesisPollTimeout) { clearTimeout(s._genesisPollTimeout); set({ _genesisPollTimeout: null }); }
    },
```

- [ ] **Step 4: Rewrite `onmessage` `system_not_ready` (`:561-591`)**

Replace the block with:
```ts
                    if (data.type === 'system_not_ready') {
                        const triggered = data.genesis_triggered as boolean | undefined;
                        if (triggered) {
                            logger.warn('[WebSocket] system_not_ready — genesis in progress, polling status every 2s');
                            get()._transition({ type: 'system_not_ready', genesisTriggered: true });
                            get()._pollGenesisStatus();
                        } else {
                            logger.warn('[WebSocket] system_not_ready — no API key configured yet, staying silent');
                            get()._transition({ type: 'system_not_ready', genesisTriggered: false });
                            get()._setError(null);
                        }
                        return;
                    }
```
(Note: `error` is NOT set to the initializing message — P8. The `system` handler `:526-528` already calls `get()._setConnected(true); get()._setConnecting(false);`; replace those two lines with `get()._transition({ type: 'system' });`.)

- [ ] **Step 5: Rewrite `onclose` switch (`:620-681`)**

Replace the whole `onclose` so it uses `_transition` and never leaves `isConnecting` stuck:
```ts
            ws.onclose = (event) => {
                get()._clearAllTimers();
                set({ _ws: null, _connectionStable: false });

                let errorMsg: string | null = null;
                const code = event.code;
                if (code === 4001) {
                    errorMsg = 'Authentication failed — please log in again';
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                } else if (code === 1000 || code === 1006) {
                    if (code === 1006) errorMsg = 'Connection lost unexpectedly';
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                } else if (code === 1013) {
                    // Genesis poll owns reconnect; keep genesis_running.
                    get()._transition({ type: 'socket_close', code });
                    if (get().connectionPhase === 'genesis_running') {
                        get()._pollGenesisStatus();
                    }
                } else {
                    errorMsg = `Connection closed (${event.code})`;
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                }
                if (errorMsg) get()._setError(errorMsg);

                const isManual = get()._isManualDisconnect;
                if (!isManual && code !== 4001 && code !== 1013) {
                    get()._scheduleReconnect();
                }
            };
```

- [ ] **Step 6: Update `notifyApiKeyAdded` (`:229-237`)**

Replace with:
```ts
    notifyApiKeyAdded: () => {
        logger.debug('[WebSocket] API key added — re-attempting connection');
        get().disconnect(true);
        setTimeout(() => {
            get()._transition({ type: 'notify_key_added' });
            get().connect();
        }, 100);
    },
```

- [ ] **Step 7: Typecheck**

Run: `cd frontend && npm run build`
Expected: PASS (tsc compiles; no type errors from the new phase usage).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/store/websocketStore.ts
git commit -m "feat(ws): drive status from connectionPhase state machine"
```

---

### Task 3: Store-level tests for P1 / P5 / P9 transitions

**Files:**
- Create: `frontend/src/store/websocketStore.test.ts`

**Interfaces:**
- Consumes: `useWebSocketStore` public API (`setState`, `getState`, actions).
- Produces: regression coverage proving the store reaches `active` without manual refresh, tolerates transient `not_started`, and flips to `genesis_failed` on `failed`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/store/websocketStore.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWebSocketStore } from './websocketStore';

// jsdom has no real WebSocket; stub it so connect()/disconnect() don't throw.
class FakeWS {
  static readonly OPEN = 1; static readonly CONNECTING = 0; static readonly CLOSED = 3;
  readyState = FakeWS.CONNECTING;
  send = vi.fn();
  close = vi.fn(() => { this.readyState = FakeWS.CLOSED; });
  onopen: any; onclose: any; onerror: any; onmessage: any;
  constructor(public url: string) {
    setTimeout(() => { this.readyState = FakeWS.OPEN; this.onopen?.({}); }, 0);
  }
}
vi.stubGlobal('WebSocket', FakeWS as any);

beforeEach(() => {
  useWebSocketStore.setState({ connectionPhase: 'offline', _genesisGraceCount: 0, error: null });
});

describe('websocketStore phase', () => {
  it('connect_start -> connecting; system -> active (P2: no error used for progress)', () => {
    useWebSocketStore.getState()._transition({ type: 'connect_start' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('connecting');
    expect(useWebSocketStore.getState().isConnecting).toBe(true);
    useWebSocketStore.getState()._transition({ type: 'system' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('active');
    expect(useWebSocketStore.getState().isConnected).toBe(true);
  });

  it('transient not_started stays genesis_running within grace (P5)', () => {
    useWebSocketStore.getState()._transition({ type: 'system_not_ready', genesisTriggered: true });
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_running');
    for (let i = 0; i < 4; i++) {
      useWebSocketStore.getState()._transition({ type: 'poll', status: 'not_started' });
    }
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_running');
    // After grace exhausted, flips to waiting_for_key.
    useWebSocketStore.getState()._transition({ type: 'poll', status: 'not_started' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('waiting_for_key');
  });

  it('poll failed -> genesis_failed and is reconnectable (P9)', () => {
    useWebSocketStore.getState()._transition({ type: 'system_not_ready', genesisTriggered: true });
    useWebSocketStore.getState()._transition({ type: 'poll', status: 'failed' });
    expect(useWebSocketStore.getState().connectionPhase).toBe('genesis_failed');
    const { canReconnect } = require('./connectionPhase');
    expect(canReconnect('genesis_failed')).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/store/websocketStore.test.ts`
Expected: FAIL (import/published API differences — e.g. `_transition` or `_genesisGraceCount` not yet present if Task 2 incomplete).

- [ ] **Step 3: Confirm Task 2 implemented the same API, then run**

Run: `cd frontend && npm test -- src/store/websocketStore.test.ts`
Expected: PASS. (If any assertion mismatches the Task 2 wiring, adjust the store to match the reducer contract — do NOT weaken the test.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/store/websocketStore.test.ts
git commit -m "test(ws): cover P1/P5/P9 phase transitions in store"
```

---

### Task 4: Add `'failed'` to `GenesisStatusResponse`

**Files:**
- Modify: `frontend/src/services/websocketReplay.ts:12-14`

**Interfaces:**
- Consumes: nothing.
- Produces: `GenesisStatusResponse.status` allows `'failed'` (Task 5 store reads `data.reason`).

- [ ] **Step 1: Update the type (no separate test — covered by build + Task 5 usage)**

```ts
export interface GenesisStatusResponse {
    status: 'complete' | 'not_started' | 'running' | 'failed';
    reason?: string;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/websocketReplay.ts
git commit -m "feat(ws): accept 'failed' genesis status from backend"
```

---

### Task 5: Single indicator in `ChatPage.tsx` (P2/P6/P8/P10)

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:198-223` (selector) and `:881-925` (status block)

**Interfaces:**
- Consumes: `connectionPhase`, `error`, `reconnect` from `useWebSocketStore`; `canReconnect`, `isGenesisProgress`, `isActive` from `./store/connectionPhase`.
- Produces: exactly one status indicator; red `error` only in `genesis_failed`; Reconnect visible in `offline`/`genesis_failed`.

- [ ] **Step 1: Update the selector to pull `connectionPhase`**

Replace `:199-223` the destructure + selector with:
```ts
    const {
        connectionPhase, error,
        sendMessage: sendWsMessage,
        reconnect, connectionStats,
        unreadCount, markAsRead,
        messageHistory, lastMessage,
    } = useWebSocketStore(
        useShallow((s) => ({
            connectionPhase: s.connectionPhase,
            error: s.error,
            sendMessage: s.sendMessage,
            reconnect: s.reconnect,
            connectionStats: s.connectionStats,
            unreadCount: s.unreadCount,
            markAsRead: s.markAsRead,
            messageHistory: s.messageHistory,
            lastMessage: s.lastMessage,
        }))
    );
```
(Delete the old `isConnected`/`isConnecting`/`genesisInProgress` fields — `genesisInProgress` is now derived as `connectionPhase === 'genesis_running'`.)

- [ ] **Step 2: Replace the status `<p>` block (`:885-906`)**

Replace the inner `{activeTab === 'ai' ? (...)` ternary with a single `switch`-style render:
```tsx
                                        {activeTab === 'ai' ? (
                                            connectionPhase === 'active' ? (
                                                <span className="text-green-600 dark:text-green-400 font-medium">Active now</span>
                                            ) : connectionPhase === 'genesis_running' ? (
                                                <span className="text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1.5">
                                                    <LoadingSpinner size="sm" /> Initializing…
                                                </span>
                                            ) : connectionPhase === 'genesis_failed' ? (
                                                <span className="text-red-600 dark:text-red-400 font-medium">Initialization failed</span>
                                            ) : connectionPhase === 'connecting' ? (
                                                <span className="text-gray-600 dark:text-gray-500 flex items-center gap-1.5">
                                                    <LoadingSpinner size="sm" /> Connecting…
                                                </span>
                                            ) : (
                                                <span className="text-gray-600 dark:text-gray-500">Offline</span>
                                            )
                                        ) : activeTab === 'inbox' ? (
```
(Keep the inbox/file-browser branches and the latency suffix `:903-905` unchanged, but note it currently guards on `isConnected` — change to `connectionPhase === 'active'`.)

- [ ] **Step 3: Replace the right-side status cluster (`:910-925`)**

Replace lines `:912-925` (error text + reconnect button + connecting spinner) with:
```tsx
                                {activeTab === 'ai' && connectionPhase === 'genesis_failed' && error && (
                                    <span className="text-sm text-red-600 dark:text-red-400 max-w-xs truncate hidden sm:block">{error}</span>
                                )}
                                {activeTab === 'ai' && canReconnect(connectionPhase) && (
                                    <button onClick={reconnect}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-xl transition-all duration-150 flex items-center gap-2 shadow-sm">
                                        <RefreshCw className="w-4 h-4" /> Reconnect
                                    </button>
                                )}
```
(Deletes the standalone `isConnecting` spinner — `connecting` is now shown in the subtitle. `error` only renders red in `genesis_failed`.)

- [ ] **Step 4: Add import for `canReconnect`**

At the top of `ChatPage.tsx` near the other store import, add:
```ts
import { canReconnect, isGenesisProgress } from '@/store/connectionPhase';
```
(Use `isGenesisProgress` if any other code referenced `genesisInProgress`; otherwise `canReconnect` alone suffices. Grep for `genesisInProgress` after editing — if no remaining reference, drop `isGenesisProgress`.)

- [ ] **Step 5: Typecheck + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS (no unused `isConnected`/`isConnecting`/`genesisInProgress` references remain — fix any that surface).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "fix(chat): render single non-red status indicator from connectionPhase"
```

---

### Task 6: Remove dead genesis-trigger code (P4)

**Files:**
- Modify: `frontend/src/hooks/useModelConfigs.ts:1-29,155-181`

**Interfaces:**
- Consumes: nothing.
- Produces: misleading `useGenesisCheck`/`genesis_check_done` references gone; genesis still triggers via backend `trigger_genesis_if_needed`.

- [ ] **Step 1: Remove the dead constant + comments**

Delete `:14-19` (Genesis integration comment block) and `:28-29`:
```ts
// Session key shared with useGenesisCheck — cleared here after a key is saved.
const GENESIS_SESSION_KEY = 'genesis_check_done';
```

- [ ] **Step 2: Clean the `handleSave` comment + dead `removeItem`**

Replace `:155-181` the comment block + `sessionStorage.removeItem(GENESIS_SESSION_KEY);` so it no longer references the removed key:
```ts
    const handleSave = useCallback(async (config: ModelConfig) => {
        await loadConfigs();

        // The backend auto-triggers Genesis (trigger_genesis_if_needed) on key save;
        // the frontend needs no extra guard here.
        if (config.provider === 'openai') {
            try {
                const { voiceApi } = await import('@/services/voiceApi');
                voiceApi.clearStatusCache();
                showToast.success('Voice features now available with OpenAI provider!');
            } catch {
                // Non-critical — voice feature may not be available in this build
            }
        }
    }, [loadConfigs]);
```
Remove the now-unused `import { ... }` if `sessionStorage` usage elsewhere is absent (it isn't imported here, so just drop the dead lines).

- [ ] **Step 3: Typecheck + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS (no reference to `GENESIS_SESSION_KEY`/`useGenesisCheck` remains).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useModelConfigs.ts
git commit -m "refactor(models): drop dead useGenesisCheck session guard (P4)"
```

---

### Task 7: Backend records genesis lifecycle in Redis (P9)

**Files:**
- Modify: `backend/services/initialization_service.py:1142-1181` (`_run_genesis`)

**Interfaces:**
- Consumes: `get_redis_client` from `backend.core.redis` (already used elsewhere in backend).
- Produces: `genesis:state` Redis key set to `{phase:"running"}` → `{phase:"complete"}` or `{phase:"failed", reason}` with ~1h TTL; cleared/overwritten to `running` when `trigger_genesis_if_needed` fires.

- [ ] **Step 1: Write the Redis writes inside `_run_genesis`**

In `trigger_genesis_if_needed` (`:1119-1183`), at the start of `_run_genesis` (just inside `async def _run_genesis() -> None:`, after `:1145` `try:`), set running:
```python
    async def _run_genesis() -> None:
        """Run genesis."""
        from backend.models.database import get_db_context
        from backend.core.redis import get_redis_client
        _redis = get_redis_client()
        try:
            _redis.set(
                "genesis:state",
                json.dumps({"phase": "running", "started_at": datetime.utcnow().isoformat()}),
                ex=3600,
            )
            logger.info("🚀 Starting genesis protocol in background task...")
```
(Add `import json` at the top of the file if not already imported — verify with a grep; add near other stdlib imports.)

On success (after `:1149` `result = await ... run_genesis_protocol()` and the log at `:1150-1153`), before the broadcast, set complete:
```python
            _redis.set("genesis:state", json.dumps({"phase": "complete"}), ex=3600)
```
In the `except Exception as exc:` branch (`:1169-1179`), set failed:
```python
        except Exception as exc:
            logger.error("❌ Auto-genesis failed: %s", exc, exc_info=True)
            try:
                _redis.set(
                    "genesis:state",
                    json.dumps({
                        "phase": "failed",
                        "reason": str(exc),
                        "failed_at": datetime.utcnow().isoformat(),
                    }),
                    ex=3600,
                )
            except Exception as rexc:
                logger.warning(f"genesis:state redis write failed: {rexc}")
            try:
```
Also, in `trigger_genesis_if_needed` itself (right before `asyncio.create_task(_run_genesis())` at `:1181`), set running so a retry after a previous failure overwrites the stale `failed`:
```python
    try:
        get_redis_client().set(
            "genesis:state",
            json.dumps({"phase": "running", "started_at": datetime.utcnow().isoformat()}),
            ex=3600,
        )
    except Exception as rexc:
        logger.warning(f"genesis:state redis write failed: {rexc}")
    asyncio.create_task(_run_genesis())
```

- [ ] **Step 2: Typecheck (Python import sanity)**

Run: `cd backend && python -c "import backend.services.initialization_service"`
Expected: Module imports with no error.

- [ ] **Step 3: Commit**

```bash
git add backend/services/initialization_service.py
git commit -m "feat(genesis): record running/complete/failed state in Redis"
```

---

### Task 8: Backend `/ws/genesis-status` returns `failed` (P9)

**Files:**
- Modify: `backend/api/routes/websocket.py:21,627-654`

**Interfaces:**
- Consumes: `get_redis_client` from `backend.core.redis`; Redis key `genesis:state` written by Task 7.
- Produces: `GET /ws/genesis-status` returns `{status:"failed", reason}` when applicable; docstring updated.

- [ ] **Step 1: Add import + rewrite the endpoint**

Add to imports (`:21` area): `from backend.core.redis import get_redis_client` (the file already imports `redis.asyncio as redis` — keep that; this adds the helper).

Replace the function (`:627-654`) with:
```python
async def genesis_status(current_user=Depends(get_current_user)):
    """
    Lightweight HTTP status check for the genesis bootstrap process.

    Resolution precedence:
      1. Head 00001 exists                        -> {"status": "complete"}
      2. Redis genesis:state phase == "failed"    -> {"status": "failed", "reason"}
      3. API key (UserModelConfig) exists         -> {"status": "running"}
      4. otherwise                                -> {"status": "not_started"}

    Returns one of: "not_started", "running", "complete", "failed".
    """
    with get_fresh_db() as db:
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if head:
            return {"status": "complete"}

        # Failure is only knowable from Redis: a crashed genesis never creates
        # Head and only logs. Without this, a failed genesis reads as "running"
        # forever (see initialization_service._run_genesis).
        try:
            _redis = get_redis_client()
            raw = _redis.get("genesis:state")
            if raw:
                state = json.loads(raw)
                if state.get("phase") == "failed":
                    return {"status": "failed", "reason": state.get("reason", "Unknown genesis error")}
        except Exception as rexc:
            logger.warning(f"genesis-status redis read failed: {rexc}")

        genesis_triggered = False
        try:
            from backend.models.entities import UserModelConfig
            genesis_triggered = db.query(UserModelConfig).limit(1).first() is not None
        except Exception:
            pass

        return {"status": "running" if genesis_triggered else "not_started"}
```
Add `import json` to `websocket.py` imports if absent (check top of file).

- [ ] **Step 2: Typecheck**

Run: `cd backend && python -c "import backend.api.routes.websocket"`
Expected: Module imports cleanly.

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "feat(ws): genesis-status reports failed from Redis state"
```

---

### Task 9: Backend test for `genesis_status` precedence

**Files:**
- Create: `backend/tests/unit/test_genesis_status.py`

**Interfaces:**
- Consumes: `genesis_status` from `backend.api.routes.websocket`; `get_redis_client` from `backend.core.redis`; SQLAlchemy `HeadOfCouncil` model.
- Produces: regression test covering all four statuses incl. `failed` with reason.

- [ ] **Step 1: Write the test**

```python
# backend/tests/unit/test_genesis_status.py
"""
Tests for GET /ws/genesis-status precedence (Spec §3, P9).

Uses monkeypatched get_fresh_db + Redis so no live services are required.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def fake_redis():
    r = MagicMock()
    r.get.return_value = None
    return r


def _make_head_query(exists: bool):
    head = MagicMock()
    head.first.return_value = (object() if exists else None)
    return head


def test_complete_when_head_exists(fake_redis):
    from backend.api.routes import websocket as ws

    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", return_value=fake_redis):
        db = MagicMock()
        db.query.return_value.filter_by.return_value = _make_head_query(exists=True)
        gdb.return_value.__enter__.return_value = db
        resp = ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "complete"


def test_failed_returns_reason(fake_redis):
    from backend.api.routes import websocket as ws

    fake_redis.get.return_value = json.dumps({"phase": "failed", "reason": "boom"})
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", return_value=fake_redis):
        db = MagicMock()
        db.query.return_value.filter_by.return_value = _make_head_query(exists=False)
        gdb.return_value.__enter__.return_value = db
        resp = ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "failed"
        assert resp["reason"] == "boom"


def test_running_when_key_present(fake_redis):
    from backend.api.routes import websocket as ws

    cfg_q = MagicMock()
    cfg_q.first.return_value = object()  # a config row exists
    head_q = _make_head_query(exists=False)

    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", return_value=fake_redis):
        db = MagicMock()
        # genesis_status queries Head first, then UserModelConfig.
        db.query.side_effect = lambda *a, **k: head_q if "HeadOfCouncil" in str(a) else cfg_q
        gdb.return_value.__enter__.return_value = db
        resp = ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "running"


def test_not_started_when_no_key(fake_redis):
    from backend.api.routes import websocket as ws

    cfg_q = MagicMock()
    cfg_q.first.return_value = None
    head_q = _make_head_query(exists=False)

    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", return_value=fake_redis):
        db = MagicMock()
        db.query.side_effect = lambda *a, **k: head_q if "HeadOfCouncil" in str(a) else cfg_q
        gdb.return_value.__enter__.return_value = db
        resp = ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "not_started"
```

- [ ] **Step 2: Run the test**

Run: `cd backend && pytest tests/unit/test_genesis_status.py -v`
Expected: PASS (4 tests). If `get_fresh_db` import path differs, adjust the patch target to the actual symbol used in `websocket.py` (it imports `get_fresh_db` from `backend.models.database`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_genesis_status.py
git commit -m "test(ws): cover genesis_status precedence incl. failed"
```

---

### Task 10: Enable store tests in the Vitest `unit` project

**Files:**
- Modify: `frontend/vite.config.ts:50-55`

**Interfaces:**
- Consumes: nothing.
- Produces: `npm test` now includes `src/store/**/*.test.ts` (Tasks 1 & 3).

- [ ] **Step 1: Add the glob**

In the `unit` project `include` array (`:50-55`), add the store glob:
```ts
        include: [
          'src/components/chat/**/*.test.{ts,tsx}',
          'src/components/tasks/**/*.test.{ts,tsx}',
          'src/components/models/**/*.test.{ts,tsx}',
          'src/store/**/*.test.{ts,tsx}',
          'src/**/*.a11y.test.{ts,tsx}',
        ],
```

- [ ] **Step 2: Run the full unit suite**

Run: `cd frontend && npm test`
Expected: PASS — `connectionPhase.test.ts` and `websocketStore.test.ts` run alongside existing unit tests.

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "test(vitest): include store unit tests in unit project"
```

---

## Self-Review Notes (applied)

- **Spec coverage:** P1 (Task 2 `_connectNow`/`_genesisWatchdog`), P2/P8/P10 (Task 5), P3 (`notifyApiKeyAdded` → `connecting` + watchdog), P4 (Task 6), P5 (Task 1 reducer + Task 2 grace), P6 (Task 5 `canReconnect`), P7 (Task 2 watchdog), P9 (Tasks 4,7,8,9), backend fail-fast (Tasks 7,8,9). All covered.
- **No placeholders:** every code step shows the actual code/config; test commands have expected output.
- **Type consistency:** `connectionPhase`, `ConnectionPhase`, `PhaseEvent`, `nextPhase`, `canReconnect`, `isGenesisProgress`, `phaseFromGenesisStatus`, `GENESIS_GRACE_ATTEMPTS` are defined once in `connectionPhase.ts` (Task 1) and reused with identical signatures in Tasks 2, 3, 5. Backend `genesis:state` key + Redis helper match between Tasks 7 and 8.
