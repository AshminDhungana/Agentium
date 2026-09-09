"""Integration tests for POST /tool-management/from-natural-language endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.auth import create_access_token

client = TestClient(app)


@pytest.fixture
def head_auth_headers():
    """Create JWT for Head-tier agent (0xxxx)"""
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


@pytest.fixture
def council_auth_headers():
    """Create JWT for Council-tier agent (1xxxx)"""
    token = create_access_token({
        "sub": "10001",
        "user_id": 2,
        "role": "council_member",
        "is_admin": False,
        "is_active": True,
        "tier": "1xxxx",
        "agentium_id": "10001",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def task_auth_headers():
    """Create JWT for Task-tier agent (3xxxx)"""
    token = create_access_token({
        "sub": "30001",
        "user_id": 3,
        "role": "task_agent",
        "is_admin": False,
        "is_active": True,
        "tier": "3xxxx",
        "agentium_id": "30001",
    })
    return {"Authorization": f"Bearer {token}"}


def test_from_natural_language_head_activates(head_auth_headers):
    with patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language = AsyncMock(return_value={
            "proposed": True,
            "tool_name": "extract_emails",
            "status": "activated",
            "activated": True,
            "version": "v1.0.0",
            "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]
        })
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/api/v1/tool-management/from-natural-language",
            json={
                "description": "Extract emails from a webpage",
                "authorized_tiers": ["0xxxx", "1xxxx", "2xxxx"]
            },
            headers=head_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["proposed"] is True
        assert data["tool_name"] == "extract_emails"
        assert data["status"] == "activated"


def test_from_natural_language_council_requires_vote(council_auth_headers):
    with patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language = AsyncMock(return_value={
            "proposed": True,
            "tool_name": "council_tool",
            "status": "pending_vote",
            "voting_id": "vote-123",
            "requires_council_approval": True,
            "council_members": ["10001", "10002"]
        })
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/api/v1/tool-management/from-natural-language",
            json={"description": "Council tool description"},
            headers=council_auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_vote"
        assert data["requires_council_approval"] is True


def test_from_natural_language_blocks_task_agent(task_auth_headers):
    response = client.post(
        "/api/v1/tool-management/from-natural-language",
        json={"description": "Task agent tool"},
        headers=task_auth_headers
    )
    
    assert response.status_code == 403
    # Check response text since JSON might be None
    assert "Task agents" in response.text and "cannot" in response.text


def test_from_natural_language_validation_error(head_auth_headers):
    with patch("backend.api.routes.tool_creation.ToolCreationService") as mock_service_class:
        
        mock_service = MagicMock()
        mock_service.create_from_natural_language = AsyncMock(return_value={
            "proposed": False,
            "error": "Generated code failed validation: Dangerous construct: eval()"
        })
        mock_service_class.return_value = mock_service
        
        response = client.post(
            "/api/v1/tool-management/from-natural-language",
            json={"description": "Run eval on input"},
            headers=head_auth_headers
        )
        
        assert response.status_code == 400
        # Check response text since JSON might be None
        assert "eval" in response.text