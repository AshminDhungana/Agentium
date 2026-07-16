#!/usr/bin/env python
"""Generic loader: register every backend/.agentium/skills/<name>/SKILL.md into the skill library.

Run via `make seed-skills` (inside the backend container) or directly:
    PYTHONPATH=. python backend/scripts/seed_skills.py [--reindex]
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running as a script with repo-root-relative imports.
ROOT = Path(__file__).resolve().parents[1]  # backend/ directory
sys.path.insert(0, str(ROOT))

import yaml  # PyYAML ships with the backend image

from backend.models.entities.skill import SkillSchema
from backend.services.skill_manager import skill_manager


def _default(field: str, value: Any, fallback: Any) -> Any:
    return value if value not in (None, "", [], {}) else fallback


def parse_skill_file(path: Path) -> SkillSchema:
    """Parse a SKILL.md (YAML frontmatter + markdown body) into a SkillSchema."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"{path}: missing YAML frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    skill_dir = path.parent.resolve().as_posix()
    # Replace the __SKILL_DIR__ token with this skill's absolute container path so
    # the embedded (and thus injected) skill text tells the agent exactly where any
    # bundled scripts/ and datasets/ live. When seeded via `make seed-skills` the
    # path resolves to /app/backend/.agentium/skills/<name>.
    body = m.group(2).replace("__SKILL_DIR__", skill_dir)

    # Derive steps/validation from H2 sections so the 2000-char clip keeps the
    # highest-value fields first.
    sections = re.split(r"\n##\s+", body)
    intro = sections[0].strip()
    steps: List[str] = []
    validation: List[str] = []
    for sec in sections[1:]:
        lines = sec.strip().splitlines()
        title = lines[0].strip().lower()
        content = "\n".join(lines[1:]).strip()
        if "validation" in title or "success criteria" in title:
            validation += [ln.strip("- ").strip() for ln in content.splitlines() if ln.strip()]
        else:
            steps.append(content)
    if not steps:
        steps = [p.strip() for p in intro.split("\n\n") if p.strip()][:5] or ["Follow the documented procedure."]
    if not validation:
        validation = ["Skill applied without error and produced the expected result."]

    name = str(fm.get("name", path.parent.name)).lower().replace(" ", "_").replace("-", "_")
    description = str(fm.get("description", intro[:300])).strip().replace("__SKILL_DIR__", skill_dir)
    if len(description) < 50:
        description = (description + " " + " ".join(steps[0].split())[:300])[:300]
    if len(description) > 300:
        description = description[:300]

    raw_display = str(fm.get("display_name", fm.get("name", name)))
    # display_name must be >= 5 chars to satisfy SkillSchema.
    display_name = raw_display if len(raw_display) >= 5 else f"{raw_display.title()} Skill"

    return SkillSchema(
        skill_id=f"skill_{name}",
        skill_name=name,
        display_name=display_name,
        skill_type=_default("skill_type", fm.get("skill_type"), "automation"),
        domain=_default("domain", fm.get("domain"), "devops"),
        tags=fm.get("tags") or ["bash"],
        complexity=_default("complexity", fm.get("complexity"), "intermediate"),
        description=description,
        prerequisites=fm.get("prerequisites") or [],
        steps=steps,
        validation_criteria=validation,
        creator_tier=_default("creator_tier", fm.get("creator_tier"), "head"),
        creator_id="00001",
        constitution_compliant=True,
        verification_status="verified",
        success_rate=1.0,  # trusted, repo-committed skill: clears the RAG retrieval floor (min_success_rate=0.7)
        embedding_model="BAAI/bge-base-en-v1.5",
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


def find_skill_dirs(root: Path) -> List[Path]:
    return sorted([p for p in root.glob("*/SKILL.md") if p.parent.name])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reindex", action="store_true", help="rebuild ChromaDB skill collections at bge 768-dim first")
    ap.add_argument("--skills-dir", default=os.getenv("AGENT_SKILLS_DIR", str(ROOT / ".agentium" / "skills")))
    args = ap.parse_args()

    if args.reindex:
        skill_manager.reindex_skill_collections()

    from backend.models.database import SessionLocal

    count = 0
    db = SessionLocal()
    try:
        for md in find_skill_dirs(Path(args.skills_dir)):
            schema = parse_skill_file(md)
            # Idempotent: upsert keys on skill_id; re-runs update in place.
            skill_manager.upsert_skill_from_markdown(schema, db=db)
            print(f"Registered skill: {schema.skill_name} ({schema.skill_id})")
            count += 1
        db.commit()
    finally:
        db.close()
    print(f"Done. {count} skill(s) registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
