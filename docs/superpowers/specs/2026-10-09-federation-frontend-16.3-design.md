# §16.3 Federation Frontend — Check & Fix Design

Date: 2026-10-09
Status: Approved
Scope: TODO.md §16.3 (16.3.1, 16.3.2, 16.3.3) plus closing the carried-forward `send_federation_result` gap

## Context

§16.3 asks for three things: `FederationPage.tsx` displays connected peers
(16.3.1), peer connection/disconnection UI works (16.3.2), and cross-instance
task status is visible (16.3.3).

Exploration found the frontend **already built and contract-clean**:

- `frontend/src/pages/FederationPage.tsx` — Peers tab (search, add-peer modal,
  inline delete-confirm, trust-level select, heartbeat display) and Delegated
  Tasks tab (status badges, direction icons, delegate modal, refresh). Sovereign-
  gated; mounted via `SovereignDashboard`'s `'federation'` tab.
- `frontend/src/services/federation.ts` — register/list/delete peer, trust
  update, delegate task, list tasks. Types match the backend serializers
  field-for-field (verified against `backend/api/routes/federation.py`, including
  the derived `direction` field).
- Only frontend test is an a11y contrast audit — behavior is unverified.

**The blocking gap is backend-side.** `send_federation_result` (celery_app.py:708,
the result callback to the originating peer) is defined but never dispatched, so
delegated tasks sit at `accepted` forever on the originating instance — 16.3.3
cannot be signed off end-to-end without closing this loop. This gap was noted as
"carried forward" in the 16.1/16.2 verification notes.

Everything the callback needs is already persisted on the receiving instance at
webhook-receive time (`backend/services/federation_service.py`):
`execution_context` stores `federated: true`, `source_instance_id`,
`source_task_id`, and `callback_url`; the `FederatedTask` row links
`local_task_id ↔ original_task_id`. **No schema migration is required.**

## Decisions (from brainstorming)

1. Wire `send_federation_result` into the task completion path — in scope.
2. Sign-off bar = behavioral tests **plus** live verification.
3. Live run = one real instance + a scripted fake peer (not two full instances).
4. Wiring approach: helper in `federation_service.py`, called from
   `task_executor.py` (keeps federation logic in the service with its 61 tests;
   avoids growing the 1,600-line executor).

## Section 1 — Backend: closing the result-callback loop

New static helper in `backend/services/federation_service.py`:

```python
@staticmethod
def notify_federation_result(db, task, status: str) -> None
```

Called with `"completed"` or `"failed"`. Logic:

1. Parse `task.execution_context` (JSON string). If the `federated` flag is
   absent, return immediately — normal tasks pay one dict-parse and nothing else.
2. Look up the local `FederatedTask` row by `local_task_id == str(task.id)` and
   update its status to `completed`/`failed`. This matters for 16.3.3: the
   receiving instance's Tasks tab also lists incoming tasks, which are otherwise
   stuck at `accepted` forever.
3. Parse `callback_url` and `source_task_id` from `execution_context`; re-fetch
   the source peer by `source_instance_id` for its signing key.
4. Best-effort dispatch `send_federation_result.delay(...)` (the Celery task at
   `celery_app.py:708` already implements HMAC signing and 3-retry exponential
   backoff). Any failure is logged and swallowed — a broken callback must never
   fail the task itself.

Executor hooks in `backend/services/tasks/task_executor.py` — one call at each
terminal transition of local task execution:

- after `task.complete(...)` (~line 170)
- in each branch that marks the task `failed` (the `provider_unreachable` path
  at ~245, plus any other `task.fail(...)` sites enumerated during planning)

The executor adds ~2 lines per site; all lookup/dispatch logic lives in the
service.

## Section 2 — Frontend: verification and fixes

No new UI surface — verification plus targeted fixes.

**16.3.1 — displays connected peers.** New behavioral suite
(`frontend/src/pages/__tests__/FederationPage.test.tsx`, Vitest + React Testing
Library, `federationService` mocked, following existing repo conventions):

