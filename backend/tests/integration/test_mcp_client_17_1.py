"""
MCP Client Integration Tests — TODO items 17.1.1 – 17.1.4
=============================================================

17.1.1 — mcp_client.py connects to external MCP servers
17.1.2 — Tool discovery from MCP servers works
17.1.3 — Tool invocation via MCP protocol works
17.1.4 — MCP tool bridge registers external tools in local registry

All tests run with the MCP package forced into mock mode so they are
hermetic and do not require a live MCP server process.
"""
import asyncio
import pytest

from backend.models.database import SessionLocal
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.mcp_tool import MCPTool
from backend.services.mcp_client import MCPClient, MCPConnectionError
from backend.services.mcp_governance import (
    MCPGovernanceService,
    STATUS_APPROVED,
    TIER_PRE_APPROVED,
)
from backend.services.mcp_tool_bridge import (
    MCPToolBridge,
    _build_pydantic_model_from_jsonschema,
    _registry_name,
    init_bridge,
)
from backend.core.tool_registry import tool_registry

pytestmark = pytest.mark.integration


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """Force MCP client mock mode for all tests in this file."""
    import backend.services.mcp_client as mcp_mod
    monkeypatch.setattr(mcp_mod, "MCP_AVAILABLE", False)


@pytest.fixture(scope="module")
def bridge():
    """Module-scoped MCPToolBridge wired to the live DB and tool_registry."""
    return init_bridge(tool_registry, SessionLocal)


def _head_agent(db):
    """Create (or reuse) a Head agent for proposal auto-approval."""
    a = Agent(
        agent_type=AgentType.HEAD_OF_COUNCIL,
        agentium_id="00099",
        status=AgentStatus.ACTIVE,
        name="TestHead99",
    )
    db.add(a)
    try:
        db.commit()
    except Exception:
        db.rollback()
    return a


# ══════════════════════════════════════════════════════════════════════════════
# 17.1.1 — MCPClient connects to external MCP servers
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPClientConnection:
    """17.1.1: MCPClient lifecycle in mock mode."""

    def test_connect_does_not_raise_in_mock_mode(self):
        """connect() must succeed silently when mcp package is absent."""
        client = MCPClient("fake://server")
        asyncio.run(client.connect())

    def test_disconnect_is_idempotent_before_connect(self):
        """disconnect() must not raise even if connect() was never called."""
        client = MCPClient("fake://server")
        asyncio.run(client.disconnect())

    def test_context_manager_enters_and_exits(self):
        """Async context manager protocol must work without errors."""
        async def _run():
            async with MCPClient("fake://server") as c:
                assert c is not None
        asyncio.run(_run())

    def test_double_connect_is_idempotent_in_mock_mode(self):
        """Calling connect() twice must not raise."""
        client = MCPClient("fake://server")
        asyncio.run(client.connect())
        asyncio.run(client.connect())

    def test_stdio_cm_initialised_to_none(self):
        """_stdio_cm must be None on a fresh MCPClient instance."""
        client = MCPClient("fake://server")
        assert client._stdio_cm is None

    def test_disconnect_clears_stdio_cm(self):
        """After disconnect(), _stdio_cm must be None."""
        client = MCPClient("fake://server")
        asyncio.run(client.connect())
        asyncio.run(client.disconnect())
        assert client._stdio_cm is None


# ══════════════════════════════════════════════════════════════════════════════
# 17.1.2 — Tool discovery from MCP servers works
# ══════════════════════════════════════════════════════════════════════════════

