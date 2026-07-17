---
name: vector_db
description: >-
  Use the 'vector_db' agent tool to read from and write to the shared ChromaDB
  vector store that powers Agentium's collective RAG memory. Covers query/get/add
  actions, the writable-collection allow-list, metadata conventions, and how to
  surface this knowledge to other agents through ChromaDB.
skill_type: integration
domain: ai
complexity: intermediate
tags: [vector-db, chromadb, rag, memory, knowledge, embedding]
creator_tier: head
---

# Vector DB Tool for Agents

Agentium stores collective memory in ChromaDB (embedding model
`BAAI/bge-base-en-v1.5`, 768-dim, cosine). Every agent can reach it through the
`vector_db` tool (registered for all tiers). A copy of this skill lives at
`backend/.agentium/skills/vector_db/SKILL.md`; it is indexed into ChromaDB by
`make seed-skills`, so you (and other agents) can retrieve it by asking
"how do I use the vector DB tool?".

The tool is invoked as `vector_db` with an `action` parameter:

- `query` — semantic search. Params: `query` (str), optional `collection`
  (single key) or `collection_keys` (list), `n_results` (int, default 5),
  `filter_dict` (ChromaDB metadata `where`).
- `get` — fetch one document by id. Params: `doc_id` (str), `collection` (str).
- `add` — upsert documents. Params: `collection` (str), `documents`
  (list[str]), `metadatas` (list[dict], optional), `ids` (list[str], optional —
  auto-generated as `<collection>_<i>` if omitted).
- `list_collections` — list every collection key and which are agent-writable.
- `help` — print usage. The `backend/.agentium/skills/vector_db/SKILL.md` path
  is printed in the result.

## The protection guard (critical)
Writes are restricted to a vetted allow-list. These collections are IMMUTABLE
and `add` rejects them with "not writable":

- `constitution` (supreme_law) — the living constitution
- `ethos` (agent_ethos) — agent behavioural rules
- `constitutional_skills` — skills governing the constitution

Writable agent collections include: `council_memory`, `task_patterns`
(execution_patterns), `best_practices`, `domain_knowledge`, `sovereign_prefs`,
`audit_semantic`. Prefer `task_patterns` for execution learnings and
`best_practices` for reusable how-tos.

## Metadata conventions
Always tag documents so they are filterable and citeable:
- `task_patterns`: `{"type": "execution_pattern", "task_type": "<kind>", "tools_used": "<json>"}`
- `best_practices`: `{"type": "best_practice", "domain": "<area>"}`
- `council_memory`: `{"type": "council_deliberation", "topic": "<x>"}`

Higher success_rate / citation_boost and fresher `last_validated_at` make a
document rank higher (decay + citation boost applied at query time).

## Steps
1. To search: `vector_db(action="query", query="how do I sandbox untrusted code?", collection_keys=["task_patterns","best_practices"], n_results=5)`.
2. To fetch a known doc: `vector_db(action="get", collection="task_patterns", doc_id="pattern_docker_1")`.
3. To store a learning: `vector_db(action="add", collection="task_patterns", documents=["Use the Docker remote executor for untrusted code."], metadatas=[{"type":"execution_pattern","task_type":"code"}], ids=["pattern_docker_1"])`.
4. To discover collections: `vector_db(action="list_collections")`.
5. To re-read this reference: `vector_db(action="help")` — it points at `backend/.agentium/skills/vector_db/SKILL.md`.
6. Run `make seed-skills` (inside the backend container: `docker compose exec -T backend python backend/scripts/seed_skills.py --reindex`) to (re)index this skill plus any other `backend/.agentium/skills/*/SKILL.md` into ChromaDB so agents find it via RAG.

## Validation
- `vector_db(action="query", query="...")` returns `{"success": true, "matches": [...]}` with `relevance_score` in [0,1].
- `vector_db(action="add", collection="constitution", documents=["x"], ids=["y"])` returns `{"success": false, "error": "...not writable..."}`.
- `make seed-skills` prints `Registered skill: vector_db (skill_vector_db)` with no exception.
- After seeding, `SkillManager.search_skills("how do I use the vector DB tool", ...)` returns the `vector_db` skill.
