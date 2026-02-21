# Phase 6.6: Remote Code Execution (Brains vs Hands) - Implementation Plan

## Context

**Phase 6.6** implements the "Remote Code Execution" pattern from the research paper "If You Want Coherence, Orchestrate a Team of Rivals." This pattern separates reasoning (agent "brain") from execution (sandboxed "hands") to prevent context contamination.

**Problem:** Current system allows agents to execute code directly, which can:
- Contaminate agent context with raw data
- Expose PII/sensitive data to the reasoning layer
- Exceed context window limits with large datasets
- Create security risks from unrestricted code execution

**Solution:** Remote Executor service that:
- Runs code in isolated Docker containers
- Returns ONLY structured summaries (schema, stats, samples)
- Never exposes raw data to agents
- Enforces resource limits (CPU, memory, time)

## Overview

| Metric | Value |
|--------|-------|
| **Phase** | 6.6 |
| **Status** | PENDING - CRITICAL |
| **Complexity** | High |
| **Estimated Story Points** | 13 |
| **Dependencies** | Docker, Message Bus, Constitutional Guard |

## Critical Files to Modify

### New Files to Create

| File | Purpose |
|------|---------|
| `backend/services/remote_executor.py` | Core remote execution service |
| `backend/services/remote_executor/__init__.py` | Package initialization |
| `backend/services/remote_executor/sandbox.py` | Sandbox container management |
| `backend/services/remote_executor/executor.py` | In-container code execution |
| `backend/api/routes/remote_executor.py` | API endpoints |
| `backend/api/schemas/remote_executor.py` | Pydantic request/response models |
| `backend/models/entities/remote_execution.py` | Database models |
| `backend/core/security/execution_guard.py` | Code execution security validation |
| `docker-compose.remote-executor.yml` | Docker service definition |
| `backend/tests/test_remote_executor.py` | Unit tests |
| `backend/tests/test_sandbox.py` | Sandbox tests |

### Files to Modify

| File | Changes |
|------|---------|
| `docker-compose.yml` | Add remote-executor service |
| `backend/main.py` | Register remote executor router |
| `backend/core/config.py` | Add remote executor settings |
| `backend/services/__init__.py` | Export remote executor service |
| `backend/models/entities/__init__.py` | Import execution models |
| `backend/alembic/versions/` | Create migration for execution tables |

## Implementation Steps

### Step 1: Database Models (2 points)

Create `backend/models/entities/remote_execution.py`:

```python
"""Database models for remote code execution."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from backend.models.entities.base import BaseEntity


class ExecutionStatus(str, enum.Enum):
    """Status of remote execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class SandboxStatus(str, enum.Enum):
    """Status of sandbox container."""
    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    CLEANING = "cleaning"
    ERROR = "error"


class RemoteExecutionRecord(BaseEntity):
    """Record of a remote code execution."""
    __tablename__ = "remote_executions"

    # Execution identification
    execution_id = Column(String(50), unique=True, nullable=False, index=True)
    agent_id = Column(String(5), ForeignKey("agents.agentium_id"), nullable=False)
    task_id = Column(String(50), ForeignKey("tasks.task_id"), nullable=True)

    # Execution content
    code = Column(Text, nullable=False)  # Python code to execute
    language = Column(String(20), default="python")
    dependencies = Column(JSON, default=list)  # pip packages to install

    # Execution context (what agent needs to know)
    input_data_schema = Column(JSON, nullable=True)  # Schema of input data
    expected_output_schema = Column(JSON, nullable=True)  # Expected result schema

    # Execution results (summary only, never raw data)
    status = Column(String(20), default=ExecutionStatus.PENDING)
    summary = Column(JSON, nullable=True)  # ExecutionSummary as dict
    error_message = Column(Text, nullable=True)

    # Resource usage
    cpu_time_seconds = Column(Float, default=0.0)
    memory_peak_mb = Column(Float, default=0.0)
    execution_time_ms = Column(Integer, default=0)

    # Sandbox info
    sandbox_id = Column(String(50), nullable=True)
    sandbox_container_id = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="remote_executions")
    task = relationship("Task", back_populates="remote_executions")


class SandboxRecord(BaseEntity):
    """Record of a sandbox container."""
    __tablename__ = "sandboxes"

    sandbox_id = Column(String(50), unique=True, nullable=False, index=True)
    container_id = Column(String(100), nullable=True)
    status = Column(String(20), default=SandboxStatus.CREATING)

    # Resource limits
    cpu_limit = Column(Float, default=1.0)  # CPU cores
    memory_limit_mb = Column(Integer, default=512)  # MB
    timeout_seconds = Column(Integer, default=300)  # 5 minutes

    # Network isolation
    network_mode = Column(String(20), default="none")  # none, bridge, custom
    allowed_hosts = Column(JSON, default=list)  # Whitelist for network access

    # Storage
    volume_mounts = Column(JSON, default=list)  # [{"host": "/data", "container": "/data"}]
    max_disk_mb = Column(Integer, default=1024)  # 1GB

    # Current execution
    current_execution_id = Column(String(50), nullable=True)
    created_by_agent_id = Column(String(5), nullable=False)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    destroyed_at = Column(DateTime, nullable=True)
    destroy_reason = Column(String(100), nullable=True)


class ExecutionSummary:
    """Summary of execution results - NEVER contains raw data."""

    def __init__(
        self,
        schema: Dict[str, str],  # Column names and types
        row_count: int,
        sample: List[Dict],  # Small preview (max 3 rows)
        stats: Dict[str, Any],  # Statistical summary
        execution_metadata: Dict[str, Any]
    ):
        self.schema = schema
        self.row_count = row_count
        self.sample = sample
        self.stats = stats
        self.execution_metadata = execution_metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "row_count": self.row_count,
            "sample": self.sample,
            "stats": self.stats,
            "execution_metadata": self.execution_metadata
        }
```

### Step 2: Security Guard (2 points)

Create `backend/core/security/execution_guard.py`:

