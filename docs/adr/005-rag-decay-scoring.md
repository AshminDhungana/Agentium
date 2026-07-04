# ADR-005: RAG Knowledge Decay Scoring Algorithm

## Status

Accepted (2026-07-04)

## Context

Agentium stores learned knowledge in ChromaDB: execution patterns, best practices, task outcomes, and general domain knowledge. Over time, the world changes — APIs evolve, libraries are deprecated, user preferences shift, and once-correct procedures become stale. If the system always retrieves the most semantically similar knowledge regardless of age, it risks returning dangerously outdated instructions.

For example: a Task Agent once learned to use a now-deprecated API call (`requests` with a flag removed in a newer version). Six months later, it retrieves that learning simply because "make API call" is still semantically relevant. The result is a broken task — not because the knowledge was wrong when learned, but because the world changed and the system failed to account for time.

We needed a mechanism that gracefully degrades the relevance of old knowledge while boosting recently validated knowledge, creating a "temporal relevance" dimension on top of pure cosine distance.

## Decision

Adopt an **exponential time-based decay scoring algorithm** that adjusts the effective distance of each ChromaDB retrieval result based on two factors:

1. **Decay score** (`0.1 — 1.0`): Decreases over time; older knowledge gets lower scores and therefore higher effective distance (sinks in the ranked results).
2. **Citation boost** (`1.0 — 1.3`): Increases with citation count; more crucial knowledge gets higher scores, counteracting some decay.

### The Decay Formula

For a knowledge entry with a current `decay_score` and a `last_validated_at` timestamp:

```
new_decay = current_decay × (decay_base ^ days_since_validation)
```

Where:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `current_decay` | `1.0` | The entry's current decay score at the start of the period |
| `decay_base` | `0.95` | The exponential decay rate (per day) |
| `days_since_validation` | `(now - last_validated_at).days` | Days elapsed since last known good use |
| `min_decay_score` | `0.1` | Floor after which entries are pruned, not decayed |

### Effective Distance Adjustment at Query Time

After querying ChromaDB, the system adjusts the raw cosine distance to produce an `effective_distance`:

```python
effective_distance = raw_distance / (decay_score × citation_boost)
```

Where:

| Component | Range | Effect |
|-----------|-------|--------|
| `raw_distance` | `0.0 — 1.0` | Original ChromaDB cosine distance (lower is more similar, per the collection default) |
| `decay_score` | `0.1 — 1.0` | Stale knowledge has a lower score → higher effective distance → sinks in rankings |
| `citation_boost` | `1.0 — 1.3` | Frequently cited knowledge is boosted → lower effective distance → rises in rankings |

The result is sorted by `effective_distance` in ascending order (best first). This gives recently validated knowledge a natural priority, while ensuring frequently cited timeless facts (like "use `celery. `@task` for background work") are not buried.

### Decay Interval

- **Frequency**: Weekly, triggered by the Celery beat task `decay-learnings` (schedule: `604800` seconds).
- **Grace period**: 30 days — documents younger than the grace period are not decayed, preventing brand-new learnings from being penalised during their initial observation period.
- **Backfill**: Documents without `last_validated_at` are backfilled from `extracted_at` or `created_at` on their first encounter. Missing score defaults to `1.0`.

### Validation — Refreshing Knowledge

When a knowledge entry is retrieved during a task and the task succeeds, the system assumes the knowledge was useful and *validates* it. This resets the decay partially by moving `last_validated_at` forward. The validation rule resets `decay_score` slightly (boost by `0.1`, capped at `1.0`), so well-tested knowledge actually gets stronger rather than decaying further.

This mirrors biological memory: every time a human recalls a skill successfully, the memory strengthens — it does not decay as much on each re-encoding.

### Pruning

Entries whose `decay_score` falls below `min_decay_score` (`0.10`) after decay are removed from ChromaDB entirely. This prevents the knowledge graph from growing without bound.

## Consequences

### Positive

1. **Staleness-proof retrieval**: Outdated knowledge naturally sinks in rankings. A newer, slightly less semantically perfect result will outrank a very old, perfectly-matched one.
2. **Domain-agnostic**: The algorithm does not care *what* the knowledge is. It works for code, legal text, user preferences, and scientific facts.
3. **Memory provenance via age**: The decay score carries an implicit signal of when the knowledge was last relevant, which can be exposed in the UI as a freshness indicator.
4. **Tunable**: Operators can adjust `decay_base`, `min_decay_score`, or the grace period if they find the decay too aggressive or too conservative.
5. **Citation boost counteracts tyranny of novelty**: Valuable foundational knowledge does not evaporate simply because it is old. If it is frequently cited, it stays afloat.

### Negative

1. **Metadata overhead**: Every ChromaDB entry must carry a `decay_score` and `last_validated_at` in its metadata. This increases the size of the metadata payload per document.
2. **Weekly O(N) scan**: The decay task scans all collections. On a system with hundreds of thousands of documents, this scan can take seconds to minutes. While it does not happen synchronously, it still consumes ChromaDB resources.
3. **Magic number tuning**: `decay_base = 0.95` is an empirically chosen constant. In some domains, knowledge decays rapidly (e.g., software APIs), while in others it does not (e.g., mathematics). A single `decay_base` may be too blunt for all collections.
4. **Deletion is destructive**: Once a document's score drops below `0.10`, it is pruned. Pruned documents cannot be recovered unless a copy exists elsewhere. This is intentional (prevents infinite growth) but creates a tension with audit or explainability.
5. **Interaction with citation boost is multiplicative, not additive**: `effective_distance = distance / (decay × boost)`. A very old but heavily cited document can still rank high. This is intentional but may be surprising and should be documented in user-facing knowledge base tools.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| No decay at all | Would accumulate stale knowledge indefinitely, leading to broken recommendations and hallucination-prone LLM context. |
| Pure sliding window (only keep documents from the last N days) | A hard cutoff is brittle. You lose the *entire history* instantly, including timeless knowledge. A user preference might not have changed in 90 days; discarding it at day 89 is counter-productive. |
| Separate decay per collection (different `decay_base` per collection) | More flexible but requires per-collection configuration and increased testing surface. Chosen after Phase 16.2 when the user requested a simpler, unified approach. Could be revisited if domain-specific tuning proves necessary. |
| Decay at write time (pre-compute `effective_distance`) | Would create an ever-growing matrix of computed distances, defeating ChromaDB's advantage of on-the-fly similarity search. Also makes citation boosts impossible to update dynamically. |
