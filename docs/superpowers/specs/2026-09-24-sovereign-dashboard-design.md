# Sovereign Dashboard — Verification & Fix Design (TODO 12.4)

> **Date**: 2026-09-24
> **Scope**: TODO 12.4.1–12.4.3, sovereign-only controls. Embedded tabs (Skills, Scaling, Dev Portal, …) are deferred to their own TODO items (12.5–12.9).
> **Approach**: Fix the confirmed bugs TDD-first, then run one verification pass (code audit + live smoke) on the fixed code.

---

## 1. Current state (verified by exploration)

The subsystem already exists — nothing needs building from scratch:

- **`frontend/src/pages/SovereignDashboard.tsx`** — 13-tab keep-alive control panel (System, Financial, Auto-Scaling, MCP Tools, Knowledge, Marketplace, Access Control, Federation, Webhooks, Dev Portal, Mobile, Events, Self-Improvement). Gates on `user?.isSovereign` with an access-denied screen. Wired at `/sovereign` in `App.tsx` inside `SovereignRoute`, lazy-loaded. Sidebar has a nav entry with route preloading.
- **`frontend/src/components/SovereignRoute.tsx`** — guard: unauthenticated → `/login`, non-sovereign → `/`.
- **`frontend/src/store/authStore.ts`** — `deriveIsSovereign()` returns `true` only when `is_sovereign === true` or `role === 'primary_sovereign'`; plain `is_admin` is deliberately **not** sufficient (B6: not all admins are sovereign).
- **`backend/api/sovereign.py`** (registered at `/api/v1/sovereign` in `main.py:655`) — all REST endpoints gated by `get_current_sovereign_user` (`is_admin` check → 403 `SOVEREIGN_ONLY`); WebSocket `/api/v1/sovereign/ws` validates JWT + admin before accepting (close codes 4001 missing/invalid token, 4003 non-admin); sovereign actions audit-logged (container actions → GOVERNANCE/WARNING, commands → CRITICAL).
- **`backend/services/host_access.py`** — `HostAccessService` talks to Docker over `unix:///var/run/docker.sock`; `docker-compose.yml` mounts the socket (`:rw`) and `/host` into the backend container, so container management can work.
- **`frontend/src/hooks/useSystemTab.ts`** — system status + containers via `useRealtimeData` (10s poll + WS refresh); command logs via sovereign WebSocket push only.
- **Existing tests**: `SovereignDashboard.a11y.browser.test.tsx` (light + dark, screenshots committed). No unit tests for the guard, hook, or verify flow.

## 2. Confirmed bugs to fix

### Fix 1 — Sovereign loses dashboard access on page refresh (12.4.2)

**Root cause chain (statically traced):**

1. Login JWT embeds `"role": getattr(user, "role", "user")` (`backend/api/routes/auth.py:249`) — the **raw** role column, which defaults to `ROLE_OBSERVER` (`backend/models/entities/user.py:56`) for the default admin.
2. The login response uses `user.to_dict()`, which returns `effective_role` (`primary_sovereign` via the `is_admin` backward-compat mapping) + `is_sovereign: True` — so login works and `isSovereign` is `true`.
3. On page refresh, `checkAuth` calls `POST /api/v1/auth/verify`, whose response is built from **JWT claims** (`role: "observer"`, no `is_sovereign` field) — the endpoint already fetches the persisted user but uses it only for `avatar_url` (`auth.py:372-386`).
4. `deriveIsSovereign({role: "observer", is_admin: true})` → `false` → `SovereignRoute` redirects the sovereign back to `/`.

**Fix (backend-only, minimal blast radius):** in `/verify`, when the persisted user exists, return DB truth: `user_payload["is_sovereign"] = user.is_sovereign` and `user_payload["role"] = user.effective_role`. The JWT stays untouched — changing JWT claims ripples into MCP governance/tier fields, and the `/verify` fix covers the frontend path. No schema change needed (`VerifyResponse.user` is a dict).

**Edge case:** JWT valid but user deleted from DB → `is_sovereign` absent → `false` → access denied (safe default).

**Regression tests:** backend test asserting `/verify` returns `is_sovereign: True` + `role: "primary_sovereign"` for an admin (reuses the `seeded_db` admin fixture pattern); frontend unit tests for `deriveIsSovereign` truth table (`primary_sovereign` → true, `is_sovereign` → true, plain admin → false, observer/JWT-fallback shape → false).

### Fix 2 — Command History never loads (12.4.3)

**Root cause — a phantom contract on both sides:**

- The backend never emits a `command_log` WebSocket message anywhere (`notify_sovereign` is only called for `agent_blocked`).
- `useSystemTab` never calls the existing `GET /api/v1/sovereign/commands` REST endpoint (`hostAccessApi.getCommandHistory` exists but is unused).

