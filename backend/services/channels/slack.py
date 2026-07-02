"""<module>."""


import httpx
import logging
from typing import Dict, Any, Optional

from backend.services.channels.base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage

logger = logging.getLogger(__name__)

class SlackAdapter(BaseChannelAdapter):
    """
    Adapter for Slack Web API.
    """
    
    BASE_URL = "https://slack.com/api/chat.postMessage"

    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send a message to Slack.
        """
        bot_token = self.config.get("bot_token")
        channel_id = message.sender_id  # In Slack, sender_id is usually the channel ID for DMs/Channels
        
        if not all([bot_token, channel_id]):
            logger.error(f"[Slack] Missing configuration for channel {self.channel.id}")
            return False
            
        headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": channel_id,
            "text": message.content
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.BASE_URL, headers=headers, json=payload, timeout=10.0)
                
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return True
                else:
                    logger.error(f"[Slack] API Error: {data.get('error')}")
                    return False
            else:
                logger.error(f"[Slack] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Slack] Exception sending message: {e}")
            return False

    async def validate_config(self) -> bool:
        """Validate config."""

        return "bot_token" in self.config
