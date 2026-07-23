"""Remote Code Execution Service – Brains vs Hands separation.

Key Principle: Raw data NEVER enters agent context.
Agents receive only structured summaries (schema, stats, samples).

Architecture:
    Agent (Brain) → Writes Code → Remote Executor → Returns Summary
         ↑                                               ↓
         └────────────── Receives Summary ←────────────┘
"""
import os
import json
import uuid
import logging
import subprocess
import subprocess as sp
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.services.remote_executor.sandbox import SandboxManager, SandboxConfig
from backend.services.remote_executor.executor import ExecutionResult
from backend.core.security.execution_guard import execution_guard
from backend.tools._workspace import (
    workspace_enabled as _ws_enabled,
    ensure_agent_workspace,
    host_visible_path,
    _manifest,
)

logger = logging.getLogger(__name__)


class RemoteExecutorService:
    """
    Service for executing code in isolated sandboxes.

    Key Principle: Raw data NEVER enters agent context.
    Agents receive only structured summaries (schema, stats, samples).
    """

    def __init__(self, db_session=None):
        """Initialize the remote executor service.

        Args:
            db_session: Optional SQLAlchemy database session.

        Returns:
            None

        Raises:
            None
        """
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

        Raises:
            None
        """
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        start_time = datetime.utcnow()

        # Step 1: Security validation
        agent_tier = agent_id[:1] if agent_id else "3"
        security_result = self.guard.validate_code(code, agent_tier)

        if not security_result.passed:
            logger.warning(
                f"Code security check failed for {execution_id}: {security_result.violations}"
            )
            return {
                "execution_id": execution_id,
                "status": "blocked",
                "summary": None,
                "error": None,
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

        # Step 2: Create database record (if DB available)
        record = None
        if self.db:
            from backend.models.entities.remote_execution import (
                RemoteExecutionRecord, ExecutionStatus
            )
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
        sandbox_id = None
        host_dir = None
        workspace_path = None
        artifacts: list = []

        # Enable host workspace persistence when allowed and we have a task id.
        # If the host dir cannot be created, degrade gracefully (no workspace,
        # summary-only) instead of aborting the whole execution.
        if _ws_enabled() and task_id:
            try:
                host_dir = ensure_agent_workspace(agent_id, task_id)
                config.workspace_enabled = True
            except Exception as ws_err:
                logger.warning(f"workspace dir creation failed for {execution_id}: {ws_err}")
                host_dir = None

        try:
            # Update status
            if self.db and record:
                from backend.models.entities.remote_execution import ExecutionStatus
                record.status = ExecutionStatus.RUNNING
                record.started_at = datetime.utcnow()
                self.db.commit()

            # Create sandbox
            sandbox = await self.sandbox_manager.create_sandbox(agent_id, config)
            sandbox_id = sandbox["sandbox_id"]

            if self.db and record:
                record.sandbox_id = sandbox_id
                record.sandbox_container_id = sandbox["container_id"]
                self.db.commit()

            # Execute code in sandbox
            result = await self._execute_in_sandbox(
                sandbox_id=sandbox_id,
                code=code,
                input_data=input_data,
                dependencies=dependencies,
                timeout=timeout_seconds
            )

            # Update record with results
            if self.db and record:
                from backend.models.entities.remote_execution import ExecutionStatus
                record.status = (
                    ExecutionStatus.COMPLETED if result.success
                    else ExecutionStatus.FAILED
                )
                record.completed_at = datetime.utcnow()
                record.summary = result.to_dict()
                record.execution_time_ms = result.execution_time_ms
                self.db.commit()

            # Copy artifacts from the sandbox /workspace using docker-py get_archive.
            if config.workspace_enabled and host_dir:
                try:
                    container = self.sandbox_manager.docker_client.containers.get(sandbox_id)
                    # Get the workspace directory as a tar archive
                    tar_data, stat = container.get_archive("/workspace")
                    
                    # Extract the tar archive to host_dir, stripping the leading 'workspace/' directory
                    import tarfile
                    import io
                    tar_stream = io.BytesIO()
                    for chunk in tar_data:
                        tar_stream.write(chunk)
                    tar_stream.seek(0)
                    
                    with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                        # Extract each member, stripping the leading 'workspace/' component
                        for member in tar.getmembers():
                            if member.name.startswith("workspace/"):
                                # Strip the first path component
                                member.name = member.name[len("workspace/"):]
                                if member.name:  # Skip the directory entry itself
                                    tar.extract(member, host_dir)
                    
                    artifacts = _manifest(host_dir)
                    workspace_path = host_visible_path(host_dir)
                except Exception as cp_err:  # pragma: no cover - best-effort copy
                    logger.warning(f"workspace get_archive failed for {execution_id}: {cp_err}")

            # Cleanup sandbox
            await self.sandbox_manager.destroy_sandbox(sandbox_id, "execution_complete")

            # Return summary to agent (NEVER raw data)
            return {
                "execution_id": execution_id,
                "status": "completed" if result.success else "failed",
                "summary": result.to_dict(),
                "error": result.error_message,
                "security_result": {
                    "passed": True,
                    "violations": [],
                    "severity": "none",
                    "recommendation": None
                },
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": result.execution_time_ms,
                "workspace_path": workspace_path,
                "artifacts": artifacts,
            }

        except Exception as e:
            logger.error(f"Execution failed for {execution_id}: {e}")

            # Update record
            if self.db and record:
                from backend.models.entities.remote_execution import ExecutionStatus
                record.status = ExecutionStatus.FAILED
                record.completed_at = datetime.utcnow()
                record.error_message = str(e)
                self.db.commit()

            # Cleanup if sandbox exists
            if sandbox_id:
                await self.sandbox_manager.destroy_sandbox(sandbox_id, "execution_failed")

            return {
                "execution_id": execution_id,
                "status": "failed",
                "summary": None,
                "error": str(e),
                "security_result": {
                    "passed": True,
                    "violations": [],
                    "severity": "none",
                    "recommendation": None
                },
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "execution_time_ms": int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                ),
                "workspace_path": workspace_path,
                "artifacts": artifacts,
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

        This method copies the executor script and code into the container
        using docker-py put_archive, runs it, and retrieves the results.
        """
        import tempfile
        import tarfile
        import io

        try:
            container = self.sandbox_manager.docker_client.containers.get(sandbox_id)

            # Create tar archives for code, input, and executor
            def create_tar(filename: str, content: bytes) -> bytes:
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                    tarinfo = tarfile.TarInfo(name=filename)
                    tarinfo.size = len(content)
                    tar.addfile(tarinfo, io.BytesIO(content))
                tar_stream.seek(0)
                return tar_stream.read()

            # Copy code.py
            code_tar = create_tar("code.py", code.encode('utf-8'))
            container.put_archive("/tmp", code_tar)

            # Copy input.json
            input_tar = create_tar("input.json", json.dumps(input_data if input_data is not None else {}).encode('utf-8'))
            container.put_archive("/tmp", input_tar)

            # Copy executor.py
            executor_script = self._build_executor_script()
            executor_tar = create_tar("executor.py", executor_script.encode('utf-8'))
            container.put_archive("/tmp", executor_tar)

            # Install dependencies inside container if needed
            if dependencies:
                result = container.exec_run(
                    ["pip", "install", "--quiet", *dependencies],
                    timeout=120
                )
                if result.exit_code != 0:
                    logger.warning(f"Dependency install failed: {result.output.decode('utf-8')}")

            # Execute in container
            proc = container.exec_run(
                ["python", "/tmp/executor.py"]
            )

            # Parse result
            if proc.exit_code == 0:
                output = json.loads(proc.output.decode('utf-8'))
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
                    error_message=f"Container execution failed: {proc.output.decode('utf-8')}",
                    execution_time_ms=0
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output_schema={},
                error_message=f"Execution error: {str(e)}",
                execution_time_ms=0
            )

    @staticmethod
    def _build_executor_script() -> str:
        """Build the Python script that runs inside the container."""
        return '''
import sys
import os
import json
import time
import traceback
import logging

logger = logging.getLogger("agentium.executor")

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


# Read input data
with open('/tmp/input.json', 'r') as f:
    input_data = json.load(f)

# Read and execute code
exec_globals = {'input_data': input_data, 'result': None}
exec_locals = {}

try:
    # Route generated files into the writable /workspace so they can be copied
    # to the host after execution. Tolerate sandboxes without the mount.
    try:
        os.chdir('/workspace')
    except Exception:
        pass

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

    # Print JSON result to stdout for the host to capture
    print(json.dumps(output))

except Exception as e:
    output = {
        'success': False,
        'error': str(e),
        'traceback': traceback.format_exc(),
        'execution_time_ms': int((time.time() - start_time) * 1000) if 'start_time' in dir() else 0,
        'output_schema': {},
        'row_count': 0,
        'sample': [],
        'stats': {}
    }
    print(json.dumps(output))
'''
