from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    REPLY = "reply"
    CREATE_TASK = "create_task"
    SPAWN_AGENT = "spawn_agent"
    DISPATCH_TASK = "dispatch_task"
    VOTE = "vote"
    DELEGATE = "delegate"


@dataclass
class Decision:
    action: DecisionAction
    rationale: str = ""
    target_tier: Optional[str] = None
    task_brief: Optional[str] = None
    tools_considered: List[str] = field(default_factory=list)
    confidence: float = 0.0
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class DecisionEngine:
    """Single structured decision layer used by all agent tiers."""

    CONFIDENCE_FALLBACK = 0.4

    async def decide(self, agent, message: str, db, cache=None, _llm=None) -> Decision:
        from backend.core.llm_client import LLMClient
        from backend.core.tool_registry import ToolRegistry

        llm = _llm or LLMClient()
        tier = getattr(agent, "agent_tier", None) or (getattr(agent, "agentium_id", "00001") or "0")[:1] + "xxxx"
        available = ToolRegistry().to_openai_tools(tier)

        cache_key = None
        if cache is not None:
            cache_key = (getattr(agent, "agentium_id", "?"), hash(message))
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            decide_call = llm.decide if hasattr(llm, "decide") else llm
            result = await decide_call(
                agent, message, db=db,
                config_id=getattr(agent, "preferred_config_id", None),
                agent_tier=tier, available_tools=available,
            )
        except Exception as exc:  # LLM failure -> safe current behavior
            logger.warning("DecisionEngine.decide failed, falling back to REPLY: %s", exc)
            decision = Decision(action=DecisionAction.REPLY, rationale=f"llm_error:{exc}", confidence=0.0)
            if cache is not None and cache_key is not None:
                cache.set(cache_key, decision)
            return decision

        decision = self._parse(result)
        if decision.confidence < self.CONFIDENCE_FALLBACK:
            decision = Decision(
                action=DecisionAction.REPLY,
                rationale=f"low_confidence:{decision.confidence}",
                confidence=decision.confidence,
            )
        if cache is not None and cache_key is not None:
            cache.set(cache_key, decision)

        if db is not None:
            try:
                from backend.models.entities.audit import AuditLog, AuditLevel
                db.add(AuditLog(
                    level=AuditLevel.INFO,
                    category="GOVERNANCE",
                    actor_type="agent",
                    actor_id=getattr(agent, "agentium_id", "?"),
                    action=f"decision:{decision.action.value}",
                    description=(
                        f"rationale={decision.rationale} | "
                        f"tier={decision.target_tier} | "
                        f"conf={decision.confidence} | "
                        f"tools={','.join(decision.tools_considered)}"
                    ),
                    target_type="agent",
                    target_id=decision.target_tier or "",
                    correlation_id=decision.decision_id,
                ))
                db.commit()
            except Exception as e:
                logger.warning("Decision audit failed: %s", e)

        return decision

    @staticmethod
    def _parse(result: Dict[str, Any]) -> Decision:
        import json
        calls = result.get("tool_calls") or []
        # Fallback: provider.generate_with_tools returns a dict whose top level
        # has no `tool_calls` key — the parsed call lives inside
        # result["messages"][*].tool_calls (the assistant turns). Scan for the
        # last assistant message that carries a `decide` call.
        if not calls:
            for message in reversed(result.get("messages", []) or []):
                if message.get("role") != "assistant":
                    continue
                for call in (message.get("tool_calls") or []):
                    if call.get("function", {}).get("name") == "decide":
                        calls = [call]
                        break
                if calls:
                    break
        if not calls:
            return Decision(action=DecisionAction.REPLY, rationale="no_tool_call", confidence=0.0)
        args = calls[0].get("function", {}).get("arguments", "{}")
        try:
            data = json.loads(args)
        except json.JSONDecodeError:
            return Decision(action=DecisionAction.REPLY, rationale="bad_args", confidence=0.0)
        return Decision(
            action=DecisionAction(data.get("action", "reply")),
            rationale=data.get("rationale", ""),
            target_tier=data.get("target_tier"),
            task_brief=data.get("task_brief"),
            tools_considered=data.get("tools_considered", []),
            confidence=float(data.get("confidence", 0.0)),
        )
