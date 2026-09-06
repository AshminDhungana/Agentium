import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.main import lifespan
from backend.services.tasks.verification_tasks import verify_agents_task
from backend.api.routes.agents import verify_agents
from fastapi import FastAPI
from backend.models.entities.user import User


def _make_mock_db():
    """Create a mock DB with all genesis agents present."""
    mock_db = MagicMock()
    
    head = MagicMock()
    head.agentium_id = "00001"
    head.is_active = True
    head.id = 1

    council1 = MagicMock()
    council1.agentium_id = "10001"
    council1.is_active = True

    council2 = MagicMock()
    council2.agentium_id = "10002"
    council2.is_active = True

    lead = MagicMock()
    lead.agentium_id = "20001"
    lead.is_active = True

    mock_db.query.return_value.filter_by.return_value.first.side_effect = [
        head, council1, council2, lead
    ]
    return mock_db


def _make_init_service_mock():
    """Create a mock InitializationService that returns ok status."""
    mock_service = AsyncMock()
    mock_service.verify_and_repair = AsyncMock(return_value={
        "status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}
    })
    return mock_service


class TestAgentVerificationFlow:
    """End-to-end test of agent verification across all triggers."""

    @pytest.mark.asyncio
    async def test_lifespan_verification(self):
        """Test lifespan calls verify_and_repair."""
        mock_db = _make_mock_db()
        mock_init_service = _make_init_service_mock()
        
        # Use patch.start/stop to avoid too many nested blocks
        patches = [
            patch("backend.models.database.get_db_context"),
            patch("backend.main.init_db"),
            patch("backend.main.create_default_admin"),
            patch("backend.services.pricing_sync_service.PricingSyncService.load_cache_from_db"),
            patch("backend.services.pricing_sync_service.PricingSyncService.sync_prices"),
            patch("backend.services.initialization_service.InitializationService.create_default_constitution"),
            patch("backend.core.security_checks.run_security_startup_checks"),
            patch("backend.tools._workspace.validate_workspace_config", return_value=True),
            patch("backend.tools._workspace.workspace_enabled", return_value=False),
            patch("backend.main.persistent_council.get_persistent_agents", return_value={}),
            patch("backend.main.MonitoringService.start_background_monitors"),
            patch("backend.main.DatabaseMaintenanceService.start_maintenance_monitors"),
            patch("backend.main.idle_governance.start"),
            patch("backend.main.init_api_manager"),
            patch("backend.main.init_model_allocator"),
            patch("backend.main.init_token_optimizer"),
            patch("backend.main.init_api_key_manager"),
            patch("backend.main.init_bridge"),
            patch("backend.main.tool_registry"),
            patch("backend.services.initialization_service.InitializationService", return_value=mock_init_service),
        ]
        
        mocks = [p.start() for p in patches]
        try:
            mock_get_db = mocks[0]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            app = FastAPI()
            async with lifespan(app):
                pass
            
            mock_init_service.verify_and_repair.assert_called_once_with(mock_db)
        finally:
            for p in patches:
                p.stop()

    @pytest.mark.asyncio
    async def test_api_verification(self):
        """Test API endpoint calls verify_and_repair."""
        mock_db = _make_mock_db()
        mock_init_service = _make_init_service_mock()
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        
        with patch("backend.api.routes.agents.InitializationService", return_value=mock_init_service):
            result = await verify_agents(db=mock_db, current_user=admin_user)
            assert result["status"] == "ok"
            mock_init_service.verify_and_repair.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_celery_task_verification(self):
        """Test Celery task calls verify_and_repair."""
        mock_db = _make_mock_db()
        mock_init_service = _make_init_service_mock()
        
        with patch("backend.services.tasks.verification_tasks.get_db_context") as mock_get_db, \
             patch("backend.services.tasks.verification_tasks.InitializationService", return_value=mock_init_service):
            
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            result = verify_agents_task()
            assert result["status"] == "ok"
            mock_init_service.verify_and_repair.assert_called_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_all_three_consistency(self):
        """Test all three triggers return consistent results."""
        mock_db = _make_mock_db()
        mock_init_service = _make_init_service_mock()
        
        # Use patch.start/stop for the many lifespan patches
        lifespan_patches = [
            patch("backend.models.database.get_db_context"),
            patch("backend.main.init_db"),
            patch("backend.main.create_default_admin"),
            patch("backend.services.pricing_sync_service.PricingSyncService.load_cache_from_db"),
            patch("backend.services.pricing_sync_service.PricingSyncService.sync_prices"),
            patch("backend.services.initialization_service.InitializationService.create_default_constitution"),
            patch("backend.core.security_checks.run_security_startup_checks"),
            patch("backend.tools._workspace.validate_workspace_config", return_value=True),
            patch("backend.tools._workspace.workspace_enabled", return_value=False),
            patch("backend.main.persistent_council.get_persistent_agents", return_value={}),
            patch("backend.main.MonitoringService.start_background_monitors"),
            patch("backend.main.DatabaseMaintenanceService.start_maintenance_monitors"),
            patch("backend.main.idle_governance.start"),
            patch("backend.main.init_api_manager"),
            patch("backend.main.init_model_allocator"),
            patch("backend.main.init_token_optimizer"),
            patch("backend.main.init_api_key_manager"),
            patch("backend.main.init_bridge"),
            patch("backend.main.tool_registry"),
            patch("backend.services.initialization_service.InitializationService", return_value=mock_init_service),
        ]
        
        mocks = [p.start() for p in lifespan_patches]
        try:
            mock_get_db = mocks[0]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            app = FastAPI()
            
            # 1. Lifespan
            async with lifespan(app):
                pass
            
            # 2. API
            admin_user = MagicMock(spec=User)
            admin_user.is_admin = True
            with patch("backend.api.routes.agents.InitializationService", return_value=mock_init_service):
                result1 = await verify_agents(db=mock_db, current_user=admin_user)
            
            # 3. Celery task
            with patch("backend.services.tasks.verification_tasks.get_db_context") as mock_get_db, \
                 patch("backend.services.tasks.verification_tasks.InitializationService", return_value=mock_init_service):
                
                mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
                result2 = verify_agents_task()
            
            # All should return consistent "ok" status
            assert result1["status"] == "ok"
            assert result2["status"] == "ok"
            assert mock_init_service.verify_and_repair.call_count == 3
        finally:
            for p in lifespan_patches:
                p.stop()