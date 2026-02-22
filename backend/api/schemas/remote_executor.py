"""Pydantic schemas for remote code execution API."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class CodeExecutionRequest(BaseModel):
    """Request to execute code remotely."""
    code: str = Field(..., description="Python code to execute")
    language: str = Field(default="python", description="Programming language")
    dependencies: Optional[List[str]] = Field(
        default=None, description="pip packages to install"
    )
    input_data: Optional[Any] = Field(
        default=None, description="Input data available as 'input_data' variable"
    )
    task_id: Optional[str] = Field(default=None, description="Associated task ID")

    # Resource limits
    timeout_seconds: int = Field(
        default=300, ge=10, le=3600, description="Execution timeout"
    )
    memory_limit_mb: int = Field(
        default=512, ge=64, le=8192, description="Memory limit in MB"
    )
    cpu_limit: float = Field(
        default=1.0, ge=0.1, le=4.0, description="CPU core limit"
    )
    network_access: bool = Field(default=False, description="Allow network access")

    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Code cannot be empty')
        return v.strip()


class SecurityCheckResultSchema(BaseModel):
    """Security validation result."""
    passed: bool
    violations: List[str] = Field(default_factory=list)
    severity: str
    recommendation: Optional[str] = None


class ExecutionSummarySchema(BaseModel):
    """Summary of execution results – NEVER contains raw data."""
    output_schema: Dict[str, str] = Field(
        default_factory=dict, description="Output schema (column names and types)"
    )
    row_count: int = Field(default=0, description="Number of rows/records")
    sample: List[Dict[str, Any]] = Field(
        default_factory=list, description="Sample data (max 3 items)"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict, description="Statistical summary"
    )
    stdout: str = Field(default="", description="Standard output (truncated)")
    stderr: str = Field(default="", description="Standard error (truncated)")
    execution_time_ms: int = Field(
        default=0, description="Execution time in milliseconds"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    success: bool = Field(default=True)


class CodeExecutionResponse(BaseModel):
    """Response from code execution."""
    execution_id: str
    status: str  # completed, failed, blocked, timeout
    summary: Optional[ExecutionSummarySchema] = None
    error: Optional[str] = None
    security_result: SecurityCheckResultSchema
    started_at: str
    completed_at: str
    execution_time_ms: int


class SandboxCreateRequest(BaseModel):
    """Request to create a persistent sandbox."""
    cpu_limit: float = Field(default=1.0, ge=0.1, le=4.0)
    memory_limit_mb: int = Field(default=512, ge=64, le=8192)
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    network_access: bool = Field(default=False)
    max_disk_mb: int = Field(default=1024, ge=100, le=10240)


class SandboxResponse(BaseModel):
    """Response with sandbox information."""
    sandbox_id: str
    container_id: str
    status: str
    config: Dict[str, Any] = Field(default_factory=dict)


class ExecutionSummaryResponse(BaseModel):
    """Response with execution record."""
    execution_id: str
    agent_id: str
    task_id: Optional[str] = None
    status: str
    summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
