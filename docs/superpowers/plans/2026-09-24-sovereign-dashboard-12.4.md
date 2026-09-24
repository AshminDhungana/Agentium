# Sovereign Dashboard Verification & Fix (TODO 12.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two confirmed bugs (sovereign loses dashboard access on refresh; Command History never loads), then verify TODO 12.4.1–12.4.3 with regression tests, full suites, and a live-stack smoke test.

**Architecture:** Fix 1 makes `POST /api/v1/auth/verify` return DB truth (`is_sovereign`, `effective_role`) instead of JWT claims, so `deriveIsSovereign()` in the auth store stays `true` across page refreshes. Fix 2 closes the command-log phantom contract on both sides: `useSystemTab` seeds history from the existing `GET /api/v1/sovereign/commands` endpoint, and the sovereign command/container endpoints emit `command_log` WebSocket pushes via the existing `notify_sovereign()` helper. Verification then runs in three layers: unit/regression tests → full suites → live E2E smoke (Playwright, env-guarded).

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + Zustand + vitest (frontend), Playwright (live E2E), pytest (backend tests).

## Global Constraints

- Work happens on feature branch `fix/sovereign-dashboard-12.4`; merge/push decision at the end (user's call).
- Backend tests run from the repo root via `python -m pytest` (cwd lands on `sys.path` so `backend.main` imports resolve). Single-file runs add `--no-cov` because `backend/pytest.ini` has `--cov-fail-under=20`.
- The JWT `role` claim stays the raw column — `/verify` is the only auth change (spec §6).
- `CommandLog.status` union stays `'pending' | 'approved' | 'rejected' | 'executed'` — the audit-to-display mapping must stay inside it.
- No destructive container actions against real containers — the smoke seeds history via a **nonexistent** container id (`smoke-nonexistent`); the audit is written before the Docker call fails.
- The E2E smoke skips (exit 0) unless `LIVE_STACK=1` so it never runs in CI by default.
- Embedded tabs (Skills, Scaling, Dev Portal, …) are out of scope — own TODO items 12.5–12.9.
- `/verify-session` (voice bridge) is not changed — recorded as a related observation only.
- Frontend unit vitest project gains exactly one include line: `'src/hooks/**/*.test.{ts,tsx}'`.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/api/routes/auth.py` | Modify (~line 379-386) | Fix 1: `/verify` returns DB sovereign fields |
| `backend/api/sovereign.py` | Modify (~line 230, ~line 277) | Fix 2: `command_log` WS push after audit commit |
| `frontend/src/store/authStore.ts` | Modify (~line 79) | Export `deriveIsSovereign` (pure refactor for testing) |
| `frontend/src/hooks/useSystemTab.ts` | Modify | Fix 2: audit→CommandLog mapper, REST seed, WS mapping |
| `frontend/vite.config.ts` | Modify (unit include list) | Add `src/hooks` to unit test glob |
| `backend/tests/api/test_auth_verify_sovereign.py` | Create | Fix 1 regression test |
| `backend/tests/api/test_sovereign_commands.py` | Create | Fix 2 backend regression tests |
| `frontend/src/store/__tests__/authStore.test.ts` | Create | `deriveIsSovereign` truth table |
| `frontend/src/components/__tests__/SovereignRoute.test.tsx` | Create | Route guard behavior (12.4.2 artifact) |
| `frontend/src/hooks/__tests__/useSystemTab.test.tsx` | Create | Hook seed/push/degrade behavior (12.4.3 artifact) |
| `frontend/e2e/sovereign-live-smoke.mjs` | Create | Live-stack E2E smoke (env-guarded) |
| `docs/documents/TODO.md` | Modify | Mark 12.4 items + Notes block |

---

### Task 1: Fix 1 — `/verify` returns DB sovereign fields

**Files:**
- Modify: `backend/api/routes/auth.py` (the `/verify` endpoint, ~lines 372-391)
- Test: `backend/tests/api/test_auth_verify_sovereign.py`

**Interfaces:**
- Consumes: `User.effective_role` (property, returns `ROLE_PRIMARY_SOVEREIGN` when `is_admin`), `User.is_sovereign` (property, `effective_role == ROLE_PRIMARY_SOVEREIGN`), `create_access_token(data: dict)` from `backend/core/auth.py`, the `db_session` fixture from `backend/tests/conftest.py`.
- Produces: `POST /api/v1/auth/verify` response `user` dict gains `is_sovereign: bool` and `role: "primary_sovereign"` for admin users (from the persisted user, overriding the JWT claims). Task 5's live smoke and the frontend `deriveIsSovereign` path rely on this.

- [ ] **Step 1: Create the feature branch** (skip if already on it, e.g. inside a worktree)

```bash
git checkout -b fix/sovereign-dashboard-12.4
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/api/test_auth_verify_sovereign.py`:

```python
# tests/api/test_auth_verify_sovereign.py
# Fix 1 regression (TODO 12.4.2): POST /api/v1/auth/verify must return the
# persisted user's sovereign fields (DB truth), not the JWT claims.
#
# The bug: login embeds the RAW role column ("observer" for the default
# admin) in the JWT, and /verify built its response from JWT claims. On page
# refresh, the frontend's deriveIsSovereign() saw role="observer" -> false ->
# SovereignRoute kicked the sovereign back to "/".
from datetime import datetime, timezone

from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.database import get_db
from backend.core.auth import create_access_token
from backend.models.entities.user import User


async def _make_sovereign(db_session) -> User:
    admin = db_session.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_admin=True,
            is_active=True,
            is_pending=False,
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
    return admin


async def test_verify_returns_sovereign_fields_from_db(db_session):
    admin = await _make_sovereign(db_session)

    # JWT carries role="observer" (the raw-column bug simulation) — the
    # response must still return DB truth for the sovereign fields.
    token = create_access_token(data={
        "sub": admin.username,
        "user_id": admin.id,
        "role": "observer",
        "is_admin": True,
        "is_active": True,
    })

    async def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    user = resp.json()["user"]
    assert user["is_sovereign"] is True
    assert user["role"] == "primary_sovereign"
    assert user["is_admin"] is True


async def test_verify_for_nonadmin_still_has_db_role(db_session):
    suffix = f"{datetime.now(timezone.utc).timestamp():.0f}"
    user_row = User(
        username=f"plainuser_{suffix}",
        email=f"plain_{suffix}@agentium.local",
        hashed_password=User.hash_password("password123"),
        is_admin=False,
        is_active=True,
        is_pending=False,
        # Non-observer role: ObserverReadOnlyMiddleware 403s POST /verify for
        # observers, so the DB-role passthrough is only reachable via a valid
        # non-observer role. deputy_sovereign also pins the 12.4.2 boundary —
        # sovereign-adjacent but NOT primary_sovereign.
        role="deputy_sovereign",
    )
    db_session.add(user_row)
    db_session.commit()
    db_session.refresh(user_row)

    token = create_access_token(data={
        "sub": user_row.username,
        "user_id": user_row.id,
        "role": "deputy_sovereign",
        "is_admin": False,
        "is_active": True,
    })

    async def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    user = resp.json()["user"]
    # Non-admin: effective_role == the raw role column — unchanged behavior.
    assert user["is_sovereign"] is False
    assert user["role"] == "deputy_sovereign"
```

- [ ] **Step 3: Run test to verify it fails**

Run (from repo root):
`python -m pytest backend/tests/api/test_auth_verify_sovereign.py -v --no-cov`
Expected: FAIL — `test_verify_returns_sovereign_fields_from_db` fails on `user["is_sovereign"] is True` (key absent / role is `"observer"`). The non-admin test also fails on `KeyError: 'is_sovereign'` (the field doesn't exist yet — the implementation adds it for all users). Requires the test-infra Postgres: `docker compose -f docker-compose.test.yml up -d postgres`, then bootstrap the schema once: `DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python -c "from backend.models.database import init_db; init_db()"`.

- [ ] **Step 4: Write minimal implementation**

In `backend/api/routes/auth.py`, find the `/verify` endpoint's user_payload block (the endpoint already fetches the persisted user and uses it only for `avatar_url`):

```python
    if user:
        user_payload["avatar_url"] = user.avatar_url
```

Replace with:

```python
    if user:
        user_payload["avatar_url"] = user.avatar_url
        # Fix 1 (TODO 12.4.2): return DB truth for the sovereign fields so the
        # frontend's deriveIsSovereign() stays correct across page refreshes.
        # The JWT role claim carries the raw role column ("observer" for the
        # default admin), which would downgrade the sovereign on refresh.
        user_payload["is_sovereign"] = user.is_sovereign
        user_payload["role"] = user.effective_role
```

- [ ] **Step 5: Run test to verify it passes**

Run (from repo root):
`python -m pytest backend/tests/api/test_auth_verify_sovereign.py -v --no-cov`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/auth.py backend/tests/api/test_auth_verify_sovereign.py
git commit -m "fix(auth): /verify returns DB sovereign fields so refresh keeps dashboard access (TODO 12.4 Fix 1)"
```

---

### Task 2: Fix 2 (backend) — `command_log` WebSocket push

> **Execution corrections (found while running this task):**
> 1. The conftest `auth_client` token 401s on `/api/v1/sovereign/*` with `USER_NOT_FOUND`: the sovereign router uses `backend/api/middleware/auth.py`'s `get_current_user`, which resolves the JWT `sub` against `User.username`, but the fixture sets `sub` to the UUID id. Tests use a local `sovereign_client` fixture (same override pattern, `sub=username` — the production login shape) instead of `auth_client`.
> 2. sovereign.py's four `AuditLog(...)` constructor calls passed **raw dicts** to the Text-typed `after_state` column — a pre-existing production bug (psycopg2 `can't adapt type 'dict'`, 500 on every sovereign container action/command/block before execution, per the C9 audit-first ordering). Fixed with `json.dumps(...)` on all four, matching the `AuditLog.log()` factory.
> 3. Test infra bootstrap: `docker compose -f docker-compose.test.yml up -d postgres` + one-time `DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python -c "from backend.models.database import init_db; init_db()"`.
> 4. Async fixtures need `@pytest_asyncio.fixture` even with `asyncio_mode = auto`, and their names must not start with `_` (pytest skips underscore-prefixed names as private).

**Files:**
- Modify: `backend/api/sovereign.py` (`manage_container` ~line 230, `execute_sovereign_command` ~line 277 — both right after their audit commit)
- Test: `backend/tests/api/test_sovereign_commands.py`

**Interfaces:**
- Consumes: `notify_sovereign(message: dict)` (existing broadcast helper in `backend/api/sovereign.py`), `_get_head_service()` (existing `lru_cache` singleton), `AuditLog.to_dict()` (returns `level`, `category`, `actor: {type, id}`, `action`, `description`, `target`, `result: {success, message, error}`, `timestamp`), the `auth_client` + `db_session` fixtures from `backend/tests/conftest.py`.
- Produces: every sovereign container action / sovereign command emits `notify_sovereign({"type": "command_log", "payload": <audit.to_dict()>})` immediately after the audit commit (before execution, matching audit-before-action ordering). Task 3's frontend maps this payload with the same mapper it uses for the REST `GET /sovereign/commands` items — the payload shape IS the `/commands` item shape.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_sovereign_commands.py`:

```python
# tests/api/test_sovereign_commands.py
# Fix 2 regression (TODO 12.4.3): close the command_log phantom contract.
# 1. GET /api/v1/sovereign/commands returns seeded sovereign AuditLog entries.
# 2. Sovereign container actions emit a command_log WebSocket push via
#    notify_sovereign() — even when the action itself fails (audit is written
#    before the Docker call, so the push must fire there too).
from datetime import datetime

import pytest

from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory


async def test_commands_returns_sovereign_entries(db_session, auth_client):
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.GOVERNANCE,
        actor_type="sovereign",
        actor_id="admin",
        action="sovereign_command",
        target_type="host_system",
        target_id="root",
        description="Sovereign executed: test",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(audit)
    db_session.commit()

    resp = await auth_client.get("/api/v1/sovereign/commands")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["action"] == "sovereign_command" for i in items)
    # Items are AuditLog.to_dict() shapes — Task 3's mapper consumes these keys.
    assert all(
        "actor" in i and "timestamp" in i and "result" in i and "action" in i
        for i in items
    )


async def test_container_action_emits_command_log_push(db_session, auth_client, monkeypatch):
    pushes = []

    async def fake_notify(message):
        pushes.append(message)

    monkeypatch.setattr("backend.api.sovereign.notify_sovereign", fake_notify)

    class FakeHead:
        def manage_container(self, action, name):
            return {"success": False, "error": "container not found"}

    monkeypatch.setattr("backend.api.sovereign._get_head_service", lambda: FakeHead())

    resp = await auth_client.post(
        "/api/v1/sovereign/containers/nonexistent-id/restart", json={}
    )
    # The action failed (400) — but the audit + push happened before execution.
    assert resp.status_code == 400
    assert len(pushes) == 1
    assert pushes[0]["type"] == "command_log"
    assert pushes[0]["payload"]["action"] == "container_restart"
    assert pushes[0]["payload"]["actor"]["id"] == "admin"


async def test_command_endpoint_emits_command_log_push(db_session, auth_client, monkeypatch):
    pushes = []

    async def fake_notify(message):
        pushes.append(message)

    monkeypatch.setattr("backend.api.sovereign.notify_sovereign", fake_notify)

    class FakeHead:
        def execute_command(self, command, cwd=None):
            return {"success": True, "output": "ok"}

        def read_file(self, path):
            return {"success": True, "content": ""}

        def write_file(self, path, content):
            return {"success": True}

    monkeypatch.setattr("backend.api.sovereign._get_head_service", lambda: FakeHead())

    resp = await auth_client.post(
        "/api/v1/sovereign/command",
        json={"command": "read_file", "params": {"path": "/tmp/x"}, "target": "head_of_council"},
    )
    assert resp.status_code == 200
    assert len(pushes) == 1
    assert pushes[0]["type"] == "command_log"
    assert pushes[0]["payload"]["action"] == "sovereign_command"
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from repo root):
`python -m pytest backend/tests/api/test_sovereign_commands.py -v --no-cov`
Expected: FAIL — `test_container_action_emits_command_log_push` and `test_command_endpoint_emits_command_log_push` fail on `len(pushes) == 1` (nothing emits `command_log` yet). `test_commands_returns_sovereign_entries` PASSES already (the REST endpoint exists and works).

- [ ] **Step 3: Write minimal implementation**

In `backend/api/sovereign.py`, in `manage_container`, find:

```python
    db.add(audit)
    db.commit()

    result = head.manage_container(action, container_id)
```

Replace with:

```python
    db.add(audit)
    db.commit()

    # C11: close the command_log contract — push the audit to open sovereign
    # dashboards. Payload shape is identical to GET /commands items, so the
    # frontend maps both paths with one mapper. Fires before execution,
    # matching the audit-before-action ordering.
    await notify_sovereign({"type": "command_log", "payload": audit.to_dict()})

    result = head.manage_container(action, container_id)
```

In `execute_sovereign_command`, find:

```python
    db.add(audit)
    db.commit()

    # Execute command
    if command_req.command == "execute":
```

Replace with:

```python
    db.add(audit)
    db.commit()

    # C11: close the command_log contract — push the audit to open sovereign
    # dashboards. Payload shape is identical to GET /commands items, so the
    # frontend maps both paths with one mapper. Fires before execution,
    # matching the audit-before-action ordering.
    await notify_sovereign({"type": "command_log", "payload": audit.to_dict()})

    # Execute command
    if command_req.command == "execute":
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from repo root):
`python -m pytest backend/tests/api/test_sovereign_commands.py -v --no-cov`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/api/sovereign.py backend/tests/api/test_sovereign_commands.py
git commit -m "fix(sovereign): emit command_log WebSocket push from command/container actions (TODO 12.4 Fix 2)"
```

---

### Task 3: Fix 2 (frontend) — REST seed, audit→CommandLog mapper, WS mapping

**Files:**
- Modify: `frontend/src/hooks/useSystemTab.ts`
- Modify: `frontend/vite.config.ts` (unit project include list — one line)
- Test: `frontend/src/hooks/__tests__/useSystemTab.test.tsx`

**Interfaces:**
- Consumes: `hostAccessApi.getCommandHistory(limit?: number)` (existing, returns `AuditLog.to_dict()` items), `hostAccessApi.connectWebSocket(onMessage, onClose?)` (existing), `useRealtimeData` (existing hook), `useBackendStore` state shape `status: { status: 'connected' | ... }`, the `command_log` push payload shape from Task 2 (`audit.to_dict()`).
- Produces: `mapAuditToCommandLog(audit: Record<string, unknown>): CommandLog` — exported, maps `action`→`command`, `result.success/error`→`status` (inside the `'pending' | 'approved' | 'rejected' | 'executed'` union), `timestamp`→`Date`, `actor.id`→`executor`. The System tab panel and the live smoke rely on this mapping. `useSystemTab` now seeds history on connect.

- [ ] **Step 1: Add `src/hooks` to the vitest unit include list**

In `frontend/vite.config.ts`, in the unit project's `include` array, find:

```ts
          'src/services/**/*.test.{ts,tsx}',
