# Bash Skill for Agentium Agents — Design Spec

**Date:** 2026-07-16
**Status:** Proposed (awaiting review)
**Scope:** A professional, reusable bash skill that the Head of Council (`00001`) and
other Agentium agents can use to operate the Agentium codebase safely via the shell,
plus a generic loader that makes any skill placed in `.agents/skills/` discoverable
and usable by the in-product agent fleet.

## Problem

1. Agentium runs entirely in Docker. Agents execute shell commands through
   `backend/tools/shell_tool.py::ShellTool.execute(command: List[str])`, which calls
   `subprocess.run` **without a shell**. This means pipes, redirects, `&&`, `$()`,
   and globbing do **not** work unless the command is wrapped in `bash -lc "..."`.
   This is the single most common failure mode for agents attempting bash tasks, and
   it is currently undocumented.
2. There is no curated, version-controlled reference for the project's real command
   surface (pytest, alembic, ruff/black/mypy, `docker compose`, `make`, Postgres/
   Redis/Chroma inspection, host-path resolution via `tools/host_path.py`).
3. Agentium already has a **skill library** (`skills` table in PostgreSQL +
   `agent_skills` collection in ChromaDB, schema in
   `backend/models/entities/skill.py`). At task time `skill_manager.search_skills(
   query, agent_tier=...)` retrieves relevant skills and `SkillRAG` injects them into
   the agent prompt (3000-char budget). But skills only become usable after they are
   **registered into that library** — there is currently no path from a markdown
   skill file to the library. A markdown file in a folder is invisible to agents.

## Approach (selected)

Author the bash skill as markdown under `.agents/skills/bash/` (matching the existing
repo skill convention used by `systematic-debugging`, `test-driven-development`,
`brainstorming`, etc.), and build a **generic markdown→skill-library loader** so any
`SKILL.md` dropped into `.agents/skills/<name>/` is automatically registered,
verified, and retrievable by agents. The folder becomes a trusted, version-controlled
skill source; the loader is not bash-specific.

## Part 1 — The bash skill content

Location: `.agents/skills/bash/`

### `SKILL.md` (entry point)
Frontmatter + body. Frontmatter follows the folder convention:
```yaml
---
name: bash
description: >-
  Run shell/terminal commands in the Agentium Docker stack safely — pytest,
  alembic, ruff/black/mypy, docker compose, make, and Postgres/Redis/Chroma
  inspection. Covers the shell_tool list-vs-shell rule and safe-bash discipline.
skill_type: automation
domain: devops
complexity: intermediate
tags: [bash, shell, docker, terminal, devops, testing, migrations]
creator_tier: head
---
```
Body sections (scaled to complexity, keep the embedded ChromaDB doc ≤ 1800 chars of
high-value content):
- **Operating context** — Agentium is fully Dockerized. Two shells:
  - *Host shell*: lifecycle via `make` + `docker compose` (`make up|down|restart`,
    `make test-integration`, `make audit`, `make benchmark`, `make docker-scout`).
  - *Container shell*: the Python 3.11 toolchain (pytest 8.4, alembic 1.14,
    ruff/black/mypy/interrogate/detect-secrets/vulture), reached via
    `docker compose exec -T backend bash -lc '...'`.
- **The ShellTool rule (critical)** — `ShellTool.execute` takes a **list of args, no
  shell**. To use pipes, redirects, `&&`, `||`, `$()`, or globs, wrap the whole
  command in `bash -lc "..."`. Always quote the inner string. Example:
  `bash -lc "docker compose exec -T backend pytest tests/foo.py -q 2>&1 | tail -40"`.
- **Host path discipline** — follow `tools/host_path.py`: `~` → `/host_home`,
  other absolute paths → `/host`, `/tmp` and relative → container-local. Never write
  Sovereign/user files into the container filesystem.
- **Safe-bash discipline (summary)** — see `safety.md`; the one-line version:
  `set -euo pipefail`, quote `"${var}"`, `[[ ]]` not `[ ]`, no `eval`, check return
  codes, idempotent, explicit `./` for globs, preview destructive ops.
- **Error handling & red flags** — unhealthy services, migration conflicts,
  port clashes, offline model download, secret-scan failures; agent foot-guns
  (guessing commands, unquoted vars, ignoring non-zero exits, unvetted `rm -rf`).

### `safety.md` (companion reference)
Full safe-bash discipline, grounded in Google Shell Style Guide + the "unofficial
bash strict mode" (`set -euo pipefail`):
- `set -euo pipefail` at the top of every script; `#!/usr/bin/env bash`.
- Always quote variable/command-substitution expansions: `"${var}"`, `"$(cmd)"`.
- Prefer `[[ ]]` over `[ ]`, `(( ))` for arithmetic, `==` for string equality.
- Use arrays for argument lists (`flags=(--foo --bar); cmd "${flags[@]}"`); never
  build command strings.