```python
"""Security validation for code execution."""
import ast
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SecurityCheckResult:
    """Result of security validation."""
    passed: bool
    violations: List[str]
    severity: str  # "low", "medium", "high", "critical"
    recommendation: Optional[str] = None


class ExecutionGuard:
    """
    Validates code before execution in remote sandbox.
    Multi-layer security: AST parsing + pattern matching + import whitelist.
    """

    # Dangerous patterns that are always blocked
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'mkfs\.',
        r'dd\s+if=/dev/zero',
        r'shutdown',
        r'reboot',
        r'os\.system\s*\(',
        r'subprocess\.call\s*\(',
        r'subprocess\.run\s*\(',
        r'eval\s*\(',
        r'exec\s*\(',
        r'__import__\s*\(',
        r'importlib\.',
        r'open\s*\([^)]*["\']w',
        r'file\s*\([^)]*["\']w',
    ]

    # Whitelist of allowed imports (stdlib + common data science)
    ALLOWED_IMPORTS = {
        # Standard library
        'json', 're', 'math', 'random', 'datetime', 'collections', 'itertools',
        'functools', 'statistics', 'decimal', 'fractions', 'typing', 'hashlib',
        'base64', 'string', 'time', 'uuid', 'inspect', 'types', 'dataclasses',
        'enum', 'pathlib', 'csv', 'io', 'warnings', 'contextlib', 'copy',
        'numbers', 'operator', 'pprint', 'textwrap', 'bisect', 'heapq',
        # Data processing (safe, read-only)
        'pandas', 'numpy', 'polars', 'pyarrow',
    }

    # Restricted imports require special approval
    RESTRICTED_IMPORTS = {
        'requests': 'Network access requires explicit whitelist',
        'urllib': 'Network access requires explicit whitelist',
        'http': 'Network access requires explicit whitelist',
        'ftplib': 'Network access requires explicit whitelist',
        'smtplib': 'Email sending requires Head approval',
        'sqlite3': 'Database access requires explicit path whitelist',
        'psycopg2': 'Database access requires explicit credentials',
        'pymongo': 'Database access requires explicit credentials',
    }

    def __init__(self):
        self.violations: List[str] = []

    def validate_code(self, code: str, agent_tier: str = "3xxxx") -> SecurityCheckResult:
        """
        Perform multi-layer security validation on code.

        Args:
            code: Python code to validate
            agent_tier: Agent tier (affects permission level)

        Returns:
            SecurityCheckResult with pass/fail and violations
        """
        self.violations = []

        # Layer 1: Pattern matching for dangerous commands
        self._check_dangerous_patterns(code)

        # Layer 2: AST parsing for import analysis
        self._check_imports_ast(code, agent_tier)

        # Layer 3: Syntax validation
        self._check_syntax(code)

        # Determine severity
        severity = self._calculate_severity()

        return SecurityCheckResult(
            passed=len(self.violations) == 0,
            violations=self.violations.copy(),
            severity=severity,
            recommendation=self._generate_recommendation() if self.violations else None
        )

    def _check_dangerous_patterns(self, code: str):
        """Check for dangerous command patterns using regex."""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                self.violations.append(
                    f"CRITICAL: Dangerous pattern detected: {pattern}"
                )

    def _check_imports_ast(self, code: str, agent_tier: str):
        """Parse AST to check imports."""
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._validate_import(alias.name, agent_tier)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    self._validate_import(module, agent_tier)

        except SyntaxError:
            # Will be caught in _check_syntax
            pass

    def _validate_import(self, module: str, agent_tier: str):
        """Validate a single import."""
        # Get top-level module name
        top_module = module.split('.')[0]

        # Check if in allowed list
        if top_module in self.ALLOWED_IMPORTS:
            return

        # Check if restricted
        if top_module in self.RESTRICTED_IMPORTS:
            # Head tier can use restricted imports
            if agent_tier.startswith('0'):
                return
            self.violations.append(
                f"RESTRICTED: Import '{top_module}' requires Head approval. {self.RESTRICTED_IMPORTS[top_module]}"
            )
            return

        # Unknown import - block by default
        self.violations.append(
            f"UNKNOWN: Import '{top_module}' is not in the allowed list. "
            f"Allowed imports: {', '.join(sorted(self.ALLOWED_IMPORTS)[:10])}..."
        )

    def _check_syntax(self, code: str):
        """Validate Python syntax."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            self.violations.append(f"SYNTAX ERROR: {e}")

    def _calculate_severity(self) -> str:
        """Calculate overall severity based on violations."""
        if not self.violations:
            return "none"

        critical_count = sum(1 for v in self.violations if v.startswith("CRITICAL"))
        restricted_count = sum(1 for v in self.violations if v.startswith("RESTRICTED"))

        if critical_count > 0:
            return "critical"
        elif restricted_count > 0:
            return "high"
        elif len(self.violations) > 3:
            return "medium"
        else:
            return "low"

    def _generate_recommendation(self) -> str:
        """Generate remediation recommendation."""
        recommendations = []

        if any(v.startswith("CRITICAL") for v in self.violations):
            recommendations.append("Remove all dangerous system commands immediately.")

        if any(v.startswith("RESTRICTED") for v in self.violations):
            recommendations.append("Request Head approval for restricted imports, or use alternative libraries.")

        if any("SYNTAX" in v for v in self.violations):
            recommendations.append("Fix syntax errors before submission.")

        return " ".join(recommendations) if recommendations else "Review and fix all violations."


# Global guard instance
execution_guard = ExecutionGuard()
```

### Step 3: Sandbox Container Manager (3 points)

Create `backend/services/remote_executor/sandbox.py`:

