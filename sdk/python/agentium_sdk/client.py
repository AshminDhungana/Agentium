"""
Agentium SDK — async-first HTTP client.

Every request includes ``X-SDK-Source: python-sdk`` so that audit
trails produced by the SDK are indistinguishable from direct API calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, TypeVar
import httpx

from .models import (
    Agent,
    Task,
    Constitution,
    Vote,
    WebhookSubscription,
    WebhookDelivery,
    ChatMessage,
    ChatResponse,
    HealthStatus,
    TokenStatus,
)
from .exceptions import (
    AgentiumError,
    AuthenticationError,
    AuthorizationError,
    ConstitutionalViolationError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    ServerError,
)

T = TypeVar("T")

_SDK_HEADER = "X-SDK-Source"
_SDK_VALUE = "python-sdk"


class AgentiumClient:
    """
    Async-first Python client for the Agentium REST API.

    Usage::

        async with AgentiumClient("http://localhost:8000", api_key="sk-...") as client:
            agents = await client.list_agents()
            task = await client.create_task(title="Hello", description="World")

    You can also authenticate with a JWT token::

        client = AgentiumClient("http://localhost:8000", token="eyJhbG...")
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._token = token
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ── Context manager ──────────────────────────────────────

    async def __aenter__(self) -> "AgentiumClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._timeout,
            headers=self._build_headers(),
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Authentication ───────────────────────────────────────

    async def login(self, username: str, password: str) -> str:
        """
        Authenticate with username/password and store the returned JWT.

        Returns the access token string.
        """
        data = await self._request(
            "POST",
            "/api/v1/auth/login",
            json={"username": username, "password": password},
            skip_auth=True,
        )
        self._token = data.get("access_token", "")
        # Rebuild client headers with new token
        if self._client:
            self._client.headers.update(self._build_headers())
        return self._token

    # ── Agent endpoints ──────────────────────────────────────

    async def list_agents(
        self,
        tier: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Agent]:
        """List all agents, optionally filtered by tier and/or status."""
        params: Dict[str, Any] = {}
        if tier is not None:
            params["tier"] = tier
        if status:
            params["status"] = status
        data = await self._request("GET", "/api/v1/agents", params=params)
        return [Agent(**a) for a in data.get("agents", [])]

    async def get_agent(self, agentium_id: str) -> Agent:
        """Get a specific agent by its Agentium ID."""
        data = await self._request("GET", f"/api/v1/agents/{agentium_id}")
        return Agent(**data)

    async def create_agent(
        self,
        role: str,
        responsibilities: List[str],
        tier: int = 3,
    ) -> Agent:
        """Create a new agent with governance compliance."""
        data = await self._request(
            "POST",
            "/api/v1/agents/create",
            params={"role": role, "tier": tier},
            json=responsibilities,
        )
        return Agent(**data)

    # ── Task endpoints ───────────────────────────────────────

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Task]:
        """List tasks with optional status filter."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        data = await self._request("GET", "/api/v1/tasks", params=params)
        tasks = data.get("tasks", data) if isinstance(data, dict) else data
        if isinstance(tasks, list):
            return [Task(**t) for t in tasks]
        return []

    async def get_task(self, task_id: str) -> Task:
        """Get a specific task by ID."""
        data = await self._request("GET", f"/api/v1/tasks/{task_id}")
        return Task(**data)

    async def create_task(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        **kwargs: Any,
    ) -> Task:
        """Create a new task."""
        payload = {
            "title": title,
            "description": description,
            "priority": priority,
            **kwargs,
        }
        data = await self._request("POST", "/api/v1/tasks", json=payload)
        return Task(**data)

    # ── Constitution endpoints ───────────────────────────────

    async def get_constitution(self) -> Constitution:
        """Get the currently active constitution."""
        data = await self._request("GET", "/api/v1/constitution")
        return Constitution(**data)

    async def update_constitution(
        self,
        preamble: Optional[str] = None,
        articles: Optional[Dict[str, Any]] = None,
        prohibited_actions: Optional[List[str]] = None,
        sovereign_preferences: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update the constitution (sovereign only)."""
        payload: Dict[str, Any] = {}
        if preamble is not None:
            payload["preamble"] = preamble
        if articles is not None:
            payload["articles"] = articles
        if prohibited_actions is not None:
            payload["prohibited_actions"] = prohibited_actions
        if sovereign_preferences is not None:
            payload["sovereign_preferences"] = sovereign_preferences
        return await self._request("POST", "/api/v1/constitution/update", json=payload)

    # ── Voting endpoints ─────────────────────────────────────

    async def list_votes(self, status: Optional[str] = None) -> List[Vote]:
        """List voting proposals."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        data = await self._request("GET", "/api/v1/voting/proposals", params=params)
        items = data.get("proposals", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [Vote(**v) for v in items]
        return []

    async def cast_vote(
        self,
        proposal_id: str,
        vote: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cast a vote on a proposal. vote should be 'for', 'against', or 'abstain'."""
        payload: Dict[str, Any] = {"vote": vote}
        if reason:
            payload["reason"] = reason
        return await self._request(
            "POST", f"/api/v1/voting/proposals/{proposal_id}/vote", json=payload
        )

    # ── Chat endpoints ───────────────────────────────────────

    async def send_message(
        self,
        content: str,
        agent_id: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat message to an agent."""
        payload: Dict[str, Any] = {"content": content}
        if agent_id:
            payload["agent_id"] = agent_id
        data = await self._request("POST", "/api/v1/chat/send", json=payload)
        return ChatResponse(**data)

    # ── Webhook subscription endpoints ───────────────────────

    async def list_webhook_subscriptions(self) -> List[WebhookSubscription]:
        """List all webhook subscriptions for the authenticated user."""
        data = await self._request("GET", "/api/v1/webhooks/subscriptions")
        items = data.get("subscriptions", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [WebhookSubscription(**w) for w in items]
        return []

    async def create_webhook_subscription(
        self,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
        description: Optional[str] = None,
    ) -> WebhookSubscription:
        """Create a new outbound webhook subscription."""
        payload: Dict[str, Any] = {"url": url, "events": events}
        if secret:
            payload["secret"] = secret
        if description:
            payload["description"] = description
        data = await self._request("POST", "/api/v1/webhooks/subscriptions", json=payload)
        return WebhookSubscription(**data)

    async def delete_webhook_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Delete a webhook subscription."""
        return await self._request(
            "DELETE", f"/api/v1/webhooks/subscriptions/{subscription_id}"
        )

    async def get_webhook_deliveries(
        self,
        subscription_id: str,
        limit: int = 50,
    ) -> List[WebhookDelivery]:
        """Get delivery log for a webhook subscription."""
        data = await self._request(
            "GET",
            f"/api/v1/webhooks/subscriptions/{subscription_id}/deliveries",
            params={"limit": limit},
        )
        items = data.get("deliveries", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [WebhookDelivery(**d) for d in items]
        return []

    async def test_webhook(self, subscription_id: str) -> Dict[str, Any]:
        """Send a test event to a webhook subscription."""
        return await self._request(
            "POST", f"/api/v1/webhooks/subscriptions/{subscription_id}/test"
        )

    # ── Health / Status ──────────────────────────────────────

    async def health(self) -> HealthStatus:
        """Check API health (no auth required)."""
        data = await self._request("GET", "/api/health", skip_auth=True)
        return HealthStatus(**data)

    async def token_status(self) -> TokenStatus:
        """Get token optimizer status."""
        data = await self._request("GET", "/api/v1/status/tokens")
        return TokenStatus(**data)

    # ══════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════

    def _build_headers(self) -> Dict[str, str]:
        """Build default headers including SDK source and auth."""
        headers: Dict[str, str] = {_SDK_HEADER: _SDK_VALUE}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                headers=self._build_headers(),
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        skip_auth: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request and return the parsed JSON response.

        Raises typed exceptions for known error patterns.
        """
        client = self._get_client()

        headers: Dict[str, str] = {}
        if skip_auth:
            headers[_SDK_HEADER] = _SDK_VALUE  # still send SDK header

        try:
            response = await client.request(
                method,
                path,
                params=params,
                json=json,
                headers=headers if skip_auth else None,
            )
        except httpx.TimeoutException as exc:
            raise AgentiumError(f"Request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise AgentiumError(f"Connection error: {exc}") from exc

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: httpx.Response) -> Dict[str, Any]:
        """Parse response and raise appropriate exceptions for errors."""
        if response.status_code < 400:
            try:
                return response.json()
            except Exception:
                return {"raw": response.text}

        # Attempt to parse error detail
        detail: Dict[str, Any] = {}
        message = f"HTTP {response.status_code}"
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body
                message = body.get("detail", body.get("message", message))
                if isinstance(message, list):
                    # FastAPI validation errors come as a list
                    message = "; ".join(str(m) for m in message)
        except Exception:
            message = response.text or message

        status = response.status_code

        if status == 401:
            raise AuthenticationError(message, detail=detail)
        if status == 403:
            if "constitutional" in message.lower() or "constitution" in message.lower():
                raise ConstitutionalViolationError(message, detail=detail)
            raise AuthorizationError(message, detail=detail)
        if status == 404:
            raise NotFoundError(message, detail=detail)
        if status == 422:
            raise ValidationError(message, detail=detail)
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message,
                retry_after=float(retry_after) if retry_after else None,
                detail=detail,
            )
        if status >= 500:
            raise ServerError(message, status_code=status, detail=detail)

        raise AgentiumError(message, status_code=status, detail=detail)
