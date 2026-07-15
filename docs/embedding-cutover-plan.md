# Embedding Cutover Runbook — MiniLM (v1) → BGE (v2)

## 1. Summary

We are mid-migration of the RAG embedding pipeline from MiniLM (`v1`) to BGE (`v2`).
The migration uses a **parallel-collections** strategy: v2 collections already exist
(created in Task 7) and are being backfilled (Task 8) alongside the live v1 collections.

Cutover is **per-collection** and controlled by the `EMBEDDING_ACTIVE_VERSIONS` env map
(e.g. `EMBEDDING_ACTIVE_VERSIONS={"task_patterns":"v2"}`). Each RAG collection flips
independently via its own key, so the system reads v1 for every collection except those
explicitly set to `"v2"`.

- **Zero downtime**: reads switch instantly to the already-populated v2 collection; no
  rebuild happens at cutover time.
- **Zero data loss**: v1 collections remain untouched until explicit retirement (Task 18);
  flipping back simply re-points reads to v1.
- **Rollback is a flag flip**: revert a collection's value to `"v1"` (or remove the key)
  and redeploy — queries immediately read v1 again (Task 20 rehearses this).

### Collections and Chroma names

| Env key          | v1 Chroma collection | v2 Chroma collection |
|------------------|----------------------|----------------------|
| `task_patterns`  | `execution_patterns` | `execution_patterns_v2` |
| `domain_knowledge` | `domain_knowledge` | `domain_knowledge_v2` |
| `ethos`          | `agent_ethos`        | `agent_ethos_v2` |
| `constitution`   | `supreme_law`        | `supreme_law_v2` (last — Constitutional Guard depends on it) |

## 2. Order of increasing blast radius

Cut over collections in this order, giving each step a **soak window** before starting the
next. Each step is independent and can be rolled back without affecting the others.

1. **`task_patterns`** (`execution_patterns`) — lowest risk, no governance dependency.
   Pure execution-history retrieval; nothing in the governance chain reads it.
2. **`domain_knowledge`** — reference knowledge used for factual/semantic context.
3. **`ethos`** (`agent_ethos`) — agent behavioral context; affects agent reasoning style.
4. **`constitution`** (`supreme_law`) — **LAST**. The Constitutional Guard (Tier 2
   semantic check) depends on it. Do not cut this over until Task 13 has verified the
   v2 guard verdicts match v1 (no false positives/negatives in constitutionality checks).

## 3. Per-step procedure

Repeat the following for each collection in the order above.

1. **Backfill prerequisite** — confirm the v2 collection is fully populated
   (see section 4). Do not flip the flag otherwise.
2. **Set the flag** in the backend + celery-worker environment
   (`docker-compose.yml` or deployment secrets):
   ```bash
   EMBEDDING_ACTIVE_VERSIONS={"<key>":"v2"}
   ```
   Example for the first step:
   ```bash
   EMBEDDING_ACTIVE_VERSIONS={"task_patterns":"v2"}
   ```
3. **Redeploy / restart** backend + celery-worker so **both** services pick up the flag
   (the worker also performs embeddings for background jobs).
4. **Soak** for a monitoring window — recommend **≥ 24h for `constitution`** (and a
   reasonable soak for the others, e.g. ≥ 12–24h depending on traffic):
   - retrieval quality (relevance of returned chunks)
   - Constitutional Guard verdicts (especially after the `constitution` flip)
   - latency (embedding + query times)
5. **Only proceed** to the next collection once the soak is clean. If anything looks off,
   roll back (section 5) and investigate before continuing.

## 4. Backfill prerequisite (before flipping each collection)

Before flipping a collection's flag, ensure the backfill from Task 8 has completed and is
clean for that key:

```bash
python -m backend.scripts.reembed_knowledge --keys <key>
```

Verify, for the `<key>` in question:

- `v2_count == v1_count` — every v1 document has a corresponding v2 embedding.
- `metadata_mismatch == 0` — no documents dropped or altered during re-embedding.

Only flip the flag once both conditions hold.

## 5. Rollback

To revert a collection **mid-soak**:

1. Set its value back to `"v1"` (or remove the key entirely) in the backend +
   celery-worker env:
   ```bash
   EMBEDDING_ACTIVE_VERSIONS={"<key>":"v1"}
   # or, to fall back to the default: remove "<key>" from the map
   ```
2. Redeploy / restart backend + celery-worker.

Queries **immediately** read v1 again (this is rehearsed by Task 20). There is **no data
loss** either way — v2 collections remain populated and can be re-enabled later, and v1
collections are untouched until retirement (Task 18).

## 6. Post-cutover

Once **ALL** collections are on v2 and soak is complete for each:

1. Point the **weekly reindex job** at v2 (Task 14).
2. **Re-baseline latency** for the v2 pipeline (Task 15).
3. **Retire v1** collections and stop writing to them (Task 18).