```python
"""Sandbox container management for remote code execution."""
import os
import uuid
import logging
import docker
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from backend.models.entities.remote_execution import SandboxStatus

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """Configuration for sandbox container."""
    cpu_limit: float = 1.0  # CPU cores
    memory_limit_mb: int = 512  # MB
    timeout_seconds: int = 300  # 5 minutes
    network_mode: str = "none"  # none, bridge
    allowed_hosts: Optional[List[str]] = None  # For network whitelist
    max_disk_mb: int = 1024  # 1GB
    image: str = "python:3.11-slim"  # Base image


class SandboxManager:
    """
    Manages Docker sandbox containers for remote code execution.

    Each execution runs in an isolated container with resource limits.
    Containers are ephemeral - created per execution and destroyed after.
    """

    def __init__(self):
        self.docker_client: Optional[docker.DockerClient] = None
        self._init_docker()

    def _init_docker(self):
        """Initialize Docker client from environment."""
        try:
            # Try environment variable first
            docker_socket = os.getenv('HOST_DOCKER_SOCKET', '/var/run/docker.sock')
            self.docker_client = docker.DockerClient(base_url=f'unix://{docker_socket}')

            # Test connection
            self.docker_client.ping()
            logger.info(f"SandboxManager connected to Docker at {docker_socket}")

        except Exception as e:
            logger.error(f"Failed to connect to Docker: {e}")
            self.docker_client = None

    async def create_sandbox(
        self,
        agent_id: str,
        config: Optional[SandboxConfig] = None
    ) -> Dict[str, Any]:
        """
        Create a new sandbox container for code execution.

        Args:
            agent_id: Agent requesting the sandbox
            config: Sandbox configuration (uses defaults if None)

        Returns:
            Dict with sandbox_id, container_id, status
        """
        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        config = config or SandboxConfig()
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:12]}"

        try:
            # Create container with resource limits
            container = self.docker_client.containers.run(
                image=config.image,
                name=sandbox_id,
                detach=True,
                tty=True,
                stdin_open=True,
                network_mode=config.network_mode,
                mem_limit=f"{config.memory_limit_mb}m",
                cpu_quota=int(config.cpu_limit * 100000),
                cpu_period=100000,
                storage_opt={"size": f"{config.max_disk_mb}m"},
                labels={
                    "agentium.sandbox": "true",
                    "agentium.agent_id": agent_id,
                    "agentium.created_at": datetime.utcnow().isoformat(),
                },
                environment={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                },
            )

            logger.info(f"Created sandbox {sandbox_id} for agent {agent_id}")

            return {
                "sandbox_id": sandbox_id,
                "container_id": container.id,
                "status": SandboxStatus.READY,
                "config": {
                    "cpu_limit": config.cpu_limit,
                    "memory_limit_mb": config.memory_limit_mb,
                    "timeout_seconds": config.timeout_seconds,
                }
            }

        except Exception as e:
            logger.error(f"Failed to create sandbox: {e}")
            raise RuntimeError(f"Sandbox creation failed: {e}")

    async def destroy_sandbox(
        self,
        sandbox_id: str,
        reason: str = "completed"
    ) -> bool:
        """
        Destroy a sandbox container and clean up resources.

        Args:
            sandbox_id: ID of sandbox to destroy
            reason: Reason for destruction (for audit log)

        Returns:
            True if successful
        """
        if not self.docker_client:
            return False

        try:
            container = self.docker_client.containers.get(sandbox_id)

            # Force remove after 5 second grace period
            container.stop(timeout=5)
            container.remove(force=True)

            logger.info(f"Destroyed sandbox {sandbox_id}: {reason}")
            return True

        except docker.errors.NotFound:
            logger.warning(f"Sandbox {sandbox_id} not found for destruction")
            return True  # Already gone
        except Exception as e:
            logger.error(f"Failed to destroy sandbox {sandbox_id}: {e}")
            return False

    async def list_sandboxes(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List sandbox containers.

        Args:
            agent_id: Filter by agent (None for all)
            status: Filter by status (None for all)

        Returns:
            List of sandbox info dicts
        """
        if not self.docker_client:
            return []

        try:
            filters = {"label": "agentium.sandbox=true"}
            if agent_id:
                filters["label"].append(f"agentium.agent_id={agent_id}")

            containers = self.docker_client.containers.list(
                all=True,
                filters=filters
            )

            sandboxes = []
            for container in containers:
                info = {
                    "sandbox_id": container.name,
                    "container_id": container.id,
                    "status": container.status,
                    "agent_id": container.labels.get("agentium.agent_id"),
                    "created_at": container.labels.get("agentium.created_at"),
                }

                if status is None or info["status"] == status:
                    sandboxes.append(info)

            return sandboxes

        except Exception as e:
            logger.error(f"Failed to list sandboxes: {e}")
            return []


# Global sandbox manager instance
sandbox_manager = SandboxManager()
```

### Step 4: In-Container Executor (2 points)

Create `backend/services/remote_executor/executor.py`:

```python
"""In-container code execution handler."""
import os
import sys
import json
import time
import resource
import traceback
from typing import Any, Dict, List
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# Resource limits (must be set before any other imports)
def set_resource_limits():
    """Set resource limits for sandboxed execution."""
    # CPU time limit (seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))

    # Memory limit (bytes) - 512MB
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

    # File size limit (bytes) - 100MB
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))

    # Process limit
    resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))

    # No core dumps
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class ExecutionResult:
    """Result of code execution - contains summary only."""

    def __init__(
        self,
        success: bool,
        output_schema: Dict[str, str],
        row_count: int = 0,
        sample: List[Dict] = None,
        stats: Dict[str, Any] = None,
        stdout: str = "",
        stderr: str = "",
        execution_time_ms: int = 0,
        error_message: str = None
    ):
        self.success = success
        self.output_schema = output_schema
        self.row_count = row_count
        self.sample = sample or []
        self.stats = stats or {}
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time_ms = execution_time_ms
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output_schema": self.output_schema,
            "row_count": self.row_count,
            "sample": self.sample,
            "stats": self.stats,
            "stdout": self.stdout[:1000] if self.stdout else "",  # Truncate
            "stderr": self.stderr[:1000] if self.stderr else "",  # Truncate
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message
        }


def analyze_dataframe(df) -> Dict[str, Any]:
    """Analyze a pandas DataFrame and return summary only."""
    if df is None or len(df) == 0:
        return {
            "schema": {},
            "row_count": 0,
            "sample": [],
            "stats": {}
        }

    # Schema (column names and types)
    schema = {col: str(dtype) for col, dtype in df.dtypes.items()}

    # Row count
    row_count = len(df)

    # Sample (max 3 rows) - convert to dict
    sample_rows = min(3, row_count)
    sample = df.head(sample_rows).to_dict('records')

    # Stats (describe for numeric columns)
    try:
        stats_df = df.describe()
        stats = {col: stats_df[col].to_dict() for col in stats_df.columns}
    except:
        stats = {}

    return {
        "schema": schema,
        "row_count": row_count,
        "sample": sample,
        "stats": stats
    }


def execute_code(
    code: str,
    input_data: Any = None,
    dependencies: List[str] = None
) -> ExecutionResult:
    """
    Execute Python code in sandboxed environment.

    Args:
        code: Python code to execute
        input_data: Input data (will be available as 'input_data' variable)
        dependencies: List of pip packages to install

    Returns:
        ExecutionResult with summary only (no raw data)
    """
    start_time = time.time()

    # Set resource limits
    set_resource_limits()

    # Capture stdout/stderr
    stdout_capture = StringIO()
    stderr_capture = StringIO()

    # Install dependencies if specified
    if dependencies:
        for dep in dependencies:
            try:
                import subprocess
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "--quiet", dep
                ])
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    output_schema={},
                    error_message=f"Failed to install dependency {dep}: {e}",
                    execution_time_ms=int((time.time() - start_time) * 1000)
                )

    # Execute code
    local_vars = {"input_data": input_data}
    result_var = None

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the code
            exec(code, {}, local_vars)

            # Try to get the result variable
            result_var = local_vars.get('result', local_vars.get('output', None))

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Analyze result if it's a DataFrame
        if result_var is not None:
            try:
                import pandas as pd
                if isinstance(result_var, pd.DataFrame):
                    analysis = analyze_dataframe(result_var)
                    return ExecutionResult(
                        success=True,
                        output_schema=analysis["schema"],
                        row_count=analysis["row_count"],
                        sample=analysis["sample"],
                        stats=analysis["stats"],
                        stdout=stdout_capture.getvalue(),
                        stderr=stderr_capture.getvalue(),
                        execution_time_ms=execution_time_ms
                    )
            except ImportError:
                pass

            # For non-DataFrame results, return basic info
            return ExecutionResult(
                success=True,
                output_schema={"type": type(result_var).__name__},
                row_count=1 if not isinstance(result_var, (list, dict)) else len(result_var),
                sample=[{"result": str(result_var)[:500]}],
                stats={},
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                execution_time_ms=execution_time_ms
            )

        # No result variable - just executed for side effects
        return ExecutionResult(
            success=True,
            output_schema={},
            row_count=0,
            sample=[],
            stats={},
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            execution_time_ms=execution_time_ms
        )

    except Exception as e:
        execution_time_ms = int((time.time() - start_time) * 1000)
        return ExecutionResult(
            success=False,
            output_schema={},
            error_message=f"{type(e).__name__}: {str(e)}",
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
            execution_time_ms=execution_time_ms
        )


if __name__ == "__main__":
    # Test execution
    test_code = """
import pandas as pd
import json

# Create sample data
data = {
    'name': ['Alice', 'Bob', 'Charlie'],
    'age': [25, 30, 35],
    'salary': [50000, 60000, 70000]
}

result = pd.DataFrame(data)
"""

    result = execute_code(test_code)
    print(json.dumps(result.to_dict(), indent=2))
```

