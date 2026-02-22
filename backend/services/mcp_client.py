"""
MCP Client Wrapper — Phase 6.7
Handles raw communication with external MCP servers.
Intentionally kept thin — all governance logic lives in mcp_governance.py.
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Graceful degradation if the mcp package is not yet installed ───────────────
try:
    from mcp import ClientSession, StdioServerParameters  # type: ignore
    from mcp.client.stdio import stdio_client             # type: ignore
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning(
        "mcp package not installed — MCP tool execution will be simulated. "
        "Run: pip install mcp>=1.0.0"
    )


class MCPConnectionError(Exception):
    """Raised when the client cannot connect to an MCP server."""


class MCPToolNotFoundError(Exception):
    """Raised when the requested tool does not exist on the server."""


class MCPClient:
    """
    Low-level MCP server client.

    Usage (async context manager):
        async with MCPClient(server_url) as client:
            tools = await client.list_tools()
            result = await client.call_tool("search", {"query": "hello"})
    """

    def __init__(self, server_url: str, timeout_seconds: int = 30):
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self._session: Optional[Any] = None

    # ── Context manager ────────────────────────────────────────────────────────

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        if not MCP_AVAILABLE:
            logger.debug("[MCPClient] mcp package absent — using mock mode for %s", self.server_url)
            return

        try:
            params = StdioServerParameters(command=self.server_url, args=[])
            self._transport, self._session = await asyncio.wait_for(
                stdio_client(params).__aenter__(),
                timeout=self.timeout_seconds,
            )
            await self._session.initialize()
            logger.info("[MCPClient] Connected to %s", self.server_url)
        except asyncio.TimeoutError:
            raise MCPConnectionError(f"Timed out connecting to MCP server: {self.server_url}")
        except Exception as exc:
            raise MCPConnectionError(f"Failed to connect to {self.server_url}: {exc}") from exc

    async def disconnect(self) -> None:
        """Close the MCP server connection."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

    # ── Core operations ────────────────────────────────────────────────────────

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        Discover all tools available on the MCP server.
        Returns a list of tool descriptors: [{name, description, inputSchema}]
        """
        if not MCP_AVAILABLE or not self._session:
            return self._mock_list_tools()

        try:
            response = await asyncio.wait_for(
                self._session.list_tools(),
                timeout=self.timeout_seconds,
            )
            return [
                {
                    "name": t.name,
                    "description": getattr(t, "description", ""),
                    "input_schema": getattr(t, "inputSchema", {}),
                }
                for t in response.tools
            ]
        except asyncio.TimeoutError:
            raise MCPConnectionError("list_tools timed out")
        except Exception as exc:
            raise MCPConnectionError(f"list_tools failed: {exc}") from exc

    async def call_tool(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Invoke a tool on the MCP server.
        Returns the raw tool result dict.
        """
        if not MCP_AVAILABLE or not self._session:
            return self._mock_call_tool(tool_name, params)

        try:
            response = await asyncio.wait_for(
                self._session.call_tool(tool_name, params),
                timeout=self.timeout_seconds,
            )
            return {
                "success": True,
                "tool": tool_name,
                "result": [
                    {"type": c.type, "text": getattr(c, "text", str(c))}
                    for c in response.content
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "tool": tool_name,
                "error": "Tool execution timed out",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            return {
                "success": False,
                "tool": tool_name,
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        Verify the MCP server is reachable and responsive.
        Returns {"healthy": bool, "latency_ms": float, "error": str|None}
        """
        start = datetime.utcnow()
        try:
            await self.connect()
            tools = await self.list_tools()
            latency = (datetime.utcnow() - start).total_seconds() * 1000
            return {
                "healthy": True,
                "latency_ms": round(latency, 2),
                "tool_count": len(tools),
                "error": None,
            }
        except MCPConnectionError as exc:
            latency = (datetime.utcnow() - start).total_seconds() * 1000
            return {
                "healthy": False,
                "latency_ms": round(latency, 2),
                "tool_count": 0,
                "error": str(exc),
            }
        finally:
            await self.disconnect()

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def hash_params(params: Dict[str, Any]) -> str:
        """SHA-256 hash of params for audit logging (avoids storing raw inputs)."""
        serialized = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    # ── Mock helpers (used when mcp package is absent) ─────────────────────────

    def _mock_list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "mock_search",
                "description": "Mock search tool (mcp package not installed)",
                "input_schema": {"query": {"type": "string"}},
            }
        ]

    def _mock_call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "tool": tool_name,
            "result": [{"type": "text", "text": f"[MOCK] Called {tool_name} with {params}"}],
            "timestamp": datetime.utcnow().isoformat(),
            "mock": True,
        }