```

Replace with:

```ts
          'src/services/**/*.test.{ts,tsx}',
          'src/hooks/**/*.test.{ts,tsx}',
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/hooks/__tests__/useSystemTab.test.tsx`:

```tsx
// frontend/src/hooks/__tests__/useSystemTab.test.tsx
// Fix 2 regression (TODO 12.4.3): the System tab's Command History panel must
// seed from the REST endpoint on connect (it was permanently empty before),
// map audit dicts to the display type, prepend live WS pushes, and degrade
// gracefully when the seed request fails.
import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSystemTab, mapAuditToCommandLog } from '@/hooks/useSystemTab';
import { hostAccessApi } from '@/services/hostAccessApi';
import { useBackendStore } from '@/store/backendStore';

const AUDIT = {
    id: 'audit-1',
    level: 'warning',
    category: 'governance',
    actor: { type: 'sovereign', id: 'admin' },
    action: 'container_restart',
    description: 'Sovereign manually restarted container xyz',
    result: { success: false, message: null, error: null },
    timestamp: '2026-09-24T10:00:00',
};

vi.mock('@/services/hostAccessApi', () => ({
    hostAccessApi: {
        getSystemStatus: vi.fn().mockResolvedValue(null),
        getContainers: vi.fn().mockResolvedValue([]),
        manageContainer: vi.fn().mockResolvedValue({}),
        getCommandHistory: vi.fn(),
        connectWebSocket: vi.fn().mockReturnValue({ send: vi.fn(), close: vi.fn() }),
    },
}));

