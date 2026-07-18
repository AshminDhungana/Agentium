# Skill Creator Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `skill_creator` agent tool that lets Head/Council agents author a valid `SKILL.md` at runtime, persist it to `backend/.agentium/skills/<name>/`, and index it into ChromaDB so it is retrievable via `skill_manager.search_skills`.

**Architecture:** A new `backend/tools/skill_creator_tool.py` singleton mirrors the existing `tool_creator_tool.py`. On `create`, it validates a structured payload against `SkillSchema`, writes the `SKILL.md` to disk for durability (with `## Steps` + `## Validation` sections so `parse_skill_file` accepts it on a later full re-seed), builds a `SkillSchema` directly, and calls `skill_manager.upsert_skill_from_markdown` to index into ChromaDB + Postgres. Registered in `tool_registry.py` for `0xxxx`/`1xxxx` only.

**Tech Stack:** Python 3, FastAPI/Pydantic (`SkillSchema`), SQLAlchemy/Postgres, ChromaDB via `skill_manager` + `VectorStore`, PyYAML.

## Global Constraints

- Authorized tiers are `0xxxx` and `1xxxx` ONLY; `authorized_tiers` param (if given) is clamped to that set.
- `SkillSchema` enums (verbatim): `skill_type` ∈ {code_generation, analysis, integration, automation, research, design, testing, deployment, debugging, optimization, documentation}; `domain` ∈ {frontend, backend, devops, data, ai, security, mobile, desktop, general, database, api}; `complexity` ∈ {beginner, intermediate, advanced}; `creator_tier` ∈ {head, council, lead, task}.
- `description` MUST be 50–300 chars; `display_name` ≥5 chars; `skill_name` 3–100; `tags` 1–10; `steps` ≥1; `validation_criteria` ≥1.
- Indexed skill is auto-verified: `constitution_compliant=True`, `success_rate=1.0`, `verification_status="verified"`, `chroma_collection="agent_skills"`, `embedding_model="BAAI/bge-base-en-v1.5"`, `version="1.0.0"`.
- The written `SKILL.md` MUST contain `## Steps` and `## Validation` H2 sections (required by `parse_skill_file`).
- All tool exceptions are caught and returned as `{"success": False, "error": <str>}` — never crash the agent loop.
- DB sessions use `backend.models.database.get_db_context` (yields a `Session`).

---

### Task 1: skill_creator tool module (core logic)

**Files:**
- Create: `backend/tools/skill_creator_tool.py`
- Test: `backend/tests/unit/test_skill_creator.py` (created in Task 4, but wire here)

**Interfaces:**
- Consumes: `backend.models.schemas.skill` → `SkillSchema` (definition in `backend/models/entities/skill.py`); `skill_manager` singleton from `backend.services.skill_manager`; `get_db_context` from `backend.models.database`.
- Produces: module-level singleton `skill_creator_tool` with method `execute(action: str = "help", **kwargs) -> Dict[str, Any]`. Later tasks register `skill_creator_tool.execute` in `tool_registry`.

- [ ] **Step 1: Write the tool module**