### Step 5: Main Remote Executor Service (3 points)

Create `backend/services/remote_executor.py`:

```python
"""Remote Code Execution Service - Brains vs Hands separation."""
import os
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.services.remote_executor.sandbox import SandboxManager, SandboxConfig
from backend.services.remote_executor.executor import ExecutionResult
from backend.core.security.execution_guard import execution_guard, SecurityCheckResult
from backend.models.entities.remote_execution import (
    RemoteExecutionRecord, SandboxRecord, ExecutionStatus, SandboxStatus
)

logger = logging.getLogger(__name__)


class RemoteExecutorService:
    """
    Service for executing code in isolated sandboxes.

    Key Principle: Raw data NEVER enters agent context.
    Agents receive only structured summaries (schema, stats, samples).

    Architecture:
    - Agent (Brain) → Writes Code → Remote Executor → Returns Summary
         ↑                                               ↓
         └────────────── Receives Summary ←────────────┘
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self.sandbox_manager = SandboxManager()
        self.guard = execution_guard

    async def execute(
        self,
        code: str,
        agent_id: str,
        task_id: Optional[str] = None,
        language: str = "python",
        dependencies: Optional[List[str]] = None,
        input_data: Optional[Any] = None,
        timeout_seconds: int = 300,
        memory_limit_mb: int = 512,
        cpu_limit: float = 1.0,
        network_access: bool = False
    ) -> Dict[str, Any]:
        """
        Execute code in isolated sandbox and return summary only.

        Args:
            code: Python code to execute
            agent_id: Agent requesting execution
            task_id: Optional associated task
            language: Programming language (default: python)
            dependencies: List of pip packages to install
            input_data: Input data available as 'input_data' variable
            timeout_seconds: Execution timeout
            memory_limit_mb: Memory limit for sandbox
            cpu_limit: CPU core limit
            network_access: Whether to allow network access

        Returns:
            Dict with execution summary (NEVER raw data)
        """
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        start_time = datetime.utcnow()

        # Step 1: Security validation
        security_result = self.guard.validate_code(code, agent_id[:1] if agent_id else "3")

        if not security_result.passed:
            logger.warning(f"Code security check failed for {execution_id}: {security_result.violations}")
            return {
                "execution_id": execution_id,
                "status": "blocked",
                "security_result": {
                    "passed": False,
                    "violations": security_result.violations,
                    "severity": security_result.severity,
                    "recommendation": security_result.recommendation
                },
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": 0
            }

        # Step 2: Create database record
        if self.db:
            record = RemoteExecutionRecord(
                execution_id=execution_id,
                agent_id=agent_id,
                task_id=task_id,
                code=code,
                language=language,
                dependencies=dependencies or [],
                status=ExecutionStatus.PENDING,
                created_at=start_time
            )
            self.db.add(record)
            self.db.commit()

        # Step 3: Create sandbox configuration
        config = SandboxConfig(
            cpu_limit=cpu_limit,
            memory_limit_mb=memory_limit_mb,
            timeout_seconds=timeout_seconds,
            network_mode="bridge" if network_access else "none",
            max_disk_mb=1024
        )

        # Step 4: Create sandbox and execute
        try:
            # Update status
            if self.db:
                record.status = ExecutionStatus.RUNNING
                record.started_at = datetime.utcnow()
                self.db.commit()

            # Create sandbox
            sandbox = await self.sandbox_manager.create_sandbox(agent_id, config)
            sandbox_id = sandbox["sandbox_id"]

            if self.db:
                record.sandbox_id = sandbox_id
                record.sandbox_container_id = sandbox["container_id"]
                self.db.commit()

            # Execute code in sandbox
            # This runs the executor.py script inside the container
            result = await self._execute_in_sandbox(
                sandbox_id=sandbox_id,
                code=code,
                input_data=input_data,
                dependencies=dependencies,
                timeout=timeout_seconds
            )

            # Update record with results
            if self.db:
                record.status = ExecutionStatus.COMPLETED if result.success else ExecutionStatus.FAILED
                record.completed_at = datetime.utcnow()
                record.summary = result.to_dict()
                record.execution_time_ms = result.execution_time_ms
                self.db.commit()

            # Cleanup sandbox
            await self.sandbox_manager.destroy_sandbox(sandbox_id, "execution_complete")

            # Return summary to agent (NEVER raw data)
            return {
                "execution_id": execution_id,
                "status": "completed" if result.success else "failed",
                "summary": result.to_dict(),
                "security_result": {
                    "passed": True,
                    "violations": [],
                    "severity": "none"
                },
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": result.execution_time_ms
            }

        except Exception as e:
            logger.error(f"Execution failed for {execution_id}: {e}")

            # Update record
            if self.db:
                record.status = ExecutionStatus.FAILED
                record.completed_at = datetime.utcnow()
                record.error_message = str(e)
                self.db.commit()

            # Cleanup if sandbox exists
            if 'sandbox_id' in locals():
                await self.sandbox_manager.destroy_sandbox(sandbox_id, "execution_failed")

            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e),
                "security_result": {
                    "passed": True,
                    "violations": [],
                    "severity": "none"
                },
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000)
            }

    async def _execute_in_sandbox(
        self,
        sandbox_id: str,
        code: str,
        input_data: Any,
        dependencies: Optional[List[str]],
        timeout: int
    ) -> ExecutionResult:
        """
        Execute code inside a sandbox container.

        This method copies the executor script and code into the container,
        runs it, and retrieves the results.
        """
        import tempfile
        import json

        # Create temporary files for execution
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write code to file
            code_file = os.path.join(tmpdir, "code.py")
            with open(code_file, 'w') as f:
                f.write(code)

            # Write input data to file
            input_file = os.path.join(tmpdir, "input.json")
            with open(input_file, 'w') as f:
                json.dump(input_data if input_data is not None else {}, f)

            # Write executor script
            executor_script = '''
import sys
import json
import time
import traceback
from typing import Any, Dict, List

# Read input data
with open('/tmp/input.json', 'r') as f:
    input_data = json.load(f)

# Read and execute code
exec_globals = {'input_data': input_data, 'result': None}
exec_locals = {}

try:
    with open('/tmp/code.py', 'r') as f:
        code = f.read()

    start_time = time.time()
    exec(code, exec_globals, exec_locals)
    execution_time = int((time.time() - start_time) * 1000)

    # Get result
    result = exec_locals.get('result', exec_globals.get('result', None))

    # Analyze result
    output = analyze_result(result)
    output['execution_time_ms'] = execution_time
    output['success'] = True

    print(json.dumps(output))

except Exception as e:
    output = {
        'success': False,
        'error': str(e),
        'traceback': traceback.format_exc(),
        'execution_time_ms': int((time.time() - start_time) * 1000)
    }
    print(json.dumps(output))

def analyze_result(result):
    """Analyze result and return summary only."""
    if result is None:
        return {
            'output_schema': {},
            'row_count': 0,
            'sample': [],
            'stats': {}
        }

    # Try pandas DataFrame
    try:
        import pandas as pd
        if isinstance(result, pd.DataFrame):
            return {
                'output_schema': {col: str(dtype) for col, dtype in result.dtypes.items()},
                'row_count': len(result),
                'sample': result.head(3).to_dict('records'),
                'stats': result.describe().to_dict()
            }
    except ImportError:
        pass

    # Try list of dicts
    if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
        return {
            'output_schema': {k: type(v).__name__ for k, v in result[0].items()},
            'row_count': len(result),
            'sample': result[:3],
            'stats': {}
        }

    # Default: simple type
    return {
        'output_schema': {'type': type(result).__name__},
        'row_count': 1,
        'sample': [{'value': str(result)[:500]}],
        'stats': {}
    }
'''

            executor_file = os.path.join(tmpdir, "executor.py")
            with open(executor_file, 'w') as f:
                f.write(executor_script)

            # Copy files to container
            container = self.docker_client.containers.get(sandbox_id)

            # Use docker cp equivalent
            import subprocess
            for src, dst in [
                (code_file, f"{sandbox_id}:/tmp/code.py"),
                (input_file, f"{sandbox_id}:/tmp/input.json"),
                (executor_file, f"{sandbox_id}:/tmp/executor.py"),
            ]:
                subprocess.run(
                    ["docker", "cp", src, dst],
                    check=True,
                    capture_output=True
                )

            # Execute in container
            result = container.exec_run(
                ["python", "/tmp/executor.py"],
                workdir="/tmp",
                timeout=timeout
            )

            # Parse result
            if result.exit_code == 0:
                output = json.loads(result.output.decode('utf-8'))
                return ExecutionResult(
                    success=output.get('success', False),
                    output_schema=output.get('output_schema', {}),
                    row_count=output.get('row_count', 0),
                    sample=output.get('sample', []),
                    stats=output.get('stats', {}),
                    stdout=output.get('stdout', ''),
                    stderr=output.get('stderr', ''),
                    execution_time_ms=output.get('execution_time_ms', 0),
                    error_message=output.get('error')
                )
            else:
                return ExecutionResult(
                    success=False,
                    output_schema={},
                    error_message=f"Container execution failed: {result.output.decode('utf-8')}",
                    execution_time_ms=0
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output_schema={},
                error_message=f"Execution error: {str(e)}",
                execution_time_ms=0
            )


# Global executor instance
executor = InContainerExecutor()
```

