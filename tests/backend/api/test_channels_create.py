"""
Tests for POST /api/v1/channels/ endpoint - Channel Creation
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.entities.channels import ExternalChannel, ChannelType, ChannelStatus
from backend.models.database import get_db
from backend.core.auth import get_current_active_user


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def auth_headers():
    """Return authorization headers for testing."""
    return {"Authorization": "Bearer test_token"}


def test_create_whatsapp_channel_cloud_api(mock_db, auth_headers):
    """Test creating a WhatsApp channel with cloud_api provider."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 0

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "1"
        channel.agentium_id = "CH0001"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test WhatsApp Cloud API",
            "type": "whatsapp",
            "config": {
                "provider": "cloud_api",
                "phone_number_id": "123456789",
                "access_token": "test-token"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test WhatsApp Cloud API"
    assert data["type"] == "whatsapp"
    assert data["agentium_id"] == "CH0001"
    assert data["config"]["provider"] == "cloud_api"
    assert data["config"]["phone_number_id"] == "123456789"
    # Check that the access_token is masked
    assert data["config"]["access_token"] == "********"
    # Credentials should not be exposed in response
    assert "test-token" not in str(data)
    assert data["webhook_path"] is not None
    assert data["routing"]["default_agent"] is None
    assert data["routing"]["auto_create_tasks"] == True
    assert data["routing"]["require_approval"] == False


def test_create_whatsapp_channel_web_bridge(mock_db, auth_headers):
    """Test creating a WhatsApp channel with web_bridge provider."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 1

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "2"
        channel.agentium_id = "CH0002"
        channel.webhook_path = "test-webhook-path"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    # Mock environment variables for web_bridge
    with patch.dict('os.environ', {
        'WHATSAPP_BRIDGE_URL': 'ws://whatsapp-bridge:3001',
        'WHATSAPP_BRIDGE_TOKEN': 'test-bridge-token'
    }):
        client = TestClient(app)
        response = client.post(
            "/api/v1/channels/",
            headers=auth_headers,
            json={
                "name": "Test WhatsApp Web Bridge",
                "type": "whatsapp",
                "config": {
                    "provider": "web_bridge",
                    "bridge_url": "env://whatsapp-bridge",
                    "bridge_token": "env://WHATSAPP_BRIDGE_TOKEN"
                },
                "auto_create_tasks": True,
                "require_approval": False
            }
        )

        # Clean up overrides
        app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test WhatsApp Web Bridge"
        assert data["type"] == "whatsapp"
        assert data["agentium_id"] == "CH0002"
        assert data["config"]["provider"] == "web_bridge"
        # Environment variables should be resolved
        assert data["config"]["bridge_url"] == "ws://whatsapp-bridge:3001"
        # The bridge_token should be masked in the response (not exposed)
        assert data["config"]["bridge_token"] == "********"
        # Credentials should not be exposed in response
        assert "test-bridge-token" not in str(data)
        assert data["webhook_path"] == "test-webhook-path"


def test_create_slack_channel(mock_db, auth_headers):
    """Test creating a Slack channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 2

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "3"
        channel.agentium_id = "CH0003"
        channel.webhook_path = "test-slack-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Slack",
            "type": "slack",
            "config": {
                "bot_token": "xoxb-test-token"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Slack"
    assert data["type"] == "slack"
    assert data["agentium_id"] == "CH0003"
    assert data["config"]["bot_token"] == "********"
    # Credentials should not be exposed in response
    assert "xoxb-test-token" not in str(data)


def test_create_telegram_channel(mock_db, auth_headers):
    """Test creating a Telegram channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 3

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "4"
        channel.agentium_id = "CH0004"
        channel.webhook_path = "test-telegram-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Telegram",
            "type": "telegram",
            "config": {
                "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Telegram"
    assert data["type"] == "telegram"
    assert data["agentium_id"] == "CH0004"
    assert data["config"]["bot_token"] == "********"
    # Credentials should not be exposed in response
    assert "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11" not in str(data)


def test_create_email_channel(mock_db, auth_headers):
    """Test creating an Email channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 4

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "5"
        channel.agentium_id = "CH0005"
        channel.webhook_path = "test-email-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Email",
            "type": "email",
            "config": {
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "test@gmail.com",
                "smtp_pass": "test-password",
                "from_email": "test@gmail.com",
                "enable_imap": True,
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "imap_user": "test@gmail.com",
                "imap_pass": "test-password"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Email"
    assert data["type"] == "email"
    assert data["agentium_id"] == "CH0005"
    assert data["config"]["smtp_host"] == "smtp.gmail.com"
    assert data["config"]["smtp_port"] == 587
    assert data["config"]["smtp_user"] == "test@gmail.com"
    assert data["config"]["from_email"] == "test@gmail.com"
    assert data["config"]["enable_imap"] == True
    assert data["config"]["imap_host"] == "imap.gmail.com"
    assert data["config"]["imap_port"] == 993
    assert data["config"]["imap_user"] == "test@gmail.com"
    # Check that passwords are masked
    assert data["config"]["smtp_pass"] == "********"
    assert data["config"]["imap_pass"] == "********"
    # Credentials should not be exposed in response
    assert "test-password" not in str(data)
    assert data["webhook_path"] == "test-email-webhook"


def test_create_invalid_channel_type(mock_db, auth_headers):
    """Test creating a channel with invalid type returns 400."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Invalid Channel",
            "type": "invalid_type",
            "config": {},
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")

    assert response.status_code == 400
    error_data = response.json()
    assert "Invalid channel type" in error_data["error"]


def test_create_channel_without_auth(mock_db):
    """Test that creating a channel without authentication returns 401/403."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    # Do not override get_current_active_user, so it will use the real one which will fail due to missing token

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        json={
            "name": "Test Unauthorized Channel",
            "type": "whatsapp",
            "config": {
                "provider": "cloud_api",
                "phone_number_id": "123456789",
                "access_token": "test-token"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    # This should return 401 or 403 for unauthorized access
    assert response.status_code in [401, 403]


def test_create_channel_duplicate_webhook_path(mock_db, auth_headers):
    """Test that duplicate webhook paths are handled correctly."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 5

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "6"
        channel.agentium_id = "CH0006"
        channel.webhook_path = "duplicate-path"

    def mock_commit():
        # Simulate integrity error on commit for duplicate webhook_path
        raise Exception("Duplicate webhook path")

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Duplicate Webhook",
            "type": "whatsapp",
            "config": {
                "provider": "cloud_api",
                "phone_number_id": "123456789",
                "access_token": "test-token"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    # Print response for debugging
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")

    # The endpoint should catch the exception and return an error response
    # Based on the implementation, it returns a 500 for unexpected errors
    assert response.status_code == 500
    # Check that some error message is returned
    assert response.json() is not None


def test_create_discord_channel(mock_db, auth_headers):
    """Test creating a Discord channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 6

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "7"
        channel.agentium_id = "CH0007"
        channel.webhook_path = "test-discord-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Discord",
            "type": "discord",
            "config": {
                "bot_token": "MTAxOTUyNzQzNDIyMDIyNTc0.CaGfQw._XYZabc123"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Discord"
    assert data["type"] == "discord"
    assert data["agentium_id"] == "CH0007"
    assert data["config"]["bot_token"] == "********"
    # Credentials should not be exposed in response
    assert "MTAxOTUyNzQzNDIyMDIyNTc0.CaGfQw._XYZabc123" not in str(data)
    assert data["webhook_path"] == "test-discord-webhook"


def test_create_signal_channel(mock_db, auth_headers):
    """Test creating a Signal channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 7

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "8"
        channel.agentium_id = "CH0008"
        channel.webhook_path = "test-signal-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Signal",
            "type": "signal",
            "config": {
                "number": "+1234567890"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Signal"
    assert data["type"] == "signal"
    assert data["agentium_id"] == "CH0008"
    # Signal uses 'number' which is not considered sensitive, so it should not be masked
    assert data["config"]["number"] == "+1234567890"
    assert data["webhook_path"] == "test-signal-webhook"


def test_create_google_chat_channel(mock_db, auth_headers):
    """Test creating a Google Chat channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 8

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "9"
        channel.agentium_id = "CH0009"
        channel.webhook_path = "test-webhook-path"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Google Chat",
            "type": "google_chat",
            "config": {
                "webhook_url": "https://chat.googleapis.com/v1/spaces/AAAAxxxxxx/messages"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Google Chat"
    assert data["type"] == "google_chat"
    assert data["agentium_id"] == "CH0009"
    # Webhook URL is generated by the system, not taken from input
    assert data["webhook_url"] is not None
    assert data["webhook_url"].startswith("https://your-domain.com/webhooks/google_chat/")
    assert data["webhook_path"] == "test-webhook-path"


def test_create_teams_channel(mock_db, auth_headers):
    """Test creating a Teams channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 9

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "10"
        channel.agentium_id = "CH0010"
        channel.webhook_path = "test-webhook-path"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Teams",
            "type": "teams",
            "config": {
                "webhook_url": "https://outlook.office.com/webhook/xxxxxx/IncomingWebhook/yyyyyy/zzzzzz"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Teams"
    assert data["type"] == "teams"
    assert data["agentium_id"] == "CH0010"
    # Webhook URL is generated by the system, not taken from input
    assert data["webhook_url"] is not None
    assert data["webhook_url"].startswith("https://your-domain.com/webhooks/teams/")
    assert data["webhook_path"] == "test-webhook-path"


def test_create_zalo_channel(mock_db, auth_headers):
    """Test creating a Zalo channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 10

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "11"
        channel.agentium_id = "CH0011"
        channel.webhook_path = "test-zalo-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Zalo",
            "type": "zalo",
            "config": {
                "access_token": "zalo_access_token_12345"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Zalo"
    assert data["type"] == "zalo"
    assert data["agentium_id"] == "CH0011"
    # Check that the access_token is masked
    assert data["config"]["access_token"] == "********"
    # Credentials should not be exposed in response
    assert "zalo_access_token_12345" not in str(data)
    assert data["webhook_path"] == "test-zalo-webhook"


def test_create_matrix_channel(mock_db, auth_headers):
    """Test creating a Matrix channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 11

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "12"
        channel.agentium_id = "CH0012"
        channel.webhook_path = "test-matrix-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Matrix",
            "type": "matrix",
            "config": {
                "homeserver_url": "https://matrix.org",
                "access_token": "matrix_access_token_12345"
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Matrix"
    assert data["type"] == "matrix"
    assert data["agentium_id"] == "CH0012"
    assert data["config"]["homeserver_url"] == "https://matrix.org"
    # Check that the access_token is masked
    assert data["config"]["access_token"] == "********"
    # Credentials should not be exposed in response
    assert "matrix_access_token_12345" not in str(data)
    assert data["webhook_path"] == "test-matrix-webhook"


def test_create_imessage_channel(mock_db, auth_headers):
    """Test creating an iMessage channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 12

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "13"
        channel.agentium_id = "CH0013"
        channel.webhook_path = "test-imessage-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test iMessage",
            "type": "imessage",
            "config": {},
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test iMessage"
    assert data["type"] == "imessage"
    assert data["agentium_id"] == "CH0013"
    # iMessage has no sensitive config by default
    assert data["webhook_path"] == "test-imessage-webhook"


def test_create_custom_channel(mock_db, auth_headers):
    """Test creating a Custom channel."""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Mock the database query for agentium_id generation
    mock_db.query.return_value.count.return_value = 13

    # Mock the database add/commit/refresh cycle
    def mock_add(channel):
        channel.id = "14"
        channel.agentium_id = "CH0014"
        channel.webhook_path = "test-custom-webhook"

    def mock_commit():
        pass

    def mock_refresh(channel):
        pass

    mock_db.add.side_effect = mock_add
    mock_db.commit.side_effect = mock_commit
    mock_db.refresh.side_effect = mock_refresh

    client = TestClient(app)
    response = client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Test Custom",
            "type": "custom",
            "config": {
                "custom_field": "custom_value",
                "another_field": 123
            },
            "auto_create_tasks": True,
            "require_approval": False
        }
    )

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Custom"
    assert data["type"] == "custom"
    assert data["agentium_id"] == "CH0014"
    assert data["config"]["custom_field"] == "custom_value"
    assert data["config"]["another_field"] == 123
    assert data["webhook_path"] == "test-custom-webhook"


if __name__ == "__main__":
    pytest.main([__file__])