```python
"""skill_creator — let Head/Council agents author and persist new Skills (SKILL.md)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.models.database import get_db_context
from backend.models.entities.skill import SkillSchema
from backend.services.skill_manager import skill_manager

SKILLS_ROOT = Path(__file__).resolve().parents[1] / ".agentium" / "skills"
ALLOWED_TIERS = {"0", "1"}
ALLOWED_TIER_IDS = ["0xxxx", "1xxxx"]

# Enums must match SkillSchema exactly.
SKILL_TYPES = {
    "code_generation", "analysis", "integration", "automation", "research",
    "design", "testing", "deployment", "debugging", "optimization", "documentation",
}
DOMAINS = {
    "frontend", "backend", "devops", "data", "ai", "security", "mobile",
    "desktop", "general", "database", "api",
}
COMPLEXITIES = {"beginner", "intermediate", "advanced"}


def _tier_to_creator_tier(agent_id: str) -> str:
    return "head" if (agent_id or "")[:1] == "0" else "council"


def _build_skill_md(name: str, display_name: str, description: str,
                     skill_type: str, domain: str, complexity: str,
                     tags: List[str], steps: List[str],
                     validation_criteria: List[str],
                     prerequisites: List[str], examples: List[Dict[str, str]],
                     code_template: str) -> str:
    def yaml_list(items):
        return "[" + ", ".join(f'"{i}"' for i in items) + "]"

    front = [
        "---",
        f"name: {name}",
        f"description: >-",
        f"  {description}",
        f"display_name: {display_name}",
        f"skill_type: {skill_type}",
        f"domain: {domain}",
        f"complexity: {complexity}",
        f"tags: {yaml_list(tags)}",
        f"creator_tier: {_tier_to_creator_tier('')}",
        "---",
        "",
    ]
    body = ["# " + display_name, ""]
    if prerequisites:
        body.append("## Prerequisites")
        body += [f"- {p}" for p in prerequisites] + [""]
    body.append("## Steps")
    body += [f"{i+1}. {s}" for i, s in enumerate(steps)] + [""]
    if code_template:
        body.append("## Code Template")
        body.append("```")
        body.append(code_template)
        body.append("```")
        body.append("")
    if examples:
        body.append("## Examples")
        for i, ex in enumerate(examples):
            body.append(f"Example {i+1}:")
            body.append(f"Input: {ex.get('input', 'N/A')}")
            body.append(f"Output: {ex.get('output', 'N/A')}")
            body.append("")
    body.append("## Validation")
    body += [f"- {v}" for v in validation_criteria]
    return "\n".join(front + body) + "\n"


class SkillCreatorTool:
    """Agent-callable tool to author and persist new skills (Head/Council only)."""

    def execute(self, action: str = "help", **kwargs) -> Dict[str, Any]:
        if action == "help":
            return self._help()
        if action != "create":
            return {"success": False, "error": f"Unknown action: {action}"}
        agent_id = kwargs.get("agent_id") or ""
        if (agent_id or "")[:1] not in ALLOWED_TIERS:
            return {
                "success": False,
                "error": "skill_creator is restricted to Head (0xxxx) and Council (1xxxx) agents",
            }
        try:
            return self._create(agent_id=agent_id, **kwargs)
        except Exception as exc:  # never crash the agent loop
            return {"success": False, "error": str(exc)}

    def _create(self, agent_id: str, **kwargs) -> Dict[str, Any]:
        name = str(kwargs["skill_name"]).lower().replace(" ", "_").replace("-", "_")
        display_name = kwargs["display_name"]
        description = kwargs["description"]
        skill_type = kwargs["skill_type"]
        domain = kwargs["domain"]
        complexity = kwargs["complexity"]
        tags = [str(t).lower().strip() for t in (kwargs.get("tags") or [])]
        steps = [str(s) for s in (kwargs.get("steps") or [])]
        validation_criteria = [str(v) for v in (kwargs.get("validation_criteria") or [])]
        prerequisites = [str(p) for p in (kwargs.get("prerequisites") or [])]
        examples = kwargs.get("examples") or []
        code_template = kwargs.get("code_template") or None

        # Validate enums/lengths via SkillSchema construction (raises on bad input).
        now = datetime.now(timezone.utc)
        schema = SkillSchema(
            skill_id=f"skill_{name}",
            skill_name=name,
            display_name=display_name,
            skill_type=skill_type,
            domain=domain,
            tags=tags,
            complexity=complexity,
            description=description,
            prerequisites=prerequisites,
            steps=steps,
            examples=examples,
            code_template=code_template,
            validation_criteria=validation_criteria,
            version="1.0.0",
            created_at=now,
            updated_at=now,
            creator_tier=_tier_to_creator_tier(agent_id),
            creator_id=agent_id,
            success_rate=1.0,
            constitution_compliant=True,
            verification_status="verified",
            chroma_collection="agent_skills",
            embedding_model="BAAI/bge-base-en-v1.5",
        )

        # 1) Persist SKILL.md for durability + future re-seed.
        skill_dir = SKILLS_ROOT / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        md_path = skill_dir / "SKILL.md"
        md_path.write_text(
            _build_skill_md(
                name, display_name, description, skill_type, domain, complexity,
                tags, steps, validation_criteria, prerequisites, examples, code_template,
            ),
            encoding="utf-8",
        )

        # 2) Index into ChromaDB + Postgres (force-compliant trusted skill).
        with get_db_context() as db:
            skill_manager.upsert_skill_from_markdown(schema, db=db)

        return {
            "success": True,
            "skill_id": schema.skill_id,
            "skill_name": schema.skill_name,
            "indexed": True,
            "md_path": str(md_path),
        }

    def _help(self) -> Dict[str, Any]:
        return {
            "success": True,
            "help": (
                "skill_creator(action='create', skill_name, display_name, description, "
                "skill_type, domain, complexity, tags, steps, validation_criteria, "
                "prerequisites=[], examples=[], code_template=None, agent_id) — "
                "Head/Council only. Writes a SKILL.md to backend/.agentium/skills/<name>/ "
                "and indexes it into ChromaDB. Full reference in "
                "backend/.agentium/skills/skill_creator/SKILL.md."
            ),
        }