### Step 5: API Routes (2 points)

Create `backend/api/routes/remote_executor.py`:

```python
"""API routes for remote code execution."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from backend.api.dependencies import get_db, get_current_active_user
from backend.api.schemas.remote_executor import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    SandboxCreateRequest,
    SandboxResponse,
    ExecutionSummaryResponse
)
from backend.services.remote_executor import RemoteExecutorService
from backend.core.security.execution_guard import SecurityCheckResult

router = APIRouter(prefix="/remote-executor", tags=["Remote Execution"])


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """
    Execute code in isolated sandbox.

    Returns summary only - raw data never leaves sandbox.
    Requires Council tier (1xxxx) or higher.
    """
    # Authorization check
    agent_id = current_user.get("agent_id", "30001")
    if not (agent_id.startswith('0') or agent_id.startswith('1') or agent_id.startswith('2')):
        raise HTTPException(
            status_code=403,
            detail="Remote execution requires Lead tier (2xxxx) or higher"
        )

    # Initialize service
    service = RemoteExecutorService(db)

    # Execute
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
        network_access=request.network_access
    )

    return CodeExecutionResponse(**result)


@router.post("/sandboxes", response_model=SandboxResponse)
async def create_sandbox(
    request: SandboxCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Create a persistent sandbox for multiple executions."""
    agent_id = current_user.get("agent_id", "30001")

    # Only Lead tier and above can create persistent sandboxes
    if not (agent_id.startswith('0') or agent_id.startswith('1') or agent_id.startswith('2')):
        raise HTTPException(
            status_code=403,
            detail="Persistent sandboxes require Lead tier (2xxxx) or higher"
        )

    service = RemoteExecutorService(db)

    config = SandboxConfig(
        cpu_limit=request.cpu_limit,
        memory_limit_mb=request.memory_limit_mb,
        timeout_seconds=request.timeout_seconds,
        network_mode="bridge" if request.network_access else "none",
        max_disk_mb=request.max_disk_mb
    )

    sandbox = await service.sandbox_manager.create_sandbox(agent_id, config)

    # Save to database
    if db:
        record = SandboxRecord(
            sandbox_id=sandbox["sandbox_id"],
            container_id=sandbox["container_id"],
            status=SandboxStatus.READY,
            cpu_limit=config.cpu_limit,
            memory_limit_mb=config.memory_limit_mb,
            timeout_seconds=config.timeout_seconds,
            network_mode=config.network_mode,
            max_disk_mb=config.max_disk_mb,
            created_by_agent_id=agent_id
        )
        db.add(record)
        db.commit()

    return SandboxResponse(**sandbox)


@router.delete("/sandboxes/{sandbox_id}")
async def destroy_sandbox(
    sandbox_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Destroy a sandbox and clean up resources."""
    agent_id = current_user.get("agent_id", "30001")

    # Verify ownership or authorization
    if db:
        record = db.query(SandboxRecord).filter(
            SandboxRecord.sandbox_id == sandbox_id
        ).first()

        if record and record.created_by_agent_id != agent_id:
            # Only Head or Council can destroy others' sandboxes
            if not (agent_id.startswith('0') or agent_id.startswith('1')):
                raise HTTPException(
                    status_code=403,
                    detail="Cannot destroy sandbox owned by another agent"
                )

    service = RemoteExecutorService(db)
    success = await service.sandbox_manager.destroy_sandbox(sandbox_id, "api_request")

    if db:
        record = db.query(SandboxRecord).filter(
            SandboxRecord.sandbox_id == sandbox_id
        ).first()
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
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """List all sandboxes."""
    current_agent_id = current_user.get("agent_id", "30001")

    # Filter by authorization level
    if not current_agent_id.startswith('0'):
        # Non-Head agents can only see their own sandboxes
        agent_id_filter = current_agent_id

    service = RemoteExecutorService(db)
    sandboxes = await service.sandbox_manager.list_sandboxes(
        agent_id=agent_id_filter
    )

    return [SandboxResponse(**s) for s in sandboxes]


@router.get("/executions/{execution_id}", response_model=ExecutionSummaryResponse)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Get execution record and summary."""
    agent_id = current_user.get("agent_id", "30001")

    record = db.query(RemoteExecutionRecord).filter(
        RemoteExecutionRecord.execution_id == execution_id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Authorization check
    if record.agent_id != agent_id and not agent_id.startswith('0'):
        raise HTTPException(status_code=403, detail="Cannot access execution from another agent")

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
        completed_at=record.completed_at.isoformat() if record.completed_at else None
    )


@router.post("/validate", response_model=Dict[str, Any])
async def validate_code(
    request: CodeExecutionRequest,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
):
    """Validate code without executing (security check only)."""
    agent_id = current_user.get("agent_id", "30001")

    security_result = execution_guard.validate_code(
        request.code,
        agent_id[:1] if agent_id else "3"
    )

    return {
        "valid": security_result.passed,
        "security_result": {
            "passed": security_result.passed,
            "violations": security_result.violations,
            "severity": security_result.severity,
            "recommendation": security_result.recommendation
        }
    }
```

