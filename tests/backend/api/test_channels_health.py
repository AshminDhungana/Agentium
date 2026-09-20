"""
Tests for GET /api/v1/channels/{id}/health endpoint - Channel Health
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.models.entities.channels import ExternalChannel, ChannelType, ChannelStatus, ChannelMetrics
from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.services.channel_manager import circuit_breaker, rate_limiter, PLATFORM_RATE_LIMITS, CircuitState
from datetime import datetime, timedelta


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_channel():
    """Create mock channel data."""
    channel = MagicMock(spec=ExternalChannel)
    channel.id = "test-channel-id"
    channel.agentium_id = "CH0001"
    channel.name = "Test WhatsApp"
    channel.channel_type = ChannelType.WHATSAPP
    channel.status = ChannelStatus.ACTIVE
    channel.config = {"provider": "cloud_api"}
    channel.messages_received = 100
    channel.messages_sent = 95
    # Use datetime objects instead of strings
    channel.last_message_at = datetime(2026, 9, 20, 10, 0, 0)
    channel.last_tested_at = datetime(2026, 9, 20, 9, 0, 0)
    return channel


@pytest.fixture
def auth_headers():
    """Return authorization headers for testing."""
    return {"Authorization": "Bearer test_token"}


def test_get_channel_health_returns_200_for_existing_channel(mock_db, mock_channel, auth_headers):
    """Test that endpoint returns HTTP 200 for existing channel"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_channel

    # Mock circuit breaker metrics
    with patch.object(circuit_breaker, 'get_metrics') as mock_cb_metrics:
        mock_cb_metrics.return_value = {
            'circuit_state': 'closed',
            'success_rate': 0.95,
            'consecutive_failures': 0,
            'total_requests': 100,
            'last_failure': None
        }

        # Mock rate limiter status
        with patch.object(rate_limiter, 'get_status') as mock_rate_status:
            mock_rate_status.return_value = {
                'requests_this_hour': 50,  # Match what API expects
                'minute_usage': 5,
                'hour_usage': 50,
                'minute_limit': 60,
                'hour_limit': 1000
            }

            # Mock message query for statistics
            # First filter: time cutoff, second filter: error_count > 0
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.count.side_effect = [5, 2]  # error_count, error_count_24h

            mock_db.query.return_value.filter.return_value = mock_query
            mock_db.query.return_value.count.return_value = 100  # total messages

            client = TestClient(app)
            response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

            # Clean up overrides
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()

            # Verify basic structure
            assert data["channel_id"] == mock_channel.id
            assert data["channel_name"] == mock_channel.name
            assert data["channel_type"] == mock_channel.channel_type.value
            assert data["status"] == mock_channel.status.value

            # Verify health section
            assert "health" in data
            health = data["health"]
            assert "circuit_breaker" in health
            assert "rate_limiting" in health
            assert "overall_status" in health
            assert health["overall_status"] in ["healthy", "degraded"]

            # Verify statistics section
            assert "statistics" in data
            stats = data["statistics"]
            assert "total_messages_received" in stats
            assert "total_messages_sent" in stats
            assert "error_count" in stats
            assert "error_count_24h" in stats
            # Verify datetime fields are properly formatted
            assert stats["last_message_at"] == "2026-09-20T10:00:00"
            assert stats["last_tested_at"] == "2026-09-20T09:00:00"

            # Verify rate_limits section
            assert "rate_limits" in data
            rate_limits = data["rate_limits"]
            assert "current_usage" in rate_limits
            assert "utilization_pct" in rate_limits
            assert "platform_limits" in rate_limits


def test_get_channel_health_healthy_status(mock_db, mock_channel, auth_headers):
    """Test that health status is healthy when circuit is closed and success rate > 0.8"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_channel

    # Mock circuit breaker metrics for healthy state
    with patch.object(circuit_breaker, 'get_metrics') as mock_cb_metrics:
        mock_cb_metrics.return_value = {
            'circuit_state': 'closed',
            'success_rate': 0.95,  # > 0.8
            'consecutive_failures': 0,
            'total_requests': 100,
            'last_failure': None
        }

        # Mock rate limiter status
        with patch.object(rate_limiter, 'get_status') as mock_rate_status:
            mock_rate_status.return_value = {
                'requests_this_hour': 50,
                'minute_usage': 5,
                'hour_usage': 50,
                'minute_limit': 60,
                'hour_limit': 1000
            }

            # Mock message query for statistics
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.count.side_effect = [0, 0]  # error_count, error_count_24h

            mock_db.query.return_value.filter.return_value = mock_query
            mock_db.query.return_value.count.return_value = 100  # total messages

            client = TestClient(app)
            response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

            # Clean up overrides
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()
            assert data["health"]["overall_status"] == "healthy"


def test_get_channel_health_degraded_status_circuit_open(mock_db, mock_channel, auth_headers):
    """Test that health status is degraded when circuit is open"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_channel

    # Mock circuit breaker metrics for open circuit
    with patch.object(circuit_breaker, 'get_metrics') as mock_cb_metrics:
        mock_cb_metrics.return_value = {
            'circuit_state': 'open',  # open circuit
            'success_rate': 0.95,
            'consecutive_failures': 5,
            'total_requests': 100,
            'last_failure': datetime(2026, 9, 20, 9, 0, 0)
        }

        # Mock rate limiter status
        with patch.object(rate_limiter, 'get_status') as mock_rate_status:
            mock_rate_status.return_value = {
                'requests_this_hour': 50,
                'minute_usage': 5,
                'hour_usage': 50,
                'minute_limit': 60,
                'hour_limit': 1000
            }

            # Mock message query for statistics
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.count.side_effect = [0, 0]  # error_count, error_count_24h

            mock_db.query.return_value.filter.return_value = mock_query
            mock_db.query.return_value.count.return_value = 100  # total messages

            client = TestClient(app)
            response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

            # Clean up overrides
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()
            assert data["health"]["overall_status"] == "degraded"


