# Scalability Strategy — 50K → 50M+ Agents

## 1. Distributed ChromaDB Sharding

### Current State
Single ChromaDB instance with four collections: `constitution_articles`, `agent_ethos`, `task_learnings`, `domain_knowledge`.

### Sharding Strategy

| Collection           | Shard Key             | Rationale                              |
|----------------------|-----------------------|----------------------------------------|
| `agent_ethos`        | `agent_id` hash       | Distributes ethos evenly across shards |
| `task_learnings`     | `created_at` range    | Time-based partitioning for decay      |
| `domain_knowledge`   | `knowledge_type` hash | Groups similar domains together        |
| `constitution_articles` | Replicated (no shard) | Small dataset, read-heavy              |

### Implementation Approach

1. **Phase A — Read replicas**: Deploy 2–3 read replicas behind a load balancer. Writes go to primary, reads fan out.
2. **Phase B — Hash-based sharding**: Use consistent hashing on the shard key to route queries to the correct shard.
3. **Phase C — Tiered storage**: Hot data (< 30 days) on SSD-backed ChromaDB; cold data (> 30 days) on cheaper S3-backed stores with on-demand rehydration.

### Config

```yaml
# docker-compose.scalability.yml (example)
services:
  chromadb-shard-0:
    image: chromadb/chroma:latest
    environment:
      CHROMA_SHARD_ID: "0"
      CHROMA_SHARD_COUNT: "4"
    volumes:
      - chromadb_shard_0:/chroma/chroma
  chromadb-shard-1:
    image: chromadb/chroma:latest
    environment:
      CHROMA_SHARD_ID: "1"
      CHROMA_SHARD_COUNT: "4"
```

---

## 2. PostgreSQL Partitioning for Agent Hierarchies

### Current State
Single `agents` table with `agentium_id` column for hierarchy (0xxxx / 1xxxx / 2xxxx / 3xxxx).

### Partitioning Strategy

**Range partitioning on `agent_type`:**

| Partition       | Agent Type     | ID Range   | Estimated Size     |
|-----------------|----------------|------------|--------------------|
| `agents_head`   | Head of Council | 0xxxx      | < 10 rows          |
| `agents_council`| Council Members | 1xxxx      | < 100 rows         |
| `agents_lead`   | Lead Agents     | 2xxxx      | < 10,000 rows      |
| `agents_task`   | Task Agents     | 3xxxx      | 50K → 50M+ rows    |

```sql
-- Partition the agents table by type
CREATE TABLE agents (
    id           VARCHAR(36) PRIMARY KEY,
    agentium_id  VARCHAR(20) NOT NULL,
    agent_type   VARCHAR(20) NOT NULL,
    ...
) PARTITION BY LIST (agent_type);

CREATE TABLE agents_head     PARTITION OF agents FOR VALUES IN ('head_of_council');
CREATE TABLE agents_council  PARTITION OF agents FOR VALUES IN ('council_member');
CREATE TABLE agents_lead     PARTITION OF agents FOR VALUES IN ('lead_agent');
CREATE TABLE agents_task     PARTITION OF agents FOR VALUES IN ('task_agent');
```

### Multi-Node Distribution (Citus / pg_partman)

For 50M+ agents, use **Citus** to distribute the `agents_task` partition across multiple PostgreSQL nodes:

1. **Coordinator node**: Handles query routing and DDL propagation.
2. **Worker nodes**: Each holds a subset of `agents_task` rows, sharded by `id` hash.
3. **Reference tables**: `agents_head`, `agents_council`, `agents_lead` replicated to all workers (small, read-heavy).

### Connection Pooling

```yaml
# PgBouncer config
[pgbouncer]
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 100
reserve_pool_size = 20
```

---

## 3. Frontend Virtual List for Large Hierarchies

### Problem
Rendering 50K+ agents in `AgentTree.tsx` causes browser freezing.

### Solution: Windowed Rendering

Use `react-window` or `@tanstack/react-virtual` to render only visible nodes:

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function AgentTreeVirtual({ agents }: { agents: Agent[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: agents.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48, // px per row
    overscan: 20,
  });

  return (
    <div ref={parentRef} style={{ height: '80vh', overflow: 'auto' }}>
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(item => (
          <AgentRow key={item.key} agent={agents[item.index]} />
        ))}
      </div>
    </div>
  );
}
```

### Pagination API

The existing `/api/v1/mobile/agents` endpoint returns a paginated agent list. The frontend should request agents in batches of 100 and append to the virtual list as the user scrolls.

---

## 4. Capacity Planning

| Scale          | Agents    | PostgreSQL     | ChromaDB      | Redis    |
|----------------|-----------|----------------|---------------|----------|
| Current        | < 1K      | 1 node, 16 GB  | 1 node, 8 GB  | 1 node   |
| Medium (10K)   | 10K       | 1 node, 64 GB  | 2 replicas    | 1 node   |
| Large (100K)   | 100K      | Citus 3-node   | 4 shards      | Sentinel |
| Enterprise (50M+) | 50M+  | Citus 10-node  | 16 shards     | Cluster  |
