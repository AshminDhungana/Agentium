"""Tests for generate_auto_tools Celery task."""
import pytest
from unittest.mock import MagicMock, patch
from backend.services.tasks.task_executor import generate_auto_tools


def test_generate_auto_tools_calls_self_improvement_service():
    with patch("backend.celery_app.BeatSessionLocal") as mock_session_class, \
         patch("backend.services.self_improvement_service.self_improvement_service") as mock_service:
        
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        mock_service.generate_auto_tools.return_value = {"tools_generated": 2, "patterns_analyzed": 50}
        
        result = generate_auto_tools()
        
        assert result == {"tools_generated": 2, "patterns_analyzed": 50}
        mock_service.generate_auto_tools.assert_called_once_with(mock_db)
        mock_db.close.assert_called_once()


def test_generate_auto_tools_handles_exception():
    with patch("backend.celery_app.BeatSessionLocal") as mock_session_class, \
         patch("backend.services.self_improvement_service.self_improvement_service") as mock_service:
        
        mock_db = MagicMock()
        mock_session_class.return_value = mock_db
        mock_service.generate_auto_tools.side_effect = Exception("DB error")
        
        # Task should handle exception gracefully and return error dict
        result = generate_auto_tools()
        
        assert "error" in result
        mock_db.close.assert_called_once()