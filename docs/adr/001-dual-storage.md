# ADR-001: Dual-Storage Architecture: PostgreSQL + ChromaDB

## Status

Accepted (2026-07-04)

## Context

Agentium manages two fundamentally different classes of data: structured system state (agents, tasks, votes, audit logs, constitutions) and semantic knowledge (constitution articles, agent ethos, task learnings, execution patterns). These two data domains serve entirely different access patterns — one demands ACID compliance, JOINs, and referential integrity; the other demands cosine-similarity-based retrieval for LLM context augmentation. No single database engine handles both patterns well.

Before the decision, the system relied on PostgreSQL alone for all data. This meant constitution articles were stored as text blobs and retrieved via `LIKE` or full-text search, which could not capture the *spirit* of the law — only exact keyword matches. Task learnings were similarly stored in tables and retrieved by metadata filtering, missing semantically related but differently phrased insights. Agents needed contextual memory that keyword search could not provide.

The dual-storage approach separates concerns: PostgreSQL remains the source of truth for all structured relational data, while ChromaDB serves as the semantic layer that powers RAG (Retrieval-Augmented Generation) pipelines for agent context. This is analogous to how modern data architecture separates OLTP (transactional) and OLAP (analytical) concerns, adapted for the generative AI era.

## Decision

Adopt a dual-storage strategy where **PostgreSQL is the canonical source of truth** for all structured data, and **ChromaDB is the semantic search layer** for vector-based retrieval. The two systems are bridged by the `VectorStore` class (`backend/core/vector_store.py`) and the `KnowledgeService` class (`backend/services/knowledge_service.py`).

### PostgreSQL (port 5432)

Used for:

- **Entity Storage**: `agents`, `tasks`, `votes`, `constitutions`, `audit_log`, `ethos`, `users`, `channels`, `workflows`
- **ACID Guarantees**: Foreign key constraints (e.g., `agents.ethos_id → ethos.id`), transaction isolation, referential enforcement
- **Audit Trail**: Immutable `audit_log` records with cryptographic chain of evidence
- **Hierarchy Navigation**: Recursive parent/child relationships via `parent_id` on `agents` table
- **Access Control**: Role-based capabilities checked at the database level (`users.role`, `permissions`)

### ChromaDB (port 8001)

Used for:

- **RAG Context Building**: Retrieving semantically relevant constitution articles, ethos, and past learnings for LLM prompts
- **Semantic Search**: Finding *similar* tasks, execution patterns, and knowledge without exact keyword matches
- **Knowledge Deduplication**: Cosine similarity > 0.95 skips duplicate learnings
- **Decay Scoring**: Time-based decay of outdated knowledge entries (see ADR-005)

### Bridge — How Data Flows

The bridge is bidirectional but not transactional across both stores:

1. **PG → ChromaDB**: When a new constitution is created, `embed_constitution()` in `knowledge_service.py` stores the article text in ChromaDB's `supreme_law` collection. When an agent spawns, its ethos is embedded into the `agent_ethos` collection.
2. **ChromaDB → (via PG)**: At task execution time, `get_agent_context()` in `knowledge_service.py` queries ChromaDB for relevant documents, then composes them into a JSON context payload that the agent's LLM prompt consumes.
3. **Failover**: If ChromaDB is unavailable, the system gracefully falls back to file-based constitution reading (see `agent.py:read_and_align_constitution()`) and skips vector checks entirely.

### Storage Separation Matrix

| Data Type | PostgreSQL | ChromaDB |
|-----------|-----------|----------|
| Agents, Tasks, Votes | ✅ Source of truth | ❌ Not stored |
| Constitution text | ✅ Full text | ✅ Embedded for search |
| Agent ethos | ✅ JSON in `ethos` table | ✅ Embedded for retrieval |
| Task learnings | ✅ Metadata, IDs | ✅ Full text + embedding |
| Execution patterns | ✅ ID + metadata | ✅ Full text + embedding |
| Audit logs | ✅ Immutable records | ❌ Not stored |

## Consequences

### Positive

1. **No compromise on either data pattern**: PostgreSQL provides full ACID, SQL JOINs, and relational integrity. ChromaDB provides sub-200ms semantic search over tens of thousands of documents.
2. **Specialised tool for each job**: Mismatch between tool and task is eliminated — no shoehorning JSON into SQL, or transactions into vector indexes.
3. **Graceful degradation**: If ChromaDB is unreachable, the system continues via file-based fallbacks and skips RAG context. Core governance (voting, agent lifecycle, audits) remains fully functional.
4. **Optimised for generative AI**: LLM prompts are enriched with semantically relevant context that keyword search could never discover.
5. **Scalable independently**: PostgreSQL can be scaled for write throughput; ChromaDB can be sharded for query volume. Their scaling开启者需手动增加，反而 forced to choose a single scaling strategy.

### Negative

1. **Data synchronisation overhead**: Constitution articles and ethos must be written to both stores. A write to ChromaDB after a PostgreSQL commit is not atomic, creating a small window of inconsistency. Mitigated by idempotent upserts in `VectorStore` and the fact that ChromaDB is not the source of truth.
2. **Operational complexity**: Two databases to monitor, back up, and tune. PostgreSQL requires connection pool tuning (see Phase 16.1); ChromaDB requires persistent storage and embedding model hosting.
3. **Dual-query latency**: Every RAG operation requires two hops — first PostgreSQL for agent/task state, then ChromaDB for semantic context. The system optimises this by eagerly caching and parallelising where possible.
4. **Schema drift risk**: Changes to `Constitution` or `Ethos` models in PostgreSQL must be mirrored in embedding logic. The `embed_constitution()` and `embed_ethos()` methods are the single source of this bridge logic, centralising the risk.
5. **Network dependency**: In a distributed deployment, ChromaDB container can become a network failure point. The `vector_store.py` handles this by initialising lazily and logging warnings on unavailability.

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|-----------------|
| Single PostgreSQL (no ChromaDB) | Keyword search cannot capture semantic similarity; defeats the purpose of RAG.
| Single ChromaDB (no PostgreSQL) | ChromaDB lacks ACID, foreign key constraints, and complex query capabilities required for governance votes, agent hierarchies, and audit trails.
| pgvector (PostgreSQL extension) | At the time, pgvector was still maturing and did not support the collection-based semantic search and metadata filtering required. ChromaDB provided a standalone, purpose-built vector store with dedicated containers and simpler horizontal scaling. |
