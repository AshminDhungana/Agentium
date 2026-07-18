"""Code Execution Tool — run code in the existing Docker sandbox.

Thin wrapper over RemoteExecutorService (brains vs hands). Reuses the
execution_guard security check and the summary-only contract — raw data never
leaves the sandbox. Distinct from execute_command (shell, 0/1/2xxxx) and from
Task-level remote execution. Registered in ToolRegistry as "code_execution",
restricted to 0xxxx/1xxxx/2xxxx.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CodeExecutionTool:
    TOOL_NAME = "code_execution"
    AUTHORIZED_TIERS = ["0xxxx", "1xxxx", "2xxxx"]

    def _make_service(self):
        from backend.services.remote_executor.service import RemoteExecutorService
        return RemoteExecutorService(db_session=None)

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        if action == "help":
            return {
                "status": "success",
                "description": (
                    "Execute code in an isolated Docker sandbox. Raw data never leaves "
                    "the sandbox; you receive only a structured summary. Full reference "
                    "in backend/.agentium/skills/code_execution/SKILL.md."
                ),
            }
        if action != "execute":
            return {"status": "error", "error": f"Unknown action: {action}"}

        code = kwargs.get("code")
        if not code:
            return {"status": "error", "error": "code is required"}
        agent_id = kwargs.get("agent_id") or "00001"

        service = self._make_service()
        try:
            result = await service.execute(
                code=code,
                agent_id=agent_id,
                task_id=kwargs.get("task_id"),
                language=kwargs.get("language", "python"),
                dependencies=kwargs.get("dependencies"),
                input_data=kwargs.get("input_data"),
                timeout_seconds=int(kwargs.get("timeout_seconds", 300)),
                network_access=bool(kwargs.get("network_access", False)),
            )
        except Exception as exc:
            logger.exception("code_execution failed")
            return {"status": "error", "error": str(exc)}
        return result


code_execution_tool = CodeExecutionTool()

# Required by ToolFactory.load_tool() dynamic loader (same as other tools).
tool_instance = code_execution_tool