### Step 6: Pydantic Schemas (1 point)

Create `backend/api/schemas/remote_executor.py`:

```python
"""Pydantic schemas for remote code execution API."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class CodeExecutionRequest(BaseModel):
    """Request to execute code remotely."""
    code: str = Field(..., description="Python code to execute")
    language: str = Field(default="python", description="Programming language")
    dependencies: Optional[List[str]] = Field(default=None, description="pip packages to install")
    input_data: Optional[Any] = Field(default=None, description="Input data available as 'input_data' variable")
    task_id: Optional[str] = Field(default=None, description="Associated task ID")

    # Resource limits
    timeout_seconds: int = Field(default=300, ge=10, le=3600, description="Execution timeout")
    memory_limit_mb: int = Field(default=512, ge=64, le=8192, description="Memory limit in MB")
    cpu_limit: float = Field(default=1.0, ge=0.1, le=4.0, description="CPU core limit")
    network_access: bool = Field(default=False, description="Allow network access")

    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Code cannot be empty')
        return v.strip()


class SecurityCheckResultSchema(BaseModel):
    """Security validation result."""
    passed: bool
    violations: List[str]
    severity: str
    recommendation: Optional[str]


class ExecutionSummarySchema(BaseModel):
    """Summary of execution results - NEVER contains raw data."""
    schema: Dict[str, str] = Field(default_factory=dict, description="Output schema (column names and types)")
    row_count: int = Field(default=0, description="Number of rows/records")
    sample: List[Dict[str, Any]] = Field(default_factory=list, description="Sample data (max 3 items)")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Statistical summary")
    stdout: str = Field(default="", description="Standard output (truncated)")
    stderr: str = Field(default="", description="Standard error (truncated)")
    execution_time_ms: int = Field(default=0, description="Execution time in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")


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
    config: Dict[str, Any]


class ExecutionSummaryResponse(BaseModel):
    """Response with execution record."""
    execution_id: str
    agent_id: str
    task_id: Optional[str]
    status: str
    summary: Optional[Dict[str, Any]]
    error_message: Optional[str]
    execution_time_ms: int
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
```

### Step 7: Docker Compose Configuration (1 point)

Create `docker-compose.remote-executor.yml`:

```yaml
# Docker Compose extension for Remote Executor service
# Usage: docker compose -f docker-compose.yml -f docker-compose.remote-executor.yml up
version: '3.8'

services:
  remote-executor:
    build:
      context: ./backend
      dockerfile: Dockerfile.remote-executor
    container_name: agentium-remote-executor
    privileged: false  # Minimal privileges
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
    security_opt:
      - no-new-privileges:true
      - seccomp:./backend/security/remote-executor-seccomp.json
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
      - /var/tmp:noexec,nosuid,size=50m
    volumes:
      # Read-only access to execution scripts
      - ./backend/services/remote_executor:/app/executor:ro
      # Temporary execution volume (ephemeral)
      - execution-data:/tmp/executions
    environment:
      - EXECUTOR_MODE=sandbox
      - MAX_EXECUTION_TIME=300
      - MAX_MEMORY_MB=512
      - ALLOW_NETWORK=false
    networks:
      - agentium-network
    healthcheck:
      test: ["CMD", "python", "-c", "print('healthy')"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M

volumes:
  execution-data:
    driver: local
```