- No `eval`. No SUID/SGID. Prefer builtins over external commands.
- Check return values (`if ! cmd; then ...; fi` or `$?` / `PIPESTATUS`).
- Destructive ops: never `rm -rf` with an unguarded variable; use `./` prefix for
  globs (`rm -f ./*` not `rm -f *`); preview (`ls`/`echo`) before deleting.
- Idempotency: commands should be safe to re-run (e.g. `CREATE DATABASE IF NOT
  EXISTS`, `mkdir -p`).
- Read-before-write for configs under `/host` and `/host_home`.
- Note `ShellTool`'s built-in blocks: `rm -rf /`, `mkfs`, `dd if=/dev/zero`,
  `shutdown`, `reboot`. These still don't cover partial wipes — stay careful.

### `commands.md` (companion reference — indexed cookbook)
Concise, copy-pasteable recipes, each a one-liner or short `bash -lc` block:
- **Tests**: full backend suite; single file; disable coverage
  (`-o addopts=""`); integration suite via `docker-compose.test.yml` with the exact
  inline env vars from `.github/workflows/integration-tests.yml`.
- **Database**: `python scripts/init_db.py`; alembic `upgrade head` / `revision -m`;
  inspect schema via `docker compose exec -T postgres psql -U agentium -d agentium`.
- **Redis / Chroma**: `docker compose exec redis redis-cli ping`; Chroma HTTP
  (`http://localhost:8001/api/v1/...`).
- **Lint / format / type**: `ruff check .`, `ruff format .`, `black .`, `mypy .`,
  `interrogate services/ --fail-under=90`, `detect-secrets scan`, `vulture .`.
- **Logs / health**: `docker compose logs -f <svc>`; `curl -sf
  http://localhost:8000/api/health`.
- **Lifecycle**: `make up|down|restart`; rebuild a single service; `make
  test-integration`; `make audit`.
- **Git**: prefer the `git_tool`; raw `git` allowed inside the repo mount.

## Part 2 — The generic loader (discovery bridge)

A loader makes any `.agents/skills/<name>/SKILL.md` discoverable by agents. This is
what answers "how does the Head of Council know and use the skill?" — it registers
the markdown into the PostgreSQL + ChromaDB skill library that `SkillRAG` already
retrieves from.

### `scripts/seed_skills.py` (new)
- Scans `.agents/skills/*/SKILL.md` (repo-root-relative; resolves correctly inside
  the backend container and on the host).
- Parses YAML frontmatter. Missing fields get safe defaults:
  - `skill_type` → `automation`, `domain` → `devops`, `complexity` → `intermediate`,
    `tags` → `["bash"]`, `creator_tier` → `head`, `verification_status` → `verified`,
    `constitution_compliant` → `True`.
- Maps markdown body → `SkillSchema` (`backend/models/entities/skill.py`):
  - `description` = frontmatter `description` (validated 50–300 chars; loader
    truncates/pads or errors loudly if outside range).
  - `steps` = derived by splitting the body on `## ` headings (each heading + its
    paragraph becomes one ordered step). A `## Validation` / `## Success Criteria`
    section maps to `validation_criteria`.
  - `skill_id` = `skill_<name slug>` (matches the `skill_[a-z0-9_-]{3,64}` pattern).
  - `creator_id` = `00001` for folder-committed skills.
- Upserts into PostgreSQL (`skills` table via `SkillDB`) and ChromaDB
  (`agent_skills` collection) using the existing `skill_manager` API
  (`create_skill` / a new idempotent `upsert_skill_from_markdown`). Idempotent:
  re-running updates in place (bump `updated_at`, keep `usage_count`).
- Embedding model must follow the project standard. The skills subsystem is the
  **last remaining MiniLM holdout** and must move to `BAAI/bge-base-en-v1.5` (the
  project-wide embedding model, already baked into the image). See the
  "Embedding model migration" section below for every file that changes.
- Clip limit: `SkillSchema.CHROMA_CHAR_LIMIT` is raised from `1_800` → `2_000` to
  match `bge-base-en-v1.5`'s 512-token window (~2 000 chars), and the module-doc
  comment referencing MiniLM is rewritten to reference bge. `to_chroma_document`
  already clips and warns; loader keeps high-value fields (description, steps,
  validation) first so clipping never drops them.

### Wiring
- Add a `make seed-skills` target invoking
  `docker compose exec -T backend python scripts/seed_skills.py` (or run directly in
  a venv during local dev).
- Optionally call `seed_skills()` once in `backend/main.py::lifespan` (guarded by a
  short-circuit so it runs only when the `skills` table is empty or a
  `--reseed` flag is set), mirroring how the fallback Constitution is seeded. This
  makes folder skills auto-register on first boot.

