"""
RAG (Retrieval-Augmented Generation) integration for skills.
Combines skill retrieval with LLM generation.

Context budget
──────────────
When multiple skills are injected into a prompt their combined size can
easily overwhelm the LLM's useful context window. _build_rag_context()
enforces a MAX_CONTEXT_CHARS budget that is distributed across retrieved
skills proportionally by relevance score, with a per-skill floor of
MIN_SKILL_CHARS so every result gets at least a meaningful snippet.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.services.skill_manager import skill_manager
from backend.services.model_provider import ModelService
from backend.models.entities.agents import Agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RAG context budget constants
# ---------------------------------------------------------------------------
# Total character budget shared across all injected skills
MAX_CONTEXT_CHARS: int = 3_000
# Floor so every retrieved skill gets at least a meaningful snippet
MIN_SKILL_CHARS: int = 200


class SkillRAG:
    """
    RAG pipeline: Retrieve skills → Augment prompt → Generate with context.
    """

    def __init__(self):
        self.skill_manager = skill_manager

    # ═══════════════════════════════════════════════════════════
    # Main execution entry point
    # ═══════════════════════════════════════════════════════════

    async def execute_with_skills(
        self,
        task_description: str,
        agent: Agent,
        db: Session,
        model_config_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute task using RAG with skills.

        Flow:
        1. Search for relevant skills
        2. Build budget-aware augmented prompt
        3. Generate response using LLM
        4. Record skill usage
        5. Return result with attribution
        """
        # Step 1: Retrieve relevant skills
        skills = self.skill_manager.search_skills(
            query=task_description,
            agent_tier=agent.agent_type.value,
            db=db,
            n_results=3,
            min_success_rate=0.7
        )

        # Step 2: Build RAG prompt with context budget enforcement
        rag_context = self._build_rag_context(skills, task_description)

        # Step 3: Generate with context
        result = await ModelService.generate_with_agent(
            agent=agent,
            user_message=rag_context["augmented_prompt"],
            config_id=model_config_id
        )

        # Step 4: Record skill usage (optimistic — critics may revise later)
        for skill in skills:
            self.skill_manager.record_skill_usage(
                skill_id=skill["skill_id"],
                success=True,
                db=db
            )

        return {
            "content": result["content"],
            "model": result["model"],
            "tokens_used": result["tokens_used"],
            "skills_used": rag_context["skills_used"],
            "rag_context": rag_context["context_text"],
            "latency_ms": result["latency_ms"]
        }

    # ═══════════════════════════════════════════════════════════
    # Context assembly (budget-aware)
    # ═══════════════════════════════════════════════════════════

    def _build_rag_context(
        self,
        skills: List[Dict],
        task_description: str
    ) -> Dict[str, Any]:
        """
        Build an augmented prompt from retrieved skills.

        Budget allocation
        ─────────────────
        The total context budget (MAX_CONTEXT_CHARS) is split across skills
        proportionally by relevance score.  Each skill is guaranteed at least
        MIN_SKILL_CHARS so lower-ranked results are still useful.
        Each skill's content_preview is trimmed to its allocated budget
        *after* the fixed header (name / type / domain / success-rate) is
        subtracted, so the header is never cut off.
        """
        if not skills:
            return {
                "augmented_prompt": task_description,
                "skills_used": [],
                "context_text": ""
            }

        # ── Proportional budget allocation ────────────────────────────────
        total_score = sum(max(s["relevance_score"], 0.0) for s in skills) or 1.0
        budgets = []
        for skill in skills:
            share = max(skill["relevance_score"], 0.0) / total_score
            allocated = max(MIN_SKILL_CHARS, int(MAX_CONTEXT_CHARS * share))
            budgets.append(allocated)

        # ── Assemble each skill block within its budget ───────────────────
        context_parts: List[str] = []
        skills_used: List[Dict] = []

        for i, (skill, budget) in enumerate(zip(skills, budgets), 1):
            meta = skill["metadata"]
            content = skill["content_preview"]

            header = (
                f"[Skill {i}] {meta.get('display_name', 'Unknown')}\n"
                f"Type: {meta.get('skill_type')} | "
                f"Domain: {meta.get('domain')} | "
                f"Success: {meta.get('success_rate', 0):.0%} | "
                f"Relevance: {skill['relevance_score']:.0%}\n"
                f"---\n"
            )

            # Reserve chars for the header; trim only the content portion
            content_budget = max(0, budget - len(header))
            if len(content) > content_budget:
                trimmed = content[:content_budget].rstrip()
                # Add ellipsis so agents know content was cut
                trimmed += " …"
            else:
                trimmed = content

            context_parts.append(header + trimmed)
            skills_used.append({
                "skill_id": skill["skill_id"],
                "name": meta.get("display_name"),
                "relevance_score": skill["relevance_score"]
            })

        context_text = "\n\n".join(context_parts)

        augmented_prompt = (
            "You are an AI agent executing a task. "
            "The following skills from your knowledge library are relevant — "
            "use them to guide your approach.\n\n"
            f"{context_text}\n\n"
            "---\n"
            f"TASK TO EXECUTE:\n{task_description}\n\n"
            "Instructions:\n"
            "1. Apply the approaches from the skills above to this specific task.\n"
            "2. If multiple skills conflict, prefer the one with the higher success rate.\n"
            "3. Adapt, do not copy — the skills are guides, not scripts.\n"
            "4. Note which skill approaches informed your solution.\n\n"
            "Begin execution:"
        )

        return {
            "augmented_prompt": augmented_prompt,
            "skills_used": skills_used,
            "context_text": context_text
        }

    # ═══════════════════════════════════════════════════════════
    # Skill creation suggestion
    # ═══════════════════════════════════════════════════════════

    async def suggest_skill_creation(
        self,
        task_description: str,
        execution_result: Dict[str, Any],
        agent: Agent,
        db: Session
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse whether a successful execution result should become a reusable skill.

        Uses the structured SKILL_CREATION_TEMPLATE from PromptTemplateManager
        so the LLM output always matches SkillSchema field expectations.

        Returns a skill draft dict if the execution is novel and reusable,
        None otherwise.
        """
        # Guard: only persist patterns from successful executions.
        # execute_with_skills() returns {content, model, tokens_used, ...} with no
        # "success" key, so checking for that key always evaluated to False and
        # skill creation never triggered. We check for non-empty content instead,
        # which is the real signal that the LLM produced a usable result.
        if not execution_result.get("content", "").strip():
            return None

        # Guard: skip if an almost-identical skill already exists
        similar = self.skill_manager.search_skills(
            query=task_description,
            agent_tier=agent.agent_type.value,
            db=db,
            n_results=1
        )
        if similar and similar[0]["relevance_score"] > 0.9:
            logger.debug(
                "suggest_skill_creation: skipping — similar skill '%s' already exists (score=%.2f)",
                similar[0].get("skill_id"),
                similar[0]["relevance_score"],
            )
            return None

        # Build task context for the template
        task_context = (
            f"Task description: {task_description}\n\n"
            f"Execution steps taken:\n{execution_result.get('steps_taken', 'N/A')}\n\n"
            f"Key output / result:\n{str(execution_result.get('output', 'N/A'))[:800]}"
        )

        # Use the structured skill creation template
        from backend.services.prompt_template_manager import prompt_template_manager
        creation_prompt = prompt_template_manager.get_skill_creation_prompt(
            task_context=task_context
        )

        try:
            analysis = await ModelService.generate_with_agent(
                agent=agent,
                user_message=creation_prompt
            )

            raw = analysis.get("content", "").strip()

            # Strip markdown fences if the model wrapped the JSON anyway
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            skill_data = json.loads(raw)

            # Minimal sanity check before returning
            required = {"skill_name", "display_name", "skill_type", "domain",
                        "description", "steps", "validation_criteria"}
            if not required.issubset(skill_data.keys()):
                logger.warning(
                    "suggest_skill_creation: LLM output missing required fields. "
                    "Got keys: %s", list(skill_data.keys())
                )
                return None

            return {
                "draft_skill": skill_data,
                "reason": "Novel successful execution pattern extracted by SkillRAG"
            }

        except json.JSONDecodeError as e:
            logger.warning("suggest_skill_creation: JSON parse failed — %s", e)
            return None
        except Exception as e:
            logger.error("suggest_skill_creation: unexpected error — %s", e)
            return None


# Global instance
skill_rag = SkillRAG()