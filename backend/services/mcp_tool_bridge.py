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

4. Schema Validation: Each MCP tool's inputSchema (JSON Schema) is converted
   to a Pydantic model at registration time, enabling pre-execution parameter
   validation with structured error responses.

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


def _build_pydantic_model_from_jsonschema(schema: Dict[str, Any]):
    """
    Convert JSON Schema (MCP inputSchema) to Pydantic model.
    Handles: type, properties, required, enum, default, description.
    Falls back to permissive Dict model for unsupported constructs.
    """
    from pydantic import create_model, Field
    from typing import Any, Dict, List, Optional, Literal, Union

    if not schema or schema.get("type") != "object":
        # Fallback permissive model
        return create_model("PermissiveParams", data=(Dict[str, Any], Field(default_factory=dict)))

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": List[Any],
        "object": Dict[str, Any],
    }

    fields = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        python_type = TYPE_MAP.get(prop_type, Any)

        is_required = prop_name in required
        has_default = "default" in prop_schema

        field_kwargs = {"description": prop_schema.get("description", "")}

        # Handle enum
        if "enum" in prop_schema:
            enum_values = prop_schema["enum"]
            python_type = Literal[tuple(enum_values)]
            if not is_required and not has_default:
                python_type = Optional[python_type]

        # Handle optional
        if not is_required:
            if has_default:
                field_kwargs["default"] = prop_schema["default"]
            else:
                python_type = Optional[python_type]
                field_kwargs["default"] = None
        elif has_default:
            field_kwargs["default"] = prop_schema["default"]

        fields[prop_name] = (python_type, Field(**field_kwargs))

    # Handle additionalProperties
    additional_props = schema.get("additionalProperties", True)
    if additional_props is False:
        config = {"extra": "forbid"}
    else:
        config = {"extra": "ignore"}

    model = create_model(
        f"MCPParams_{hash(tuple(sorted(fields.keys())))}",
        __config__=config,
        **fields
    )

    return model


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
        """Invoke the governed MCP tool using the provided agent context and parameters."""
        # Validate params against the specific sub-tool's inputSchema if available
        from backend.core.tool_registry import tool_registry
        tool_entry = tool_registry.tools.get(f"mcp__{tool_name}")
        if tool_entry and "mcp_input_models" in tool_entry:
            sub_tool = tool_name_override or (tool_entry.get("mcp_capabilities", [{}])[0].get("name") if tool_entry.get("mcp_capabilities") else None)
            if sub_tool and sub_tool in tool_entry["mcp_input_models"]:
                model = tool_entry["mcp_input_models"][sub_tool]
                from pydantic import ValidationError
                try:
                    validated = model.model_validate(params or {})
                    params = validated.model_dump()
                except ValidationError as e:
                    return {
                        "status": "error",
                        "error": {
                            "type": "schema_validation_error",
                            "message": f"Invalid parameters for MCP tool '{sub_tool}'",
                            "details": e.errors(),
                        }
                    }

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
                "enum": [c["name"] for c in tool.capabilities if isinstance(c, dict) and c.get("name")],
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

        # Store the full capability descriptors (with inputSchema) for validation
        self._registry.tools[key]["mcp_capabilities"] = tool.capabilities

        # Build Pydantic models for each sub-tool's inputSchema
        mcp_models = {}
        for cap in tool.capabilities:
            if isinstance(cap, dict) and cap.get("input_schema"):
                sub_tool_name = cap.get("name")
                if sub_tool_name:
                    mcp_models[sub_tool_name] = _build_pydantic_model_from_jsonschema(cap["input_schema"])
        if mcp_models:
            self._registry.tools[key]["mcp_input_models"] = mcp_models


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