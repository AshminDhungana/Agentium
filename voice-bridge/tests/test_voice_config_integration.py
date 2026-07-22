"""
Test voice bridge integration with new voice configuration system.
Tests the config sync from backend to voice bridge.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import aiohttp
import main


@pytest.mark.asyncio
async def test_fetch_voice_config_success():
    """Test successful fetching of voice configuration from backend."""
    mock_config = {
        "user_id": "test-user",
        "require_wake_word": False,
        "tts_voice": "am_adam",
        "tts_provider": "kokoro",
        "proactive_enabled": True,
        "speaker_identification": False,
    }

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=mock_config)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response), \
         patch("main.VOICE_TOKEN", "test-token"), \
         patch("main.BACKEND_URL", "http://test-backend"):
        result = await main._fetch_voice_config()
        assert result == mock_config


@pytest.mark.asyncio
async def test_fetch_voice_config_no_token():
    """Test fetching voice config when no token is available."""
    with patch("main.VOICE_TOKEN", ""):
        result = await main._fetch_voice_config()
        assert result is None


@pytest.mark.asyncio
async def test_fetch_voice_config_failure():
    """Test fetching voice config when backend request fails."""
    with patch("aiohttp.ClientSession.get", side_effect=aiohttp.ClientError("Connection failed")), \
         patch("main.VOICE_TOKEN", "test-token"), \
         patch("main.BACKEND_URL", "http://test-backend"):
        result = await main._fetch_voice_config()
        assert result is None


@pytest.mark.asyncio
async def test_fetch_voice_config_http_error():
    """Test fetching voice config when backend returns HTTP error."""
    mock_response = MagicMock()
    mock_response.status = 404
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response), \
         patch("main.VOICE_TOKEN", "test-token"), \
         patch("main.BACKEND_URL", "http://test-backend"):
        result = await main._fetch_voice_config()
        assert result is None
