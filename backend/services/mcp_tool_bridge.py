"""
MCP Tool Bridge — Phase 6.7
===========================
Bridges the database-backed MCPTool registry into the in-memory ToolRegistry
so agents can discover and invoke MCP tools exactly the same way they use
built-in tools (browser_control, read_file, execute_command, etc.).

How it works
------------
1. At application startup, `MCPToolBridge.sync_all(db)` loads every approved
   MCPTool from the database and calls `tool_registry.register_tool(...)` for
   each one, wrapping the async MCP execution in a sync-compatible coroutine
   closure that carries the tool's DB id and tier permissions.

2. After any approve / revoke / disable event the route calls
   `MCPToolBridge.sync_one(tool, db)` or `MCPToolBridge.deregister(tool)`
   so the in-memory registry is updated in < 1 second — no server restart
   needed, satisfying the "revoked tools immediately unavailable" acceptance
   criterion.

3. Every registered MCP tool function signature is:
       async def _mcp_invoke(agent_id, agent_tier, params, **kwargs)
   The tools.py route is updated to pass `agent_id` and `agent_tier` through
   for all MCP tools (identified by the "is_mcp" flag in their registry entry).

Tier → authorized_tiers mapping
---------------------------------
pre_approved  → ["0xxxx", "1xxxx", "2xxxx", "3xxxx"]  (all agents)
restricted    → ["0xxxx", "1xxxx"]                      (Head + Council only)
forbidden     → []                                      (never registered)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.entities.mcp_tool import MCPTool
from backend.services.mcp_governance import (
    MCPGovernanceService,
    STATUS_APPROVED,
    TIER_FORBIDDEN,
    TIER_PRE_APPROVED,
    TIER_RESTRICTED,
)

logger = logging.getLogger(__name__)

# Prefix added to every MCP tool name in the registry so they are easy to
# identify and filter without touching the tool's human-readable name.
MCP_PREFIX = "mcp__"

# Tier → agent tiers that may call the tool
_TIER_TO_AUTHORIZED: Dict[str, List[str]] = {
    TIER_PRE_APPROVED: ["0xxxx", "1xxxx", "2xxxx", "3xxxx"],
    TIER_RESTRICTED:   ["0xxxx", "1xxxx"],
    TIER_FORBIDDEN:    [],   # never registered
}


def _registry_name(tool: MCPTool) -> str:
    """Canonical registry key for an MCPTool: 'mcp__<tool.name>'."""
    return f"{MCP_PREFIX}{tool.name}"


def _build_invoke_fn(tool_id: str, tool_name: str, db_factory):
    """
    Return an *async* callable that the ToolRegistry stores as the tool's
    `function`.  The closure captures only the tool id and a DB factory so
    it stays lightweight and picklable.

    The route calls it as:
        await fn(agent_id=..., agent_tier=..., params={...})
    """
    async def _mcp_invoke(
        agent_id: str,
        agent_tier: str,
        params: Optional[Dict[str, Any]] = None,
        has_head_approval_token: bool = False,
        tool_name_override: Optional[str] = None,
        **_extra,
    ) -> Dict[str, Any]:
        db: Session = db_factory()
        try:
            svc = MCPGovernanceService(db)
            return await svc.execute_mcp_tool(
                tool_id,
                agent_id=agent_id,
                agent_tier=agent_tier,
                params=params or {},
                has_head_approval_token=has_head_approval_token,
                tool_name=tool_name_override,
            )
        finally:
            db.close()

    # Give the function a readable name for debugging
    _mcp_invoke.__name__ = f"mcp_invoke_{tool_name}"
    return _mcp_invoke


class MCPToolBridge:
    """
    Singleton-style service that keeps the in-memory ToolRegistry in sync
    with the approved MCPTool rows in the database.
    """

    def __init__(self, tool_registry, db_factory):
        """
        Parameters
        ----------
        tool_registry : ToolRegistry
            The global `tool_registry` singleton from backend/core/tool_registry.py
        db_factory : callable
            Zero-arg callable that returns a new SQLAlchemy Session.
            Typically `next(get_db)` pattern or a SessionLocal factory.
        """
        self._registry = tool_registry
        self._db_factory = db_factory

    # ── Public API ─────────────────────────────────────────────────────────────

    def sync_all(self, db: Session) -> int:
        """
        Load all approved MCP tools from DB and register them.
        Called once at application startup (from main.py lifespan).
        Returns the count of tools registered.
        """
        tools = (
            db.query(MCPTool)
            .filter(
                MCPTool.status == STATUS_APPROVED,
                MCPTool.tier != TIER_FORBIDDEN,
                MCPTool.is_active == True,
            )
            .all()
        )

        registered = 0
        for tool in tools:
            self._register(tool)
            registered += 1

        logger.info("[MCPBridge] Startup sync complete — %d MCP tools registered", registered)
        return registered

    def sync_one(self, tool: MCPTool) -> None:
        """
        Register or re-register a single tool.
        Called after approval so the tool is immediately available to agents.
        """
        if tool.tier == TIER_FORBIDDEN:
            logger.warning(
                "[MCPBridge] Skipping forbidden-tier tool during sync: %s", tool.name
            )
            return

        if tool.status != STATUS_APPROVED:
            logger.info(
                "[MCPBridge] Skipping non-approved tool during sync: %s (status=%s)",
                tool.name, tool.status,
            )
            return

        self._register(tool)
        logger.info("[MCPBridge] Registered MCP tool: %s", _registry_name(tool))

    def deregister(self, tool: MCPTool) -> None:
        """
        Remove a tool from the registry immediately.
        Called after revocation / disabling so agents can no longer invoke it.
        Satisfies the "< 1s cache invalidation" acceptance criterion.
        """
        key = _registry_name(tool)
        removed = self._registry.deregister_tool(key)
        if removed:
            logger.warning("[MCPBridge] Deregistered MCP tool (revoked/disabled): %s", key)
        else:
            logger.debug("[MCPBridge] deregister called for unknown key: %s", key)

    def list_mcp_registry_keys(self) -> List[str]:
        """Return all registry keys that belong to MCP tools."""
        return [k for k in self._registry.tools if k.startswith(MCP_PREFIX)]

    # ── Private ────────────────────────────────────────────────────────────────

    def _register(self, tool: MCPTool) -> None:
        """
        Build the invocation closure and register the tool into the
        in-memory ToolRegistry with correct tier permissions.
        """
        key = _registry_name(tool)
        authorized_tiers = _TIER_TO_AUTHORIZED.get(tool.tier, [])

        # Build parameter schema from the tool's capability list so agents
        # can inspect what inputs the tool accepts.
        params_schema: Dict[str, Any] = {
            "params": {
                "type": "object",
                "description": "Key-value pairs passed to the MCP tool",
            },
            "has_head_approval_token": {
                "type": "boolean",
                "description": "Required for restricted-tier tools",
            },
        }
        # If the tool has explicit capabilities, surface them as enum hints
        if tool.capabilities:
            params_schema["tool_name_override"] = {
                "type": "string",
                "description": "Specific sub-tool to invoke",
                "enum": tool.capabilities,
            }

        invoke_fn = _build_invoke_fn(str(tool.id), tool.name, self._db_factory)

        self._registry.register_tool(
            name=key,
            description=f"[MCP/{tool.tier.upper()}] {tool.description}",
            function=invoke_fn,
            parameters=params_schema,
            authorized_tiers=authorized_tiers,
        )

        # Tag the registry entry with MCP metadata so the route layer can
        # detect it and route execution correctly.
        self._registry.tools[key]["is_mcp"] = True
        self._registry.tools[key]["mcp_tool_id"] = str(tool.id)
        self._registry.tools[key]["mcp_tier"] = tool.tier
        self._registry.tools[key]["mcp_server_url"] = tool.server_url
        self._registry.tools[key]["mcp_original_name"] = tool.name


# ── Module-level singleton ─────────────────────────────────────────────────────
# Instantiated lazily in main.py after the DB and registry are ready.
# Access via: from backend.services.mcp_tool_bridge import mcp_bridge
mcp_bridge: Optional["MCPToolBridge"] = None


def init_bridge(tool_registry, db_factory) -> "MCPToolBridge":
    """
    Create and store the global bridge instance.
    Call this once from main.py after all dependencies are initialised.

    Example in main.py:
        from backend.services.mcp_tool_bridge import init_bridge
        from backend.core.tool_registry import tool_registry
        from backend.models.database import SessionLocal

        @asynccontextmanager
        async def lifespan(app):
            bridge = init_bridge(tool_registry, SessionLocal)
            with SessionLocal() as db:
                bridge.sync_all(db)
            yield

        app = FastAPI(lifespan=lifespan)
    """
    global mcp_bridge
    mcp_bridge = MCPToolBridge(tool_registry, db_factory)
    return mcp_bridge