### Governance
- Folder-committed skills auto-register as `verified` (head tier) so they are
  immediately live for all tiers via `search_skills`'s tier filter.
- Agent-created skills at runtime continue to follow the normal
  `pending → verified` Council review flow (`SkillSubmission`); the loader is only
  for the trusted, version-controlled folder.

## Embedding model migration (MiniLM → bge-base-en-v1.5)

The main RAG/vector store already uses `BAAI/bge-base-en-v1.5` (see ADR-021), but
the **skills subsystem still uses `sentence-transformers/all-MiniLM-L6-v2`** (384-dim).
Every MiniLM reference in active code must switch to bge-base. bge-base produces
768-dim vectors, so existing skill ChromaDB collections must be rebuilt.

Concrete changes:
1. **`backend/models/entities/skill.py`**
   - `SkillSchema.embedding_model` default → `"BAAI/bge-base-en-v1.5"`.
   - `SkillDB.embedding_model` column `default` → `"BAAI/bge-base-en-v1.5"`.
   - `CHROMA_CHAR_LIMIT` `1_800` → `2_000`; rewrite the module-doc comment that
     references MiniLM's 512-token window to reference bge-base's 512-token window.
2. **`backend/services/skill_manager.py`**
   - `create_skill` (line ~146): replace `SentenceTransformer(skill.embedding_model)`
     with the project embedder — load from `settings.EMBEDDING_MODEL`
     (`BAAI/bge-base-en-v1.5`) so storage always uses bge, not the per-row default.
   - `search_skills` (line ~247): replace the **hardcoded**
     `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` with
     `settings.EMBEDDING_MODEL`. This is a latent bug — the query was embedded with
     MiniLM (384-dim) while the project's other collections are bge (768-dim).
3. **`backend/tools/embedding_tool.py`** (line ~144): default
   `model or "all-MiniLM-L6-v2"` → `model or settings.EMBEDDING_MODEL`.
4. **`.github/workflows/integration-tests.yml`** (line ~133): remove the
   `SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')` pre-download from
   the model cache step (keep the bge-base pre-download).
5. **Collection rebuild (required):** the `agent_skills`, `best_practices`, and
   `constitutional_skills` ChromaDB collections currently hold 384-dim MiniLM
   vectors. After switching to bge (768-dim), they must be dropped and re-embedded.
   Add a reindex step (in `seed_skills.py` or `services/tasks/reindex_knowledge.py`):
   iterate `SkillDB` rows, rebuild each skill's `SkillSchema`, recompute the bge
   embedding, and `collection.add` into a freshly created collection. Guard against
   dimension-mismatch errors on first run after the switch.
6. **Alembic:** add a migration to change the `skills.embedding_model` column
   `server_default` from `'sentence-transformers/all-MiniLM-L6-v2'` to
   `'BAAI/bge-base-en-v1.5'` (cosmetic for new rows; the SQLAlchemy default in
   `skill.py` covers app-level creation).
7. **Comments only** (no behavior change): `docker-compose.yml`, `Dockerfile`,
   `Dockerfile.privileged`, `constitutional_guard.py`, `reindex_knowledge.py`,
   `vector_store.py` contain MiniLM mentions that are *historical notes* ("MiniLM was
   retired"). These may stay as migration history, but any line that still implies
   MiniLM is in use (vs. was retired) should be clarified. The `docs/adr/021-*`
   history must NOT be rewritten.

Note: `backend/tests/unit/test_no_legacy_embedding.py` scans for `all-MiniLM-L6-v2`
markers — removing the strings above keeps it green.

## Testing / Verification

- `seed_skills.py` registers the bash skill: assert a `skills` row exists with
  `skill_id="skill_bash"`, `verification_status="verified"`, and a ChromaDB
  `agent_skills` document exists.
- `skill_manager.search_skills("run pytest in the backend", agent_tier="head")`
  returns the bash skill in the top results.
- `SkillRAG.execute_with_skills(...)` injects the bash skill content into the
  augmented prompt for a shell-related task.
- A second throwaway `SKILL.md` (different name) placed in the folder is also picked
  up by a re-run of `seed_skills.py` → confirms the loader is generic, not
  bash-specific.
- `markdownlint`/YAML parse check on frontmatter; `py_compile` clean.

## Out of scope

- No new Python execution tool (the `ShellTool` already exists).
- No change to the `SkillSchema` *shape* or `SkillRAG` retrieval logic — only the
  `embedding_model` default and the `CHROMA_CHAR_LIMIT` constant change.
- No UI changes; the frontend skill browser is unaffected (folder skills appear
  like any other verified skill).
- Runtime agent skill *creation* (`suggest_skill_creation`) is unchanged.
