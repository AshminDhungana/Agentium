"""
Ethos Tool — agent-callable read access to an agent's working memory (Ethos).

Provides a read-only first action ("read"). The Ethos ORM model is the source
of truth for an agent's current objective, active plan, task progress, reasoning
artifacts, lessons learned, constitutional references, and identity verification.

Tool contract (matches backend.tools.governance_tool / embedding_tool):
- Declares `db: Session = None` and `agent_id: str = None`, injected by the executor.
- Returns a uniform dict: {"success": bool, "data": dict|None, "error": str|None}.
"""

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.models.entities.agents import Agent
from backend.models.entities.constitution import Ethos

logger = logging.getLogger(__name__)

# All hierarchical tiers may read their own Ethos.
ALL_TIERS = [
    "0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx",
    "5xxxx", "6xxxx", "7xxxx", "8xxxx", "9xxxx",
]


def _result(success: bool, data: Optional[dict] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Uniform tool return envelope."""
    return {"success": success, "data": data, "error": error}


def _load_ethos(db: Session, agent_id: str) -> Optional[Ethos]:
    """Resolve the calling agent and return its Ethos, or None."""
    agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
    if agent is None or not agent.ethos_id:
        return None
    return db.query(Ethos).filter(Ethos.id == agent.ethos_id).first()


class EthosTool:
    """
    Agent-callable tool for managing an agent's working memory (Ethos).

    Actions:
    - read:            Return the agent's current working memory snapshot.
    - append:          (planned) Append a reasoning artifact / lesson learned.
    - compress:        (planned) Compress transient working state.
    - edit_identity:   (planned) Update core identity fields (higher-tier only).
    - verify_identity: (planned) Mark Ethos verified by a higher authority.
    """

    TOOL_NAME = "ethos"
    TOOL_DESCRIPTION = (
        "Read and manage an agent's Ethos (working memory). "
        "Actions: read (return current working memory: mission, objective, "
        "active plan, task progress, reasoning artifacts, lessons learned, "
        "constitutional references, outcome summary, version, verification); "
        "append (add reasoning artifact or lesson learned); "
        "compress (summarize transient state); "
        "edit_identity (update core identity, higher-tier only); "
        "verify_identity (mark Ethos verified)."
    )
    AUTHORIZED_TIERS = ALL_TIERS

    async def execute(
        self,
        action: str,
        db: Session = None,
        agent_id: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if db is None or not agent_id:
            return _result(False, error="db and agent_id are required")

        if action == "read":
            return self._read(db, agent_id)

        if action == "append":
            return self._append(db, agent_id, kwargs)

        if action == "compress":
            return self._compress(db, agent_id, kwargs)

        if action == "edit_identity":
            return self._edit_identity(db, agent_id, kwargs)
        if action == "verify_identity":
            return self._verify_identity(db, agent_id)

        return _result(False, error=f"Unknown or unimplemented action: {action}")

    def _read(self, db: Session, agent_id: str) -> Dict[str, Any]:
        ethos = _load_ethos(db, agent_id)
        if ethos is None:
            return _result(False, error=f"No Ethos found for agent {agent_id}")

        data = {
            "agent_type": ethos.agent_type,
            "mission_statement": ethos.mission_statement,
            "current_objective": ethos.current_objective,
            "active_plan": ethos.get_active_plan(),
            "task_progress": ethos.get_task_progress(),
            "reasoning_artifacts": ethos.get_reasoning_artifacts(),
            "lessons_learned": ethos.get_lessons_learned(),
            "constitutional_references": ethos.get_constitutional_references(),
            "outcome_summary": ethos.outcome_summary,
            "version": ethos.version,
            "is_verified": ethos.is_verified,
            "environment_context": ethos.environment_context,
        }
        return _result(True, data=data)

    def _append(self, db: Session, agent_id: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        ethos = _load_ethos(db, agent_id)
        if ethos is None:
            return _result(False, error=f"Ethos not found for agent {agent_id}")
        kind = kwargs.get("kind")
        payload = kwargs.get("payload")
        if kind == "lesson":
            if not isinstance(payload, dict):
                return _result(False, error="lesson payload must be a dict")
            ethos.add_lesson_learned(payload)
            return _result(True, data={"kind": "lesson", "written": payload})
        if kind == "progress":
            if not isinstance(payload, dict):
                return _result(False, error="progress payload must be a dict")
            ethos.set_task_progress(payload)
            return _result(True, data={"kind": "progress", "written": payload})
        if kind == "reasoning":
            artifacts = ethos.get_reasoning_artifacts()
            artifacts.append(payload if isinstance(payload, (str, dict)) else str(payload))
            ethos.reasoning_artifacts = json.dumps(artifacts)
            ethos.increment_version()
            return _result(True, data={"kind": "reasoning", "written": payload})
        return _result(False, error=f"Unknown append kind: {kind}")

    def _compress(self, db: Session, agent_id: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
        if agent is None or not agent.ethos_id:
            return _result(False, error=f"Agent or ethos not found for {agent_id}")
        completed_steps = kwargs.get("completed_steps") or []
        try:
            agent.compress_ethos(db, completed_steps=completed_steps)
            db.flush()
        except Exception as exc:  # compression must never hard-fail the agent turn
            logger.warning("ethos compress failed for %s: %s", agent_id, exc)
            db.rollback()
            return _result(False, error=f"compress failed: {exc}")
        ethos = _load_ethos(db, agent_id)
        return _result(True, data={
            "version": ethos.version,
            "lessons_count": len(ethos.get_lessons_learned()),
            "reasoning_count": len(ethos.get_reasoning_artifacts()),
        })

    def _edit_identity(self, db: Session, agent_id: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        ethos = _load_ethos(db, agent_id)
        agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
        if ethos is None or agent is None:
            return _result(False, error=f"Agent or ethos not found for {agent_id}")
        patch = kwargs.get("patch")
        if not isinstance(patch, dict):
            return _result(False, error="edit_identity requires a dict 'patch'")
        allowed = {"mission_statement", "behavioral_rules",
                   "restrictions", "capabilities"}
        cleaned = {k: v for k, v in patch.items() if k in allowed}
        if not cleaned:
            return _result(False, error=f"patch must contain one of {sorted(allowed)}")
        agent.pending_identity_edit = json.dumps(cleaned)
        agent.ethos_action_pending = True
        db.flush()
        return _result(True, data={"staged": cleaned, "pending": True})

    def _verify_identity(self, db: Session, agent_id: str) -> Dict[str, Any]:
        caller_tier = agent_id[0] if agent_id and agent_id[0].isdigit() else "?"
        if caller_tier not in ("0", "2"):
            return _result(False, error="only Lead (2xxxx) or Head (0xxxx) may verify identity edits")
        pending_agent = db.query(Agent).filter(Agent.ethos_action_pending == True).first()
        if pending_agent is None:
            return _result(False, error="no pending identity edit to verify")
        pending_ethos = _load_ethos(db, pending_agent.agentium_id)
        patch = json.loads(pending_agent.pending_identity_edit) if pending_agent.pending_identity_edit else None
        if not patch:
            return _result(False, error="pending edit payload missing")
        for field, value in patch.items():
            setattr(pending_ethos, field,
                    json.dumps(value) if isinstance(value, (list, dict)) else value)
        pending_ethos.verify(agent_id)
        pending_agent.pending_identity_edit = None
        pending_agent.ethos_action_pending = False
        db.flush()
        return _result(True, data={"applied": patch, "verified_by": agent_id})


ethos_tool = EthosTool()
