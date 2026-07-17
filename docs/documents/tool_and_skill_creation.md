# Tool & Skill Creation — Best Practices & How-To

> Practical guide for adding a new **agent tool** and a companion **skill** to
> Agentium. Grounded in the real code paths (`backend/tools/`,
> `backend/core/tool_registry.py`, `backend/.agentium/skills/`,
> `backend/scripts/seed_skills.py`). Use it as the reference when extending
> agent capabilities. The `vector_db` tool + skill (added 2026-07-17) is the
> canonical worked example.

---

## 1. Mental model: Tools vs Skills

| | **Tool** | **Skill** |
|---|---|---|
| What it is | Executable Python function agents can *call* | Markdown *knowledge* agents can *retrieve* |
| Lives in | `backend/tools/<name>_tool.py` | `backend/.agentium/skills/<name>/SKILL.md` |
| Wired via | `backend/core/tool_registry.py` (`register_tool`) | `backend/scripts/seed_skills.py` → ChromaDB |
| Reaches agent by | LLM function-calling schema (`to_openai_tools` / `to_anthropic_tools`) | Semantic RAG search (`SkillManager.search_skills`) |
| Capabilities Assignment | Capabilities must be assigned to Agents to use this tool see tool_registry.py | Can be used by any agent |
| Answers | "*Do* this action" | "*How/when* to do it" |

They are complementary. A well-designed capability ships **both**: a tool that
performs the action and a skill that teaches agents when/how to use it. The tool
should *point to* its skill (in the `description` and/or a `help` action) so an
agent that discovers the tool can find the deeper guidance, and the skill is
indexed into ChromaDB so an agent searching by intent discovers the tool.

---

## 2. Creating a Tool

### 2.1 Anatomy of a tool file

Create `backend/tools/<name>_tool.py`. Follow the existing pattern
(`embedding_tool.py`, `deep_think_tool.py`, `vector_db_tool.py`):

```python
from typing import Any, Dict, List, Optional

from backend.core.vector_store import get_vector_store  # or whatever you wrap


class MyThingTool:
    TOOL_NAME = "my_thing"
    # Which agent tiers may call this. See §2.4.
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]

    def __init__(self) -> None:
        self._dep = None  # lazy — do NOT do network/IO at import time

    @property
    def dep(self):
        if self._dep is None:
            self._dep = get_vector_store()
        return self._dep

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "do_x":
            return self._do_x(**kwargs)
        if action == "help":
            return self._help()
        return {"success": False, "error": f"Unknown action: {action}"}


my_thing_tool = MyThingTool()  # module-level singleton
```

### 2.2 Rules that matter

1. **Return a dict with `success`.** Every path returns
   `{"success": True, ...}` or `{"success": False, "error": "..."}`. The
   registry's `execute_tool` also catches exceptions and returns
   `{"status": "error", ...}`, but explicit `success` keys are the convention
   agents rely on.
2. **Prefer a single `execute(action=...)` entry point** with an `action`
   dispatch, rather than many top-level functions. This keeps the LLM schema
   small and consistent (`data_transform`, `embedding`, `vector_db` all do this).
3. **Lazy-init heavy dependencies.** `tool_registry.py` imports every tool
   module at process start. Do not open DB/Chroma/network connections at import
   or in `__init__` — use a lazy `@property` (see `vector_db_tool.store`). The
   `get_vector_store()` singleton is itself lazy by design.
4. **`async def execute` is fine.** The executor is async-aware
   (`tool_registry.execute_tool` / `tool_creation_service.execute_tool` run
   coroutines correctly). If your tool is async, **tests must `await` it**
   (pytest is configured `asyncio_mode = auto`, so `async def test_...` works).
5. **`db` / `agent_id` auto-injection.** If — and only if — your `execute`
   signature declares a `db` and/or `agent_id` parameter, the executor injects
   them (see `tool_creation_service.execute_tool`, ~line 326). Don't declare them
   unless you need them; keep `**kwargs` to absorb extras safely.
6. **Never hardcode ChromaDB collection strings.** Use the logical keys in
   `VectorStore.COLLECTIONS`; resolve via `get_collection(key)`.

### 2.3 Registering the tool

Edit `backend/core/tool_registry.py`:

1. Add the import near the other tool imports at the top:
   ```python
   from backend.tools.my_thing_tool import my_thing_tool
   ```
2. Add a `self.register_tool(...)` block inside `_initialize_tools`:
   ```python
   self.register_tool(
       name="my_thing",
       description=(
           "One or two sentences telling the agent WHAT this does and WHEN to "
           "use it. Point to the skill: 'Full reference is in the skill file at "
           "backend/.agentium/skills/my_thing/SKILL.md'."
       ),
       function=my_thing_tool.execute,
       parameters={
           "action": {"type": "string", "description": "do_x | help"},
           "foo":    {"type": "string", "description": "...", "optional": True},
       },
       authorized_tiers=["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
   )
   ```