def test_get_channel_health_degraded_status_low_success_rate(mock_db, mock_channel, auth_headers):
    """Test that health status is degraded when success rate <= 0.8"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_channel

    # Mock circuit breaker metrics for low success rate
    with patch.object(circuit_breaker, 'get_metrics') as mock_cb_metrics:
        mock_cb_metrics.return_value = {
            'circuit_state': 'closed',
            'success_rate': 0.75,  # <= 0.8
            'consecutive_failures': 0,
            'total_requests': 100,
            'last_failure': None
        }

        # Mock rate limiter status
        with patch.object(rate_limiter, 'get_status') as mock_rate_status:
            mock_rate_status.return_value = {
                'requests_this_hour': 50,
                'minute_usage': 5,
                'hour_usage': 50,
                'minute_limit': 60,
                'hour_limit': 1000
            }

            # Mock message query for statistics
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.count.side_effect = [0, 0]  # error_count, error_count_24h

            mock_db.query.return_value.filter.return_value = mock_query
            mock_db.query.return_value.count.return_value = 100  # total messages

            client = TestClient(app)
            response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

            # Clean up overrides
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()
            assert data["health"]["overall_status"] == "degraded"


def test_get_channel_health_returns_404_for_nonexistent_channel(mock_db, auth_headers):
    """Test that endpoint returns HTTP 404 for non-existent channel"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return None (channel not found)
    mock_db.query.return_value.filter_by.return_value.first.return_value = None

    client = TestClient(app)
    response = client.get("/api/v1/channels/non-existent-id/health", headers=auth_headers)

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_get_channel_health_calculates_rate_limit_utilization_correctly(mock_db, mock_channel, auth_headers):
    """Test that rate limit utilization percentage is calculated correctly"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_channel

    # Mock circuit breaker metrics
    with patch.object(circuit_breaker, 'get_metrics') as mock_cb_metrics:
        mock_cb_metrics.return_value = {
            'circuit_state': 'closed',
            'success_rate': 0.95,
            'consecutive_failures': 0,
            'total_requests': 100,
            'last_failure': None
        }

        # Mock rate limiter status with known values
        with patch.object(rate_limiter, 'get_status') as mock_rate_status:
            mock_rate_status.return_value = {
                'requests_this_hour': 300,  # 300 requests in last hour
                'minute_usage': 30,
                'hour_usage': 300,
                'minute_limit': 60,
                'hour_limit': 1000
            }

            # Mock message query for statistics
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.count.side_effect = [0, 0]  # error_count, error_count_24h

            mock_db.query.return_value.filter.return_value = mock_query
            mock_db.query.return_value.count.return_value = 100  # total messages

            client = TestClient(app)
            response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

            # Clean up overrides
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()

            # Verify utilization calculation: (300 / 5000) * 100 = 6.0%
            # Note: WhatsApp platform limit is 5000 requests per hour
            assert data["rate_limits"]["utilization_pct"] == 6.0
            assert data["rate_limits"]["current_usage"]["requests_this_hour"] == 300
            assert data["rate_limits"]["platform_limits"]["requests_per_hour"] == 5000


def test_get_channel_health_includes_24_hour_error_window(mock_db, mock_channel, auth_headers):
    """Test that error_count_24h is properly calculated"""
    # Override dependencies
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_active_user] = lambda: {"id": "test-user"}

    # Set up the mock_db to return our mock_channel for channel lookup
    mock_channel_query = MagicMock()
    mock_channel_query.filter_by.return_value.first.return_value = mock_channel

    # Create a single mock query object for message statistics
    # We need to handle the chained filter calls properly
    mock_message_query = MagicMock()

    # Set up the filter_by call to return our mock query object
    mock_db.query.return_value.filter_by.return_value = mock_message_query

    # Set up the filter method to return the query object itself (for chaining)
    mock_message_query.filter.return_value = mock_message_query

    # Set up count to return different values based on call order
    # Based on the actual code in channels.py:
    # 1. error_count_24h = message_stats.filter(created_at >= cutoff_24h).filter(error_count > 0).count()
    # 2. error_count = message_stats.filter(error_count > 0).count()
    # 3. total_messages is not actually used in the response, but let's include it for completeness
    # So the order of count() calls is: error_count_24h, error_count
    mock_message_query.count.side_effect = [2, 5]  # error_count_24h, error_count

    client = TestClient(app)
    response = client.get(f"/api/v1/channels/{mock_channel.id}/health", headers=auth_headers)

    # Clean up overrides
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["statistics"]["error_count"] == 5
    assert data["statistics"]["error_count_24h"] == 2