"""tool_creator — let Head/Council agents define and register new runtime tools."""

from typing import Any, Dict, List, Optional

from backend.models.schemas.tool_creation import ToolCreationRequest, ToolParameter
from backend.models.database import get_db_context
from backend.services.tool_creation_service import ToolCreationService

ALLOWED_TIERS = {"0", "1"}
ALLOWED_TIER_IDS = ["0xxxx", "1xxxx"]


class ToolCreatorTool:
    """Agent-callable tool to create new tools (Head/Council only)."""

    def __init__(self) -> None:
        pass

    def execute(self, action: str = "help", **kwargs) -> Dict[str, Any]:
        if action == "help":
            return self._help()
        if action != "create":
            return {"success": False, "error": f"Unknown action: {action}"}

        agent_id = kwargs.get("agent_id") or ""
        tier = (agent_id or "")[:1]
        if tier not in ALLOWED_TIERS:
            return {
                "success": False,
                "error": "tool_creator is restricted to Head (0xxxx) and Council (1xxxx) agents",
            }

        try:
            return self._create(**kwargs)
        except Exception as exc:  # never crash the agent loop
            return {"success": False, "error": str(exc)}

    def _create(self, **kwargs) -> Dict[str, Any]:
        requested_tiers = kwargs.get("authorized_tiers") or list(ALLOWED_TIER_IDS)
        safe_tiers = [t for t in requested_tiers if t in ALLOWED_TIER_IDS] or list(ALLOWED_TIER_IDS)

        params = [
            ToolParameter(
                name=p["name"],
                type=p.get("type", "string"),
                description=p.get("description", ""),
                required=p.get("required", True),
                default=p.get("default"),
            )
            for p in (kwargs.get("parameters") or [])
        ]

        request = ToolCreationRequest(
            tool_name=kwargs["tool_name"],
            description=kwargs["description"],
            parameters=params,
            code_template=kwargs["code_template"],
            test_cases=kwargs.get("test_cases") or [],
            authorized_tiers=safe_tiers,
            created_by_agentium_id=kwargs.get("agent_id") or "",
            rationale=kwargs.get("rationale") or "",
        )

        with get_db_context() as db:
            svc = ToolCreationService(db)
            result = svc.propose_tool(request)

        if not result.get("proposed"):
            return {"success": False, "error": result.get("error", "proposal rejected")}

        return {"success": True, **result}

    def _help(self) -> Dict[str, Any]:
        return {
            "success": True,
            "help": (
                "tool_creator(action='create', tool_name, description, parameters, "
                "code_template, rationale, test_cases=[], authorized_tiers=['0xxxx','1xxxx']) "
                "— Head-created tools auto-activate; Council-created tools enter the "
                "democratic Council vote. Restricted to Head/Council. Full reference in "
                "backend/.agentium/skills/tool_creator/SKILL.md."
            ),
        }


tool_creator_tool = ToolCreatorTool()
