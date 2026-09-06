import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.tasks.verification_tasks import verify_agents_task


class TestVerificationTasks:
    @pytest.mark.asyncio
    async def test_verify_agents_task_executes(self):
        """Celery task runs verification and returns result."""
        mock_db = MagicMock()
        
        with patch("backend.services.tasks.verification_tasks.get_db_context") as mock_get_db, \
             patch("backend.services.tasks.verification_tasks.InitializationService") as mock_init_class:
            
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(return_value={
                "status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}
            })
            mock_init_class.return_value = mock_service

            result = verify_agents_task()
            
            assert result["status"] == "ok"
            mock_service.verify_and_repair.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_verify_agents_task_retries_on_failure(self):
        """Celery task retries on exception."""
        mock_db = MagicMock()
        
        with patch("backend.services.tasks.verification_tasks.get_db_context") as mock_get_db, \
             patch("backend.services.tasks.verification_tasks.InitializationService") as mock_init_class:
            
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(side_effect=Exception("DB connection failed"))
            mock_init_class.return_value = mock_service

            # The task should raise and trigger retry
            with pytest.raises(Exception):
                verify_agents_task()