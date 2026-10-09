# §16.3 Federation Frontend — Check & Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close TODO §16.3 by wiring the missing federated result-callback loop and verifying/fixing the already-built `FederationPage` with behavioral tests plus a live end-to-end run against a scripted fake peer.

**Architecture:** Backend — a best-effort `FederationService.notify_federation_result(db, task, status, ...)` helper, called from the task executor's three terminal paths, which flips the incoming `FederatedTask` row's status and dispatches the already-defined `send_federation_result` Celery callback to the source instance. Frontend — a behavioral RTL suite for `FederationPage` covering peers display (16.3.1), connection/disconnection flows (16.3.2), and task status (16.3.3), plus one Sovereign-gate fix it surfaces. Verification — `scripts/fake_federation_peer.py` (an HMAC-signing HTTP stub) and a live browser click-through.

**Tech Stack:** FastAPI + SQLAlchemy + Celery (backend), React + Vitest + React Testing Library (frontend), Python `http.server` + `httpx` (fake peer script).

## Global Constraints

- Backend integration tests need ephemeral infra up first: `docker compose -f docker-compose.test.yml up -d` (run from repo root). Then run tests with the exact env from the Makefile's `test-integration` target: `cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test REDIS_URL=redis://localhost:6379/1 CHROMA_HOST=localhost CHROMA_PORT=8001 CELERY_TASK_ALWAYS_EAGER=true TESTING=true PYTHONPATH=. pytest <files> -v`
- Frontend unit tests: `cd frontend && npx vitest run --project unit <file>` (there is no `@testing-library/user-event` dependency — use `fireEvent` from `@testing-library/react`)
- This plan touches **no `backend/api/` files** — the repo's pre-commit guard (fails on backend API changes without SDK type regeneration) is therefore not triggered; do not regenerate SDK types
- The TODO doc is `docs/documents/TODO.md` (section 16, lines ~785-807)
- `FederationPage` is Sovereign-gated (`user.isSovereign`) and mounted via `SovereignDashboard`'s `'federation'` tab — there is no standalone `/federation` route
- Status badge labels come from `frontend/src/utils/statusColors.ts`: peers → Active/Suspended/Pending; federated tasks → Pending/Delivered/Accepted/Rejected/Completed/Failed
- No new backend endpoints and no schema migrations — everything needed already exists
- Commit style: conventional commits (`feat:`, `fix:`, `test:`, `docs:`), matching repo history

---

### Task 1: Backend — `FederationService.notify_federation_result` helper (TDD)

**Files:**
- Modify: `backend/services/federation_service.py` (add one static method after `receive_task_result`, which ends ~line 385)
- Test: `backend/tests/integration/test_federation_result_callback.py` (new)

**Interfaces:**
- Consumes: existing `FederationService.receive_delegated_task(db, source_peer, original_task_id, payload)` (creates the local Task + incoming `FederatedTask` with `local_task_id`, `status="accepted"`); existing Celery task `backend.celery_app.send_federation_result` (signature: `delay(callback_url, peer_url, signing_key, original_task_id, local_task_id, task_status, result_summary, result_data)`); the local Task's `execution_context` JSON string, which `receive_delegated_task` populates with `{"federated": true, "source_instance_id", "source_task_id", "callback_url"}`
- Produces: `FederationService.notify_federation_result(db: Session, task: Task, status: str, result_summary: Optional[str] = None, result_data: Optional[Dict[str, Any]] = None) -> None` — never raises; updates the incoming `FederatedTask` row (status + `completed_at`), then best-effort dispatches the callback

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/integration/test_federation_result_callback.py` with exactly this content:

```python
"""
Integration tests for the federated result-callback loop (TODO 16.3.3).

Covers FederationService.notify_federation_result: the hook the task
executor calls when a federated local task reaches a terminal state.
It must (a) update the incoming FederatedTask row so the receiving
instance's UI shows completion, and (b) best-effort dispatch the
send_federation_result Celery callback to the source instance.
"""

import hashlib
import json

import pytest

from backend.core.config import settings
from backend.services.federation_service import FederationService
from backend.models.entities.federation import FederatedInstance, FederatedTask
from backend.models.entities.task import Task

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"


def _derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _make_peer(db, name="Peer Alpha", base_url="http://peer-alpha.local"):
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(SECRET.encode()).hexdigest(),
        signing_key=_derive_signing_key(SECRET),
        status="active",
        trust_level="limited",
        capabilities_shared=["tasks"],
    )
    db.add(peer)
    db.flush()
    return peer