Result: the Command History panel is **permanently empty** — invisible because keep-alive tabs render an empty state rather than erroring.

**Fix (both sides, closing the contract):**

- **Frontend:** `useSystemTab` seeds `commandLogs` from `hostAccessApi.getCommandHistory(50)` on connect (graceful on failure — error banner + retry pattern), and maps the `AuditLog.to_dict()` shape (`action`, `description`, `created_at`, `level`, `actor_id`) onto the `CommandLog` display type: `action` becomes the display text, `level` maps to status colors, `created_at` → timestamp. Live WS `command_log` pushes then prepend new entries.
- **Backend:** sovereign command + container-action endpoints emit a `command_log` WS push via the existing `notify_sovereign()` helper, so live updates appear while the dashboard is open.

**Regression tests:** backend test asserting `/commands` returns seeded entries and that the command endpoint calls `notify_sovereign` (monkeypatched); frontend `useSystemTab` unit test with mocked `hostAccessApi` — REST seeds history, WS `command_log` appends, seed failure degrades gracefully.

## 3. Verification plan

### Code audit (per TODO checklist item)

- **12.4.1 — Dashboard loads (admin-only route):** route wiring in `App.tsx`, sidebar nav entry + preload, keep-alive tab mounting, a11y suite passes (light + dark), `npm run build` green.
- **12.4.2 — SovereignRoute enforces access:** guard logic (unauthenticated → `/login`, non-sovereign → `/`), `deriveIsSovereign` correctness (unit tests), backend 403 `SOVEREIGN_ONLY` on every `/api/v1/sovereign/*` endpoint for a non-admin token, WebSocket close codes (4001/4003).
- **12.4.3 — System-wide controls:** each control traced frontend → API → backend: system status (psutil, `/host` disk fallback), containers list/actions (Docker socket), command history (after Fix 2), audit endpoint filters, agent block/unblock (audit + WS notification). Single-worker WS registry and restricted host-access mode are understood limitations, not bugs.

### Live smoke (real stack, non-destructive)

- **Backend via API calls:** login `admin/admin` → token; `GET /api/v1/sovereign/system/status` (200, CPU > 0); `GET /api/v1/sovereign/containers` (200, real list); seed a command-history entry harmlessly via `POST /api/v1/sovereign/containers/nonexistent-id/restart` (the audit is written *before* the Docker call fails — also exercises the C9 history fix); `GET /api/v1/sovereign/commands` returns it; WebSocket connects with a valid token, closes 4003 with a non-admin token.
- **Frontend E2E (Playwright against the live stack, guarded by an env flag so it never runs in CI):** sovereign login → `/sovereign` renders "Sovereign Control Panel" → **page refresh keeps access** (Fix 1 regression, asserted in the browser) → System tab cards show non-zero real data → non-sovereign user is redirected from `/sovereign`.
- **Destructive actions** (container start/stop/remove on real containers) stay audit-only — the endpoint path is traced, not executed.
- **Fallback:** if Playwright-against-live-stack is blocked by env/infra issues, fall back to curl API smoke + a manual browser checklist for the user.

## 4. Testing strategy

- **New regression tests (durable, TDD-first):**
  - Backend: `/verify` sovereign fields from DB (Fix 1); `/commands` seeded entries + `notify_sovereign` push contract (Fix 2).
  - Frontend (vitest; infra exists from the Settings work): `deriveIsSovereign` truth table; `SovereignRoute` guard (sovereign stays, non-sovereign → `/`, unauthenticated → `/login`); `useSystemTab` with mocked `hostAccessApi`.
- **Existing suites re-run:** SovereignDashboard a11y browser test (light + dark), backend pytest (auth + sovereign-relevant files), frontend test suite + `npm run build`.

## 5. Recording results

- TODO.md: mark 12.4.1–12.4.3 `[x]` with a Notes (12.4) block — verified items, the two fixes, contract corrections, accepted limitations.
- Code fixes + tests committed; verification summary in commit messages (existing doc-commit style). Design doc may be removed after completion per established practice.

## 6. Out of scope (explicitly)

- Embedded tabs (Skills, Scaling, Dev Portal, Mobile, etc.) → own TODO items 12.5–12.9.
- `/verify-session` (voice bridge) has the same raw-role gap but doesn't consume `isSovereign` — recorded as a related observation only.
- JWT `role` claim stays the raw column — the `/verify` fix covers the frontend path with far less blast radius.
- Multi-worker WebSocket registry (module-level `active_connections`, single-worker assumption) — documented limitation, already noted in code.
- Container start/stop/restart/remove executed against real containers.
- Work happens on a feature branch (`fix/sovereign-dashboard-12.4`); merge/push decision at the end.
