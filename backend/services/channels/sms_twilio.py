"""SMS/Twilio adapter."""
import logging
from typing import Dict, Any
import httpx

from .base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage

logger = logging.getLogger(__name__)

class SMSAdapter(BaseChannelAdapter):
    """
    Adapter for SMS via Twilio API.
    """

    BASE_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send an SMS message via Twilio.
        """
        account_sid = self.config.get("account_sid")
        auth_token = self.config.get("auth_token")
        from_number = self.config.get("from_number")  # Twilio phone number
        to_number = message.sender_id  # Recipient phone number

        if not all([account_sid, auth_token, from_number, to_number]):
            logger.error(f"[SMS] Missing configuration for channel {self.channel.id}")
            return False

        url = self.BASE_URL.format(account_sid=account_sid)
        payload = {
            "From": from_number,
            "To": to_number,
            "Body": message.content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url,
                                           auth=(account_sid, auth_token),
                                           data=payload,  # Twilio expects form data
                                           timeout=10.0)

            if response.status_code == 201:  # Twilio returns 201 for successful message creation
                return True
            else:
                logger.error(f"[SMS] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[SMS] Exception sending message: {e}")
            return False

    @classmethod
    async def send_plain_message(cls, config: Dict[str, Any], recipient: str, content: str) -> bool:
        """
        Class method to send a plain text message via SMS (used by ChannelManager).
        """
        account_sid = config.get("account_sid")
        auth_token = config.get("auth_token")
        from_number = config.get("from_number")
        to_number = recipient

        if not all([account_sid, auth_token, from_number, to_number]):
            logger.error(f"[SMS] Missing configuration for SMS message")
            return False

        url = cls.BASE_URL.format(account_sid=account_sid)
        payload = {
            "From": from_number,
            "To": to_number,
            "Body": content
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url,
                                           auth=(account_sid, auth_token),
                                           data=payload,
                                           timeout=10.0)

            if response.status_code == 201:
                return True
            else:
                logger.error(f"[SMS] HTTP Error: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[SMS] Exception sending message: {e}")
            return False

    async def validate_config(self) -> bool:
        """Validate config."""
        return all(key in self.config for key in ["account_sid", "auth_token", "from_number"])