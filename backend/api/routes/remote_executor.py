"""API routes for remote code execution.

Phase 6.6: Brains vs Hands — separates reasoning from execution.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.api.dependencies.auth import get_current_active_user
from backend.api.schemas.remote_executor import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    SandboxCreateRequest,
    SandboxResponse,
    ExecutionSummaryResponse,
)
from backend.services.remote_executor.service import RemoteExecutorService
from backend.services.remote_executor.sandbox import SandboxConfig
from backend.core.security.execution_guard import execution_guard
from backend.models.entities.remote_execution import (
    RemoteExecutionRecord,
    SandboxRecord,
    SandboxStatus,
)

router = APIRouter(prefix="/remote-executor", tags=["Remote Execution"])


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """
    Execute code in isolated sandbox.

    Returns summary only – raw data never leaves sandbox.
    Requires authenticated user.
    """
    # Use a default agent_id for API-initiated executions
    agent_id = "00001"  # System / Head of Council for user-initiated

    service = RemoteExecutorService(db)

    result = await service.execute(
        code=request.code,
        agent_id=agent_id,
        task_id=request.task_id,
        language=request.language,
        dependencies=request.dependencies,
        input_data=request.input_data,
        timeout_seconds=request.timeout_seconds,
        memory_limit_mb=request.memory_limit_mb,
        cpu_limit=request.cpu_limit,
        network_access=request.network_access,
    )

    return CodeExecutionResponse(**result)


@router.post("/sandboxes", response_model=SandboxResponse)
async def create_sandbox(
    request: SandboxCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Create a persistent sandbox for multiple executions. Requires admin."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required to create persistent sandboxes",
        )

    agent_id = "00001"
    service = RemoteExecutorService(db)

    config = SandboxConfig(
        cpu_limit=request.cpu_limit,
        memory_limit_mb=request.memory_limit_mb,
        timeout_seconds=request.timeout_seconds,
        network_mode="bridge" if request.network_access else "none",
        max_disk_mb=request.max_disk_mb,
    )

    sandbox = await service.sandbox_manager.create_sandbox(agent_id, config)

    # Save to database
    record = SandboxRecord(
        sandbox_id=sandbox["sandbox_id"],
        container_id=sandbox["container_id"],
        status=SandboxStatus.READY,
        cpu_limit=config.cpu_limit,
        memory_limit_mb=config.memory_limit_mb,
        timeout_seconds=config.timeout_seconds,
        network_mode=config.network_mode,
        max_disk_mb=config.max_disk_mb,
        created_by_agent_id=agent_id,
    )
    db.add(record)
    db.commit()

    return SandboxResponse(**sandbox)


@router.delete("/sandboxes/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Destroy a sandbox and clean up resources."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required to destroy sandboxes",
        )

    service = RemoteExecutorService(db)
    success = await service.sandbox_manager.destroy_sandbox(sandbox_id, "api_request")

    # Update database record
    record = (
        db.query(SandboxRecord)
        .filter(SandboxRecord.sandbox_id == sandbox_id)
        .first()
    )
    if record:
        record.status = SandboxStatus.DESTROYED
        record.destroyed_at = datetime.utcnow()
        record.destroy_reason = "api_request"
        db.commit()

    return {"success": success, "sandbox_id": sandbox_id}


@router.get("/sandboxes", response_model=List[SandboxResponse])
async def list_sandboxes(
    agent_id_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """List all sandboxes."""
    service = RemoteExecutorService(db)
    sandboxes = await service.sandbox_manager.list_sandboxes(
        agent_id=agent_id_filter
    )
    return [SandboxResponse(**s) for s in sandboxes]


@router.get("/executions/{execution_id}", response_model=ExecutionSummaryResponse)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user),
):
    """Get execution record and summary."""
    record = (
        db.query(RemoteExecutionRecord)
        .filter(RemoteExecutionRecord.execution_id == execution_id)
        .first()
    )

    if not record:
        raise HTTPException(status_code=404, detail="Execution not found")

    return ExecutionSummaryResponse(
        execution_id=record.execution_id,
        agent_id=record.agent_id,
        task_id=record.task_id,
        status=record.status,
        summary=record.summary,
        error_message=record.error_message,
        execution_time_ms=record.execution_time_ms,
        created_at=record.created_at.isoformat() if record.created_at else None,
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
    )


@router.post("/validate")
async def validate_code(
    request: CodeExecutionRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """Validate code without executing (security check only)."""
    security_result = execution_guard.validate_code(request.code, "3xxxx")

    return {
        "valid": security_result.passed,
        "security_result": {
            "passed": security_result.passed,
            "violations": security_result.violations,
            "severity": security_result.severity,
            "recommendation": security_result.recommendation,
        },
    }
