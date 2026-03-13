"""
Agentium SDK — Python client for the Agentium AI Agent Governance platform.

Usage:
    from agentium_sdk import AgentiumClient

    client = AgentiumClient("http://localhost:8000", api_key="your-key")
    agents = await client.list_agents()
"""

__version__ = "0.1.0"

from .client import AgentiumClient
from .models import Agent, Task, Constitution, Vote, WebhookSubscription
from .exceptions import (
    AgentiumError,
    AuthenticationError,
    ConstitutionalViolationError,
    RateLimitError,
    NotFoundError,
)

__all__ = [
    "AgentiumClient",
    "Agent",
    "Task",
    "Constitution",
    "Vote",
    "WebhookSubscription",
    "AgentiumError",
    "AuthenticationError",
    "ConstitutionalViolationError",
    "RateLimitError",
    "NotFoundError",
]
