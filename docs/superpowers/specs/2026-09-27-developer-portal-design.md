# Developer Portal — Verification & API Keys — Design

**Date**: 2026-09-27
**Scope**: TODO 12.5 — 12.5.1 (`DeveloperPortalPage.tsx` renders API documentation) and 12.5.2 (API key generation from portal works)
**Process**: Brainstorming session 2026-09-27; design approved by user.

---

## 1. Current State (code audit findings)

**12.5.1 — the page exists, but its documentation is partly fictional.**

- `frontend/src/pages/DeveloperPortalPage.tsx` renders five static tabs (API Reference, Python SDK, TypeScript SDK, cURL, Webhook Events) and is embedded as the `developer-portal` tab inside the sovereign-only Sovereign Dashboard's keep-alive panel (`SovereignDashboard.tsx:162`). It is not a standalone route in `App.tsx`. An a11y browser test audits color contrast in light+dark.
- Accurate as-is: `/api/health` (`backend/main.py:705`), `/docs`, `/openapi.json`, the constitution paths (`/api/v1/constitution/update`, `/preferences`), the voting paths, `/api/v1/webhooks/subscriptions` CRUD (`backend/api/routes/outbound_webhooks.py`), and all eight webhook event names (`backend/services/webhook_dispatch_service.py:31-38`).
- Fictional: `GET /api/v1/agents/:id` and `POST /api/v1/agents/create` (the real `backend/api/routes/agents.py` has only `POST /verify`; agents are created via Genesis). The TypeScript sample is broken code — its `console.log` lines were commented out mid-expression, likely by a secret-scanner pass.
- The Authentication section advertises `X-API-Key: sk-...` header auth; the backend has no such inbound auth. The only `X-API-Key` usage in the backend is outbound (`http_api_tool.py:97`, `model_provider.py:2581`).

**12.5.2 — nothing exists.**

- No developer-key entity, no generation endpoint, no middleware validating inbound `X-API-Key` headers, no key UI in the portal.
- `backend/api/routes/api_keys.py` (Phase 5.4) is a different concept: upstream LLM provider keys stored as `UserModelConfig` rows.
- Both in-repo SDKs (`sdk/python/agentium_sdk`, `sdk/typescript/src`) already send `X-API-Key` when constructed with an `api_key` (`sdk/python/agentium_sdk/client.py:324`) — wired for a feature the backend never got.

## 2. Decisions

1. **Full build** for 12.5.2 (user-selected): entity + migration, generate/list/revoke endpoints, dual-header auth, portal UI, tests.
2. **Keep the embedded tab** (user-selected): the portal stays as the SovereignDashboard `developer-portal` tab; keys are stored per-user, so a future standalone route is a pure frontend addition.
3. **Dual-header auth in the shared auth dependency** (user-selected, Approach A): resolve Bearer JWT or X-API-Key inside `get_current_user`; every existing route accepts keys automatically; RBAC, rate limits, and audit apply unchanged because a key resolves to a user identity.

---

## 3. Design

### 3.1 Backend — `DeveloperApiKey` entity + migration

New entity `backend/models/entities/developer_api_key.py`, extending `BaseEntity` (which supplies `id`, `agentium_id`, `created_at`, `updated_at`):

| column | type | notes |
|---|---|---|
| `name` | String | human-readable label |
| `key_hash` | String, unique index | SHA-256 hex of the full key |
| `key_prefix` | String | display form, e.g. `sk-ag_ab12cd34…` |
| `user_id` | FK → users.id, indexed | owner |
| `last_used_at` | DateTime, nullable | bumped on each key-authenticated request |
| `revoked_at` | DateTime, nullable | soft revoke; row never deleted |
| `expires_at` | DateTime, nullable | optional expiry |

Registered in `entities/__init__.py`. Alembic migration `025_developer_api_keys.py` (current head `024`; verify the actual head with `alembic heads` at implementation time). A migration is mandatory, not optional: the integration suite builds its schema via Alembic, not `create_all` (lesson from §10.4, migration `024`).

### 3.2 Backend — key service + `/api/v1/developer` routes