vi.mock('@/hooks/useRealtimeData', () => {
    // Stable refresh identity — useSystemTab's connectWebSocket callback
    // depends on [refreshStatus, refreshContainers], and the seed sets state
    // on resolve; a fresh function per call would re-run the lifecycle effect
    // (and re-seed) on every render, looping forever.
    const refresh = () => {};
    return { useRealtimeData: () => ({ data: null, refresh }) };
});

describe('mapAuditToCommandLog', () => {
    it('maps an audit dict to the CommandLog display type', () => {
        const log = mapAuditToCommandLog(AUDIT);
        expect(log.id).toBe('audit-1');
        expect(log.command).toBe('container_restart');
        expect(log.status).toBe('pending');
        expect(log.executor).toBe('admin');
        expect(log.timestamp.getFullYear()).toBe(2026);
    });

    it('maps successful result to executed and errored result to rejected', () => {
        expect(
            mapAuditToCommandLog({ ...AUDIT, result: { success: true, error: null } }).status,
        ).toBe('executed');
        expect(
            mapAuditToCommandLog({ ...AUDIT, result: { success: false, error: 'boom' } }).status,
        ).toBe('rejected');
    });
});

describe('useSystemTab command history', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        useBackendStore.setState({ status: { status: 'connected' } as never });
    });

    it('seeds command history from the REST endpoint on connect', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockResolvedValue([AUDIT]);
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(result.current.commandLogs).toHaveLength(1));
        expect(result.current.commandLogs[0].command).toBe('container_restart');
        expect(hostAccessApi.getCommandHistory).toHaveBeenCalledWith(50);
    });

    it('prepends a live command_log WebSocket push', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockResolvedValue([]);
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(hostAccessApi.connectWebSocket).toHaveBeenCalled());
        const onMessage = vi.mocked(hostAccessApi.connectWebSocket).mock.calls[0][0];
        act(() => onMessage({ type: 'command_log', payload: AUDIT }));

        expect(result.current.commandLogs).toHaveLength(1);
        expect(result.current.commandLogs[0].command).toBe('container_restart');
    });

    it('degrades gracefully when the seed request fails', async () => {
        vi.mocked(hostAccessApi.getCommandHistory).mockRejectedValue(new Error('network down'));
        const { result } = renderHook(() => useSystemTab());

        await waitFor(() => expect(hostAccessApi.getCommandHistory).toHaveBeenCalled());
        await act(async () => { await Promise.resolve(); });
        expect(result.current.commandLogs).toHaveLength(0);
        expect(result.current.error).toBeNull();
    });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `frontend/`):