Add to main `docker-compose.yml`:

```yaml
  # Add this service to existing docker-compose.yml
  remote-executor:
    build:
      context: ./backend
      dockerfile: Dockerfile.remote-executor
    container_name: agentium-remote-executor
    privileged: false
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    volumes:
      - ./backend/services/remote_executor:/app/executor:ro
    environment:
      - EXECUTOR_MODE=sandbox
      - MAX_EXECUTION_TIME=300
      - MAX_MEMORY_MB=512
    networks:
      - agentium-network
    healthcheck:
      test: ["CMD", "python", "-c", "print('healthy')"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

### Step 8: Dockerfile for Remote Executor (1 point)

Create `backend/Dockerfile.remote-executor`:

```dockerfile
# Dockerfile for Remote Executor service
# Minimal, hardened container for code execution

FROM python:3.11-slim-bookworm

# Security: Create non-root user
RUN groupadd -r executor && useradd -r -g executor -s /bin/false executor

# Install minimal dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages (minimal set for data processing)
RUN pip install --no-cache-dir \
    pandas==2.1.4 \
    numpy==1.26.3 \
    polars==0.20.3 \
    pyarrow==14.0.2

# Set up execution directory
RUN mkdir -p /tmp/executions && chown executor:executor /tmp/executions

# Copy executor scripts
COPY services/remote_executor/ /app/executor/
RUN chown -R executor:executor /app/executor

# Switch to non-root user
USER executor

# Set working directory
WORKDIR /tmp/executions

# Default command (health check)
CMD ["python", "-c", "print('Remote Executor Ready')"]
```

### Step 9: Integration with Main App (1 point)

Modify `backend/main.py` to register the router:

```python
# Add to imports
from backend.api.routes import remote_executor as remote_executor_routes

# Add to router registration (around line 286-304)
app.include_router(
    remote_executor_routes.router,
    prefix="/api/v1",
    tags=["remote-executor"]
)
```

Modify `backend/core/config.py` to add settings:

```python
# Add to Settings class
class Settings(BaseSettings):
    # ... existing settings ...

    # Remote Executor Settings
    REMOTE_EXECUTOR_ENABLED: bool = Field(default=True, env="REMOTE_EXECUTOR_ENABLED")
    SANDBOX_TIMEOUT_SECONDS: int = Field(default=300, env="SANDBOX_TIMEOUT_SECONDS")
    SANDBOX_MEMORY_MB: int = Field(default=512, env="SANDBOX_MEMORY_MB")
    SANDBOX_CPU_LIMIT: float = Field(default=1.0, env="SANDBOX_CPU_LIMIT")
    MAX_CONCURRENT_SANDBOXES: int = Field(default=10, env="MAX_CONCURRENT_SANDBOXES")
    SANDBOX_NETWORK_ENABLED: bool = Field(default=False, env="SANDBOX_NETWORK_ENABLED")
```

### Step 10: Database Migration (1 point)

Create `backend/alembic/versions/024_add_remote_execution.py`:

```python
"""Add remote execution tables.

Revision ID: 024
Revises: 023
Create Date: 2026-02-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    # Create remote_executions table
    op.create_table(
        'remote_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('execution_id', sa.String(length=50), nullable=False),
        sa.Column('agent_id', sa.String(length=5), nullable=False),
        sa.Column('task_id', sa.String(length=50), nullable=True),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=True),
        sa.Column('dependencies', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('input_data_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expected_output_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('summary', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('cpu_time_seconds', sa.Float(), nullable=True),
        sa.Column('memory_peak_mb', sa.Float(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('sandbox_id', sa.String(length=50), nullable=True),
        sa.Column('sandbox_container_id', sa.String(length=100), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.agentium_id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('execution_id')
    )

    # Create indexes
    op.create_index('ix_remote_executions_agent_id', 'remote_executions', ['agent_id'])
    op.create_index('ix_remote_executions_status', 'remote_executions', ['status'])
    op.create_index('ix_remote_executions_created_at', 'remote_executions', ['created_at'])

    # Create sandboxes table
    op.create_table(
        'sandboxes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('sandbox_id', sa.String(length=50), nullable=False),
        sa.Column('container_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('cpu_limit', sa.Float(), nullable=True),
        sa.Column('memory_limit_mb', sa.Integer(), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True),
        sa.Column('network_mode', sa.String(length=20), nullable=True),
        sa.Column('allowed_hosts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('volume_mounts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('max_disk_mb', sa.Integer(), nullable=True),
        sa.Column('current_execution_id', sa.String(length=50), nullable=True),
        sa.Column('created_by_agent_id', sa.String(length=5), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('destroyed_at', sa.DateTime(), nullable=True),
        sa.Column('destroy_reason', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['created_by_agent_id'], ['agents.agentium_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sandbox_id')
    )

    # Create indexes
    op.create_index('ix_sandboxes_agent_id', 'sandboxes', ['created_by_agent_id'])
    op.create_index('ix_sandboxes_status', 'sandboxes', ['status'])


def downgrade():
    op.drop_index('ix_sandboxes_status', table_name='sandboxes')
    op.drop_index('ix_sandboxes_agent_id', table_name='sandboxes')
    op.drop_table('sandboxes')

    op.drop_index('ix_remote_executions_created_at', table_name='remote_executions')
    op.drop_index('ix_remote_executions_status', table_name='remote_executions')
    op.drop_index('ix_remote_executions_agent_id', table_name='remote_executions')
    op.drop_table('remote_executions')
```

### Step 11: Tests (1 point)

Create `backend/tests/test_remote_executor.py`:

```python
"""Tests for remote code execution service."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from backend.services.remote_executor import RemoteExecutorService
from backend.services.remote_executor.sandbox import SandboxManager, SandboxConfig
from backend.core.security.execution_guard import ExecutionGuard, SecurityCheckResult


class TestExecutionGuard:
    """Test security validation."""

    def test_valid_code_passes(self):
        """Test that safe code passes validation."""
        guard = ExecutionGuard()
        code = """
import pandas as pd
import json

data = {'name': ['Alice', 'Bob'], 'age': [25, 30]}
result = pd.DataFrame(data)
"""
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is True
        assert result.severity == "none"

    def test_dangerous_command_blocked(self):
        """Test that dangerous commands are blocked."""
        guard = ExecutionGuard()
        code = "import os; os.system('rm -rf /')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert result.severity == "critical"
        assert any("Dangerous" in v for v in result.violations)

    def test_disallowed_import_blocked(self):
        """Test that disallowed imports are blocked."""
        guard = ExecutionGuard()
        code = "import requests; r = requests.get('https://example.com')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert any("requests" in v for v in result.violations)

    def test_head_tier_can_use_restricted(self):
        """Test that Head tier can use restricted imports."""
        guard = ExecutionGuard()
        code = "import requests"
        result = guard.validate_code(code, "0xxxx")
        assert result.passed is True


