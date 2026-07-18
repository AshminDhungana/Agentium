"""E2E verification: tool created via frontend propose flow is registered,
exported to provider schemas, and invocable by an authorized agent.

Covers planning task §3.4 (P2): confirm UI-created tools actually persist on
the backend and are not lost to a stale registry / cache.
"""
import pytest

from sqlalchemy import select

from backend.core.auth import create_access_token


@pytest.fixture
def head_auth_headers():
    """Mint a Head-tier (0xxxx) JWT so the propose route auto-activates.

    The default admin login JWT carries no `tier` claim, so
    get_current_agent_tier() defaults to 3xxxx (Task) and the route blocks it
    via _require_not_task_agent. The Head path auto-approves + activates.
    """
    token = create_access_token({
        "sub": "00001",
        "user_id": 1,
        "role": "head",
        "is_admin": True,
        "is_active": True,
        "tier": "0xxxx",
        "agentium_id": "00001",
    })
    return {"Authorization": f"Bearer {token}"}


from uuid import uuid4

from backend.core.tool_registry import tool_registry
from backend.models.entities.tool_staging import ToolStaging
from backend.models.schemas.tool_creation import ToolCreationRequest
from backend.services.tool_creation_service import ToolCreationService


def _make_request(unique_name: str) -> ToolCreationRequest:
    return ToolCreationRequest(
        tool_name=unique_name,
        description="E2E probe tool",
        parameters=[],
        code_template="result = {'echo': 'ok', 'n': 42}",
        test_cases=[],
        authorized_tiers=["0xxxx", "1xxxx"],
        created_by_agentium_id="00001",
        rationale="e2e verification",
    )


@pytest.mark.integration
def test_direct_service_tool_persists_and_is_invocable(seeded_db):
    name = f"e2e_probe_{uuid4().hex[:8]}"
    service = ToolCreationService(seeded_db)
    res = service.propose_tool(_make_request(name))
    try:
        assert res.get("proposed") is True, res
        assert res.get("status") == "activated", res

        # 1) Persisted in the live registry
        assert name in tool_registry.tools

        # (1b) Persisted at the storage layer (not just the in-memory registry)
        from sqlalchemy import select
        row = seeded_db.execute(
            select(ToolStaging).where(ToolStaging.tool_name == name)
        ).scalar_one_or_none()
        assert row is not None, "ToolStaging row missing after activation"
        assert row.status == "activated", row.status

        # 2) Exported to OpenAI schema
        oai = tool_registry.to_openai_tools("0xxxx")
        oai_names = [t["function"]["name"] for t in oai]
        assert name in oai_names
        spec = next(t for t in oai if t["function"]["name"] == name)
        assert spec["function"]["description"] == "E2E probe tool"

        # 3) Exported to Anthropic schema
        ant = tool_registry.to_anthropic_tools("0xxxx")
        assert name in [t["name"] for t in ant]

        # 4) Invocable by an authorized agent
        fn = tool_registry.get_tool_function(name)
        assert fn() == {"status": "success", "result": {"echo": "ok", "n": 42}}
    finally:
        tool_registry.deregister_tool(name)


@pytest.mark.integration
def test_http_propose_route_registers_and_exports_tool(client, seeded_db, head_auth_headers):
    name = f"e2e_probe_{uuid4().hex[:8]}"
    body = _make_request(name).model_dump()
    resp = client.post(
        "/api/v1/tool-management/propose",
        json=body,
        headers=head_auth_headers,
    )
    try:
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "activated", data
        assert data.get("tool_name") == name, data

        # Live persistence in the registry singleton (catches stale/cache gaps)
        assert name in tool_registry.tools

        # (1b) Persisted at the storage layer (not just the in-memory registry)
        from sqlalchemy import select
        row = seeded_db.execute(
            select(ToolStaging).where(ToolStaging.tool_name == name)
        ).scalar_one_or_none()
        assert row is not None, "ToolStaging row missing after activation"
        assert row.status == "activated", row.status

        oai = tool_registry.to_openai_tools("0xxxx")
        assert name in [t["function"]["name"] for t in oai]
        spec = next(t for t in oai if t["function"]["name"] == name)
        assert spec["function"]["description"] == "E2E probe tool"

        ant = tool_registry.to_anthropic_tools("0xxxx")
        assert name in [t["name"] for t in ant]

        fn = tool_registry.get_tool_function(name)
        assert fn() == {"status": "success", "result": {"echo": "ok", "n": 42}}
    finally:
        tool_registry.deregister_tool(name)