- Stats cards and `PeerTable` render with peer data (name, URL, trust level,
  status badge, heartbeat)
- Search filter narrows by name and URL; "no results" state when filter matches
  nothing
- Loading and empty states
- Sovereign gate: non-Sovereign user sees Access Denied and no data fetch occurs

**16.3.2 — connection/disconnection UI.** Mocked-interaction tests:
Add Peer modal submits valid data → `registerPeer` called → success toast → list
refreshed; inline delete-confirm → `deletePeer` called → peer removed; trust
select → `updatePeerTrust` called. "Connection" = registration (peer becomes
active after heartbeat), "disconnection" = removal — the backend has no
suspend/resume endpoint, so the UI matches the existing contract.

**16.3.3 — cross-instance task status.** Tasks tab tests: each status renders
the correct badge via `getFedTaskStatusColors`; direction (↑ outgoing /
↓ incoming) shows correctly; completed tasks show completion timestamp; Delegate
Task button disabled when no active peers.

**Fixes as found.** Tests decide, but candidates from code reading:
Delegate Task button doesn't account for initial load (`peerStats.active === 0`
while peers still loading → button flashes disabled); tasks list lacks an
error state distinct from empty.

## Section 3 — Fake peer and live verification

**Script** — `scripts/fake_federation_peer.py` (repo already has a `scripts/`
directory). Single-file, dependency-light (`http.server`, `hmac`/`hashlib`,
`httpx` or `requests`):

- Listens on configurable port (default `8100`) for
  `POST /api/v1/federation/webhooks/tasks/receive`
- Logs the delegation payload, then posts back to the payload's `callback_url`
  with an HMAC-SHA256 signature derived from the shared secret (CLI arg / env),
  mirroring the format `authenticate_peer` expects (pinned by the existing 61
  federation tests — mirror their fixture signing code)
- Result body: `original_task_id` + `local_task_id` echoed, `status:
  "completed"`, short `result_summary`
- Optionally answers `/webhooks/heartbeat` probes with 200 so the Active /
  heartbeat column is exercised

**Live run procedure** (encoded as concrete plan steps):

1. Start backend dev stack (API + Celery worker + beat)
2. Start frontend dev server
3. Register the fake peer via the UI's Add Peer modal (base_url
   `http://localhost:8100`, shared secret) — exercises 16.3.2 connection side
4. Delegate a task from the Tasks tab → fake peer receives it, calls back
5. Refresh Tasks tab → status `completed` with timestamp — 16.3.3 verified live
6. Remove peer via inline delete flow — 16.3.2 disconnection side

## Section 4 — Testing, error handling, scope

**Backend tests** (extending the 61 existing federation tests):
- Unit tests for `notify_federation_result`: non-federated → no-op with no
  dispatch; federated → dispatch with correct callback URL, signing key, IDs;
  missing `callback_url`/peer → logged, skipped, never raises; local
  `FederatedTask` row flips status even when dispatch is skipped
- Integration test for the executor hook: federated local task created via the
  receive webhook completes through the executor → callback dispatched
  (Celery eager mode or mocked `.delay`, per existing delegation-test
  conventions)

**Error handling:**
- Result callbacks are best-effort; `send_federation_result` retries 3× with
  backoff; the helper never lets callback problems fail the task
- Frontend surfaces API errors via toasts and re-fetches to revert optimistic
  state — tests pin existing behavior rather than change it

**Out of scope:**
- UI for agent migration, knowledge sync, federated votes (not in the 16.3
  sub-items)
- Heartbeat/suspend mechanics changes (16.1 verified)
- New backend endpoints — none needed
- `send_federation_result` retry tuning

**Success criteria:** all three sub-items verified live and by test suites; TODO
checkboxes ticked with a verification note in the 16.1/16.2 style, recording that
the carried-forward result-callback gap is now closed.
