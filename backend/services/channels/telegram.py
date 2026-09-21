"""Telegram Bot API adapter."""
import logging
from typing import Dict, Any
import httpx

from .base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage

logger = logging.getLogger(__name__)

class TelegramAdapter(BaseChannelAdapter):
    """
    Adapter for Telegram Bot API.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send a message to Telegram.
        """
        bot_token = self.config.get("bot_token")
        chat_id = message.sender_id  # In Telegram, sender_id is the chat ID

        if not all([bot_token, chat_id]):
            logger.error(f"[Telegram] Missing configuration for channel {self.channel.id}")
            return False

        url = self.BASE_URL.format(token=bot_token)
        payload = {
            "chat_id": chat_id,
            "text": message.content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return True
                else:
                    logger.error(f"[Telegram] API Error: {data.get('description')}")
                    return False
            else:
                logger.error(f"[Telegram] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] Exception sending message: {e}")
            return False

    @classmethod
    async def send_plain_message(cls, config: Dict[str, Any], recipient: str, content: str) -> bool:
        """
        Class method to send a plain text message to Telegram (used by ChannelManager).
        """
        bot_token = config.get("bot_token")
        chat_id = recipient

        if not all([bot_token, chat_id]):
            logger.error(f"[Telegram] Missing configuration for Telegram message")
            return False

        url = cls.BASE_URL.format(token=bot_token)
        payload = {
            "chat_id": chat_id,
            "text": content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return True
                else:
                    logger.error(f"[Telegram] API Error: {data.get('description')}")
                    return False
            else:
                logger.error(f"[Telegram] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] Exception sending message: {e}")
            return False

    async def validate_config(self) -> bool:
        """Validate config."""
        return "bot_token" in self.config