`npm run test -- useSystemTab`
Expected: FAIL — the seed test fails on `toHaveLength(1)` (`getCommandHistory` never called), and `mapAuditToCommandLog` is not exported.

- [ ] **Step 4: Write minimal implementation**

In `frontend/src/hooks/useSystemTab.ts`, add the mapper after the `CommandLog` interface:

```ts
// Map an AuditLog.to_dict() item (GET /commands and the WS command_log
// payload share this shape) onto the CommandLog display type. Shared by
// the REST seed and the WS handler so both paths render identically.
// `result.success` is only set on audits whose outcome was recorded; the
// pre-execution audits (success=false, error=null) honestly show as pending.
export function mapAuditToCommandLog(audit: Record<string, unknown>): CommandLog {
    const result = (audit.result ?? {}) as { success?: boolean; error?: string | null };
    const status: CommandLog['status'] =
        result.success === true ? 'executed'
        : result.error ? 'rejected'
        : 'pending';
    return {
        id: String(audit.id ?? `cmd_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`),
        command: String(audit.action ?? 'unknown_action'),
        status,
        timestamp: new Date((audit.timestamp as string) ?? Date.now()),
        executor: (audit.actor as { id?: string } | null)?.id,
    };
}
```

Add the seed function inside the hook (after the WebSocket `connectWebSocket` callback):

```ts
    // ── REST seed for command history (C11) ───────────────────────────────
    // GET /sovereign/commands returns the historical AuditLog entries; the
    // WebSocket only pushes NEW ones. Seed on connect so the panel is not
    // permanently empty.
    const seedCommandHistory = useCallback(async () => {
        try {
            const logs = await hostAccessApi.getCommandHistory(50);
            if (mountedRef.current && Array.isArray(logs)) {
                setCommandLogs(logs.map(mapAuditToCommandLog));
            }
        } catch {
            // Best-effort seed — live WS pushes still populate the panel.
        }
    }, []);
```

In the WS handler, find:

```ts
                } else if (data.type === 'command_log') {
                    setCommandLogs((prev) => [data.payload, ...prev]);
                }
```

Replace with:

```ts
                } else if (data.type === 'command_log') {
                    setCommandLogs((prev) => [mapAuditToCommandLog(data.payload), ...prev]);
                }
```

In the lifecycle `useEffect`, find:

```ts
        if (backendStatus.status !== 'connected') return;

        // Command-log WebSocket (push-only)
        connectWebSocket();
```

Replace with:

```ts
        if (backendStatus.status !== 'connected') return;

        // REST seed for history (C11) + command-log WebSocket (push-only)
        void seedCommandHistory();
        connectWebSocket();
```

And update the effect's dependency array (it currently reads `[backendStatus.status, connectWebSocket]`):

```ts
    }, [backendStatus.status, connectWebSocket, seedCommandHistory]);
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `frontend/`):
`npm run test -- useSystemTab`
Expected: PASS (5 tests across both describes).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useSystemTab.ts frontend/vite.config.ts frontend/src/hooks/__tests__/useSystemTab.test.tsx
git commit -m "fix(frontend): System tab seeds command history from REST and maps audit entries (TODO 12.4 Fix 2)"
```

---

### Task 4: Guard test coverage — `deriveIsSovereign` truth table + `SovereignRoute` behavior

