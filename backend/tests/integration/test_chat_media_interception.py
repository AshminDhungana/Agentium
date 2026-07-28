"""
Integration tests for System-Generated Media Interception in ChatService.
Tests the full pipeline: LLM response -> MediaInterceptor -> Storage -> Broadcast.
"""

import asyncio
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO
from datetime import datetime
from typing import Dict, Any

from backend.services import chat_service as cs
from backend.models.entities.agents import HeadOfCouncil
from backend.models.entities.user import User
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus
from backend.models.entities.chat_message import ChatMessage
from backend.models.database import SessionLocal
from backend.services.model_provider import ModelService, OpenAICompatibleProvider
import httpx


def _find_head_message_with_media(db, user_id: str, expected_media_url: str) -> bool:
    """Query the database directly using a fresh session to find the persisted head message with media URL."""
    msg = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id,
        ChatMessage.role == "head_of_council",
        ChatMessage.content.like(f"%{expected_media_url}%")
    ).first()
    return msg is not None


def _find_head_message_with_metadata_media(db, user_id: str, expected_media_url: str) -> bool:
    """Query the database directly using a fresh session to find the persisted head message with media_urls in metadata."""
    msgs = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id,
        ChatMessage.role == "head_of_council"
    ).all()
    for m in msgs:
        if m.message_metadata and "media_urls" in (m.message_metadata or {}):
            if any(expected_media_url in url for url in m.message_metadata["media_urls"]):
                return True
    return False


class MockProvider(OpenAICompatibleProvider):
    """Mock provider that doesn't make real API calls."""

    def __init__(self):
        # Don't call super().__init__ to avoid needing a real config
        self.config = MagicMock()
        self.config.provider = ProviderType.OPENAI_COMPATIBLE
        self.config.default_model = "test-model"
        self.config.max_tokens = 4000
        self.config.temperature = 0.7
        self.config.top_p = 1.0
        self.config.timeout_seconds = 60
        self.api_key = "test-key"
        self.base_url = "http://test-url"

    async def generate(self, system_prompt: str, user_message: str, **kwargs) -> Dict[str, Any]:
        return {
            "content": "Mock response",
            "model": "test-model",
            "tokens_used": 10,
            "prompt_tokens": 5,
            "completion_tokens": 5,
            "latency_ms": 10,
            "cost_usd": 0.0,
            "finish_reason": "stop",
        }

    async def generate_with_tools(self, *args, **kwargs) -> Dict[str, Any]:
        # This will be overridden by the test's mock
        return await self.generate("", "")


