# ADR-021: Embedding Model Migration to BAAI/bge-base-en-v1.5

## Status

Accepted (2026-07-15)

Decision authored for the RAG/ChromaDB embedding-model migration from
`sentence-transformers/all-MiniLM-L6-v2` (384-dim) to
`BAAI/bge-base-en-v1.5` (768-dim).

## Context

Agentium's RAG pipeline (knowledge retrieval, ethos, task learnings, and the
Constitutional Guard's semantic tier) embeds text with
`all-MiniLM-L6-v2` into 384-dimensional vectors stored in four ChromaDB
collections. We are migrating to `BAAI/bge-base-en-v1.5`, a 768-dimensional
model that delivers materially stronger retrieval quality on passage search.

This is **not** a config flip. A 384-dim and a 768-dim vector live in
incompatible spaces and cannot be compared — any collection holding old vectors
must be fully re-embedded before it can serve queries. The four affected
collections and their actual ChromaDB names are:

| Logical collection     | v1 Chroma name        | v2 Chroma name          | Notes |
|------------------------|-----------------------|-------------------------|-------|
| `constitution`         | `supreme_law`         | `supreme_law_v2`        | Spec calls it `constitution_articles`; the Constitutional Guard reads from it. |
| `ethos`                | `agent_ethos`         | `agent_ethos_v2`        | Per-agent working-memory store. |
| `task_patterns`        | `execution_patterns`  | `execution_patterns_v2` | Spec calls it `task_learnings`. |
| `domain_knowledge`     | `domain_knowledge`    | `domain_knowledge_v2`   | Created ad-hoc in `federation_service.py:512`; **not** in the `VectorStore.COLLECTIONS` registry. |

`skill_manager.py` (`agent_skills` / `best_practices` / `constitutional_skills`)
is explicitly **out of scope** for this migration.

### Model-specific facts (web-verified, to be encoded in the re-embed pipeline)

- **Asymmetric instruction tuning.** bge-base-en-v1.5 expects queries to be
  prefixed with `"Represent this sentence for searching relevant passages: "`,
  while stored passages must be left unprefixed. The embedding path must branch
  on write-vs-query accordingly.
- **L2 normalization required.** bge vectors must be produced with
  `normalize_embeddings=True`, and v2 collections must be created with
  `hnsw:space="cosine"` so that `similarity = 1 - distance` holds and scores
  stay in a sane `[-1, 1]`-shaped range.
- **High baseline similarity.** bge-v1.5 baseline similarities run HIGH — even
  dissimilar pairs often score > 0.5. What matters is relative ordering, not
  absolute magnitude. Any dedup / relevance threshold must be **measured on
  labeled data** (expect true duplicates at cosine ≥ ~0.9, i.e. distance
  ≤ ~0.1). Thresholds inherited from MiniLM's L2 numbers must not be reused.
- **Offline runtime.** `HF_HUB_OFFLINE=1` is set on `backend` and
  `celery-worker`, so the model must be baked into the Docker image at build
  time. There is no runtime download path during normal operation.

### Why parallel collections, not in-place rebuild

The deployment contract requires **zero data loss on container restart** and a
**rollback path without a redeploy**. An in-place wipe-and-rebuild of a live
collection risks losing the in-flight v1 vectors if a restart occurs mid-rebuild,
and offers no cheap way back to the known-good v1 model if v2 underperforms in
production. Parallel `*_v2` collections let the old and new vectors coexist,
populated and validated side by side, with a per-collection switch that can be
flipped back instantly.

## Decision

Adopt **parallel `*_v2` collections** plus a **per-collection
`EMBEDDING_ACTIVE_VERSIONS` feature flag** that selects, for each logical
collection, whether reads/writes go to the v1 (`*`) or v2 (`*_v2`) Chroma name.

1. Bake `BAAI/bge-base-en-v1.5` into the Docker image at build time; do not
   rely on runtime HF download.
2. Create each v2 collection with `hnsw:space="cosine"` and re-embed all source
   documents with `normalize_embeddings=True`, applying the asymmetric query
   prefix only at query time.
3. Gate each collection behind its own flag in `EMBEDDING_ACTIVE_VERSIONS`
   (default to v1 until that collection's v2 is validated). Cutover proceeds in
   order of **increasing blast radius**:
   - `task_patterns` (`execution_patterns` → `execution_patterns_v2`) — first;
     read path is non-critical.
   - `domain_knowledge` (`domain_knowledge` → `domain_knowledge_v2`) — ad-hoc
     collection; validate registry registration at cutover.
   - `ethos` (`agent_ethos` → `agent_ethos_v2`) — per-agent memory.
   - `constitution` (`supreme_law` → `supreme_law_v2`) — **last**, because the
     Constitutional Guard depends on it; its semantic tier is the highest-risk
     consumer.
4. Each cutover step gets a **soak window** (monitoring retrieval quality,
   latency, and Constitutional Guard verdict distribution) before the next
   collection is flipped. Rollback for any step is a single flag flip back to v1.

## Consequences

### Positive

- **Zero data loss on restart**: v1 collections remain intact throughout; old
  vectors are never destroyed until v2 is proven.
- **Instant, redeploy-free rollback**: per-collection flag flip reverts any
  step without touching the image or other collections.
- **Stronger retrieval**: 768-dim bge-v1.5 improves passage relevance across all
  four collections.
- **Measured, staged risk**: cutover order and soak windows contain blast
  radius; the Constitutional Guard — the most sensitive consumer — is last.

### Negative / Risks

- **2× vector storage and memory**: 768 float32 dims vs 384 roughly doubles
  ChromaDB storage and in-memory HNSW footprint while both versions coexist.
- **Possible p95 latency regression**: larger embeddings and bigger index may
  raise query p95. A benchmark re-baseline is required; ONNX-quantized
  inference is the designated fallback if regression is unacceptable.
- **Constitutional Guard thresholds must be re-validated**: the current
  BLOCK / GREY cutoffs (0.70 / 0.40) were calibrated on MiniLM's L2 cosine
  distribution. Under bge's high-similarity distribution they may need to
  **rise** (e.g. duplicates and near-matches score far above 0.70). Re-validate
  against labeled constitutional-violation data before flipping `constitution`.
- **Re-measured dedup/relevance thresholds**: every similarity-based gate in the
  RAG pipeline must be re-tuned on labeled data; MiniLM thresholds do not
  transfer.
- **`domain_knowledge` registry gap**: because it is created ad-hoc in
  `federation_service.py:512` and absent from `VectorStore.COLLECTIONS`, the v2
  path must explicitly register/handle it or the flag will not cover it.

### Unchanged

- The skills pipeline (`skill_manager.py`, `agent_skills` /
  `best_practices` / `constitutional_skills`) is unaffected and out of scope.

## Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| **In-place wipe + rebuild** of each collection | Data-loss risk on container restart mid-rebuild; no zero-downtime rollback without redeploy; forces a "big bang" cutover with no soak period. |
| **Dual model serving with runtime download** | `HF_HUB_OFFLINE=1` on backend and celery-worker forbids runtime fetch; also adds model-load latency per process. |
| **Switch without re-embedding (config-only flip)** | 384-dim and 768-dim vectors are incomparable; queries against old vectors with the new model (or vice versa) return meaningless distances, silently corrupting retrieval and the Constitutional Guard. |
| **Migrate all collections in one atomic cutover** | Maximizes blast radius and removes the staged soak/rollback safety net; violates the increasing-blast-radius principle. |
