# Agent → ChromaDB Knowledge Write Schema (6.6)

All agent writes to ChromaDB MUST go through `write_knowledge()` in
`backend/services/knowledge_assist.py`. The `parent_id` is the dedup key:
re-writing the same `parent_id` updates the existing `KnowledgeDocument` row
and replaces its chunk vectors in place.

## Metadata fields

| Field           | Type   | Required | Meaning                                         |
| --------------- | ------ | -------- | ---------------------------------------------- |
| `parent_id`     | str    | auto     | Dedup key (set by `write_knowledge`).          |
| `type`          | str    | yes      | `web_result` \| `agent_learning` \| `seed` …   |
| `source`        | str    | yes      | `web` \| `agent` \| `seed`                      |
| `source_url`    | str?   | no       | Origin URL for web results.                    |
| `title`         | str?   | no       | Human-readable title.                          |
| `created_at`    | str    | auto     | ISO timestamp, preserved across revisions.     |
| `updated_at`    | str    | auto     | ISO timestamp of last write.                   |
| `revision`      | int    | auto     | Incremented on every upsert.                   |
| `revision_id`   | str    | auto     | UUID per write (auditability).                 |
| `agent_id`      | str?   | no       | Agent that authored the write.                 |
| `document_type` | str    | auto     | Mirrors `type` for filtering.                  |
| `decay_score`   | float  | auto     | Default 1.0 (consumed by `query_knowledge`).   |
| `citation_boost`| float  | auto     | Default 1.0.                                   |

## Collections

Web-search write-backs use `web_knowledge`. Agent learnings use
`task_patterns` / `best_practices` / `domain_knowledge` as appropriate.
