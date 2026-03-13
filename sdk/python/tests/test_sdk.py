"""
Unit tests for the Agentium Python SDK.

Uses ``respx`` to mock httpx requests so no real server is needed.
"""

import pytest
import respx
import httpx
from agentium_sdk import AgentiumClient
from agentium_sdk.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ConstitutionalViolationError,
    ServerError,
    ValidationError,
)
from agentium_sdk.models import Agent, Task, Constitution, Vote, WebhookSubscription


BASE = "http://testserver"


# ═══════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_health():
    respx.get(f"{BASE}/api/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy", "timestamp": "2026-01-01T00:00:00"})
    )
    async with AgentiumClient(BASE, api_key="test-key") as client:
        health = await client.health()
        assert health.status == "healthy"


# ═══════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_login():
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "jwt-token-123"})
    )
    async with AgentiumClient(BASE) as client:
        token = await client.login("admin", "password")
        assert token == "jwt-token-123"
        assert client._token == "jwt-token-123"


@respx.mock
@pytest.mark.asyncio
async def test_login_failure():
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid credentials"})
    )
    async with AgentiumClient(BASE) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            await client.login("bad", "wrong")
        assert "Invalid credentials" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════
# Agents
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_list_agents():
    respx.get(f"{BASE}/api/v1/agents").mock(
        return_value=httpx.Response(200, json={
            "agents": [
                {"agentium_id": "00001", "role": "Head of Council", "status": "active", "tier": 0},
                {"agentium_id": "10001", "role": "Ethics Advisor", "status": "active", "tier": 1},
            ]
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        agents = await client.list_agents()
        assert len(agents) == 2
        assert agents[0].agentium_id == "00001"
        assert agents[1].tier == 1
        assert isinstance(agents[0], Agent)


@respx.mock
@pytest.mark.asyncio
async def test_get_agent():
    respx.get(f"{BASE}/api/v1/agents/00001").mock(
        return_value=httpx.Response(200, json={
            "agentium_id": "00001", "role": "Head", "status": "active", "tier": 0
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        agent = await client.get_agent("00001")
        assert agent.role == "Head"


@respx.mock
@pytest.mark.asyncio
async def test_get_agent_not_found():
    respx.get(f"{BASE}/api/v1/agents/99999").mock(
        return_value=httpx.Response(404, json={"detail": "Agent 99999 not found"})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        with pytest.raises(NotFoundError):
            await client.get_agent("99999")


# ═══════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_create_task():
    respx.post(f"{BASE}/api/v1/tasks").mock(
        return_value=httpx.Response(200, json={
            "id": "task-1", "title": "Test", "description": "A test task", "status": "pending"
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        task = await client.create_task(title="Test", description="A test task")
        assert task.id == "task-1"
        assert task.status == "pending"
        assert isinstance(task, Task)


@respx.mock
@pytest.mark.asyncio
async def test_list_tasks():
    respx.get(f"{BASE}/api/v1/tasks").mock(
        return_value=httpx.Response(200, json={
            "tasks": [
                {"id": "t1", "title": "Task 1", "status": "completed"},
                {"id": "t2", "title": "Task 2", "status": "pending"},
            ]
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        tasks = await client.list_tasks()
        assert len(tasks) == 2


# ═══════════════════════════════════════════════════════════
# Constitution
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_get_constitution():
    respx.get(f"{BASE}/api/v1/constitution").mock(
        return_value=httpx.Response(200, json={
            "version": "v1.0.0", "preamble": "We the agents...", "is_active": True
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        constitution = await client.get_constitution()
        assert constitution.version == "v1.0.0"
        assert constitution.is_active is True
        assert isinstance(constitution, Constitution)


# ═══════════════════════════════════════════════════════════
# Voting
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_list_votes():
    respx.get(f"{BASE}/api/v1/voting/proposals").mock(
        return_value=httpx.Response(200, json={
            "proposals": [
                {"id": "v1", "title": "Amend Article 3", "status": "active", "votes_for": 2, "votes_against": 1}
            ]
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        votes = await client.list_votes()
        assert len(votes) == 1
        assert votes[0].votes_for == 2
        assert isinstance(votes[0], Vote)


# ═══════════════════════════════════════════════════════════
# Webhooks
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_create_webhook_subscription():
    respx.post(f"{BASE}/api/v1/webhooks/subscriptions").mock(
        return_value=httpx.Response(200, json={
            "id": "wh-1", "url": "https://example.com/hook",
            "events": ["task.created"], "is_active": True
        })
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        sub = await client.create_webhook_subscription(
            url="https://example.com/hook",
            events=["task.created"],
        )
        assert sub.id == "wh-1"
        assert sub.is_active is True
        assert isinstance(sub, WebhookSubscription)


@respx.mock
@pytest.mark.asyncio
async def test_delete_webhook():
    respx.delete(f"{BASE}/api/v1/webhooks/subscriptions/wh-1").mock(
        return_value=httpx.Response(200, json={"status": "deleted"})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        result = await client.delete_webhook_subscription("wh-1")
        assert result["status"] == "deleted"


# ═══════════════════════════════════════════════════════════
# Error Handling
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_error():
    respx.get(f"{BASE}/api/v1/agents").mock(
        return_value=httpx.Response(
            429,
            json={"detail": "Rate limit exceeded"},
            headers={"Retry-After": "30"},
        )
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        with pytest.raises(RateLimitError) as exc_info:
            await client.list_agents()
        assert exc_info.value.retry_after == 30.0


@respx.mock
@pytest.mark.asyncio
async def test_constitutional_violation():
    respx.post(f"{BASE}/api/v1/tasks").mock(
        return_value=httpx.Response(403, json={"detail": "Constitutional violation: action prohibited"})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        with pytest.raises(ConstitutionalViolationError):
            await client.create_task(title="Bad", description="rm -rf /")


@respx.mock
@pytest.mark.asyncio
async def test_server_error():
    respx.get(f"{BASE}/api/v1/agents").mock(
        return_value=httpx.Response(500, json={"detail": "Internal error"})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        with pytest.raises(ServerError):
            await client.list_agents()


@respx.mock
@pytest.mark.asyncio
async def test_validation_error():
    respx.post(f"{BASE}/api/v1/tasks").mock(
        return_value=httpx.Response(422, json={"detail": [{"msg": "field required", "loc": ["body", "title"]}]})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        with pytest.raises(ValidationError):
            await client.create_task(title="", description="")


# ═══════════════════════════════════════════════════════════
# SDK Header Verification
# ═══════════════════════════════════════════════════════════

@respx.mock
@pytest.mark.asyncio
async def test_sdk_header_present():
    """Verify that X-SDK-Source header is sent on every request."""
    route = respx.get(f"{BASE}/api/v1/agents").mock(
        return_value=httpx.Response(200, json={"agents": []})
    )
    async with AgentiumClient(BASE, api_key="key") as client:
        await client.list_agents()

    assert route.called
    request = route.calls[0].request
    assert request.headers.get("X-SDK-Source") == "python-sdk"


@respx.mock
@pytest.mark.asyncio
async def test_api_key_header():
    """Verify that API key is sent via X-API-Key header."""
    route = respx.get(f"{BASE}/api/v1/agents").mock(
        return_value=httpx.Response(200, json={"agents": []})
    )
    async with AgentiumClient(BASE, api_key="my-secret-key") as client:
        await client.list_agents()

    request = route.calls[0].request
    assert request.headers.get("X-API-Key") == "my-secret-key"