**Parameter schema notes** (`_build_props` / `to_openai_tools`):
- Valid `type` values: `string`, `integer`, `number`, `boolean`, `array`,
  `object` (anything else falls back to `string`).
- Mark a param `"optional": True` to keep it out of the JSON-Schema `required`
  list. Params without `optional` are **required** — so `action` (no `optional`)
  is always required, which is what you want.
- Add `"enum": [...]` to constrain a value.

### 2.4 Tier authorization

Agentium IDs are tiered (`0xxxx` Head … `6xxxx`). `authorized_tiers` gates who
sees the tool in `list_tools` / `to_openai_tools`. Guidance:
- **All tiers** (`0`–`6`) for safe, read-mostly utilities (`web_search`,
  `deep_think`, `embedding`, `vector_db`).
- **Restrict** destructive or privileged tools: `execute_command` and `git` are
  `0xxxx,1xxxx,2xxxx` only; `conclude_vote` is Head-only (`0xxxx`).
- Enforce *destructive-scope* guards **inside** the tool too, not just via tiers.
  Example: `vector_db` is callable by all tiers but its `add` action blocks
  writes to immutable collections (`constitution`, `ethos`,
  `constitutional_skills`) via a `WRITABLE_COLLECTIONS` allow-list. Defense in
  depth: tier gate + in-tool guard.

### 2.5 Testing a tool

- **Unit tests** (`backend/tests/unit/test_<name>_tool.py`): test the tool's
  logic with the heavy dependency mocked via `monkeypatch.setattr` on the
  module-level import (e.g. patch
  `backend.tools.vector_db_tool.get_vector_store`). Use a `Fake*` class.
- **Registration test** (`backend/tests/integration/test_<name>_registration.py`):
  assert the tool is in `tool_registry.tools`, appears in `list_tools(tier)` for
  each intended tier, and is exported by `to_openai_tools` / `to_anthropic_tools`
  with the right `required` params. (Importing `tool_registry` pulls the whole
  tool graph, so this lives under `tests/integration/`.)
- Run in the container, disabling the repo coverage gate:
  ```bash
  docker compose exec -T backend bash -lc \
    "cd /app/backend && pytest tests/unit/test_my_thing_tool.py -o addopts='' -q"
  ```

---

## 3. Creating a Skill

### 3.1 Anatomy of a SKILL.md

Create `backend/.agentium/skills/<name>/SKILL.md`. It is YAML frontmatter +
markdown body. The loader is `backend/scripts/seed_skills.py::parse_skill_file`.

```markdown
---
name: my_thing
description: >-
  50–300 char summary. This is the PRIMARY semantic-search surface — write it as
  the query an agent would type. Mention the tool name and the SKILL.md path.
skill_type: integration      # enum, see §3.3
domain: ai                   # enum, see §3.3
complexity: intermediate     # beginner | intermediate | advanced
tags: [my-thing, rag]        # 1–10 tags
creator_tier: head           # head | council | lead | task
---

# My Thing

Intro paragraph.

## Steps
1. Concrete, copy-pasteable invocation examples.
2. ...

## Validation
- Observable success criteria (one per line).
```

### 3.2 How the loader maps markdown → SkillSchema

`parse_skill_file` (in `seed_skills.py`) does the following, so structure your
file accordingly:
- Splits the body on `##` headings. A section whose title contains
  `validation`/`success criteria` populates `validation_criteria`; every other
  section becomes a `steps` entry.
- If there are no `##` sections, the first ~5 paragraphs become `steps`.
- **Field ordering for the 2000-char ChromaDB clip** (`CHROMA_CHAR_LIMIT`): the
  document is assembled highest-value-first (identity → description → steps →
  validation), so put the most important guidance (tool name, SKILL.md path,
  safety guards) **early** in your first steps. Anything past 2000 chars is
  clipped (a warning is logged — see §3.5).
- The `__SKILL_DIR__` token in the body is replaced with the skill's absolute
  container path at seed time (`/app/backend/.agentium/skills/<name>`). Use it to
  reference bundled `scripts/` or `datasets/`.
- Folder skills are trusted: the loader forces
  `constitution_compliant=True`, `success_rate=1.0`,
  `verification_status="verified"`, `embedding_model="BAAI/bge-base-en-v1.5"`,
  so they clear the RAG retrieval floor (`min_success_rate=0.7`).

### 3.3 Valid enum values (from `SkillSchema`)

