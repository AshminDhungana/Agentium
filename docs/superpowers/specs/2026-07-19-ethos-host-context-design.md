# Design: Environment/Host Context in every Agent's Ethos + ChromaDB (6.1)

**Date:** 2026-07-19
**Status:** Approved design (pending user review of written spec)
**Priority:** P1

## Problem

Agents lack basic situational grounding about the runtime they execute in. They
do not reliably know that they run **inside a Docker container**, where the
**host** filesystem is relative to that container, what "the internet" means
from inside the container, what part of the host filesystem they are allowed to
touch, and how to reach the host.

**Failure mode (from the task):** a user says "create a folder on my desktop"
and the agent writes into the *container's* filesystem instead of the host's
real Desktop, because it has no model of `/host_home` vs. its own root.

This is a known, documented class of failure. Industry write-ups (Docker AI
sandbox guidance; tianpan.co "Agent Sandboxing and Secure Code Execution")
call out the *gap between the sandbox's filesystem boundary and the user's
home* as a prime source of both agent confusion and prompt-injection-driven
miswrites. LangChain and OpenAI sandbox docs stress that agent workflows "get
brittle when the model needs a workspace but only receives prompt context" —
i.e. environment grounding must live in **persistent** memory and be
**retrievable via RAG**, not only in a transient system prompt.

## Goal

Give every agent, at creation, environment/host grounding in **two** channels so
it survives both the working-memory read and RAG retrieval:

1. **Default Ethos** — a persistent `environment_context` field on the agent's
   working memory, populated at agent creation.
2. **ChromaDB** — a constitution-adjacent, **read-only** collection
   (`agent_environment`) seeded at knowledge-base init, retrieved alongside the
   constitution during hierarchical RAG grounding.

**Acceptance criteria (verbatim from task):**
A new agent, without any task-specific context, correctly answers:
- "where does 'my desktop' refer to" → `/host_home/Desktop`
- "can you reach the internet" → yes, normal outbound egress from the container;
  host mounts are the way to touch the real machine.

## Approach

### Channel 1 — Default Ethos (working memory)

- Add a new `environment_context` **Text, nullable** column to the `ethos`
  table. (Alembic migration `018_add_ethos_environment_context.py`.)
- `Agent._create_default_ethos()` (`backend/models/entities/agents.py:1150`)
  populates it from a single shared grounding string constant so every agent
  type gets identical baseline context.
- The field is **core identity**, not transient working state, so it must be
  preserved by `Ethos.compress()` and `Ethos.clear_working_state()` and
  surfaced by:
  - `Ethos.to_dict()` (API serialization),
  - `Ethos.build_compression_payload()` (LLM compression prompt),
  - the `ethos` tool `read` action (`backend/tools/ethos_tool.py:96`),
  - `Ethos.get_outcome_snapshot()`-style display is unaffected (outcome stays
    separate).

### Channel 2 — ChromaDB (constitution-adjacent, read-only)

- New collection key `agent_environment` added to `VectorStore.COLLECTIONS`
  (sibling of `constitution`). It carries `immutable: True` metadata so it is
  never subject to decay/pruning like learned-behavior collections.
- New method `VectorStore.add_environment_context(doc_id, content, metadata, db)`
  mirroring `add_constitution_article` (chunk-aware: full text in Postgres
  `knowledge_documents`, chunk vectors in ChromaDB).
- `KnowledgeService.initialize_knowledge_base()`
  (`backend/services/knowledge_service.py:657`) seeds the block once (idempotent
  upsert) when no active constitution article of that id exists.
- `VectorStore.query_hierarchical_context()`
  (`backend/core/vector_store.py:505`) includes `agent_environment` for **all**
  tiers (currently every tier already receives `constitution`; we add the
  environment block to that same returned context dict) so grounding is present
  during RAG regardless of agent role.

## The grounding text (single source of truth)

Defined once (e.g. `backend/core/environment_context.py` or a module-level
constant in `vector_store`/Ethos) and reused by both channels:

```
You execute inside a sandboxed Docker container. The container is NOT the user's
machine — it is an isolated execution environment with its own filesystem and
process space. The real (host) machine is reachable through explicit bind mounts:

- /host_home  → the host user's home directory (Desktop, Documents, Downloads,
                etc.). Example: the Sovereign's Desktop is /host_home/Desktop.
- /host       → the entire host filesystem root (e.g. /host/Users/... on macOS,
                /host/c/Users/... on Windows).

When the Sovereign says "my desktop", "my Documents", or "save to my machine",
write to /host_home/... (NOT the container's own filesystem). These mounts are
read-write; treat them as the user's real files. Prefer writing generated
artifacts directly to the host mount over copying them out of the container.

Your per-agent workspace for generated files is
/host_home/agentium-workspace/<your_agent_id>/ so the user can open them on
their machine. Use the get_workspace tool to discover your exact path.

Network: the container has normal outbound internet egress, so you CAN reach
external APIs, websites, and services. (Inbound/loopback and host-internal
services are governed separately.) The host machine is reachable from the
container via host.docker.internal when needed.
```

This text is derived from the existing `HOST_ACCESS_HINT` /
`WORKSPACE_HINT` (`backend/services/prompt_template_manager.py:582`) but
consolidated and extended with the explicit **internet-egress** statement the
acceptance criteria require.

## Affected files

| File | Change |
|------|--------|
| `backend/models/entities/constitution.py` | `environment_context` column; serialization in `to_dict()`; preserve in `compress()` / `clear_working_state()`; include in `build_compression_payload()` |
| `backend/models/entities/agents.py` | populate `environment_context` in `_create_default_ethos()` (line 1150) from the shared constant |
| `backend/tools/ethos_tool.py` | include `environment_context` in the `read` action payload (~line 96) |
| `backend/core/vector_store.py` | new `agent_environment` collection key; `add_environment_context()`; include in `query_hierarchical_context()` |
| `backend/services/knowledge_service.py` | seed `agent_environment` block in `initialize_knowledge_base()` |
| `backend/alembic/versions/018_add_ethos_environment_context.py` | add column migration |
| `backend/core/environment_context.py` (new) | single source-of-truth grounding string constant |
| Tests | unit + integration coverage (see below) |

## Testing

- **Unit:** `Ethos` created via `_create_default_ethos` carries non-empty
  `environment_context`; `to_dict()` and `build_compression_payload()` include
  it; `compress()` / `clear_working_state()` do **not** drop it; `ethos` tool
  `read` returns it.
- **Unit:** `VectorStore.add_environment_context` writes to the
  `agent_environment` collection (immutable metadata) and
  `query_hierarchical_context` returns it for every tier.
- **Integration:** `initialize_knowledge_base` seeds the block; a fresh agent
  with no task context, given the Ethos `read` payload + RAG context, can answer
  the two acceptance questions (assert both answers appear in retrieved context).
- **Migration:** new Alembic revision applies cleanly against the current head
  and adds the `environment_context` column to `ethos`.

## Out of scope (YAGNI)

- Per-agent customization of the grounding text (all agents share the baseline).
- Runtime re-seeding on config change / dynamic network-policy awareness.
- Extending the text with OS-specific details beyond the existing `/host` vs
  `/host_home` contract already used by `host_path.py` / `desktop_tool.py`.