**Files:**
- Modify: `frontend/src/store/authStore.ts` (~line 79 — add `export` keyword, pure refactor)
- Test: `frontend/src/store/__tests__/authStore.test.ts`
- Test: `frontend/src/components/__tests__/SovereignRoute.test.tsx`

**Interfaces:**
- Consumes: `deriveIsSovereign(user: { role?: string; is_admin?: boolean; is_sovereign?: boolean }): boolean` (existing function in `authStore.ts`), `SovereignRoute({ children })` (existing component), `useAuthStore` zustand store.
- Produces: `deriveIsSovereign` becomes a named export (no behavior change — Task 3's hook test and future consumers can import it); regression tests locking the 12.4.2 guard behavior.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/store/__tests__/authStore.test.ts`:

```ts
// frontend/src/store/__tests__/authStore.test.ts
// 12.4.2 artifact: deriveIsSovereign truth table. Plain is_admin is
// deliberately NOT sufficient (B6: not all admins are sovereign); the
// sovereign flag or the primary_sovereign role is required.
import { describe, it, expect } from 'vitest';
import { deriveIsSovereign } from '@/store/authStore';

describe('deriveIsSovereign', () => {
    it('returns true for the is_sovereign flag (DB path)', () => {
        expect(deriveIsSovereign({ is_sovereign: true })).toBe(true);
    });

    it('returns true for the primary_sovereign role', () => {
        expect(deriveIsSovereign({ role: 'primary_sovereign' })).toBe(true);
    });

    it('returns false for a plain admin (not all admins are sovereign)', () => {
        expect(deriveIsSovereign({ is_admin: true, role: 'admin' })).toBe(false);
    });

    it('returns false for the observer role', () => {
        expect(deriveIsSovereign({ role: 'observer' })).toBe(false);
    });

    it('returns false for the JWT-fallback shape (no role/is_sovereign claims)', () => {
        expect(deriveIsSovereign({ is_admin: true })).toBe(false);
    });

    it('returns false for an empty user', () => {
        expect(deriveIsSovereign({})).toBe(false);
    });
});
```

Create `frontend/src/components/__tests__/SovereignRoute.test.tsx`:

```tsx
// frontend/src/components/__tests__/SovereignRoute.test.tsx
// 12.4.2 artifact: SovereignRoute enforces sovereign access —
// sovereign stays, non-sovereign → "/", unauthenticated → "/login".
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach } from 'vitest';
import { SovereignRoute } from '@/components/SovereignRoute';
import { useAuthStore } from '@/store/authStore';

function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route
                    path="/sovereign"
                    element={<SovereignRoute><div>SOVEREIGN CONTENT</div></SovereignRoute>}
                />
                <Route path="/login" element={<div>LOGIN PAGE</div>} />
                <Route path="/" element={<div>MAIN DASHBOARD</div>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe('SovereignRoute', () => {
    beforeEach(() => {
        useAuthStore.setState({ user: null, isLoading: false });
    });

    it('renders children for a sovereign user', () => {
        useAuthStore.setState({
            user: { isAuthenticated: true, username: 'admin', is_admin: true, isSovereign: true } as never,
        });
        renderAt('/sovereign');
        expect(screen.getByText('SOVEREIGN CONTENT')).toBeInTheDocument();
    });

    it('redirects non-sovereign users to /', () => {
        useAuthStore.setState({
            user: { isAuthenticated: true, username: 'user', is_admin: false, isSovereign: false } as never,
        });
        renderAt('/sovereign');
        expect(screen.getByText('MAIN DASHBOARD')).toBeInTheDocument();
        expect(screen.queryByText('SOVEREIGN CONTENT')).not.toBeInTheDocument();
    });

    it('redirects unauthenticated users to /login', () => {
        renderAt('/sovereign');
        expect(screen.getByText('LOGIN PAGE')).toBeInTheDocument();
        expect(screen.queryByText('SOVEREIGN CONTENT')).not.toBeInTheDocument();
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`):
`npm run test -- authStore SovereignRoute`
Expected: FAIL — `authStore.test.ts` fails to import (`deriveIsSovereign` is not exported). The `SovereignRoute` tests PASSES already (the guard logic exists).

- [ ] **Step 3: Export `deriveIsSovereign`**

In `frontend/src/store/authStore.ts`, find:

```ts
function deriveIsSovereign(user: {
```

Replace with:

```ts
export function deriveIsSovereign(user: {
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`):
`npm run test -- authStore SovereignRoute`
Expected: PASS (9 tests across both files).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/store/__tests__/authStore.test.ts frontend/src/components/__tests__/SovereignRoute.test.tsx
git commit -m "test(frontend): lock SovereignRoute guard and deriveIsSovereign truth table (TODO 12.4.2)"
```

---

### Task 5: Full verification suites (code-audit layer)

**Files:**
- No source changes. If any suite fails, fix forward in this task (the failures are regressions from Tasks 1–4 or pre-existing broken tests — diagnose with the specific output before changing anything).

**Interfaces:**
- Consumes: all tests from Tasks 1–4; existing suites (`backend/tests/api`, `backend/tests/unit`, SovereignDashboard a11y browser test); `npm run build`.
- Produces: green-run evidence for 12.4.1's "build green + a11y passes" and 12.4.2's guard tests. Task 7 records the results in TODO.md.

- [ ] **Step 1: Run the new backend tests together**

Run (from repo root):
`python -m pytest backend/tests/api/test_auth_verify_sovereign.py backend/tests/api/test_sovereign_commands.py -v --no-cov`
Expected: PASS (5 tests).

- [ ] **Step 2: Run the existing backend API + unit suites**

Run (from repo root):
`python -m pytest backend/tests/api backend/tests/unit -v`
Expected: PASS — no failures introduced by Task 1's `/verify` change. If a pre-existing failure appears, check `git stash` + re-run to confirm it predates this branch before fixing it here.

- [ ] **Step 3: Run the frontend unit suite**

Run (from `frontend/`):
`npm run test`
Expected: PASS — all existing tests plus the three new files (9 guard tests, 5 hook tests).

- [ ] **Step 4: Run the a11y browser suite**

Run (from `frontend/`):
`npm run test:a11y`
Expected: PASS — `SovereignDashboard.a11y.browser.test.tsx` passes in light and dark themes (12.4.1 evidence).

- [ ] **Step 5: Run the production build**

Run (from `frontend/`):
`npm run build`
Expected: build completes with no type errors (12.4.1 evidence).

- [ ] **Step 6: Commit (only if fixes were made in this task)**

```bash
git add -A
git commit -m "fix: address regressions found during TODO 12.4 verification suites"
```

If no fixes were needed, skip this step — the previous commits stand.

> **Execution corrections (found while running this task):** the full suites were NOT green at the start of this task — four pre-existing broken-test categories (none caused by Tasks 1–4; the three frontend files and both backend files are byte-identical to main) were fixed forward per this task's mandate:
> 1. **`backend/tests/unit/test_browser_tool.py` hung mid-suite** (the 10-minute timeout killed two full-suite runs): the tests monkeypatched `playwright.async_api.async_playwright`, but `browser_tool.py` does `from playwright.async_api import async_playwright` at module load — the code resolved the REAL function and the tests were silently launching real Chromium + real network navigation to example.com (4.5s isolated, IOCP-selector deadlock mid-suite). Fixed: repoint all four `monkeypatch.setattr` to `backend.tools.browser_tool.async_playwright` (the binding the code actually reads) and add the mock methods the code calls (`MockPlaywright.start`, `MockBrowser.launch`, `MockBrowser.new_page`). Result: 4 passed in 0.23s, no real browser, no hang.
> 2. **`backend/tests/unit/test_bge_prefix.py` 3 tests failed**: `patch("backend.core.vector_store.SentenceTransformer", ...)` requires the attribute to exist, but vector_store moved to a lazy import (`from sentence_transformers import SentenceTransformer` inside `_get_sentence_transformer`) so the module-level name no longer exists. Fixed: patch target → `sentence_transformers.SentenceTransformer` (the source module the lazy import reads). Result: 4 passed.
> 3. **`frontend/src/components/chat/__tests__/chat-tokens.test.ts` failed to parse**: JSX (`<FloatingChatWidget />`) in a `.ts` file — a phantom test that could never have run. Fixed: `git mv` to `.tsx` + rewrite to attach `styles/chat-tokens.css` to the jsdom document (jsdom has no cascade for `:root` custom properties from external sheets; `getComputedStyle` on `document.documentElement` after injecting the sheet resolves them). Result: 1 passed.
> 4. **`ChatPage`/`SettingsPage.a11y.browser.test.tsx` failed color-contrast in the unit (jsdom) project**: the pre-existing broad `src/pages/**/*.test.tsx` include line caught these real-browser a11y tests (added in `811b197` with their own CI gate — their home is the `a11y` project). Fixed: unit project `exclude: ['src/**/*.a11y.browser.test.{ts,tsx}']`. In real Chromium both files pass both themes (a11y suite 38 files / 78 tests green).
>
> Final state: backend `backend/tests/api backend/tests/unit` all green (with the fixed files, no deselects); frontend unit 70 files / 302 tests green; a11y 38 files / 78 tests green; production build ✓ 57s.

---

### Task 6: Live-stack E2E smoke (Playwright, env-guarded)

**Files:**
- Create: `frontend/e2e/sovereign-live-smoke.mjs`

**Interfaces:**
- Consumes: `playwright` package (already in `frontend/node_modules` via the vitest browser provider); the live backend at `BACKEND_URL` (default `http://localhost:8000`) with the default admin (`admin`/`admin`); the frontend dev server at `FRONTEND_URL` (default `http://localhost:5173`); `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, `POST /api/v1/admin/users/{user_id}/approve`, `POST /api/v1/sovereign/containers/{id}/{action}`, `GET /api/v1/sovereign/commands`, `GET /api/v1/sovereign/audit`, `GET /api/v1/sovereign/system/status`; the checkAuth localStorage flow (`access_token` key) and the Fix 1 `/verify` change.
- Produces: a durable, re-runnable live smoke script proving 12.4.1/12.4.2/12.4.3 end-to-end on the real stack. Skips (exit 0) unless `LIVE_STACK=1`.

- [ ] **Step 1: Create the smoke script**

Create `frontend/e2e/sovereign-live-smoke.mjs`:

```js
// frontend/e2e/sovereign-live-smoke.mjs
// Sovereign Dashboard live smoke (TODO 12.4). Drives the REAL stack — the
// backend and the frontend dev server must be running. Skips (exit 0) unless
// LIVE_STACK=1, so it never runs in CI by default.
//
// Usage:
//   LIVE_STACK=1 FRONTEND_URL=http://localhost:5173 node frontend/e2e/sovereign-live-smoke.mjs
import { chromium } from 'playwright';

const LIVE = process.env.LIVE_STACK === '1';
const FRONTEND_URL = process.env.FRONTEND_URL ?? 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

if (!LIVE) {
    console.log('[sovereign-live-smoke] LIVE_STACK!=1 — skipping (never runs in CI).');
    process.exit(0);
}

const results = [];
const check = (name, ok, detail = '') => {
    results.push({ name, ok });
    console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ` — ${detail}` : ''}`);
};

const api = async (method, path, { token, body } = {}) => {
    const res = await fetch(`${BACKEND_URL}${path}`, {
        method,
        headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
    });
    let json = null;
    try { json = await res.json(); } catch { /* non-JSON body */ }
    return { status: res.status, json };
};

// ── 1. Sovereign login via the real API ───────────────────────────────────────
const login = await api('POST', '/api/v1/auth/login', {
    body: { username: 'admin', password: 'admin' },
});
if (login.status !== 200 || !login.json?.access_token) {
    console.error('❌ Sovereign login failed — is the backend running with the default admin?', login.status);
    process.exit(1);
}
const token = login.json.access_token;
check('sovereign login', true);