skill_creator_tool = SkillCreatorTool()
```

- [ ] **Step 2: Sanity import**

Run: `cd /app/backend && python -c "from backend.tools.skill_creator_tool import skill_creator_tool; print(skill_creator_tool.execute(action='help'))"`
Expected: prints the help dict with `"success": true`.

- [ ] **Step 3: Commit**

```bash
git add backend/tools/skill_creator_tool.py
git commit -m "feat: add skill_creator tool module (Head/Council skill authoring)"
```

---

### Task 2: Register skill_creator in tool_registry

**Files:**
- Modify: `backend/core/tool_registry.py` (add block inside `_initialize_tools`, near the `tool_creator` registration at lines 57-109)
- Test: covered by `list_tools` reachability (manual/integration; unit test in Task 4)

**Interfaces:**
- Consumes: `skill_creator_tool.execute` from `backend.tools.skill_creator_tool` (Task 1).
- Produces: tool name `"skill_creator"` registered with `authorized_tiers=["0xxxx","1xxxx"]`.

- [ ] **Step 1: Add the registration block**

Insert immediately after the `tool_creator` registration block (after line 109, before the `governance_tool` import on line 111):

```python
        from backend.tools.skill_creator_tool import skill_creator_tool
        # ══════════════════════════════════════════════════════════════════════
        # SKILL CREATOR TOOL — Head/Council agents author new Skills at runtime
        # ══════════════════════════════════════════════════════════════════════
        self.register_tool(
            name="skill_creator",
            description=(
                "Let a Head or Council agent define and persist a new Skill (SKILL.md) "
                "at runtime. Accepts skill_name, display_name, description (50-300 chars), "
                "skill_type, domain, complexity (enums), tags, steps, validation_criteria, "
                "and optional prerequisites/examples/code_template. The skill is written to "
                "backend/.agentium/skills/<name>/ and indexed into ChromaDB, retrievable via "
                "semantic search. Restricted to 0xxxx/1xxxx tiers. Full reference in "
                "backend/.agentium/skills/skill_creator/SKILL.md."
            ),
            function=skill_creator_tool.execute,
            parameters={
                "action": {
                    "type": "string",
                    "description": "create | help",
                },
                "skill_name": {
                    "type": "string",
                    "description": "Unique skill name (3-100 chars, slugified to lower/underscore)",
                },
                "display_name": {
                    "type": "string",
                    "description": "Human-readable name (>=5 chars)",
                },
                "description": {
                    "type": "string",
                    "description": "What the skill does (50-300 chars)",
                },
                "skill_type": {
                    "type": "string",
                    "description": "code_generation|analysis|integration|automation|research|design|testing|deployment|debugging|optimization|documentation",
                },
                "domain": {
                    "type": "string",
                    "description": "frontend|backend|devops|data|ai|security|mobile|desktop|general|database|api",
                },
                "complexity": {
                    "type": "string",
                    "description": "beginner|intermediate|advanced",
                },
                "tags": {
                    "type": "array",
                    "description": "List of 1-10 lowercase tags",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of how-to steps (>=1)",
                },
                "validation_criteria": {
                    "type": "array",
                    "description": "List of success/validation criteria (>=1)",
                },
                "prerequisites": {
                    "type": "array",
                    "description": "Optional list of prerequisites",
                    "optional": True,
                },
                "examples": {
                    "type": "array",
                    "description": "Optional list of {input, output} examples",
                    "optional": True,
                },
                "code_template": {
                    "type": "string",
                    "description": "Optional code template body",
                    "optional": True,
                },
                "authorized_tiers": {
                    "type": "array",
                    "description": "Ignored/clamped; skill_creator is always 0xxxx/1xxxx only",
                    "optional": True,
                },
                "agent_id": {
                    "type": "string",
                    "description": "Caller agentium id, used for tier authorization",
                    "optional": True,
                },
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
```

- [ ] **Step 2: Verify registration**

Run: `cd /app/backend && python -c "from backend.core.tool_registry import ToolRegistry; r=ToolRegistry(); print('skill_creator' in r.tools); print(r.tools['skill_creator']['authorized_tiers'])"`
Expected: `True` then `['0xxxx', '1xxxx']`.

- [ ] **Step 3: Commit**

```bash
git add backend/core/tool_registry.py
git commit -m "feat: register skill_creator tool for Head/Council tiers"
```

---

### Task 3: Author the skill_creator SKILL.md

**Files:**
- Create: `backend/.agentium/skills/skill_creator/SKILL.md`

**Interfaces:**
- Consumes: behaviour defined in Tasks 1-2 (tool name `skill_creator`, params, auto-verify).
- Produces: a repo-committed skill that `make seed-skills` indexes; must pass `parse_skill_file`.

- [ ] **Step 1: Write the SKILL.md**

```markdown
---
name: skill_creator
description: >-
  Head or Council agents use the skill_creator tool to define and persist a new
  runtime Skill (SKILL.md) that is indexed into ChromaDB for collective RAG
  retrieval. Full reference in backend/.agentium/skills/skill_creator/SKILL.md.
skill_type: automation
domain: backend
complexity: advanced
tags: [skill-creation, knowledge, governance, rag]
creator_tier: head
---

# Skill Creator

Let a Head (0xxxx) or Council (1xxxx) agent author a new callable Skill at runtime.

## Steps
1. Call skill_creator(action="create", skill_name=..., display_name=..., description=..., skill_type=..., domain=..., complexity=..., tags=[...], steps=[...], validation_criteria=[...], prerequisites=[], examples=[], code_template=None, agent_id=...).
2. description must be 50-300 characters; skill_type/domain/complexity use the fixed SkillSchema enums.
3. The tool writes backend/.agentium/skills/<name>/SKILL.md and indexes it into ChromaDB (agent_skills), so it is retrievable by semantic search immediately.
4. authorized_tiers is always 0xxxx/1xxxx — you cannot grant skill authoring to Task (3xxxx-6xxxx) or Critic (7xxxx-9xxxx) tiers.

## Validation
- skill_creator appears in list_tools for 0xxxx and 1xxxx only.
- A created skill passes parse_skill_file validation (valid frontmatter, 50-300 char description, ## Steps + ## Validation sections).
- A subsequent skill_manager.search_skills retrieves the new skill by semantic query.
```

- [ ] **Step 2: Verify it parses through the loader**

Run: `cd /app/backend && python -c "from backend.scripts.seed_skills import parse_skill_file; from pathlib import Path; s=parse_skill_file(Path('.agentium/skills/skill_creator/SKILL.md')); print(s.skill_name, len(s.description), len(s.steps), len(s.validation_criteria))"`
Expected: `skill_creator 300 4 3` (description length >=50 and <=300, steps>=1, validation>=1).

- [ ] **Step 3: Commit**

```bash
git add backend/.agentium/skills/skill_creator/SKILL.md
git commit -m "docs: add skill_creator SKILL.md reference"
```

---

### Task 4: Unit tests

**Files:**
- Create: `backend/tests/unit/test_skill_creator.py`

**Interfaces:**
- Consumes: `skill_creator_tool` (Task 1), `parse_skill_file` from `backend.scripts.seed_skills`, `skill_manager.search_skills` from `backend.services.skill_manager`, `get_db_context` from `backend.models.database`.
- Produces: passing test suite proving the acceptance criteria.

- [ ] **Step 1: Write the tests**

```python
"""Validate the skill_creator tool end-to-end: write, parse, and retrieve."""

from pathlib import Path

from backend.models.database import get_db_context
from backend.scripts.seed_skills import parse_skill_file
from backend.services.skill_manager import skill_manager
from backend.tools.skill_creator_tool import skill_creator_tool, SKILLS_ROOT

SKILL_TYPES = ["automation", "analysis", "research", "debugging", "testing",
               "deployment", "design", "code_generation", "integration",
               "optimization", "documentation"]
DOMAINS = ["backend", "frontend", "devops", "data", "ai", "security", "mobile",
           "desktop", "general", "database", "api"]


def _valid_payload(**overrides):
    p = dict(
        action="create",
        skill_name="demo_skill_xyz",
        display_name="Demo Skill XYZ",
        description="A demo skill used by the skill_creator unit test to verify end to end.",
        skill_type="automation",
        domain="devops",
        complexity="intermediate",
        tags=["demo", "test"],
        steps=["Run the thing.", "Verify the thing."],
        validation_criteria=["Thing completed without error."],
        agent_id="00001",
    )
    p.update(overrides)
    return p


def test_unauthorized_tier_rejected():
    res = skill_creator_tool.execute(**_valid_payload(agent_id="30001"))
    assert res["success"] is False
    assert "restricted" in res["error"].lower()


def test_invalid_description_rejected():
    res = skill_creator_tool.execute(**_valid_payload(description="too short"))
    assert res["success"] is False


def test_invalid_enum_rejected():
    res = skill_creator_tool.execute(**_valid_payload(skill_type="not_a_type"))
    assert res["success"] is False


def test_valid_create_writes_and_parses():
    res = skill_creator_tool.execute(**_valid_payload())
    try:
        assert res["success"] is True, res
        md = SKILLS_ROOT / "demo_skill_xyz" / "SKILL.md"
        assert md.exists(), "SKILL.md should be written"
        schema = parse_skill_file(md)
        assert schema.skill_name == "demo_skill_xyz"
        assert 50 <= len(schema.description) <= 300
        assert len(schema.steps) >= 1
        assert len(schema.validation_criteria) >= 1
        assert schema.constitution_compliant is True
        assert schema.success_rate == 1.0
    finally:
        # Clean up the on-disk skill dir written during the test.
        import shutil
        d = SKILLS_ROOT / "demo_skill_xyz"
        if d.exists():
            shutil.rmtree(d)


def test_created_skill_is_retrievable():
    res = skill_creator_tool.execute(**_valid_payload())
    try:
        assert res["success"] is True, res
        with get_db_context() as db:
            hits = skill_manager.search_skills(
                query="demo skill verify end to end",
                agent_tier="head",
                db=db,
                n_results=5,
            )
        ids = [h["skill_id"] for h in hits]
        assert "skill_demo_skill_xyz" in ids, ids
    finally:
        import shutil
        d = SKILLS_ROOT / "demo_skill_xyz"
        if d.exists():
            shutil.rmtree(d)
```

- [ ] **Step 2: Run the tests**

Run: `cd /app/backend && pytest tests/unit/test_skill_creator.py -o addopts='' -q`
Expected: all 5 tests PASS. (If ChromaDB is unavailable in the test env, run inside the backend container: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_skill_creator.py -o addopts='' -q"`.)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_skill_creator.py
git commit -m "test: add skill_creator unit tests (auth, validation, write, parse, retrieve)"
```

---

## Self-Review Checklist

**1. Spec coverage**
- Head/Council-only authorization → Task 1 (`ALLOWED_TIERS`), Task 2 (`authorized_tiers`), Task 4 (`test_unauthorized_tier_rejected`). ✓
- Structured-field input → Task 1 `_create` params. ✓
- Write SKILL.md with `## Steps` + `## Validation` → Task 1 `_build_skill_md`, Task 3. ✓
- Build `SkillSchema` + `upsert_skill_from_markdown` → Task 1. ✓
- Auto-verify (compliant, success_rate 1.0, verified) → Task 1 schema fields. ✓
- `parse_skill_file` passes → Task 3 verify + Task 4 `test_valid_create_writes_and_parses`. ✓
- `search_skills` retrieves → Task 4 `test_created_skill_is_retrievable`. ✓
- Unit test shipped → Task 4. ✓

**2. Placeholder scan** — No TBD/TODO/"handle edge cases" present. All code steps show full code. ✓

**3. Type consistency** — `skill_creator_tool.execute(action, **kwargs) -> Dict[str,Any]` used consistently across Tasks 1-4. `SkillSchema` field names match `backend/models/entities/skill.py` (skill_id, skill_name, display_name, skill_type, domain, tags, complexity, description, prerequisites, steps, examples, code_template, validation_criteria, version, created_at, updated_at, creator_tier, creator_id, success_rate, constitution_compliant, verification_status, chroma_collection, embedding_model). `upsert_skill_from_markdown(schema, db=db)` signature matches `skill_manager.py:345`. ✓