class TestChatServiceMediaInterception:
    """Integration tests for media interception in chat flow."""

    @pytest.fixture(autouse=True)
    def mock_model_provider(self, monkeypatch):
        """Mock ModelService.get_provider to return a mock provider."""
        mock_provider = MockProvider()
        monkeypatch.setattr(ModelService, "get_provider", AsyncMock(return_value=mock_provider))
        yield

    @pytest.fixture(autouse=True)
    def mock_llm_client(self, monkeypatch):
        """Mock LLMClient to return controlled responses."""
        # Each test will override the return value as needed
        mock_llm = AsyncMock()
        monkeypatch.setattr(cs, "LLMClient", MagicMock(return_value=mock_llm))
        yield mock_llm

    @pytest.fixture(autouse=True)
    def patch_httpx_for_background(self):
        """Patch httpx.AsyncClient at the module level so it persists across the background task."""
        # Create a shared mock client that persists beyond the test function scope
        from unittest.mock import AsyncMock, MagicMock

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"fake-png-data"
        mock_response.headers = {"content-type": "image/png"}
        mock_client.get = AsyncMock(return_value=mock_response)

        # We'll patch at the service module level where it's actually imported
        with patch("backend.services.chat_service.httpx.AsyncClient", MagicMock(return_value=mock_client)) as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client
            yield mock_client

    @pytest.fixture(autouse=True)
    def mock_storage_service(self, monkeypatch):
        """Mock storage_service.upload_file to return test URLs."""
        from backend.services import storage_service
        storage_service.upload_file = MagicMock(return_value="https://s3.bucket/files/user/test.png")
        yield storage_service

    @pytest.mark.asyncio
    async def test_markdown_image_intercepted_and_stored(self, seeded_db, mock_llm_client, mock_storage_service, patch_httpx_for_background):
        """LLM response with ![alt](url) gets URL replaced with storage URL."""
        # Setup: Create Head agent and admin user
        head = HeadOfCouncil(
            agentium_id="MEDIAH01",
            name="Test Head 1",
            is_active=True
        )
        seeded_db.add(head)

        admin = User(
            id="user-admin-media-1",
            username="admin_media_1",
            email="admin_media_1@agentium.test",
            hashed_password="fake-hash-for-test",
            is_admin=True,
            is_active=True,
        )
        seeded_db.add(admin)
        seeded_db.commit()

        model = UserModelConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            config_name="test-config",
            default_model="test-model",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
            api_base_url="http://test-url",
        )
        seeded_db.add(model)
        seeded_db.flush()

        head.preferred_config_id = str(model.id)
        seeded_db.flush()
        seeded_db.commit()

        mock_llm_result = {
            "content": "Here is your chart: ![Sales Chart](https://charts.example.com/sales.png)",
            "model": "test-model",
            "tokens_used": 50
        }
        mock_llm_client.generate_with_tools = AsyncMock(return_value=mock_llm_result)

        storage_url = "https://s3.bucket/files/user-admin-media-1/abc123.png"
        mock_storage_service.upload_file = MagicMock(return_value=storage_url)

        # The httpx mock is already patched at module level via patch_httpx_for_background

        result = await cs.ChatService.process_message(head, "Show me sales", seeded_db)

        # Immediate response should still have original URL (background task rewrites later)
        assert "https://charts.example.com/sales.png" in result["content"]
        assert storage_url not in result["content"]

        # Wait for background task to complete
        await asyncio.sleep(0.5)

        # Query using a fresh database session (background task uses its own SessionLocal)
        db = SessionLocal()
        try:
            found = _find_head_message_with_media(db, "user-admin-media-1", storage_url)
            assert found, f"Expected media URL {storage_url} not found in head_of_council messages"

            # Also verify the original URL was replaced
            msgs = db.query(ChatMessage).filter_by(
                user_id="user-admin-media-1", role="head_of_council"
            ).all()
            assert any(storage_url in m.content for m in msgs), "Storage URL not in message content"
            assert any("https://charts.example.com/sales.png" not in m.content for m in msgs), "Original URL still in message"
            assert any("![Sales Chart]" in m.content for m in msgs), "Alt text not preserved"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_raw_image_url_intercepted_and_stored(self, seeded_db, mock_llm_client, mock_storage_service, patch_httpx_for_background):
        """Bare https://.../image.jpg URL gets replaced."""
        head = HeadOfCouncil(agentium_id="MEDIAH02", name="Test Head 2", is_active=True)
        seeded_db.add(head)

        admin = User(
            id="user-admin-media-2",
            username="admin_media_2",
            email="admin_media_2@agentium.test",
            hashed_password="fake-hash-for-test",
            is_admin=True,
            is_active=True,
        )
        seeded_db.add(admin)
        seeded_db.commit()

        model = UserModelConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            config_name="test-config-2",
            default_model="test-model",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
            api_base_url="http://test-url",
        )
        seeded_db.add(model)
        seeded_db.flush()

        head.preferred_config_id = str(model.id)
        seeded_db.flush()
        seeded_db.commit()

        mock_llm_result = {
            "content": "See this photo: https://cdn.example.com/photo.jpg",
            "model": "test-model",
            "tokens_used": 30
        }
        mock_llm_client.generate_with_tools = AsyncMock(return_value=mock_llm_result)

        storage_url = "https://s3.bucket/files/user-admin-media-2/xyz789.jpg"
        mock_storage_service.upload_file = MagicMock(return_value=storage_url)

        # httpx is already patched via patch_httpx_for_background fixture

        result = await cs.ChatService.process_message(head, "Show photo", seeded_db)

        assert "https://cdn.example.com/photo.jpg" in result["content"]
        assert storage_url not in result["content"]

        # Wait for background task to complete
        await asyncio.sleep(0.5)

        # Query using a fresh database session (background task uses its own SessionLocal)
        db = SessionLocal()
        try:
            found = _find_head_message_with_media(db, "user-admin-media-2", storage_url)
            assert found, f"Expected media URL {storage_url} not found in head_of_council messages"

            msgs = db.query(ChatMessage).filter_by(
                user_id="user-admin-media-2", role="head_of_council"
            ).all()
            assert any(storage_url in m.content for m in msgs), "Storage URL not in message content"
            assert any("https://cdn.example.com/photo.jpg" not in m.content for m in msgs), "Original URL still in message"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_non_media_text_passthrough(self, seeded_db, mock_llm_client, mock_storage_service):
        """Text without media URLs passes through unchanged."""
        head = HeadOfCouncil(agentium_id="MEDIAH03", name="Test Head 3", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-media-3", username="admin_media_3", email="admin_media_3@agentium.test", hashed_password="fake-hash-for-test", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        model = UserModelConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            config_name="test-config-3",
            default_model="test-model",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
            api_base_url="http://test-url",
        )
        seeded_db.add(model)
        seeded_db.flush()

        head.preferred_config_id = str(model.id)
        seeded_db.commit()

        mock_llm_result = {
            "content": "Hello! This is just plain text with no images.",
            "model": "test-model",
            "tokens_used": 20
        }
        mock_llm_client.generate_with_tools = AsyncMock(return_value=mock_llm_result)

        mock_storage_service.upload_file = MagicMock()

        result = await cs.ChatService.process_message(head, "Hi", seeded_db)

        assert result["content"] == "Hello! This is just plain text with no images."
        mock_storage_service.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_download_graceful_fallback(self, seeded_db, mock_llm_client, mock_storage_service, patch_httpx_for_background):
        """Failed media download preserves original URL, doesn't crash."""
        head = HeadOfCouncil(agentium_id="MEDIAH04", name="Test Head 4", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-media-4", username="admin_media_4", email="admin_media_4@agentium.test", hashed_password="fake-hash-for-test", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        model = UserModelConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            config_name="test-config-4",
            default_model="test-model",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
            api_base_url="http://test-url",
        )
        seeded_db.add(model)
        seeded_db.flush()

        head.preferred_config_id = str(model.id)
        seeded_db.commit()

        mock_llm_result = {
            "content": "![Broken](https://gone.example.com/missing.png)",
            "model": "test-model",
            "tokens_used": 15
        }
        mock_llm_client.generate_with_tools = AsyncMock(return_value=mock_llm_result)

        # Override the patched httpx mock to return 404
        patch_httpx_for_background.get.return_value.status_code = 404

        result = await cs.ChatService.process_message(head, "Show broken", seeded_db)

        assert result["content"] == "![Broken](https://gone.example.com/missing.png)"
        mock_storage_service.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_media_urls_persisted_in_chat_message_metadata(self, seeded_db, mock_llm_client, mock_storage_service, patch_httpx_for_background):
        """New storage URLs stored in ChatMessage metadata.media_urls."""
        head = HeadOfCouncil(agentium_id="MEDIAH05", name="Test Head 5", is_active=True)
        seeded_db.add(head)

        admin = User(
            id="user-admin-media-5",
            username="admin_media_5",
            email="admin_media_5@agentium.test",
            hashed_password="fake-hash-for-test",
            is_admin=True,
            is_active=True,
        )
        seeded_db.add(admin)
        seeded_db.commit()

        model = UserModelConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            config_name="test-config-5",
            default_model="test-model",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
            api_base_url="http://test-url",
        )
        seeded_db.add(model)
        seeded_db.flush()

        head.preferred_config_id = str(model.id)
        seeded_db.commit()

        mock_llm_result = {
            "content": "![Chart](https://charts.example.com/chart.png)",
            "model": "test-model",
            "tokens_used": 40
        }
        mock_llm_client.generate_with_tools = AsyncMock(return_value=mock_llm_result)

        storage_url = "https://s3.bucket/files/user-admin-media-5/chart.png"
        mock_storage_service.upload_file = MagicMock(return_value=storage_url)

        # httpx is already patched via patch_httpx_for_background fixture

        result = await cs.ChatService.process_message(head, "Chart please", seeded_db)

        # Drive the background media interception + Head-turn persistence
        await asyncio.sleep(0.5)

        # Verify ChatMessage was created with media_urls in metadata using a fresh session
        db = SessionLocal()
        try:
            found = _find_head_message_with_metadata_media(db, "user-admin-media-5", storage_url)
            assert found, "Expected media URL not found in ChatMessage metadata.media_urls"
        finally:
            db.close()