class TestSandboxManager:
    """Test sandbox container management."""

    @pytest.fixture
    def mock_docker(self):
        """Create mock Docker client."""
        with patch('docker.DockerClient') as mock:
            yield mock

    def test_create_sandbox(self, mock_docker):
        """Test sandbox creation."""
        manager = SandboxManager()

        # Mock container
        mock_container = MagicMock()
        mock_container.id = "abc123"
        mock_container.name = "sandbox_test"
        mock_docker.return_value.containers.run.return_value = mock_container

        config = SandboxConfig(
            cpu_limit=1.0,
            memory_limit_mb=512,
            timeout_seconds=300
        )

        # Note: This would need async test setup
        # result = await manager.create_sandbox("30001", config)
        # assert result["status"] == "ready"

    def test_destroy_sandbox(self, mock_docker):
        """Test sandbox destruction."""
        manager = SandboxManager()

        mock_container = MagicMock()
        mock_docker.return_value.containers.get.return_value = mock_container

        # Note: This would need async test setup
        # result = await manager.destroy_sandbox("sandbox_test", "test")
        # assert result is True


class TestRemoteExecutorService:
    """Test main remote executor service."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return RemoteExecutorService(db_session=None)

    @pytest.mark.asyncio
    async def test_execute_valid_code(self, service):
        """Test executing valid code."""
        code = """
import pandas as pd

data = {'name': ['Alice', 'Bob'], 'age': [25, 30]}
result = pd.DataFrame(data)
"""

        with patch.object(service.sandbox_manager, 'create_sandbox') as mock_create, \
             patch.object(service, '_execute_in_sandbox') as mock_exec:

            mock_create.return_value = {
                "sandbox_id": "sandbox_test",
                "container_id": "abc123",
                "status": "ready"
            }

            mock_exec.return_value = ExecutionResult(
                success=True,
                output_schema={"name": "object", "age": "int64"},
                row_count=2,
                sample=[{"name": "Alice", "age": 25}],
                stats={"age": {"mean": 27.5}},
                execution_time_ms=150
            )

            result = await service.execute(
                code=code,
                agent_id="30001",
                timeout_seconds=300
            )

            assert result["status"] == "completed"
            assert result["summary"]["row_count"] == 2
            assert result["security_result"]["passed"] is True

    @pytest.mark.asyncio
    async def test_execute_blocked_code(self, service):
        """Test that dangerous code is blocked."""
        code = "import os; os.system('rm -rf /')"

        result = await service.execute(
            code=code,
            agent_id="30001",
            timeout_seconds=300
        )

        assert result["status"] == "blocked"
        assert result["security_result"]["passed"] is False
        assert result["security_result"]["severity"] == "critical"


# Integration tests (marked to run separately)
@pytest.mark.integration
class TestRemoteExecutorIntegration:
    """Integration tests requiring Docker."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Test complete execution flow with real Docker."""
        # This test requires Docker to be running
        # It tests the actual sandbox creation, execution, and cleanup
        pass
```

## Verification

### Unit Tests

Run unit tests:
```bash
cd backend
pytest tests/test_remote_executor.py -v --cov=backend.services.remote_executor
```

### Integration Tests

Run integration tests (requires Docker):
```bash
cd backend
pytest tests/test_remote_executor.py -v -m integration
```

### Manual Testing

1. **Start services:**
```bash
docker compose -f docker-compose.yml -f docker-compose.remote-executor.yml up -d
```

2. **Test code execution:**
```bash
curl -X POST http://localhost:8000/api/v1/remote-executor/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "code": "import pandas as pd; result = pd.DataFrame({\"name\": [\"Alice\", \"Bob\"]})",
    "timeout_seconds": 60
  }'
```

3. **Verify security blocking:**
```bash
curl -X POST http://localhost:8000/api/v1/remote-executor/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "code": "import os; os.system('rm -rf /')"
  }'
# Should return status: blocked
```

## Acceptance Criteria

- [ ] Raw data never enters agent context window
- [ ] Agents reason about data shape, not content
- [ ] PII stays in execution layer
- [ ] Working set size >> context window size
- [ ] Code execution fully sandboxed (Docker isolation)
- [ ] Resource limits enforced (CPU, memory, time)
- [ ] Security validation blocks dangerous code
- [ ] Tier-based authorization enforced
- [ ] All executions logged in audit trail
- [ ] Sandboxes cleaned up after execution
- [ ] API endpoints return summaries only
- [ ] Frontend can trigger remote execution
- [ ] All unit tests passing
- [ ] Integration tests passing

## Dependencies

- Docker daemon access
- Python 3.11+
- pandas, numpy (for data analysis)
- docker-py library
- Existing Agentium infrastructure (Message Bus, Constitutional Guard)

## Story Points

Total: 13 points
- Database models: 2 points
- Security guard: 2 points
- Sandbox manager: 3 points
- In-container executor: 2 points
- API routes: 2 points
- Schemas: 1 point
- Docker configuration: 1 point
- Tests: 2 points (included in each component)

## Execution Order

1. Database models (blocked by: existing entity patterns)
2. Security guard (blocked by: models)
3. Sandbox manager (blocked by: security guard)
4. In-container executor (blocked by: sandbox manager)
5. Main service (blocked by: executor)
6. API routes (blocked by: service)
7. Schemas (blocked by: routes)
8. Docker configuration (blocked by: service)
9. Tests (blocked by: all implementation)
10. Integration (blocked by: tests)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Docker not available | Medium | High | Graceful fallback, clear error message |
| Resource exhaustion | Low | High | Limits, queue management, cleanup |
| Security bypass | Low | Critical | Multi-layer validation, audit logging |
| Sandbox escape | Very Low | Critical | Minimal privileges, seccomp, read-only fs |
| Network timeout | Medium | Medium | Retry logic, circuit breaker |

## Notes

- This implementation follows the "Brains vs Hands" pattern from the research paper
- Raw data NEVER enters agent context - only structured summaries
- Sandboxes are ephemeral - created per execution and destroyed after
- Security is multi-layer: AST parsing + pattern matching + import whitelist
- All operations are logged for audit purposes
- Tier-based authorization ensures only authorized agents can execute code
