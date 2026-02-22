"""
Tool Registry — updated for Phase 6.7 (MCP tool support)

Changes vs original:
- `execute_tool` detects async functions and awaits them via asyncio
- `execute_tool_async` — new native async path used by the updated tools.py route
- `list_tools` now surfaces MCP metadata (tier, server_url) in the descriptor
- All original sync behaviour is 100% preserved for existing browser/file/shell tools
"""
import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional

from backend.tools.browser_tool import BrowserTool
from backend.tools.file_tool import FileSystemTool
from backend.tools.shell_tool import ShellTool


class ToolRegistry:
    """Registry of available tools for agents."""

    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._initialize_tools()

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _initialize_tools(self):
        """Register all built-in (non-MCP) tools."""

        # Browser Tool
        browser = BrowserTool()
        self.register_tool(
            name="browser_control",
            description="Control web browser for navigation, form filling, and data extraction",
            function=browser.navigate,
            parameters={
                "url": {"type": "string", "description": "URL to navigate to"}
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )
        self.register_tool(
            name="browser_screenshot",
            description="Take screenshot of current page",
            function=browser.screenshot,
            parameters={
                "path": {"type": "string", "description": "Save path for screenshot"}
            },
        )

        # File Tool
        file_tool = FileSystemTool()
        self.register_tool(
            name="read_file",
            description="Read file contents from host filesystem",
            function=file_tool.read_file,
            parameters={
                "filepath": {"type": "string", "description": "Absolute file path"},
                "limit": {"type": "integer", "description": "Max characters to read"},
            },
            authorized_tiers=["0xxxx", "1xxxx", "2xxxx"],
        )
        self.register_tool(
            name="write_file",
            description="Write content to file (Head only)",
            function=file_tool.write_file,
            parameters={
                "filepath": {"type": "string", "description": "Absolute file path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            authorized_tiers=["0xxxx"],
        )

        # Shell Tool
        shell_tool = ShellTool()
        self.register_tool(
            name="execute_command",
            description="Execute shell command on host system",
            function=shell_tool.execute,
            parameters={
                "command": {"type": "array", "description": "Command and args as list"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
            },
            authorized_tiers=["0xxxx", "1xxxx"],
        )

    # ── Registration ───────────────────────────────────────────────────────────

    def register_tool(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: Dict[str, Any],
        authorized_tiers: Optional[List[str]] = None,
    ) -> None:
        """Register a tool in the registry."""
        self.tools[name] = {
            "name": name,
            "description": description,
            "function": function,
            "parameters": parameters,
            "authorized_tiers": authorized_tiers or [],
            # MCP-specific fields are added by MCPToolBridge after registration:
            # "is_mcp", "mcp_tool_id", "mcp_tier", "mcp_server_url", "mcp_original_name"
        }

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get tool by name."""
        return self.tools.get(name)

    def list_tools(self, agent_tier: str) -> Dict[str, Any]:
        """
        List all tools available to a specific agent tier.
        MCP tools include additional metadata (mcp_tier, server_url).
        """
        available: Dict[str, Any] = {}
        for name, tool in self.tools.items():
            if agent_tier not in tool["authorized_tiers"]:
                continue

            descriptor: Dict[str, Any] = {
                "description": tool["description"],
                "parameters": tool["parameters"],
            }

            # Surface deprecation warning if present
            if tool.get("deprecated"):
                descriptor["deprecated"] = True
                descriptor["deprecation_reason"] = tool.get("deprecation_reason")
                descriptor["replacement"] = tool.get("replacement")

            # Surface MCP metadata so agents know what kind of tool this is
            if tool.get("is_mcp"):
                descriptor["is_mcp"] = True
                descriptor["mcp_tier"] = tool.get("mcp_tier")
                descriptor["mcp_server_url"] = tool.get("mcp_server_url")
                descriptor["mcp_original_name"] = tool.get("mcp_original_name")

            available[name] = descriptor

        return available

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool synchronously.

        For MCP tools (async functions), this bridges into asyncio so callers
        that are not async-aware still work.  Prefer `execute_tool_async` when
        calling from an async context (FastAPI route) to avoid nesting event
        loops.
        """
        tool = self.get_tool(name)
        if not tool:
            return {"status": "error", "error": f"Tool '{name}' not found"}

        try:
            fn = tool["function"]
            if inspect.iscoroutinefunction(fn):
                # Running from a sync context — use asyncio.run() safely.
                # If there is already a running loop (e.g. inside pytest-asyncio)
                # fall back to creating a new loop in a thread.
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, fn(**kwargs))
                        result = future.result(timeout=60)
                else:
                    result = asyncio.run(fn(**kwargs))
            else:
                result = fn(**kwargs)

            return result

        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def execute_tool_async(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool natively from an async context (FastAPI route).

        - Awaits coroutine functions directly (zero overhead for MCP tools).
        - Runs sync functions in a thread-pool executor so they don't block
          the event loop.
        """
        tool = self.get_tool(name)
        if not tool:
            return {"status": "error", "error": f"Tool '{name}' not found"}

        try:
            fn = tool["function"]
            if inspect.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: fn(**kwargs)
                )
            return result

        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ── Lifecycle helpers (called by ToolVersioningService / DeprecationService) ─

    def get_tool_function(self, name: str) -> Optional[Callable]:
        """Return just the callable for a registered tool."""
        tool = self.tools.get(name)
        return tool["function"] if tool else None

    def update_tool_function(self, name: str, function: Callable) -> bool:
        """Replace the callable for an existing tool."""
        if name not in self.tools:
            return False
        self.tools[name]["function"] = function
        return True

    def mark_deprecated(
        self,
        name: str,
        reason: str,
        replacement: Optional[str] = None,
    ) -> bool:
        """Soft-mark a tool as deprecated."""
        if name not in self.tools:
            return False
        self.tools[name]["deprecated"] = True
        self.tools[name]["deprecation_reason"] = reason
        self.tools[name]["replacement"] = replacement
        return True

    def unmark_deprecated(self, name: str) -> bool:
        """Remove deprecation flag from a tool."""
        if name not in self.tools:
            return False
        self.tools[name].pop("deprecated", None)
        self.tools[name].pop("deprecation_reason", None)
        self.tools[name].pop("replacement", None)
        return True

    def deregister_tool(self, name: str) -> bool:
        """Hard-remove a tool from the registry."""
        if name not in self.tools:
            return False
        del self.tools[name]
        return True


# Global registry instance
tool_registry = ToolRegistry()