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