- `skill_type`: `code_generation, analysis, integration, automation, research,
  design, testing, deployment, debugging, optimization, documentation`
- `domain`: `frontend, backend, devops, data, ai, security, mobile, desktop,
  general, database, api`
- `complexity`: `beginner, intermediate, advanced`
- `creator_tier`: `head, council, lead, task`
- `description`: **50–300 chars** (validated). `tags`: 1–10. `display_name` (if
  set) ≥ 5 chars.

### 3.4 Seeding into ChromaDB

Skills are indexed so agents discover them via semantic search:
```bash
# Reindex + seed all folder skills (inside the backend container)
docker compose exec -T backend python backend/scripts/seed_skills.py --reindex
# or
make seed-skills
```
On boot, seeding also runs if `SEED_SKILLS_ON_BOOT=true` (see
`backend/main.py`). The upsert keys on `skill_id` (`skill_<name>`), so re-runs
update in place (idempotent).

Verify retrieval:
```bash
docker compose exec -T backend bash -lc "cd /app/backend && python -c \"from backend.services.skill_manager import skill_manager
from backend.models.database import SessionLocal
db=SessionLocal(); print([h['skill_id'] for h in skill_manager.search_skills('how do I use my thing', 'task', db)]); db.close()\""
```

### 3.5 Testing a skill

Add `backend/tests/unit/test_<name>_skill.py` that calls `parse_skill_file` on
your `SKILL.md` and asserts: correct `skill_name`, `success_rate == 1.0`,
`verification_status == "verified"`, non-empty `steps`/`validation_criteria`,
and that key guidance (tool name, SKILL.md path, safety notes) survives into
`steps`/`description`. See `tests/unit/test_seed_skills.py` and
`tests/unit/test_vector_db_skill.py`.

**Avoid the clip warning** where possible: keep the total document under
~2000 chars, or ensure the essential content is in the first steps. The
`vector_db` and `bash` skills currently exceed it slightly and get clipped —
acceptable but not ideal.

---

## 4. Connecting a Tool to its Skill (the "pointing" pattern)

Best practice — do **all** of these so discovery works from any direction:

1. **In the tool `description`** (registry): name the skill file path, e.g.
   *"Full reference is in `backend/.agentium/skills/vector_db/SKILL.md`."*
2. **Add a `help` action** to the tool that returns the skill path + a usage
   summary at runtime (see `VectorDBTool._help`). Agents can call `help` when
   unsure.
3. **Seed the skill into ChromaDB** so an agent searching by intent ("how do I
   store learnings?") finds the skill, which names the tool.
4. **In the skill body**, name the tool and its actions/params, and repeat the
   SKILL.md path so it survives even if injected as an isolated snippet.

This closes the loop: tool → skill (via description/help) and skill → tool (via
RAG), and the ChromaDB index means the knowledge is visible to every agent, not
just ones that already know the tool exists.

---

## 5. End-to-end checklist

- [ ] `backend/tools/<name>_tool.py` — `execute(action=...)`, dict returns, lazy deps, module singleton.
- [ ] In-tool guards for any destructive scope (allow-lists, confirmations).
- [ ] Registered in `tool_registry.py` (import + `register_tool` with correct `authorized_tiers` and param schema).
- [ ] Unit tests (mocked deps) + registration test (all intended tiers, schema export).
- [ ] `backend/.agentium/skills/<name>/SKILL.md` — valid frontmatter enums, 50–300 char description, `## Steps` + `## Validation`, tool name + SKILL.md path early.
- [ ] Skill test (`parse_skill_file`) passes.
- [ ] Tool description + `help` action point to the skill; skill names the tool.
- [ ] `make seed-skills` registers the skill; RAG search returns it.
- [ ] One focused commit per unit of work (`feat:` / `test:` / `docs:`).

---

## 6. Reference files

- Tool examples: `backend/tools/vector_db_tool.py`, `embedding_tool.py`, `deep_think_tool.py`
- Registry: `backend/core/tool_registry.py` (`register_tool`, `_build_props`, `to_openai_tools`)
- Executor + injection: `backend/services/tool_creation_service.py` (`execute_tool`)
- Vector store: `backend/core/vector_store.py` (`get_vector_store`, `COLLECTIONS`, `query_knowledge`)
- Skill loader: `backend/scripts/seed_skills.py` (`parse_skill_file`); manager: `backend/services/skill_manager.py`
- Skill schema: `backend/models/entities/skill.py` (`SkillSchema`, `CHROMA_CHAR_LIMIT`)
- Skill examples: `backend/.agentium/skills/bash/SKILL.md`, `backend/.agentium/skills/vector_db/SKILL.md`
- Implementation plan: `docs/superpowers/plans/2026-07-17-vector-db-tool.md`