const browser = await chromium.launch();
try {
    const page = await browser.newPage();
    const sovereignSockets = [];
    page.on('websocket', (ws) => {
        if (ws.url().includes('/api/v1/sovereign/ws')) sovereignSockets.push(ws);
    });

    // ── 2. Seed the token, open /sovereign, verify the dashboard ────────────
    // Setting localStorage directly exercises the real checkAuth → /verify →
    // deriveIsSovereign path (Fix 1) without depending on login-form selectors.
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((t) => localStorage.setItem('access_token', t), token);
    await page.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });

    await page.waitForSelector('text=Sovereign Control Panel', { timeout: 15_000 });
    check('dashboard loads for sovereign', true);

    // System tab is active by default — the four status cards + container table
    for (const card of ['CPU Usage', 'Memory', 'Disk Usage', 'System Uptime']) {
        await page.waitForSelector(`text=${card}`, { timeout: 15_000 });
    }
    check('system status cards render', true);

    await page.waitForSelector('text=Container Management', { timeout: 15_000 });
    check('container management section renders', true);

    // Sovereign WebSocket connects when the System tab mounts
    const wsDeadline = Date.now() + 15_000;
    let wsOk = false;
    while (Date.now() < wsDeadline) {
        wsOk = sovereignSockets.some((ws) => !ws.isClosed());
        if (wsOk) break;
        await page.waitForTimeout(500);
    }
    check('sovereign WebSocket connected', wsOk);

    // Fix 1 regression — page refresh keeps sovereign access
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('text=Sovereign Control Panel', { timeout: 15_000 });
    check('refresh keeps sovereign access (Fix 1 regression)', true);

    // ── 3. Fix 2 end-to-end: live push + REST history ──────────────────────
    // Listen for command_log frames, then seed a harmless history entry:
    // the audit is written BEFORE the Docker call fails on the nonexistent id.
    let sawCommandLog = false;
    for (const ws of sovereignSockets) {
        ws.on('framereceived', (data) => {
            try {
                const raw = typeof data === 'string' ? data : (data.payload ?? '');
                if (JSON.parse(raw)?.type === 'command_log') sawCommandLog = true;
            } catch { /* non-JSON frame */ }
        });
    }

    await api('POST', '/api/v1/sovereign/containers/smoke-nonexistent/restart', { token });

    const pushDeadline = Date.now() + 5_000;
    while (Date.now() < pushDeadline && !sawCommandLog) {
        await page.waitForTimeout(250);
    }
    check('live command_log push received (Fix 2 regression)', sawCommandLog);

    const cmds = await api('GET', '/api/v1/sovereign/commands?limit=50', { token });
    const seeded = cmds.status === 200
        && Array.isArray(cmds.json)
        && cmds.json.some((c) => c.action === 'container_restart');
    check('command history endpoint returns seeded entry', seeded);

    const auditLogs = await api('GET', '/api/v1/sovereign/audit?limit=10', { token });
    check('audit endpoint returns 200', auditLogs.status === 200);

    const block = await api('POST', '/api/v1/sovereign/agents/smoke-agent-99999/block', {
        token, body: { reason: 'live smoke' },
    });
    const unblock = await api('POST', '/api/v1/sovereign/agents/smoke-agent-99999/unblock', { token });
    check('agent block/unblock endpoints respond', block.status === 200 && unblock.status === 200);

    // ── 4. Non-sovereign enforcement ────────────────────────────────────────
    const unique = `smoke_${Date.now()}`;
    const reg = await api('POST', '/api/v1/auth/register', {
        body: { username: unique, password: 'smoke-password-1', email: `${unique}@agentium.local` },
    });
    const userId = reg.json?.user?.id ?? reg.json?.id ?? null;
    if (reg.status === 200 || reg.status === 201) {
        if (userId) {
            await api('POST', `/api/v1/admin/users/${userId}/approve`, { token });
        }
        const userLogin = await api('POST', '/api/v1/auth/login', {
            body: { username: unique, password: 'smoke-password-1' },
        });
        if (userLogin.status === 200 && userLogin.json?.access_token) {
            const forbidden = await api('GET', '/api/v1/sovereign/system/status', {
                token: userLogin.json.access_token,
            });
            check('non-sovereign gets 403 on sovereign API', forbidden.status === 403, `status=${forbidden.status}`);

            await page.evaluate((t) => localStorage.setItem('access_token', t), userLogin.json.access_token);
            await page.goto(`${FRONTEND_URL}/sovereign`, { waitUntil: 'domcontentloaded' });
            await page.waitForTimeout(2_000);
            const denied = (await page.locator('text=Sovereign Control Panel').count()) === 0;
            check('non-sovereign redirected from /sovereign', denied);
        } else {
            check('non-sovereign browser check skipped (login unavailable)', true, `login status=${userLogin.status}`);
        }
    } else {
        check('non-sovereign checks skipped (registration unavailable)', true, `register status=${reg.status}`);
    }
} finally {
    await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n[sovereign-live-smoke] ${results.length - failed.length}/${results.length} checks passed.`);
if (failed.length > 0) process.exit(1);
```

- [ ] **Step 2: Ensure the live stack is up**

Run (from repo root):
`docker compose up -d postgres redis chroma backend`
Then wait for the backend to become healthy:
`docker compose ps` — repeat until `backend` shows `healthy` (or Up); typically 1-3 minutes after a cold start.

- [ ] **Step 3: Start the frontend dev server** (skip if already running)

Run (from `frontend/`, in the background):
`npm run dev`
Confirm it serves: `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173` returns `200` (or `304`). If your dev server uses a different port, pass `FRONTEND_URL=http://localhost:<port>` in Step 4.

- [ ] **Step 4: Run the smoke**

Run (from repo root):
`LIVE_STACK=1 node frontend/e2e/sovereign-live-smoke.mjs`
Expected: all checks ✅ and `N/N checks passed` — sovereign login, dashboard loads, status cards, container section, WS connected, refresh keeps access (Fix 1), live `command_log` push received (Fix 2), command history seeded, audit 200, block/unblock respond, non-sovereign 403 + redirect. Exit code 0.

Fallback (spec §3): if the stack can't come up or Playwright is unavailable in this environment, fall back to a curl API smoke (login → status → nonexistent-container restart → commands → 403 for a non-admin) plus a manual browser checklist for the user, and record that in the Task 7 Notes block instead of the smoke results.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/sovereign-live-smoke.mjs
git commit -m "test(e2e): add env-guarded live-stack Sovereign Dashboard smoke (TODO 12.4)"
```

---

### Task 7: Record results in TODO.md + wrap up

**Files:**
- Modify: `docs/documents/TODO.md` (12.4 section, lines 542-545 — unique in the file)
- Delete: `docs/superpowers/specs/2026-09-24-sovereign-dashboard-design.md` (per established practice: docs are removed after completion; the tests are the durable record)
- Delete: `docs/superpowers/plans/2026-09-24-sovereign-dashboard-12.4.md` (this plan — execution is complete by the time Task 7 runs)

**Interfaces:**
- Consumes: green-run evidence from Tasks 1-6 (regression test names, fix locations, smoke script path) to write the Notes (12.4) block.
- Produces: TODO.md marked `[x]` for 12.4.1-12.4.3 with the Notes block recording verified items, both fixes, and accepted limitations — the durable verification record for future sessions.

- [ ] **Step 1: Mark the 12.4 items and add the Notes block**

In `docs/documents/TODO.md`, find (unique — verified at line 542):

```markdown
- [ ] **12.4 — Sovereign Dashboard**
  - [ ] 12.4.1 — `SovereignDashboard.tsx` loads (admin-only route)
  - [ ] 12.4.2 — `SovereignRoute` component enforces sovereign access
  - [ ] 12.4.3 — System-wide controls function correctly
```

Replace with (indentation matches the existing 10.4-style Notes blocks — 2-space-indented blockquote):

```markdown
- [x] **12.4 — Sovereign Dashboard**
  - [x] 12.4.1 — `SovereignDashboard.tsx` loads (admin-only route)
  - [x] 12.4.2 — `SovereignRoute` component enforces sovereign access
  - [x] 12.4.3 — System-wide controls function correctly

  > **Notes (12.4)** — Verified by code audit + live-stack smoke (`frontend/e2e/sovereign-live-smoke.mjs`, env-guarded by `LIVE_STACK=1`, non-destructive — history seeded via a nonexistent container id). Two bugs found & fixed:
  > - **12.4.2 bug found & fixed**: the login JWT embedded the raw role column (`"observer"` for the default admin) and `POST /api/v1/auth/verify` built its response from JWT claims, so on page refresh `deriveIsSovereign()` saw a non-sovereign and `SovereignRoute` redirected the sovereign to `/`. `/verify` now returns DB truth (`is_sovereign`, `effective_role`) when the persisted user exists (`backend/api/routes/auth.py`); JWT claims untouched (minimal blast radius). Locked by `tests/api/test_auth_verify_sovereign.py`, the `deriveIsSovereign` truth table, and `SovereignRoute` guard tests.
  > - **12.4.3 bug found & fixed (phantom contract)**: the backend never emitted a `command_log` WS message and the frontend never called `GET /api/v1/sovereign/commands` (`getCommandHistory` existed unused), so the Command History panel was permanently empty (invisible behind keep-alive tabs). Both sides closed: sovereign command/container endpoints emit `notify_sovereign({"type": "command_log", "payload": audit.to_dict()})` right after the audit commit (`backend/api/sovereign.py`), and `useSystemTab` seeds history from the REST endpoint on connect + maps audit dicts via the shared `mapAuditToCommandLog()`. Locked by `tests/api/test_sovereign_commands.py` + `useSystemTab` unit tests.
  > - **12.4.1 verified**: `/sovereign` wired inside `SovereignRoute` (lazy-loaded, sidebar nav + route preload), 13-tab keep-alive panel gates on `isSovereign`; a11y suite passes light+dark; `npm run build` green.
  > - **12.4.3 verified (controls)**: system status via psutil (`/host` disk fallback), containers via Docker socket (mounted `:rw` in compose), command history (post-fix), audit endpoint filters, agent block/unblock (audit + WS notify). Non-sovereign gets 403 `SOVEREIGN_ONLY` on every `/api/v1/sovereign/*` endpoint and is redirected from `/sovereign`; WS closes 4001 (missing/invalid token) / 4003 (non-admin).
  > - **Accepted limitations**: single-worker WS registry (module-level `active_connections`); restricted host-access mode; embedded tabs deferred to 12.5–12.9; `/verify-session` (voice bridge) shares the raw-role gap but doesn't consume `isSovereign`.
```

- [ ] **Step 2: Remove the design + plan docs**

```bash
git rm docs/superpowers/specs/2026-09-24-sovereign-dashboard-design.md docs/superpowers/plans/2026-09-24-sovereign-dashboard-12.4.md
```

(If the plan file is still untracked at this point, plain-delete it instead: `rm docs/superpowers/plans/2026-09-24-sovereign-dashboard-12.4.md`.)

- [ ] **Step 3: Update session memory with the completion marker**

Create `C:\Users\Lenovo\.claude\projects\E--Ongoing-Projects-Agentium\memory\sovereign-dashboard-12.4-complete.md`:

```markdown
---
name: sovereign-dashboard-12.4-complete
description: TODO 12.4 Sovereign Dashboard verified complete — two bugs fixed, live smoke green; next TODO 12.5
metadata:
  type: project
---

TODO 12.4 (Sovereign Dashboard) completed 2026-09-24 on branch `fix/sovereign-dashboard-12.4`: Fix 1 (`/verify` returns DB sovereign fields so refresh keeps dashboard access) + Fix 2 (command_log contract closed on both sides — REST seed in `useSystemTab` + `notify_sovereign` push in `backend/api/sovereign.py`), verified by regression tests + full suites + live-stack smoke (`frontend/e2e/sovereign-live-smoke.mjs`, `LIVE_STACK=1` guarded). Recorded in TODO.md Notes (12.4). Next verification items: 12.5 Developer Portal, 12.6 Skills, 12.7 AB Testing.
```

And append one line to `C:\Users\Lenovo\.claude\projects\E--Ongoing-Projects-Agentium\memory\MEMORY.md`:

```markdown
- [Sovereign Dashboard 12.4 complete](sovereign-dashboard-12.4-complete.md) — two fixes + live smoke green; next 12.5
```

- [ ] **Step 4: Final commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark TODO 12.4 Sovereign Dashboard verified (12.4.1-12.4.3) with Notes block"
```

- [ ] **Step 5: Report the merge/push decision to the user**

The work is on `fix/sovereign-dashboard-12.4`. Report the verification summary (test counts, smoke results, the two fixes) and ask the user whether to merge to `main` / push — per the plan's Global Constraints this is the user's call, not the executor's.

---
