import pytest
from unittest.mock import AsyncMock, patch, MagicMock, MagicMock as Mock
from backend.main import lifespan
from fastapi import FastAPI


class TestLifespanVerification:
    @pytest.mark.asyncio
    async def test_lifespan_calls_verify_and_repair(self):
        """Lifespan should call verify_and_repair after init_db."""
        mock_db = MagicMock()
        app = FastAPI()
        
        # Use a single patch context with multiple targets
        patches = [
            patch("backend.models.database.get_db_context"),
            patch("backend.main.init_db"),
            patch("backend.services.initialization_service.InitializationService"),
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
        ]
        
        mocks = [p.start() for p in patches]
        try:
            mock_get_db, mock_init_db, mock_init_class, mock_create_admin, \
            mock_load_cache, mock_sync_prices, mock_create_constitution, \
            mock_security, mock_validate_ws, mock_ws_enabled, \
            mock_get_persistent, mock_start_monitors, mock_start_maint, \
            mock_idle_start, mock_init_api_mgr, mock_init_model_alloc, \
            mock_init_token_opt, mock_init_api_key, mock_init_bridge, mock_tool_reg = mocks
            
            mock_get_db.return_value.__enter__ = Mock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = Mock(return_value=None)
            
            mock_init_service = AsyncMock()
            mock_init_service.verify_and_repair = AsyncMock(return_value={
                "status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}
            })
            mock_init_class.return_value = mock_init_service

            # Run lifespan directly
            async with lifespan(app):
                pass

            mock_init_service.verify_and_repair.assert_called_once_with(mock_db)
        finally:
            for p in patches:
                p.stop()