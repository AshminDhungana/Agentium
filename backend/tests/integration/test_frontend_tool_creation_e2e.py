"""E2E verification: tool created via frontend propose flow is registered,
exported to provider schemas, and invocable by an authorized agent.

Covers planning task §3.4 (P2): confirm UI-created tools actually persist on
the backend and are not lost to a stale registry / cache.
"""
import pytest

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
