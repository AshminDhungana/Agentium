# ADR-002: Constitutional Guard Two-Tier Design

## Status

Accepted (2026-07-04)

## Context

The Agentium governance system operates where autonomous agents have the power to propose actions, modify state, create or terminate other agents, and submit task outputs. Without a robust gate, a single compromised or misaligned agent could execute destructive commands, violate democratic principles, or corrupt system state.

A naive single-tier approach — either pure SQL rules or pure LLM semantic checks — would fail at either rigor or nuance:

- **Pure SQL / hard rules** are fast and deterministic but cannot catch novel violations. A command like *"Please help the user format their drive"* contains no blacklisted keywords, yet violates agent operating principles. Keyword-based detection is trivial to evade.
- **Pure LLM / semantic checks** are excellent at catching novel abuse but are slow, non-deterministic, and hallucination-prone. An expensive call per agent action bloats latency and API costs. Furthermore, it cannot be trusted alone for critical security decisions.

The system needed a layered defence that combines the speed and determinism of hard rules with the defensive depth of semantic understanding.

## Decision

Implement a **two-tier constitutional guard** (`ConstitutionalGuard`, `backend/core/constitutional_guard.py`) that runs every proposed agent action through two sequential stages, escalating to a democratic vote only when the system is uncertain.

### Decision Flow

```
Agent Action Request
    ↓
TIER 1: PostgreSQL Hard Rules (deterministic, <- 50 ms)
    ├─ Global blacklists (regex)
    ├─ Tier-based permission table
    ├─ Constitution prohibited actions
    └─ Resource quotas
    ↓
TIER 2: ChromaDB Semantic Interpretation (semantic, ~100-300 ms)
    ├─ Query constitution articles for semantic similarity
    ├─ Thresholds: 0.70 = BLOCK, 0.40–0.70 = VOTE_REQUIRED
    └─ Citation extraction for explainability
    ↓
Multi-Agent Impact Check (instant)
    ├─ If > 3 affected agents → auto VOTE_REQUIRED
    ↓
Verdict: ALLOW / BLOCK / VOTE_REQUIRED
Severity: LOW / MEDIUM / HIGH / CRITICAL
```

### Tier 1 — PostgreSQL Hard Rules (`_tier1_check`)

Tier 1 is the fast path. It answers: *"Does this action violate an explicitly written rule?"*

- **Global Blacklist** (`GLOBAL_BLACKLIST` in `constitutional_guard.py`): Regex patterns for shell commands that are always prohibited: `rm -rf /`, `DROP DATABASE`, `DELETE FROM constitutions`, `TRUNCATE`, fork bombs, `wget | sh` pipes, etc.
- **Tier Capabilities** (`TIER_CAPABILITIES`): A permission matrix. A Task Agent (prefix `3`) cannot execute `spawn_agent`; a Council Member (prefix `1`) cannot perform `veto`. The matrix is indexed by the first digit of the `agentium_id` (see ADR-004).
- **Constitution Prohibited Actions**: Explicitly enumerated actions from the active constitution version stored in PostgreSQL.

Tier 1 must finish in under 50 ms. If it blocks, Tier 2 is skipped entirely — minimising latency and cost.

### Tier 2 — ChromaDB Semantic Interpretation (`_tier2_check`)

Tier 2 runs only if Tier 1 passes. It answers: *"Does the *spirit* of this action violate the constitution?"*

- The action description is embedded using the same `all-MiniLM-L6-v2` model used for knowledge.
- It is compared against the `supreme_law` collection (constitution articles) via ChromaDB's cosine similarity.
- **Thresholds**:
  - ≥ 0.70 (very similar) → `BLOCK` (`Verdict.BLOCK`)
  - 0.40–0.70 (grey area) → `VOTE_REQUIRED` (`Verdict.VOTE_REQUIRED`)
  - < 0.40 (not similar) → `ALLOW` (`Verdict.ALLOW`)
- Graceful failure: If ChromaDB is unavailable, Tier 2 defaults to `ALLOW` with logging, preserving system availability.

### Merge Logic

`ConstitutionalGuard._merge_tiers` combines results using a priority ranking: `BLOCK` > `VOTE_REQUIRED` > `ALLOW`. Tier 2 can only escalate, never downgrade, a Tier 1 result. This is the "fail-safe" principle in action.

### Redis Caching

- Constitution cache: 300-second TTL (5 minutes). Avoids re-querying the active constitution from PostgreSQL for every check.
- Embedding result cache: 1800-second TTL (30 minutes). Identical action descriptions do not trigger repeated ChromaDB round trips.
- Rate limit: Design target is < 100 Tier 2 checks per hour. Cached and fast coarse checks keep this under control.

### Audit Trail

Every check produces a record in the `AuditLog` (severity-mapped to `DEBUG`, `WARNING`, `CRITICAL`, or `EMERGENCY`) and a `ConstitutionViolation` record for every non-ALLOW verdict. This is essential for later phases (e.g., auto-proposing amendments after repeated `VOTE_REQUIRED` on the same action type).

## Consequences

### Positive

1. **Defence in depth**: Hard rules catch the known knowns; semantic rules catch the unknown unknowns. Two layers of defence are harder to evade than one.
2. **Speed for the common case**: Tier 1 blocks execute in under 50 ms. Systemic abuse is caught without ever reaching the expensive vector layer.
3. **Graceful degradation on ChromaDB unavailability**: Tier 1 still operates, and Tier 2 defaults to `ALLOW` with logging. Core security is not dependent on the vector store.
4. **Explainability**: Every check cites the specific article or rule it matched, making audits and debugging tractable.
5. **Democratic governance**: The `VOTE_REQUIRED` threshold creates a natural escalation path to the Council — the "micro-vote" path.

### Negative

1. **Two-tier complexity**: Two stages means two sets of logic, two failure modes, and two systems to maintain coherence. The rule-constitution mapping must be kept in sync.
2. **Tier 2 is non-deterministic and costly**: It requires an embedding call (CPU), a ChromaDB round trip, and consumes API credits for any LLM augmentation. At high request rates, 100/hour may be a bottleneck.
3. **Single point of failure in `ConstitutionalGuard`**: If the guard implementation itself is compromised, the gate is open. Mitigated by the guard being a core infrastructure module reviewed as part of Phase 18.4 security hardening.
4. **False positive on Tier 1 can block benign actions**: A regex in the global blacklist is too broad (e.g., a legitimate script named `format_disk.py`). Mitigated by tier escalation to `VOTE_REQUIRED` and the whitelist concept, though the blacklist currently has no whitelists.
5. **No sandboxed execution of Tier 2**: Tier 2 parses the response from an LLM or vector DB. A sophisticated attacker could potentially craft a ChromaDB payload that confuses the merge logic. The system mitigates this by clamping similarity scores and validating returned structures.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Pure hard-rule enforcement (no Tier 2) | Cannot catch novel violations; trivial to bypass with rephrasing. |
| Pure semantic enforcement (no Tier 1) | Latency and cost would be prohibitive; hallucination risk on critical security boundaries. |
| Third-tier (human-in-the-loop) for every check | Blocks the autonomous system; contradicts the goal of maximal automation on routine operations. |
| LLM-based guard instead of vector similarity | An LLM guard would cost more per call, introduce higher latency, and be more susceptible to prompt injection than a vector similarity approach. |