class TestToolDiscovery:
    """17.1.2: list_tools() returns well-formed descriptor dicts."""

    def test_list_tools_returns_list_in_mock_mode(self):
        """list_tools() must return a non-empty list in mock mode."""
        client = MCPClient("fake://server")
        tools = asyncio.run(client.list_tools())
        assert isinstance(tools, list)
        assert len(tools) >= 1

    def test_list_tools_items_have_name_key(self):
        """Each tool descriptor must contain a 'name' key."""
        client = MCPClient("fake://server")
        tools = asyncio.run(client.list_tools())
        for t in tools:
            assert "name" in t, f"Tool descriptor missing 'name': {t}"

    def test_list_tools_items_have_input_schema_key(self):
        """Each tool descriptor must contain an 'input_schema' key."""
        client = MCPClient("fake://server")
        tools = asyncio.run(client.list_tools())
        for t in tools:
            assert "input_schema" in t, f"Tool descriptor missing 'input_schema': {t}"

    def test_capabilities_stored_as_dicts(self, db_session):
        """
        propose_mcp_server_with_vote must store capabilities as dicts
        with name/description/input_schema keys (not raw strings).
        """
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="disc_test_tool",
                description="discovery dict test",
                server_url="disc_test_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        assert out.get("proposed") is True
        caps = out.get("capabilities", [])
        assert isinstance(caps, list)
        for cap in caps:
            assert isinstance(cap, dict), f"Capability is not a dict: {cap}"
            assert "name" in cap
            assert "description" in cap
            assert "input_schema" in cap

    def test_capabilities_description_is_string_not_object(self, db_session):
        """
        Bug E regression: description must be a string, not the result of
        getattr() on a dict (which would be empty string from __dict__ miss).
        """
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="desc_check_tool",
                description="description check",
                server_url="desc_check_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        for cap in out.get("capabilities", []):
            assert isinstance(cap["description"], str)
            assert isinstance(cap["input_schema"], dict)


# ══════════════════════════════════════════════════════════════════════════════
# 17.1.3 — Tool invocation via MCP protocol works
# ══════════════════════════════════════════════════════════════════════════════

class TestToolInvocation:
    """17.1.3: call_tool() and execute_mcp_tool() work correctly."""

    def test_call_tool_returns_success_true_in_mock_mode(self):
        """call_tool() must return success=True in mock mode."""
        client = MCPClient("fake://server")
        result = asyncio.run(client.call_tool("mock_search", {"query": "hello"}))
        assert result["success"] is True

    def test_call_tool_result_is_list(self):
        """The 'result' field must be a list of content blocks."""
        client = MCPClient("fake://server")
        result = asyncio.run(client.call_tool("mock_search", {"query": "test"}))
        assert isinstance(result["result"], list)
        assert len(result["result"]) >= 1

    def test_call_tool_echoes_tool_name(self):
        """The 'tool' key in the response must match what was passed."""
        client = MCPClient("fake://server")
        result = asyncio.run(client.call_tool("my_custom_tool", {}))
        assert result["tool"] == "my_custom_tool"

    def test_execute_mcp_tool_target_resolution_from_dict_caps(self, db_session):
        """
        Bug G regression: when capabilities is a list of dicts, execute_mcp_tool
        must resolve target_tool to cap["name"] (a string), not the dict itself.
        """
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="invoke_test_tool",
                description="invocation target resolution test",
                server_url="invoke_test_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        assert out["proposed"] is True
        tool_id = out["tool_id"]

        result = asyncio.run(
            svc.execute_mcp_tool(
                tool_id,
                agent_id="30001",
                agent_tier="3xxxx",
                params={},
            )
        )
        assert result.get("success") is True
        tool_name_in_result = result.get("tool", "")
        assert isinstance(tool_name_in_result, str)
        # Must not be a dict repr like "{'name': 'mock_search', ...}"
        assert "{" not in tool_name_in_result

    def test_execute_mcp_tool_none_params_normalised(self, db_session):
        """
        Bug H regression: passing params=None must not raise AttributeError;
        the guard at the top of execute_mcp_tool converts it to {}.
        """
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="nullparams_tool",
                description="null params guard test",
                server_url="nullparams_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        tool_id = out["tool_id"]
        result = asyncio.run(
            svc.execute_mcp_tool(
                tool_id,
                agent_id="30001",
                agent_tier="3xxxx",
                params=None,
            )
        )
        assert result.get("success") is True


# ══════════════════════════════════════════════════════════════════════════════
# 17.1.4 — MCP tool bridge registers external tools in local registry
# ══════════════════════════════════════════════════════════════════════════════

