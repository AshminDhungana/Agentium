# 16.2 — Cross-Instance Communication: Design

**Date:** 2026-10-08
**TODO section:** `docs/documents/TODO.md` §16.2 (16.2.1–16.2.3)
**Predecessor:** §16.1 Federation API — verified complete (commit `0a0039b0`, 33 integration tests passing)

## Summary

TODO 16.2 has two halves with very different shapes:

- **16.2.1 (task delegation)** and **16.2.2 (knowledge sharing)** are already implemented. They follow the §16.1 playbook: write end-to-end integration tests around the existing code, fix any bugs the tests surface, mark verified.
- **16.2.3 (agent migration)** has no implementation anywhere in the repo. It is a new feature, designed below.

## Decisions (made during brainstorming)

| Decision | Choice |
|---|---|
| Migration transfer scope | **Agent definition only** — no conversation memory, no knowledge/vector-store entries |
| Move vs copy semantics | **Move** — source agent is terminated only after the peer confirms receipt |
| Delivery architecture | **Synchronous** (direct `httpx` call from the admin route; no Celery choreography) |

## Part 1 — 16.2.1 Task Delegation (verify)

**Existing code:** `FederationService.delegate_task` records a `FederatedTask` (`status="pending"`) and queues Celery delivery via `deliver_federated_task.delay(...)` with the peer's receive-webhook URL, a callback URL for results, and a derived HMAC signing key (`backend/services/federation_service.py:226`). The inbound webhooks `/webhooks/tasks/receive` and `/webhooks/tasks/result` were already covered by the §16.1 test suite (`TestTaskReceiveWebhook`, `TestTaskResultWebhook`).

**Gap:** the *outbound* half is untested.

**New tests** (`backend/tests/integration/test_federation_delegation.py` or an extension of the existing suite):

1. `delegate_task` creates a `FederatedTask` row with `status="pending"`, `target_instance_id` set, `original_task_id` preserved.
2. Celery dispatch receives the correct arguments: target URL `{peer.base_url}/api/v1/federation/webhooks/tasks/receive`, callback URL ending in `/webhooks/tasks/result`, derived signing key, payload carrying `original_task_id` (mock `.delay`).
3. Dispatch failure (Celery `.delay` raises) does **not** roll back the committed `FederatedTask` record.
4. `delegate_task` against a non-`active` peer raises the typed `BadRequestError` (`TARGET_PEER_IS_NOT_ACTIVE`).
5. `list_federated_tasks` returns records in both directions (outgoing and incoming).

## Part 2 — 16.2.2 Knowledge Sharing (verify)

**Existing code:**

- `POST /knowledge-share` webhook (Phase 13.4): ingests a document list into the local knowledge store via `knowledge_service.store_or_revise_knowledge`, tagging `source='federated'` and `shared_by=<peer name>`, with deduplication (`backend/api/routes/federation.py:486`).
- `POST /knowledge/sync/{peer_id}` (admin-only): pulls the peer's constitution into the local vector store via `FederationService.sync_constitution_from_peer` (`backend/api/routes/federation.py:381`).

**Gap:** neither endpoint has tests.

**New tests:**

1. `/knowledge-share` without valid peer auth → 401 (unauthenticated webhook).
2. `/knowledge-share` with valid auth → documents ingested with `source='federated'` metadata; duplicate content is deduplicated on re-send; response reports `items_shared`.
3. `/knowledge/sync/{peer_id}` as non-admin → 403 (`ONLY_SOVEREIGN_CAN_SYNC_KNOWLEDGE`).
4. `/knowledge/sync/{peer_id}` as admin with mocked peer HTTP → success message; peer unreachable → typed 500 (`FAILED_TO_SYNC_KNOWLEDGE_FROM`), no partial state.

Test isolation: the knowledge service / vector store will be mocked at the service boundary (as the §16.1 suite does for peer HTTP), so tests do not require a live vector DB.

## Part 3 — 16.2.3 Agent Migration (new build)

### Semantics

Admin-initiated, synchronous, definition-only, **move** semantics: the peer recreates the agent from a portable snapshot; only after the peer acknowledges success does the source instance terminate its local copy. Any failure leaves the source agent untouched.

### Portable snapshot format

Versioned JSON, `{"schema": "agentium/agent-definition/v1", ...}`:

```json
{
  "schema": "agentium/agent-definition/v1",
  "source_instance": "https://source.example.com",
  "source_agentium_id": "01234",
  "agent": {
    "name": "...",
    "description": "...",
    "agent_type": "task",
    "system_prompt_override": "... | null",
    "persistent_role": "... | null"
  },
  "preferred_model_config_name": "gpt-4o-standard | null",
  "ethos": { "...": "snapshot of the local Ethos row, or null" }
}
```

- Model preference travels as a **name**, never a local FK — the receiving instance resolves the name against its own `user_model_configs` and falls back to `null` if no match.
- The agent's **ethos** (identity text) is embedded in the snapshot because it is part of the agent's identity, not its memory. The receiving instance creates its own local `Ethos` row from it.
- Conversation memory, knowledge/vector entries, task history, and counters (`tasks_completed` etc.) do **not** transfer.

### New endpoints

**`POST /api/v1/federation/agents/{agent_id}/migrate`** (admin route, `get_current_user_from_token` + `is_admin`):

1. Validate the agent exists (404 if not) and the target peer is registered and `active` (typed 400 otherwise).
2. Build the snapshot from the local `Agent` (resolving the model-config FK to a name; serializing the ethos).
3. POST the signed payload directly to `{peer.base_url}/api/v1/federation/webhooks/agents/receive` via `httpx` (30s timeout), using the existing HMAC signing helpers so the peer's `authenticate_peer` dependency accepts it.
4. On 200 ack (`{"agentium_id": "...", "id": "..."}`): set the local agent's `terminated_at` and `termination_reason = "migrated_to:<peer_id>"`; return old and new IDs.
5. On non-200 / timeout / connection error: local agent untouched; raise `ServiceUnavailableError` (the existing typed exception in `backend/core/exceptions.py:71`).

**`POST /api/v1/federation/webhooks/agents/receive`** (peer webhook, `authenticate_peer` HMAC dependency — inherits replay-window protection):

1. Validate the snapshot schema tag (400 on mismatch).
2. Create a **base `Agent`** row: freshly generated `agentium_id`, payload `name`/`description`/`agent_type`/`system_prompt_override`/`persistent_role`, status `INITIALIZING`.
3. Resolve `preferred_model_config_name` to a local config ID if one matches; else leave null.
4. Create a local `Ethos` row from the embedded snapshot and link it, if present.
5. Return `{"agentium_id": ..., "id": ...}`.

**Known limitations (documented, accepted):**

- Subclass tables (`TaskAgent`, `CouncilMember`, `LeadAgent`, `HeadOfCouncil`) are not recreated — the agent arrives as a base `Agent` with its type string preserved.
- The receiver does not deduplicate repeated migrations (freshly signed re-POSTs). Admin-triggered one-shot flow plus HMAC replay-window rejection make this acceptable; double-invocation would require a provenance table (schema change — out of scope).

### Error handling

| Failure | Behavior |
|---|---|
| Unknown agent id | 404 typed error |
| Target peer missing / not `active` | 400 `TARGET_PEER_IS_NOT_ACTIVE` |
| Non-admin calls migrate | 403 |
| Peer unreachable / timeout / non-200 | `ServiceUnavailableError` (503); source agent untouched |
| Bad snapshot schema on receive | 400 |
| Invalid HMAC on receive | 401 (existing `authenticate_peer` behavior) |

### Testing

- Migrate: admin gating (401/403), success with mocked peer HTTP (agent terminated with `migrated_to:` reason, response carries both IDs), peer-down leaves agent fully intact, unknown agent 404, inactive peer 400.
- Receive webhook: HMAC auth rejection, successful creation (new `agentium_id` generated, model-config name resolution hit and miss, ethos row created), bad schema 400.
- Provenance: `termination_reason` recorded on the source agent.

## Non-goals

- No schema migrations — provenance lives in the existing `termination_reason` field.
- No automatic/federated migration orchestration, no scheduled migrations.
- No transfer of memory, knowledge, task history, or analytics counters.
- No changes to the frontend (§16.3 handles that separately).

## Bug-fix policy

As in §16.1: any bug surfaced by the new tests in existing delegation or knowledge-sharing code is fixed as part of this work, with its own test.

## Success criteria

- All TODO 16.2 checkboxes demonstrable: delegation works end-to-end (outbound + inbound), knowledge sharing works (share + sync), migration works (move with definition snapshot).
- Full federation test suite (existing 33 + new) passes on `main`.
- TODO.md §16.2 marked complete with verification notes.
