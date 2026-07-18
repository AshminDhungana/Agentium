"""
remote_exec — agent-callable bridge to the isolated Remote Executor sandbox.

Brains vs Hands: the calling agent's reasoning runs in the backend/Celery
process; this tool ships the agent's *code* (not its data) into an isolated
Docker sandbox. The sandbox runs with a default-deny network, a read-only
rootfs + scoped tmpfs, as a non-root user, with CPU/mem caps. Raw data and PII
NEVER leave the container: executor.py returns only an ExecutionSummary
(output_schema, row_count, sample of <=3 truncated rows, stats, truncated
stdout/stderr). The full result payload stays in the sandbox.
"""
import logging

from backend.services.remote_executor.service import RemoteExecutorService

logger = logging.getLogger(__name__)


async def execute(
    agent_id: str,
    code: str,
    input_data=None,
    dependencies: list = None,
    network_access: bool = False,
    timeout_seconds: int = 300,
    memory_limit_mb: int = 512,
    cpu_limit: float = 1.0,
    db=None,
) -> dict:
    """
    Execute code inside the isolated Remote Executor sandbox.

    Args:
        agent_id: Agentium ID of the calling agent (auto-injected by
            ToolCreationService.execute_tool — never the hardcoded "00001").
        code: Python source to run. Must assign its output to a variable
            named ``result`` (or ``output``) to get a structured summary.
        input_data: Optional data available inside the sandbox as
            ``input_data``. Shape/schema only — never raw PII rows.
        dependencies: Optional list of pip packages to install in the sandbox.
        network_access: If True, allow opt-in outbound internet via a bridge
            network. Default False (network_mode="none"). Note the intended
            egress deny-list is recorded as a label only and is not enforced;
            avoid passing secrets.
        timeout_seconds / memory_limit_mb / cpu_limit: Resource bounds.
        db: Injected by ToolCreationService. Passed through to the service so the
            audit-trail DB record is written; defaults to None for direct/test
            calls where no session is available.

    Returns:
        Dict with execution_id, status, summary (NEVER raw data),
        error, security_result, timings.
    """
    service = RemoteExecutorService(db_session=db)
    result = await service.execute(
        code=code,
        agent_id=agent_id,
        task_id=None,
        language="python",
        dependencies=dependencies,
        input_data=input_data,
        timeout_seconds=timeout_seconds,
        memory_limit_mb=memory_limit_mb,
        cpu_limit=cpu_limit,
        network_access=network_access,
    )

    logger.info(
        "remote_exec agent=%s status=%s network=%s duration_ms=%s sandbox_id=%s",
        agent_id,
        result.get("status"),
        network_access,
        result.get("execution_time_ms"),
        result.get("execution_id"),
    )
    return result