class TestMCPToolBridge:
    """17.1.4: MCPToolBridge registers/deregisters tools in ToolRegistry."""

    def test_sync_registers_approved_tool(self, db_session, bridge):
        """sync_one() after proposal must put mcp__<name> in tool_registry."""
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="bridge_sync_tool",
                description="bridge sync test",
                server_url="bridge_sync_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        assert out["proposed"] is True
        key = out["registry_key"]
        assert key in tool_registry.tools

    def test_registered_entry_has_is_mcp_flag(self, db_session, bridge):
        """Registered MCP tool entries must have is_mcp=True."""
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="bridge_flag_tool",
                description="flag check",
                server_url="bridge_flag_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        key = out["registry_key"]
        entry = tool_registry.tools.get(key)
        assert entry is not None
        assert entry.get("is_mcp") is True

    def test_registered_entry_has_mcp_tool_id(self, db_session, bridge):
        """Registered MCP tool entries must carry mcp_tool_id."""
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="bridge_id_tool",
                description="id check",
                server_url="bridge_id_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        key = out["registry_key"]
        entry = tool_registry.tools.get(key)
        assert entry is not None
        assert "mcp_tool_id" in entry
        assert entry["mcp_tool_id"] == out["tool_id"]

    def test_deregister_removes_key(self, db_session, bridge):
        """deregister() must immediately remove the tool from tool_registry."""
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        out = asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="bridge_dereg_tool",
                description="deregister test",
                server_url="bridge_dereg_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        key = out["registry_key"]
        assert key in tool_registry.tools

        tool_row = db_session.query(MCPTool).filter_by(name="bridge_dereg_tool").first()
        assert tool_row is not None
        bridge.deregister(tool_row)
        assert key not in tool_registry.tools

    def test_bridge_none_capabilities_does_not_raise(self, bridge):
        """
        Bug K regression: _register() must not raise when tool.capabilities
        is None (old DB rows before the capabilities dict migration).
        """
        class _FakeTool:
            id = "00000000-0000-0000-0000-000000000099"
            name = "null_cap_tool"
            description = "null capabilities guard"
            server_url = "null_cap_cmd"
            tier = TIER_PRE_APPROVED
            status = STATUS_APPROVED
            capabilities = None

        bridge._register(_FakeTool())
        key = "mcp__null_cap_tool"
        assert key in tool_registry.tools
        tool_registry.tools.pop(key, None)

    def test_pydantic_model_string_property(self):
        """_build_pydantic_model_from_jsonschema handles a required string property."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "search query"},
            },
            "required": ["query"],
        }
        model = _build_pydantic_model_from_jsonschema(schema)
        instance = model.model_validate({"query": "hello"})
        assert instance.query == "hello"

    def test_pydantic_model_integer_with_default(self):
        """_build_pydantic_model_from_jsonschema handles integer + default."""
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "page count"},
                "page": {"type": "integer", "description": "page number", "default": 1},
            },
            "required": ["count"],
        }
        model = _build_pydantic_model_from_jsonschema(schema)
        instance = model.model_validate({"count": 5})
        assert instance.count == 5
        assert instance.page == 1

    def test_pydantic_model_boolean_property(self):
        """_build_pydantic_model_from_jsonschema handles boolean property."""
        schema = {
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean", "description": "verbose output"},
            },
        }
        model = _build_pydantic_model_from_jsonschema(schema)
        instance = model.model_validate({"verbose": True})
        assert instance.verbose is True

    def test_pydantic_model_forbid_extra_fields(self):
        """
        Bug I regression: ConfigDict(extra='forbid') must actually reject
        unexpected fields (was broken by __config__=dict usage).
        """
        from pydantic import ValidationError
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
            "additionalProperties": False,
        }
        model = _build_pydantic_model_from_jsonschema(schema)
        with pytest.raises(ValidationError):
            model.model_validate({"q": "ok", "unexpected_field": "value"})

    def test_list_mcp_registry_keys_returns_mcp_prefixed(self, db_session, bridge):
        """list_mcp_registry_keys() must only return keys starting with 'mcp__'."""
        _head_agent(db_session)
        svc = MCPGovernanceService(db_session)
        asyncio.run(
            svc.propose_mcp_server_with_vote(
                name="prefix_check_tool",
                description="prefix check",
                server_url="prefix_check_cmd",
                tier=TIER_PRE_APPROVED,
                proposed_by="00099",
            )
        )
        keys = bridge.list_mcp_registry_keys()
        assert all(k.startswith("mcp__") for k in keys)
        assert "mcp__prefix_check_tool" in keys
