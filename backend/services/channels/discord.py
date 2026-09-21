"""Discord API adapter."""
import logging
from typing import Dict, Any
import httpx

from .base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage

logger = logging.getLogger(__name__)

class DiscordAdapter(BaseChannelAdapter):
    """
    Adapter for Discord Bot API.
    """

    BASE_URL = "https://discord.com/api/v10/channels/{channel_id}/messages"

    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send a message to Discord.
        """
        bot_token = self.config.get("bot_token")
        channel_id = message.sender_id  # In Discord, sender_id is the channel ID

        if not all([bot_token, channel_id]):
            logger.error(f"[Discord] Missing configuration for channel {self.channel.id}")
            return False

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "content": message.content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.BASE_URL.format(channel_id=channel_id),
                                           headers=headers, json=payload, timeout=10.0)

            if response.status_code == 200:
                return True
            else:
                logger.error(f"[Discord] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Discord] Exception sending message: {e}")
            return False

    @classmethod
    async def send_plain_message(cls, config: Dict[str, Any], recipient: str, content: str) -> bool:
        """
        Class method to send a plain text message to Discord (used by ChannelManager).
        """
        bot_token = config.get("bot_token")
        channel_id = recipient

        if not all([bot_token, channel_id]):
            logger.error(f"[Discord] Missing configuration for Discord message")
            return False

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "content": content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(cls.BASE_URL.format(channel_id=channel_id),
                                           headers=headers, json=payload, timeout=10.0)

            if response.status_code == 200:
                return True
            else:
                logger.error(f"[Discord] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Discord] Exception sending message: {e}")
            return False

    async def validate_config(self) -> bool:
        """Validate config."""
        return "bot_token" in self.config and "application_id" in self.config