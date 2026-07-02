"""<module>."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from backend.models.entities.channels import ExternalChannel, ExternalMessage

class BaseChannelAdapter(ABC):
    """
    Abstract base class for all channel adapters.
    """
    
    def __init__(self, channel: ExternalChannel):
        """Init."""

        self.channel = channel
        self.config = channel.config or {}

    @abstractmethod
    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send a message to the external channel.
        Returns True if successful, False otherwise.
        """
        pass

    async def fetch_history(self, limit: int = 10) -> list:
        """
        Fetch conversation history (if supported).
        """
        return []

    async def validate_config(self) -> bool:
        """
        Validate channel configuration (credentials, etc).
        """
        return True
