import pytest
from unittest.mock import MagicMock, patch
from backend.api.routes.api_keys import (
    create_api_key,
    get_health_report,
    get_spend_history,
    CreateKeyRequest,
)
from backend.core.exceptions import BadRequestError


class TestApiKeysRoutes:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def current_user(self):
        return {"id": "user-1", "username": "admin", "is_admin": True}

    @pytest.mark.asyncio
    async def test_create_api_key_unknown_provider(self, mock_db, current_user):
        """Unknown provider raises BadRequestError."""
        req = CreateKeyRequest(
            provider="NON_EXISTENT_PROVIDER",
            api_key="sk-test-secret-12345",
            config_name="Test Config",
            model_name="test-model",
        )
        with pytest.raises(BadRequestError):
            await create_api_key(request=req, db=mock_db, current_user=current_user)

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, mock_db, current_user):
        """Successful key creation encrypts, saves to db, and triggers genesis check without NameError."""
        req = CreateKeyRequest(
            provider="OPENAI",
            api_key="sk-test-secret-12345",
            config_name="OpenAI Prod",
            model_name="gpt-4o",
            monthly_budget_usd=50.0,
            priority=1,
            is_default=True,
        )

        with patch("backend.core.security.encrypt_api_key", return_value="encrypted-key-bytes"), \
             patch("backend.services.initialization_service.trigger_genesis_if_needed", return_value=False):
            res = await create_api_key(request=req, db=mock_db, current_user=current_user)

            assert res.success is True
            assert res.provider == "OPENAI"
            assert res.config_name == "OpenAI Prod"
            assert res.genesis_triggered is False
            assert mock_db.add.called
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_get_spend_history_timedelta_import(self, mock_db, current_user):
        """Test get_spend_history runs without timedelta NameError."""
        mock_key = MagicMock()
        mock_key.id = "key-123"
        mock_key.provider.value = "OPENAI"
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_key

        mock_daily_entry = MagicMock()
        mock_daily_entry.date = "2026-09-29"
        mock_daily_entry.cost = 0.5
        mock_daily_entry.tokens = 1000
        mock_daily_entry.requests = 5
        mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [mock_daily_entry]

        res = await get_spend_history(
            key_id="key-123",
            days=30,
            db=mock_db,
            current_user=current_user,
        )
        assert res["key_id"] == "key-123"
        assert res["total_spend_usd"] == 0.5
        assert res["total_tokens"] == 1000
        assert res["total_requests"] == 5
