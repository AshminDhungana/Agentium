"""
Unit tests for check_health() function.
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text
from backend.models.database import check_health


def test_check_health_success():
    """check_health returns healthy with valid latency."""
    with patch('backend.models.database.engine') as mock_engine:
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        result = check_health()

        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], (int, float))
        assert result["latency_ms"] >= 0
        assert result["database"] == "connected"
        # Check execute was called with a TextClause containing "SELECT 1"
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0][0]
        assert hasattr(call_args, 'text'), "Expected TextClause argument"
        assert "SELECT 1" in call_args.text


def test_check_health_failure():
    """check_health returns unhealthy on exception."""
    with patch('backend.models.database.engine') as mock_engine:
        mock_engine.connect.side_effect = Exception("Connection refused")

        result = check_health()

        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection refused" in result["error"]
        assert result["database"] == "disconnected"