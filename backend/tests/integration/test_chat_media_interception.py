"""
Integration tests for System-Generated Media Interception in ChatService.
Tests the full pipeline: LLM response -> MediaInterceptor -> Storage -> Broadcast.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

from backend.services.chat_service import ChatService
from backend.models.entities.agents import HeadOfCouncil
from backend.models.entities.user import User


class TestChatServiceMediaInterception:
    """Integration tests for media interception in chat flow."""

    @pytest.mark.asyncio
    async def test_markdown_image_intercepted_and_stored(self, seeded_db, monkeypatch):
        """LLM response with ![alt](url) gets URL replaced with storage URL."""
        # Setup: Create Head agent and admin user
        head = HeadOfCouncil(
            agentium_id="HEAD00001",
            name="Test Head",
            is_active=True
        )
        seeded_db.add(head)

        admin = User(
            id="user-admin-123",
            username="admin",
            is_admin=True,
            is_active=True
        )
        seeded_db.add(admin)
        seeded_db.commit()

        # Mock LLM response with markdown image
        mock_llm_result = {
            "content": "Here is your chart: ![Sales Chart](https://charts.example.com/sales.png)",
            "model": "test-model",
            "tokens_used": 50
        }

        # Mock LLMClient.generate_with_tools
        with patch("backend.services.chat_service.LLMClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm.generate_with_tools = AsyncMock(return_value=mock_llm_result)
            mock_llm_class.return_value = mock_llm

            # Mock StorageService.upload_file to return fake S3 URL
            from backend.services.storage_service import storage_service
            storage_service.upload_file = MagicMock(
                return_value="https://s3.bucket/files/user-admin-123/abc123.png"
            )

            # Mock httpx download
            with patch("backend.services.media_interceptor.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.content = b"fake-png-data"
                mock_response.headers = {"content-type": "image/png"}
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Execute
                result = await ChatService.process_message(head, "Show me sales", seeded_db)

        # Verify: content rewritten with storage URL
        assert "https://s3.bucket/files/user-admin-123/abc123.png" in result["content"]
        assert "https://charts.example.com/sales.png" not in result["content"]
        assert "![Sales Chart]" in result["content"]  # alt text preserved

    @pytest.mark.asyncio
    async def test_raw_image_url_intercepted_and_stored(self, seeded_db, monkeypatch):
        """Bare https://.../image.jpg URL gets replaced."""
        head = HeadOfCouncil(agentium_id="HEAD00001", name="Test", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-123", username="admin", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        mock_llm_result = {
            "content": "See this photo: https://cdn.example.com/photo.jpg",
            "model": "test-model",
            "tokens_used": 30
        }

        with patch("backend.services.chat_service.LLMClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm.generate_with_tools = AsyncMock(return_value=mock_llm_result)
            mock_llm_class.return_value = mock_llm

            from backend.services.storage_service import storage_service
            storage_service.upload_file = MagicMock(
                return_value="https://s3.bucket/files/user-admin-123/xyz789.jpg"
            )

            with patch("backend.services.media_interceptor.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.content = b"jpg-data"
                mock_response.headers = {"content-type": "image/jpeg"}
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                result = await ChatService.process_message(head, "Show photo", seeded_db)

        assert "https://s3.bucket/files/user-admin-123/xyz789.jpg" in result["content"]
        assert "https://cdn.example.com/photo.jpg" not in result["content"]

    @pytest.mark.asyncio
    async def test_non_media_text_passthrough(self, seeded_db):
        """Text without media URLs passes through unchanged."""
        head = HeadOfCouncil(agentium_id="HEAD00001", name="Test", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-123", username="admin", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        mock_llm_result = {
            "content": "Hello! This is just plain text with no images.",
            "model": "test-model",
            "tokens_used": 20
        }

        with patch("backend.services.chat_service.LLMClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm.generate_with_tools = AsyncMock(return_value=mock_llm_result)
            mock_llm_class.return_value = mock_llm

            # Storage should NOT be called
            from backend.services.storage_service import storage_service
            storage_service.upload_file = MagicMock()

            result = await ChatService.process_message(head, "Hi", seeded_db)

        assert result["content"] == "Hello! This is just plain text with no images."
        storage_service.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_download_graceful_fallback(self, seeded_db):
        """Failed media download preserves original URL, doesn't crash."""
        head = HeadOfCouncil(agentium_id="HEAD00001", name="Test", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-123", username="admin", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        mock_llm_result = {
            "content": "![Broken](https://gone.example.com/missing.png)",
            "model": "test-model",
            "tokens_used": 15
        }

        with patch("backend.services.chat_service.LLMClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm.generate_with_tools = AsyncMock(return_value=mock_llm_result)
            mock_llm_class.return_value = mock_llm

            # Mock download to fail (404)
            with patch("backend.services.media_interceptor.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 404
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                result = await ChatService.process_message(head, "Show broken", seeded_db)

        # Original markdown preserved
        assert result["content"] == "![Broken](https://gone.example.com/missing.png)"
        # No storage upload attempted
        from backend.services.storage_service import storage_service
        storage_service.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_media_urls_persisted_in_chat_message_metadata(self, seeded_db):
        """New storage URLs stored in ChatMessage metadata.media_urls."""
        head = HeadOfCouncil(agentium_id="HEAD00001", name="Test", is_active=True)
        seeded_db.add(head)
        admin = User(id="user-admin-123", username="admin", is_admin=True, is_active=True)
        seeded_db.add(admin)
        seeded_db.commit()

        mock_llm_result = {
            "content": "![Chart](https://charts.example.com/chart.png)",
            "model": "test-model",
            "tokens_used": 40
        }

        with patch("backend.services.chat_service.LLMClient") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_llm.generate_with_tools = AsyncMock(return_value=mock_llm_result)
            mock_llm_class.return_value = mock_llm

            from backend.services.storage_service import storage_service
            storage_service.upload_file = MagicMock(
                return_value="https://s3.bucket/files/user-admin-123/chart.png"
            )

            with patch("backend.services.media_interceptor.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 200
                mock_response.content = b"png-data"
                mock_response.headers = {"content-type": "image/png"}
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value.__aenter__.return_value = mock_client

                result = await ChatService.process_message(head, "Chart please", seeded_db)

        # Verify ChatMessage was created with media_urls in metadata
        from backend.models.entities.chat_message import ChatMessage
        msg = seeded_db.query(ChatMessage).filter_by(role="head_of_council").first()
        assert msg is not None
        assert msg.metadata is not None
        assert "media_urls" in msg.metadata
        assert "https://s3.bucket/files/user-admin-123/chart.png" in msg.metadata["media_urls"]