@pytest.fixture
def recorder(monkeypatch):
    """Capture send_federation_result.delay kwargs.

    The helper imports send_federation_result inside its method body from
    backend.celery_app, so patching the module attribute is enough.
    """
    calls = []

    class _FakeTask:
        @staticmethod
        def delay(**kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("backend.celery_app.send_federation_result", _FakeTask())
    return calls


def _receive_task(db, peer, original_task_id="T0100",
                  callback_url="http://primary.local/api/v1/federation/webhooks/tasks/result"):
    """Create a federated local task via the real receive path."""
    fed_task = FederationService.receive_delegated_task(
        db=db,
        source_peer=peer,
        original_task_id=original_task_id,
        payload={"title": "Federated job", "callback_url": callback_url},
    )
    local_task = db.query(Task).filter(Task.id == fed_task.local_task_id).one()
    db.refresh(local_task)
    return local_task, fed_task


class TestNotifyFederationResult:

    def test_completed_dispatches_callback_with_correct_arguments(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)
        local_task.result_summary = "Job finished OK"
        local_task.result_data = {"full_output": "done"}
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert len(recorder) == 1
        kwargs = recorder[0]
        assert kwargs["callback_url"] == "http://primary.local/api/v1/federation/webhooks/tasks/result"
        assert kwargs["signing_key"] == peer.signing_key
        assert kwargs["original_task_id"] == "T0100"
        assert kwargs["local_task_id"] == fed_task.local_task_id
        assert kwargs["task_status"] == "completed"
        assert kwargs["result_summary"] == "Job finished OK"
        assert kwargs["result_data"] == {"full_output": "done"}
        assert kwargs["peer_url"] == settings.FEDERATION_INSTANCE_URL.rstrip("/")

        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"
        assert fed_task.completed_at is not None

    def test_failed_dispatches_callback_with_failed_status(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)

        FederationService.notify_federation_result(
            seeded_db, local_task, "failed",
            result_summary="Failed: provider_unreachable",
        )

        assert recorder[0]["task_status"] == "failed"
        assert recorder[0]["result_summary"] == "Failed: provider_unreachable"
        seeded_db.refresh(fed_task)
        assert fed_task.status == "failed"
        assert fed_task.completed_at is None

    def test_non_federated_task_is_a_no_op(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        local_task.execution_context = json.dumps({"federated": False})
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []

    def test_missing_callback_url_still_updates_status_and_skips_dispatch(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer, callback_url=None)

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []
        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"

    def test_unknown_source_peer_skips_dispatch_but_updates_status(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)
        ctx = json.loads(local_task.execution_context)
        ctx["source_instance_id"] = "00000000-0000-0000-0000-000000000000"
        local_task.execution_context = json.dumps(ctx)
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []
        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"

    def test_malformed_execution_context_never_raises(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        local_task.execution_context = "not-json{{"
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")
        # malformed context == treated as non-federated: no dispatch, no raise
        assert recorder == []

    def test_no_federated_task_row_never_raises(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        seeded_db.query(FederatedTask).delete()
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")
        assert recorder == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose -f docker-compose.test.yml up -d
cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test REDIS_URL=redis://localhost:6379/1 CHROMA_HOST=localhost CHROMA_PORT=8001 CELERY_TASK_ALWAYS_EAGER=true TESTING=true PYTHONPATH=. pytest tests/integration/test_federation_result_callback.py -v
```

Expected: FAIL — every test errors with `AttributeError: type object 'FederationService' has no attribute 'notify_federation_result'`

- [ ] **Step 3: Implement the helper**

In `backend/services/federation_service.py`, add this static method to the `FederationService` class immediately after the `receive_task_result` method (before the next section comment). All imports it needs (`json`, `datetime`, `Optional`, `Dict`, `Any`, `settings`, `logger`, `FederatedInstance`, `FederatedTask`) already exist at the top of the file.

```python
    # ── Result callback (outbound) ────────────────────────────────────────────

    @staticmethod
    def notify_federation_result(
        db: Session,
        task: Task,
        status: str,
        result_summary: Optional[str] = None,
        result_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Phase 16.3: fire a result callback to the delegating instance when a
        federated local task reaches a terminal state ("completed" | "failed").

        Also flips the incoming FederatedTask row's status so the receiving
        instance's own Delegated Tasks tab reflects the outcome (16.3.3).

        Best-effort and total: NEVER raises — a broken callback must not fail
        the task it reports on. Safe to call for every task, federated or not.
        """
        try:
            ctx: Dict[str, Any] = {}
            if task.execution_context:
                try:
                    parsed = json.loads(task.execution_context)
                    if isinstance(parsed, dict):
                        ctx = parsed
                except (TypeError, ValueError):
                    ctx = {}
            if not ctx.get("federated"):
                return  # normal local task — nothing to do

            fed_task = (
                db.query(FederatedTask)
                .filter(FederatedTask.local_task_id == str(task.id))
                .first()
            )
            if not fed_task:
                logger.warning(f"Federation: no FederatedTask row for local task {task.id} — callback skipped")
                return

            # 1. Reflect the terminal state on the incoming record first —
            #    this must happen even if the outbound callback cannot be sent.
            fed_task.status = status
            fed_task.completed_at = datetime.utcnow() if status == "completed" else None
            db.commit()

            # 2. Best-effort outbound callback to the source instance.
            callback_url = ctx.get("callback_url")
            if not callback_url:
                logger.warning(f"Federation: task {task.id} has no callback_url — status recorded, callback skipped")
                return

            source_peer_id = ctx.get("source_instance_id")
            source_peer = None
            if source_peer_id:
                source_peer = (
                    db.query(FederatedInstance)
                    .filter(FederatedInstance.id == source_peer_id)
                    .first()
                )
            if not source_peer:
                logger.warning(f"Federation: source peer {source_peer_id} not found — status recorded, callback skipped")
                return

            data = result_data if isinstance(result_data, dict) else (
                task.result_data if isinstance(task.result_data, dict) else {}
            )
            summary = result_summary or task.result_summary or ""

            from backend.celery_app import send_federation_result
            send_federation_result.delay(
                callback_url=callback_url,
                peer_url=(settings.FEDERATION_INSTANCE_URL or "").rstrip("/"),
                signing_key=source_peer.signing_key,
                original_task_id=ctx.get("source_task_id") or fed_task.original_task_id,
                local_task_id=fed_task.local_task_id,
                task_status=status,
                result_summary=summary[:500],
                result_data=data,
            )
            logger.info(f"Federation: queued result callback for task {task.id} → {callback_url}")
        except Exception as exc:
            logger.error(f"Federation: notify_federation_result failed for task {getattr(task, 'id', '?')}: {exc}")
            try:
                db.rollback()
            except Exception:
                pass
```

- [ ] **Step 4: Run the tests to verify they pass**

Same command as Step 2. Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/federation_service.py backend/tests/integration/test_federation_result_callback.py
git commit -m "feat(federation): notify_federation_result helper closes result-callback loop"
```

---

### Task 2: Backend — wire the helper into the task executor's terminal paths

**Files:**
- Modify: `backend/services/tasks/task_executor.py` — three hook sites in `execute_task_async` (success path after `task.complete(...)` at line ~170; provider-exhaustion failure after the `db.commit()` at line ~289; retry-exhaustion failure after the `db.commit()` at line ~400)

**Interfaces:**
- Consumes: `FederationService.notify_federation_result(db, task, status, result_summary=None, result_data=None)` from Task 1
- Produces: no new interface — executor behavior only (a federated task's terminal transition now dispatches the callback)

Context: the executor hooks cannot be unit-tested in isolation because `execute_task_async` drives a full LLM pipeline (`agent.execute_with_skill_rag`). The helper is fully covered by Task 1's tests; this task's wiring is verified by the import smoke below and the live run in Task 7. The helper itself never raises; each hook's try/except only guards against import failure, matching the executor's defensive style.

- [ ] **Step 1: Add the success-path hook**

In `backend/services/tasks/task_executor.py`, immediately after the `task.complete(...)` call (the block ending at line ~173):

```python
            # Phase 16.3: report the result to the delegating peer
            # (no-op for non-federated tasks; never raises)
            try:
                from backend.services.federation_service import FederationService
                FederationService.notify_federation_result(db, task, "completed")
            except Exception as fed_exc:  # pragma: no cover - import safety
                logger.warning(f"Federation result callback failed for {task_id}: {fed_exc}")
```

- [ ] **Step 2: Add the provider-exhaustion failure hook**

In the `except RuntimeError` branch, immediately after the existing `db.commit()` (line ~289) and before the Phase 19.3 task-degraded broadcast:

```python
            # Phase 16.3: report failure to the delegating peer
            try:
                from backend.services.federation_service import FederationService
                FederationService.notify_federation_result(
                    db, task, "failed", result_summary=f"Failed: {reason}",
                )
            except Exception as fed_exc:  # pragma: no cover - import safety
                logger.warning(f"Federation result callback failed for {task_id}: {fed_exc}")
```

- [ ] **Step 3: Add the retry-exhaustion failure hook**

In the generic-exception branch's retry-exhausted block, immediately after the existing `db.commit()` (line ~400) and before the `return`:

```python
                # Phase 16.3: report failure to the delegating peer
                if task is not None:
                    try:
                        from backend.services.federation_service import FederationService
                        FederationService.notify_federation_result(
                            db, task, "failed", result_summary=f"Failed after retries: {exc}",
                        )
                    except Exception as fed_exc:  # pragma: no cover - import safety
                        logger.warning(f"Federation result callback failed for {task_id}: {fed_exc}")
```

- [ ] **Step 4: Verify imports and run the federation suite as regression**

```bash
PYTHONPATH=. DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test TESTING=true python -c "import backend.services.tasks.task_executor; import backend.services.federation_service; print('imports OK')"
cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test REDIS_URL=redis://localhost:6379/1 CHROMA_HOST=localhost CHROMA_PORT=8001 CELERY_TASK_ALWAYS_EAGER=true TESTING=true PYTHONPATH=. pytest tests/integration/test_federation_result_callback.py tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py tests/integration/test_federation_migration.py -v
```

Expected: `imports OK`, then all federation tests pass (68 total: 61 existing + 7 from Task 1). This confirms no circular imports and no regressions.

- [ ] **Step 5: Commit**

```bash
git add backend/services/tasks/task_executor.py
git commit -m "feat(federation): dispatch result callback from task executor terminal paths"
```

---

### Task 3: Frontend — 16.3.1 peers display tests + Sovereign-gate fetch fix (TDD)

**Files:**
- Test: `frontend/src/pages/__tests__/FederationPage.test.tsx` (new)
- Modify: `frontend/src/pages/FederationPage.tsx` — the bootstrap `useEffect` at lines 78-81

**Interfaces:**
- Consumes: `FederationPage` (named + default export from `@/pages/FederationPage`); `federationService` methods `listPeers`, `listFederatedTasks`, `registerPeer`, `deletePeer`, `updatePeerTrust`, `delegateTask`; pure helpers `getPeerStats`, `getTaskStats`, `formatHeartbeat` (kept real via `vi.importActual`); `useAuthStore` (reads `user.isSovereign`); `showToast` from `@/hooks/useToast`
- Produces: the shared mock scaffold in `FederationPage.test.tsx` (the `state` object and three `vi.mock` blocks) that Tasks 4 and 5 append their `describe` blocks to

Key DOM facts for the test code (verified against the components): the peers table has `aria-label="Registered peer instances"`; row buttons are `Remove peer {name}` / `Confirm removal of {name}` / `Cancel removal`; the trust select is `Trust level for {name}`; the search input is `Search peers`; empty states are `No Peer Instances` / `No Peers Found`; the access-denied card says `Access Denied`; stat cards read `Total Peers` / `Active` / `Suspended` / `Delegated Tasks`.

- [ ] **Step 1: Create the test file with the shared scaffold and 16.3.1 tests**

Create `frontend/src/pages/__tests__/FederationPage.test.tsx` with exactly this content:

```tsx
// frontend/src/pages/__tests__/FederationPage.test.tsx
// Behavioral tests for TODO §16.3 (16.3.1 peers display in this block;
// 16.3.2 connection/disconnection and 16.3.3 task status appended by
// later tasks of the implementation plan).

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FederationPage } from '@/pages/FederationPage';
import { showToast } from '@/hooks/useToast';

// ── Shared mutable mock state ─────────────────────────────────────────────────
// vi.hoisted runs before vi.mock factories are hoisted, so the factories
// can close over `state`. Tests mutate `state.user` and per-method vi.fn()s.

const state = vi.hoisted(() => ({
    user: { id: 'u1', name: 'Sovereign', isSovereign: true },
    listPeers: vi.fn(),
    listFederatedTasks: vi.fn(),
    registerPeer: vi.fn(),
    deletePeer: vi.fn(),
    updatePeerTrust: vi.fn(),
    delegateTask: vi.fn(),
}));

vi.mock('@/store/authStore', () => ({
    useAuthStore: () => ({ user: state.user }),
}));

vi.mock('@/hooks/useToast', () => ({
    showToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/services/federation', async () => {
    // Keep the pure derived helpers real; override only the API methods.
    const actual = await vi.importActual<typeof import('@/services/federation')>('@/services/federation');
    return {
        federationService: {
            ...actual.federationService,
            listPeers: state.listPeers,
            listFederatedTasks: state.listFederatedTasks,
            registerPeer: state.registerPeer,
            deletePeer: state.deletePeer,
            updatePeerTrust: state.updatePeerTrust,
            delegateTask: state.delegateTask,
        },
    };
});

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PEERS = [
    {
        id: 'p1', name: 'Peer Alpha', base_url: 'http://peer-alpha.local',
        status: 'active', trust_level: 'limited', capabilities_shared: ['tasks'],
        last_heartbeat_at: new Date().toISOString(), registered_at: '2026-01-01T00:00:00Z',
    },
    {
        id: 'p2', name: 'Peer Beta', base_url: 'http://peer-beta.local',
        status: 'suspended', trust_level: 'read_only', capabilities_shared: [],
        last_heartbeat_at: null, registered_at: '2026-01-02T00:00:00Z',
    },
];

const TASKS = [
    {
        id: 'f1', original_task_id: 'T0100', local_task_id: 'lt-1',
        source_instance_id: null, target_instance_id: 'p1',
        status: 'completed', direction: 'outgoing',
        delegated_at: '2026-10-09T10:00:00Z', completed_at: '2026-10-09T10:05:00Z',
    },
    {
        id: 'f2', original_task_id: 'T9900',
        source_instance_id: 'ext-1', target_instance_id: null,
        status: 'accepted', direction: 'incoming',
        delegated_at: '2026-10-09T11:00:00Z', completed_at: null,
    },
];

const resetMocks = () => {
    state.user = { id: 'u1', name: 'Sovereign', isSovereign: true };
    vi.clearAllMocks();
    state.listPeers.mockResolvedValue(PEERS);
    state.listFederatedTasks.mockResolvedValue(TASKS);
};

// ── 16.3.1 — displays connected peers ─────────────────────────────────────────

describe('FederationPage — 16.3.1 displays connected peers', () => {
    beforeEach(resetMocks);

    it('renders peer rows with name, URL, trust level and status', async () => {
        render(<FederationPage />);
        const table = await screen.findByLabelText('Registered peer instances');
        const row = within(table).getByText('Peer Alpha').closest('tr')!;
        expect(within(row).getByText('http://peer-alpha.local')).toBeInTheDocument();
        expect(within(row).getByLabelText('Trust level for Peer Alpha')).toHaveValue('limited');
        expect(within(row).getByText('Active')).toBeInTheDocument();
    });

    it('shows the empty state when no peers are registered', async () => {
        state.listPeers.mockResolvedValue([]);
        render(<FederationPage />);
        expect(await screen.findByText('No Peer Instances')).toBeInTheDocument();
    });

    it('filters peers by search query', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.change(screen.getByLabelText('Search peers'), { target: { value: 'beta' } });
        expect(screen.getByText('Peer Beta')).toBeInTheDocument();
        expect(screen.queryByText('Peer Alpha')).not.toBeInTheDocument();
    });

    it('shows the no-search-results empty state', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.change(screen.getByLabelText('Search peers'), { target: { value: 'zzz' } });
        expect(screen.getByText('No Peers Found')).toBeInTheDocument();
    });

    it('does not fetch federation data for non-Sovereign users', async () => {
        state.user = { id: 'u2', name: 'Pleb', isSovereign: false };
        render(<FederationPage />);
        expect(screen.getByText('Access Denied')).toBeInTheDocument();
        expect(state.listPeers).not.toHaveBeenCalled();
        expect(state.listFederatedTasks).not.toHaveBeenCalled();
    });
});
```

- [ ] **Step 2: Run the suite to see the gate test fail**

```bash
cd frontend && npx vitest run --project unit src/pages/__tests__/FederationPage.test.tsx
```

Expected: 4 pass, 1 fail — `does not fetch federation data for non-Sovereign users` fails because the bootstrap `useEffect` fires both fetches on mount before the Sovereign gate renders. (If a different test fails, fix the test to match actual rendered DOM before touching the component.)

- [ ] **Step 3: Gate the bootstrap fetch on Sovereign status**

In `frontend/src/pages/FederationPage.tsx`, replace the bootstrap effect (lines 78-81):

```tsx
    useEffect(() => {
        void fetchPeers();
        void fetchTasks();
    }, []);
```

with:

```tsx
    useEffect(() => {
        if (!user?.isSovereign) return;
        void fetchPeers();
        void fetchTasks();
    }, [user?.isSovereign]);
```

- [ ] **Step 4: Run the suite to verify all pass**

Same command as Step 2. Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/__tests__/FederationPage.test.tsx frontend/src/pages/FederationPage.tsx
git commit -m "test(federation): FederationPage 16.3.1 peer display suite; gate fetch on Sovereign"
```

---

### Task 4: Frontend — 16.3.2 connection/disconnection tests

**Files:**
- Test: `frontend/src/pages/__tests__/FederationPage.test.tsx` (append one describe block before the final closing lines of the file)

**Interfaces:**
- Consumes: the shared scaffold from Task 3 (`state`, `resetMocks`, `PEERS`); the AddPeerModal form labels `Peer Name` / `Base URL` / `Shared Secret` / `Capabilities` / submit button `Add Peer`; PeerTable's inline delete labels `Remove peer {name}` / `Confirm removal of {name}` / `Cancel removal`; trust select `Trust level for {name}`
- Produces: none — verification only

- [ ] **Step 1: Append the 16.3.2 describe block**

Append to `frontend/src/pages/__tests__/FederationPage.test.tsx` (after the 16.3.1 describe):

```tsx
// ── 16.3.2 — peer connection/disconnection ───────────────────────────────────

describe('FederationPage — 16.3.2 peer connection/disconnection', () => {
    beforeEach(resetMocks);

    it('registers a new peer through the Add Peer modal', async () => {
        state.registerPeer.mockResolvedValue(PEERS[0]);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Add new peer instance' }));
        fireEvent.change(screen.getByLabelText('Peer Name'), { target: { value: 'Peer Gamma' } });
        fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'http://peer-gamma.local' } });
        fireEvent.change(screen.getByLabelText('Shared Secret'), { target: { value: 's3cret' } });
        fireEvent.change(screen.getByLabelText(/Capabilities/), { target: { value: 'tasks' } });
        fireEvent.click(screen.getByRole('button', { name: 'Add Peer' }));

        await waitFor(() => expect(state.registerPeer).toHaveBeenCalledTimes(1));
        expect(state.registerPeer).toHaveBeenCalledWith(expect.objectContaining({
            name: 'Peer Gamma',
            base_url: 'http://peer-gamma.local',
            shared_secret: 's3cret',
            trust_level: 'limited',
            capabilities: ['tasks'],
        }));
        // list refreshed after successful registration
        expect(state.listPeers.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('shows an error toast and keeps the modal open when registration fails', async () => {
        state.registerPeer.mockRejectedValue(new Error('Failed to register peer: boom'));
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Add new peer instance' }));
        fireEvent.change(screen.getByLabelText('Peer Name'), { target: { value: 'Peer Gamma' } });
        fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'http://peer-gamma.local' } });
        fireEvent.change(screen.getByLabelText('Shared Secret'), { target: { value: 's3cret' } });
        fireEvent.click(screen.getByRole('button', { name: 'Add Peer' }));

        await waitFor(() => expect(vi.mocked(showToast.error)).toHaveBeenCalledWith('Failed to register peer: boom'));
        // modal stays open for a retry
        expect(screen.getByLabelText('Peer Name')).toBeInTheDocument();
    });

    it('removes a peer via the inline delete confirmation', async () => {
        state.deletePeer.mockResolvedValue(undefined);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Remove peer Peer Alpha' }));
        fireEvent.click(screen.getByRole('button', { name: 'Confirm removal of Peer Alpha' }));

        await waitFor(() => expect(state.deletePeer).toHaveBeenCalledWith('p1'));
    });

    it('cancelling the inline delete leaves the peer in place', async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.click(screen.getByRole('button', { name: 'Remove peer Peer Alpha' }));
        fireEvent.click(screen.getByRole('button', { name: 'Cancel removal' }));

        expect(state.deletePeer).not.toHaveBeenCalled();
        expect(screen.getByText('Peer Alpha')).toBeInTheDocument();
    });

    it('updates a peer trust level from the row select', async () => {
        state.updatePeerTrust.mockResolvedValue(PEERS[0]);
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');

        fireEvent.change(screen.getByLabelText('Trust level for Peer Alpha'), { target: { value: 'full' } });

        await waitFor(() => expect(state.updatePeerTrust).toHaveBeenCalledWith('p1', 'full'));
    });
});
```

- [ ] **Step 2: Run the suite**

```bash
cd frontend && npx vitest run --project unit src/pages/__tests__/FederationPage.test.tsx
```

Expected: all pass (10 total). These tests pin existing behavior — if one fails, it has surfaced a real defect: fix the component (not the test) and note the fix in the commit message.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/__tests__/FederationPage.test.tsx
git commit -m "test(federation): FederationPage 16.3.2 connection/disconnection suite"
```

---

### Task 5: Frontend — 16.3.3 cross-instance task status tests

**Files:**
- Test: `frontend/src/pages/__tests__/FederationPage.test.tsx` (append one describe block)

**Interfaces:**
- Consumes: the shared scaffold from Task 3 (`state`, `resetMocks`, `PEERS`, `TASKS`); the tabs `Peer Instances` / `Delegated Tasks` (`role="tab"`); the tasks list `aria-label="Federated task list"`; DelegateTaskModal labels `Target Peer` / `Original Task ID` / `Payload` / submit button `Delegate`; status badge labels `Completed` / `Accepted` (from `@/utils/statusColors` `FED_TASK_STATUS_COLORS`)
- Produces: none — verification only

- [ ] **Step 1: Append the 16.3.3 describe block**

Append to `frontend/src/pages/__tests__/FederationPage.test.tsx` (after the 16.3.2 describe):

```tsx
// ── 16.3.3 — cross-instance task status ───────────────────────────────────────

describe('FederationPage — 16.3.3 cross-instance task status', () => {
    beforeEach(resetMocks);

    const openTasksTab = async () => {
        render(<FederationPage />);
        await screen.findByText('Peer Alpha');
        fireEvent.click(screen.getByRole('tab', { name: /Delegated Tasks/ }));
    };

    it('lists federated tasks with status badges, direction and completion time', async () => {
        await openTasksTab();
        const list = screen.getByLabelText('Federated task list');

        expect(within(list).getByText('T0100')).toBeInTheDocument();
        expect(within(list).getByText('T9900')).toBeInTheDocument();
        expect(within(list).getByText('Completed')).toBeInTheDocument();
        expect(within(list).getByText('Accepted')).toBeInTheDocument();
        expect(within(list).getByText('↑ Outgoing')).toBeInTheDocument();
        expect(within(list).getByText('↓ Incoming')).toBeInTheDocument();
    });

    it('shows the empty state when there are no federated tasks', async () => {
        state.listFederatedTasks.mockResolvedValue([]);
        await openTasksTab();
        expect(await screen.findByText('No Delegated Tasks')).toBeInTheDocument();
    });

    it('disables Delegate Task when there are no active peers', async () => {
        state.listPeers.mockResolvedValue([PEERS[1]]); // suspended peer only
        await openTasksTab();
        expect(screen.getByRole('button', { name: 'Delegate a task to a peer' })).toBeDisabled();
    });

    it('delegates a task through the modal', async () => {
        state.delegateTask.mockResolvedValue({ id: 'f9', status: 'pending', message: 'queued' });
        await openTasksTab();

        fireEvent.click(screen.getByRole('button', { name: 'Delegate a task to a peer' }));
        fireEvent.change(screen.getByLabelText('Target Peer'), { target: { value: 'p1' } });
        fireEvent.change(screen.getByLabelText('Original Task ID'), { target: { value: 'T0100' } });
        fireEvent.change(screen.getByLabelText(/Payload/), { target: { value: '{"title": "hello"}' } });
        fireEvent.click(screen.getByRole('button', { name: 'Delegate' }));

        await waitFor(() => expect(state.delegateTask).toHaveBeenCalledWith({
            target_peer_id: 'p1',
            original_task_id: 'T0100',
            payload: { title: 'hello' },
        }));
    });
});
```

- [ ] **Step 2: Run the full FederationPage suite**

```bash
cd frontend && npx vitest run --project unit src/pages/__tests__/FederationPage.test.tsx
```

Expected: all pass (14 total). Same rule as Task 4: a failure is a surfaced defect — fix the component, not the test.

- [ ] **Step 3: Run the existing a11y suite for the page to confirm no regression**

```bash
cd frontend && npx vitest run --project a11y src/pages/FederationPage.a11y.browser.test.tsx
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/__tests__/FederationPage.test.tsx
git commit -m "test(federation): FederationPage 16.3.3 task-status suite"
```

---

### Task 6: Script — `scripts/fake_federation_peer.py`

**Files:**
- Create: `scripts/fake_federation_peer.py`

**Interfaces:**
- Consumes: the delegation payload the primary sends to `/api/v1/federation/webhooks/tasks/receive` — a JSON body containing at least `original_task_id` and `callback_url`; peer auth headers `X-Agentium-Peer-Url` / `X-Agentium-Timestamp` / `X-Agentium-Signature` where the signature is HMAC-SHA256 keyed by `SHA-256(secret + ":sign")` over `"{timestamp}:" + body` (mirrors `backend/celery_app._hmac_sign` / `_signed_headers` and `FederationService._derive_signing_key`)
- Produces: a running HTTP server on `--port` (default 8100) that the primary instance registers as a peer; used by Task 7's live run

Wire contract for the result callback (must match what `/webhooks/tasks/result` expects — same shape `send_federation_result` sends): `{"original_task_id", "local_task_id", "status", "result_summary", "result_data"}`.

- [ ] **Step 1: Write the script**

Create `scripts/fake_federation_peer.py` with exactly this content:

```python
#!/usr/bin/env python3
"""
fake_federation_peer.py — dev tool for live-verifying TODO §16.3.

Emulates a remote Agentium peer for a single local instance:
  * receives delegated tasks on POST /api/v1/federation/webhooks/tasks/receive
  * immediately posts a signed "completed" result back to the payload's
    callback_url (exercising the 16.3.3 result-callback loop end-to-end)
  * answers heartbeat probes with 200 so the peer shows as active

HMAC headers mirror backend/celery_app._signed_headers; the signing key
mirrors FederationService._derive_signing_key (SHA-256(secret + ":sign")).

Usage:
    python scripts/fake_federation_peer.py --secret my-dev-secret --port 8100

Then register this in the UI with base_url http://localhost:8100 and the
SAME shared secret.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import httpx
except ImportError:
    sys.exit("httpx is required (already a backend dependency): pip install httpx")


def derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def signed_headers(peer_url: str, signing_key: str, body: bytes) -> dict:
    """Mirror backend.celery_app._signed_headers."""
    ts = int(time.time())
    sig = hmac.new(signing_key.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(ts),
        "X-Agentium-Signature": f"sha256={sig}",
    }


class FakePeerHandler(BaseHTTPRequestHandler):
    # Set from main(); carries --peer-url and the derived signing key.
    args: argparse.Namespace

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        if self.path.endswith("/webhooks/heartbeat"):
            print("[fake-peer] heartbeat probe received → 200 OK")
            self._reply(200, {"status": "ok"})
            return

        if self.path.endswith("/webhooks/tasks/receive"):
            payload = json.loads(raw)
            original_task_id = payload.get("original_task_id")
            callback_url = payload.get("callback_url")
            print(f"[fake-peer] received delegation {original_task_id} → {callback_url}")

            result = {
                "original_task_id": original_task_id,
                "local_task_id": f"fake-{int(time.time())}",
                "status": "completed",
                "result_summary": "Completed by fake_federation_peer (dev tool).",
                "result_data": {"source": "scripts/fake_federation_peer.py"},
            }
            body = json.dumps(result).encode()
            try:
                resp = httpx.post(
                    callback_url,
                    content=body,
                    headers=signed_headers(self.args.peer_url, self.args.signing_key, body),
                    timeout=20,
                )
                resp.raise_for_status()
                print(f"[fake-peer] result callback accepted: {resp.status_code}")
            except Exception as exc:
                print(f"[fake-peer] result callback FAILED: {exc}")

            self._reply(200, {"status": "accepted", "task_id": original_task_id})
            return

        self._reply(404, {"detail": "Not found"})

    def log_message(self, fmt, *args):  # silence http.server's stderr noise
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Agentium federation peer (TODO 16.3 dev tool)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--secret", required=True,
                        help="Shared secret — must match the one used to register this peer in the UI")
    parser.add_argument("--peer-url", default=None,
                        help="Value sent as X-Agentium-Peer-Url — must match the registered base_url "
                             "(default: http://localhost:<port>)")
    args = parser.parse_args()

    args.signing_key = derive_signing_key(args.secret)
    if not args.peer_url:
        args.peer_url = f"http://localhost:{args.port}"
    FakePeerHandler.args = args

    server = ThreadingHTTPServer((args.host, args.port), FakePeerHandler)
    print(f"[fake-peer] listening on http://{args.host}:{args.port}")
    print(f"[fake-peer] register in the UI with base_url={args.peer_url} and the same shared secret")
    print(f"[fake-peer] Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify signing parity against the backend**

Run from the repo root (Git Bash):

```bash
PYTHONPATH=. python - <<'EOF'
import importlib.util, hashlib, hmac

spec = importlib.util.spec_from_file_location("fake_peer", "scripts/fake_federation_peer.py")
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

from backend.services.federation_service import FederationService, _sign_payload

# Key derivation must match the backend exactly
assert fp.derive_signing_key("s") == FederationService._derive_signing_key("s")

# Signature algorithm must match _sign_payload (key = signing_key over "{ts}:" + body)
body = b'{"original_task_id": "T0100"}'
ts = 1234567890
key = fp.derive_signing_key("s")
script_style = hmac.new(key.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
assert script_style == _sign_payload(key, body, ts)
print("signing parity OK")
EOF
```

Expected: `signing parity OK`. (If importing `backend.services.federation_service` needs env vars, prefix the same env used for backend tests: `DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test TESTING=true PYTHONPATH=.`)

- [ ] **Step 3: Commit**

```bash
git add scripts/fake_federation_peer.py
git commit -m "feat(scripts): fake_federation_peer dev tool for live federation verification"
```

---

### Task 7: Live verification run

**Files:**
- No file changes — this is the live sign-off of 16.3.1, 16.3.2, 16.3.3 (unless it surfaces a defect; fix any defect found and commit it with `fix(federation): ...` before continuing)

**Interfaces:**
- Consumes: everything from Tasks 1-6
- Produces: the verified behaviors that Task 8's TODO note records

- [ ] **Step 1: Start the dev stack**

```bash
make up
```

Then confirm the backend is reachable and federation is enabled — `FEDERATION_ENABLED` must be true and `FEDERATION_INSTANCE_URL` must be host-reachable (e.g. `http://localhost:8000`, since the fake peer posts the result callback from the host). Check `docker compose ps` and the backend logs.

- [ ] **Step 2: Start the frontend and the fake peer**

Terminal A:

```bash
cd frontend && npm run dev
```

Terminal B:

```bash
python scripts/fake_federation_peer.py --port 8100 --secret dev-fed-secret
```

- [ ] **Step 3: Verify 16.3.1 — peers display**

In the browser: log in as a Sovereign (admin) user → open the Sovereign Dashboard → Federation tab. Confirm the page renders: stats cards, Peers tab, empty state ("No Peer Instances").

- [ ] **Step 4: Verify 16.3.2 — connection/disconnection**

Click **Add Peer**: name "Fake Peer", base URL `http://localhost:8100`, shared secret `dev-fed-secret`, trust "Limited", capabilities `tasks`. Submit → the peer appears in the table (16.3.1+16.3.2 connection side verified live; heartbeat may show "Never" until the 5-minute Celery beat probe runs — the fake peer answers it with 200).

- [ ] **Step 5: Verify 16.3.3 — task status closes the loop**

Switch to the **Delegated Tasks** tab → **Delegate Task**: target "Fake Peer", Original Task ID `T0100`, payload `{"title": "Live loop check"}` → Delegate. Watch the fake peer's console ("received delegation T0100", "result callback accepted: 200"). Click **Refresh** in the Tasks tab → the task shows status **Completed** with a completion timestamp (pending → delivered → completed all visible in the log/status history as applicable).

- [ ] **Step 6: Verify disconnection**

Back on the Peers tab: click the trash icon on "Fake Peer" → **Confirm** → the row disappears and the stats update.

- [ ] **Step 7: Record the outcome**

Note anything that failed and was fixed (commit any fixes). The next task records the verification in the TODO.

---

### Task 8: TODO.md sign-off and final commit

**Files:**
- Modify: `docs/documents/TODO.md` (§16.3 block at lines ~804-807)

**Interfaces:**
- Consumes: completed Tasks 1-7 (all tests green, live run successful)
- Produces: ticked §16.3 checkboxes with a verification note in the 16.1/16.2 style

- [ ] **Step 1: Tick the checkboxes and add the verification note**

In `docs/documents/TODO.md`, replace:

```markdown
- [ ] **16.3 — Federation Frontend**
  - [ ] 16.3.1 — `FederationPage.tsx` displays connected peers
  - [ ] 16.3.2 — Peer connection/disconnection UI works
  - [ ] 16.3.3 — Cross-instance task status is visible
```

with:

```markdown
- [x] **16.3 — Federation Frontend**
  - [x] 16.3.1 — `FederationPage.tsx` displays connected peers
  - [x] 16.3.2 — Peer connection/disconnection UI works
  - [x] 16.3.3 — Cross-instance task status is visible

  > **Verified:** Behavioral suite in `frontend/src/pages/__tests__/FederationPage.test.tsx` passes (peer table rendering/search/empty states, Sovereign gate now skips fetching for non-Sovereign users, Add Peer → register → refresh flow, inline delete-confirm, trust-level editing, task status badges with direction + completion timestamps, delegate-task modal, disabled Delegate when no active peers); existing a11y contrast suite unaffected. Closes the `send_federation_result` gap carried forward from 16.1/16.2: `FederationService.notify_federation_result` (federation_service.py) updates the incoming `FederatedTask` row and dispatches the Celery result callback from all three terminal paths in `task_executor.py` (completion, provider exhaustion, retry exhaustion) — 7 new integration tests in `backend/tests/integration/test_federation_result_callback.py`. Verified live end-to-end via `scripts/fake_federation_peer.py` (delegate from the UI → signed result callback → status shows Completed in the Tasks tab) plus peer register/remove round-trip.
```

- [ ] **Step 2: Run the full federation suites one final time**

```bash
cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test REDIS_URL=redis://localhost:6379/1 CHROMA_HOST=localhost CHROMA_PORT=8001 CELERY_TASK_ALWAYS_EAGER=true TESTING=true PYTHONPATH=. pytest tests/integration/test_federation_result_callback.py tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py tests/integration/test_federation_migration.py -v
cd frontend && npx vitest run --project unit src/pages/__tests__/FederationPage.test.tsx
```

Expected: all 68 backend federation tests and all 14 frontend tests pass.

- [ ] **Step 3: Commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark §16.3 federation frontend verified (TODO 16.3.1-16.3.3)"
```
