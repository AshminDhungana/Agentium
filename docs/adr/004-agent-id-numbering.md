# ADR-004: Hierarchical Agent Identity Numbering (0xxxx / 1xxxx / 2xxxx / 3xxxx)

## Status

Accepted (2026-07-04)

## Context

Agentium is a multi-agent system with a strict hierarchy of authority. A Task Agent cannot spawn other agents. A Lead Agent cannot modify a higher-tier agent's ethos. A Council Member cannot override the Head of Council. These permission boundaries must be enforced at every level of the system.

If agents were identified by arbitrary UUIDs (e.g., `uuid4()`), every permission check would require:

1. A database join from `agents.id` to `agents.agent_type`
2. A conditional check against four or more tier types
3. Complex multi-table logic for hierarchy traversal

This would make spawn permission checks, ethos access control, and hierarchy rendering computationally expensive and bug-prone. Furthermore, agents spawn other agents while operating, so a lightweight, non-database hierarchy derivation is highly desirable.

## Decision

Adopt a **single-prefix digit numbering scheme** where the first digit of the `agentium_id` always encodes the agent's tier. The ID is numeric, 5 digits long, and hierarchically ordered.

### The Numbering Scheme

| Prefix | Tier | Description | ID Range |
|--------|------|-------------|----------|
| `0` | Head of Council | Executive authority, veto power, emergency override | `00001`–`09999` |
| `1` | Council Member | Legislative body, democratic vote, constitutional oversight | `10001`–`19999` |
| `2` | Lead Agent | Department coordinators, spawn Task Agents, manage teams | `20001`–`29999` |
| `3-6` | Task Agent | Execution workers, complete assigned tasks | `30001`–`69999` |
| `7` | Code Critic | Independent judiciary — syntax, security, logic validation | `70001`–`79999` |
| `8` | Output Critic | Independent judiciary — user intent alignment, output quality | `80001`–`89999` |
| `9` | Plan Critic | Independent judiciary — DAG soundness, feasibility | `90001`–`99999` |

### Why This Scheme

- **O(1) tier determination**: `tier = agentium_id[0]` (first character). No database lookup required.
- **Efficient SQL queries**: `LIKE '3%'` or `BETWEEN '30001' AND '39999'` leverage PostgreSQL index range scans.
- **Hierarchical authority check**: To see if `agent_a` can access `agent_b`:
  ```python
  can_access = int(agent_a.agentium_id[0]) < int(agent_b.agentium_id[0])
  ```
- **Self-documenting**: An ID like `20042` immediately tells you "Lead Agent, `


## Consequences

### Positive

1. **Zero-cost hierarchy enforcement**: Permission checks at runtime cost a single character comparison. No database join for basic tier checks.
2. **Self-enforcing governance**: It is technically impossible to "accidentally" give a Task Agent a `1` prefix, because the ID generation logic is tied to the spawn permissions.
3. **Compact and human-readable**: Five digits are easy to fit in JSON, URLs, logs, UI fields, and chat messages.
4. **Efficient database indexing**: `LIKE 'prefix%'` uses a b-tree index efficiently for range queries.
5. **Deterministic spawn order**: Agents are assigned the lowest available numeric ID, with multiple prefixes for Task Agents (3-6) to handle expansion.

### Negative

1. **Fixed prefix count**: Ten prefixes limit the system to 10 conceptually distinct tiers. While currently unexhausted, this is a hard ceiling.
2. **Renumbering is impossible**: Once an agent has a `0xxxx` ID, it can never be reassigned to a `2xxxx` (even across reincarnation), so a promoted agent gets a newly spawned Head ID representation. Migration would be a major data migration requiring, effectively, all other agents to be re-assigned and references to their old IDs updated in logs, votes, tasks, and cross-history.
3. **Tight coupling of tier-as-digit and tier-as-role**: The digit is the tier. If the system's governance model changes (e.g., introducing a new tier between Lead and Task), the entire ID scheme requires a renumbering migration.
4. **Concurrent creation race**: Two simultaneous spawn requests for the same tier could both attempt to increment the same `max(id)`. Mitigated by the existing database's write serialization, but this is an O(n) operation on every spawn (`SELECT max(...) FOR UPDATE`).
5. **Task Agent expansion required range growth**: Task agents needed 4 prefixes (3-6) because the original single-prefix (3xxxx) would have been exhausted at 9,999 agents. This is documented in the `AgentType` enum and handled in `_generate_agentium_id`.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Purely hierarchical names (e.g., `head.00001 → council.00042 → lead.00006 → task.00091`) | More human-readable, but harder to parse on the database level and impossible to fit in indexed integer-like columns. Regex is more expensive than char indexing on every query. |
| UUID per agent with a `tier` column | Extremely flexible but requires a `JOIN` or separate `tier` column lookup every single time a permission check is needed. Adds complexity to every permission check, ethos view, and spawn operation. |
| Flat counter (e.g., `00001`, `00002`) with `tier` as metadata | Loses tier at a glance, complicates audit log reviews, and requires querying a `tier` field to understand an agent's authority level. |
