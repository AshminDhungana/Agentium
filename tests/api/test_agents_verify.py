import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.api.routes.agents import verify_agents
from backend.models.entities.user import User


class TestAgentsVerifyEndpoint:
    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def admin_user(self):
        user = MagicMock(spec=User)
        user.is_admin = True
        return user

    @pytest.fixture
    def non_admin_user(self):
        user = MagicMock(spec=User)
        user.is_admin = False
        return user

    @pytest.mark.asyncio
    async def test_verify_endpoint_requires_admin(self, mock_db, non_admin_user):
        """Non-admin users get 403."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_agents(db=mock_db, current_user=non_admin_user)
        
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Admin access required"

    @pytest.mark.asyncio
    async def test_verify_endpoint_returns_report(self, mock_db, admin_user):
        """Admin gets verification report."""
        with patch("backend.api.routes.agents.InitializationService") as mock_init_class:
            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(return_value={
                "status": "repaired",
                "checked": 4,
                "missing": ["10001"],
                "recreated": ["10001"],
                "warnings": [],
                "details": {
                    "00001": {"status": "ok", "existed": True},
                    "10001": {"status": "recreated", "existed": False, "new_id": "10001"},
                    "10002": {"status": "ok", "existed": True},
                    "20001": {"status": "ok", "existed": True},
                }
            })
            mock_init_class.return_value = mock_service

            result = await verify_agents(db=mock_db, current_user=admin_user)
            
            assert result["status"] == "repaired"
            assert result["recreated"] == ["10001"]
            mock_service.verify_and_repair.assert_called_once_with(mock_db)