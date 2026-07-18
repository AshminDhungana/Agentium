# backend/tools/tool_search_tool.py
"""Tool Search Tool — runtime discovery of registered tools by capability.

Lets an agent find the right tool without being handed the entire tool list.
Scores the caller's authorized tools (via tool_registry.list_tools) by
token-overlap over name + description + parameter names, with a boost for
name/substring hits. In-memory scoring — no new vector store needed.
Registered in ToolRegistry as "tool_search", available to all tiers.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", (text or "").lower()) if t]


class ToolSearchTool:
    TOOL_NAME = "tool_search"
    AUTHORIZED_TIERS = [f"{i}xxxx" for i in range(10)]

    def _resolve_tier(self, kwargs: Dict[str, Any]) -> str:
        aid = kwargs.get("agent_id") or ""
        caller_tier = (aid[:1] + "xxxx") if aid else "0xxxx"
        requested = kwargs.get("tier")
        if not requested:
            return caller_tier
        # A caller may not discover tools more privileged than its own tier
        # (lower leading digit == higher privilege). Clamp upward requests.
        try:
            caller_level = int(caller_tier[0])
            req_level = int(str(requested)[0])
        except (ValueError, TypeError, IndexError):
            return caller_tier
        if req_level < caller_level:
            return caller_tier
        return requested

    def _score(self, query_tokens: List[str], name: str, desc: str, params: Dict) -> tuple:
        hay = _tokens(name) + _tokens(desc) + _tokens(" ".join(params.keys()))
        name_tokens = set(_tokens(name))
        overlap = len(set(query_tokens) & set(hay))
        name_hit = len(set(query_tokens) & name_tokens)
        score = overlap + 2.0 * name_hit
        reasons = []
        if name_hit:
            reasons.append(f"name match: {', '.join(set(query_tokens) & name_tokens)}")
        elif overlap:
            reasons.append("description/parameter match")
        return score, "; ".join(reasons) or "partial relevance"

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Discover registered tools by describing what you need. Returns ranked "
                    "tool names + descriptions scoped to your tier. Full reference in "
                    "backend/.agentium/skills/tool_search/SKILL.md."
                ),
            }
        if action == "get":
            name = kwargs.get("name")
            if not name:
                return {"status": "error", "error": "name is required"}
            tier = self._resolve_tier(kwargs)
            from backend.core.tool_registry import tool_registry
            available = tool_registry.list_tools(tier)
            if name not in available:
                return {"status": "error", "error": f"tool '{name}' not found / not authorized"}
            return {"status": "success", "name": name, **available[name]}

        if action != "search":
            return {"status": "error", "error": f"Unknown action: {action}"}

        query = (kwargs.get("query") or "").strip()
        if not query:
            return {"status": "error", "error": "query is required"}
        limit = int(kwargs.get("limit", 10))
        tier = self._resolve_tier(kwargs)
        from backend.core.tool_registry import tool_registry
        available = tool_registry.list_tools(tier)
        q_tokens = _tokens(query)

        scored = []
        for name, desc in available.items():
            score, reason = self._score(
                q_tokens, name, desc.get("description", ""), desc.get("parameters", {})
            )
            if score > 0:
                scored.append({
                    "name": name,
                    "description": desc.get("description", ""),
                    "score": round(score, 2),
                    "match_reason": reason,
                })
        scored.sort(key=lambda r: r["score"], reverse=True)
        return {
            "status": "success",
            "query": query,
            "count": len(scored[:limit]),
            "results": scored[:limit],
        }


tool_search_tool = ToolSearchTool()
tool_instance = tool_search_tool