- Key format: `sk-ag_` + `secrets.token_urlsafe(32)`. Only the SHA-256 hash is stored; the plaintext is returned exactly once, in the generate response.
- New router `backend/api/routes/developer.py`, prefix `/api/v1/developer` (mirrors the `sovereign.py` pattern), registered in `main.py` (route modules 44 → 45):
  - `POST /keys` — body `{name, expires_at?}` → `{id, name, key, key_prefix, created_at}`; writes an AuditLog entry.
  - `GET /keys` — the current user's keys: `{id, name, key_prefix, created_at, last_used_at, revoked_at, expires_at, status}`.
  - `DELETE /keys/{id}` — soft revoke (sets `revoked_at`); owner or admin only; AuditLog entry.

### 3.3 Backend — dual-header auth

One shared lookup helper (e.g. `resolve_api_key_user(db, key)`) wired into **both** `get_current_user` implementations:

- `backend/core/auth.py` (dict-returning, used by ~30 route modules): uses `HTTPBearer(auto_error=False)`, which already tolerates a missing `Authorization` header — add a `Request` parameter and fall back to `X-API-Key` when `credentials` is absent.
- `backend/api/middleware/auth.py` (User-ORM-returning, used by `agents.py` + `users.py`): uses `OAuth2PasswordBearer`, which hard-fails 401 before the function body runs — replace its token extraction with optional-token + `Request` header inspection.

Resolution order: valid `Bearer` JWT (existing path, untouched) → else `X-API-Key` → SHA-256 → lookup active, unrevoked, unexpired key → owner user. The identity dict mirrors `_normalize_user` (`backend/core/auth.py:69-81`), with role taken from DB truth (consistent with the §12.4 `/verify` fix). `last_used_at` is updated on each key-authenticated request (accepted simplification at self-hosted scale). 401s keep `WWW-Authenticate: Bearer`; a deactivated owner's key → 403. WebSocket auth stays JWT-only (out of scope); rate limiting untouched (key requests fall back to IP-based limiting in the middleware, which runs before route dependencies).

### 3.4 Frontend — "API Keys" tab in the portal

New tab (KeyRound icon) in `DeveloperPortalPage.tsx`'s existing tab bar — no SovereignDashboard changes:

- Generate form: name input + expiry select (never / 30 / 60 / 90 days) + Generate button.
- Copy-once modal: plaintext key with a "you won't see this again" warning, reusing the page's clipboard helper and Check/Copy icons.
- Key list: name, monospace prefix, created, last used, status badge (active / revoked / expired), revoke with confirm.

New `frontend/src/services/developerApi.ts` following the existing typed-service pattern in `frontend/src/services/`.

### 3.5 Docs fixes (12.5.1)

- Remove phantom `GET /api/v1/agents/:id` and `POST /api/v1/agents/create` from ENDPOINTS; add the new `/api/v1/developer/keys` endpoints.
- Keep: `/api/health`, all webhook paths/events, constitution/voting paths.
- Repair the broken TypeScript sample (restore the commented-out lines as valid code).
- The Authentication section and SDK samples become accurate once §3.3 lands (X-API-Key is real; the SDKs already send it). SDK install commands reference in-repo packages — verify the documented SDK methods (`health`, `list_agents`, `create_task`, `create_webhook_subscription`) against `sdk/python/agentium_sdk/client.py` and fix install instructions to reference the repo path.

### 3.6 Testing & verification

- **Backend API tests** (`tests/api/` pattern, cf. `test_auth_verify_sovereign.py`): valid key → 200; invalid / revoked / expired key → 401; JWT coexistence (Bearer still works, and takes precedence when both headers present); deactivated owner → 403; revoke ownership (non-owner rejected); audit entries created on generate + revoke.
- **Backend unit tests**: key format (`sk-ag_` prefix, length), hash round-trip, prefix derivation.
- **Frontend unit tests**: API Keys tab — generate flow, copy-once modal, revoke flow.
- **a11y**: extend `DeveloperPortalPage.a11y.browser.test.tsx` to audit the API Keys tab; light + dark.
- **Build**: `npm run build` green; full backend suite green.
- **Live smoke** (env-guarded, non-destructive, cf. `frontend/e2e/sovereign-live-smoke.mjs`): generate key via API → call a GET endpoint with `X-API-Key` → 200 → revoke → 401.

---

## 4. Out of scope

- Standalone `/developer` route / portal access for all users (backend is per-user-ready; pure frontend addition later).
- API-key auth for WebSocket endpoints and `get_voice_or_session_user` routes.
- Per-key rate limits, scopes/permissions, IP allowlisting.
- Key usage analytics endpoint (can be added later from `last_used_at` / audit data).
