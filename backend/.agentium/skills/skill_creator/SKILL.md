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
