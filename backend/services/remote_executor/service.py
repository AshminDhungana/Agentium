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
from datetime import datetime
from typing import Optional, Dict, Any, List

from backend.services.remote_executor.sandbox import SandboxManager, SandboxConfig
from backend.services.remote_executor.executor import ExecutionResult
from backend.core.security.execution_guard import execution_guard

logger = logging.getLogger(__name__)


class RemoteExecutorService:
    """
    Service for executing code in isolated sandboxes.

    Key Principle: Raw data NEVER enters agent context.
    Agents receive only structured summaries (schema, stats, samples).
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
                "execution_time_ms": result.execution_time_ms
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
                )
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
        import subprocess as sp

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Write code to file
                code_file = os.path.join(tmpdir, "code.py")
                with open(code_file, 'w') as f:
                    f.write(code)

                # Write input data to file
                input_file = os.path.join(tmpdir, "input.json")
                with open(input_file, 'w') as f:
                    json.dump(input_data if input_data is not None else {}, f)

                # Write executor script that runs inside the container
                executor_script = self._build_executor_script()
                executor_file = os.path.join(tmpdir, "executor.py")
                with open(executor_file, 'w') as f:
                    f.write(executor_script)

                # Copy files to container
                for src, dst in [
                    (code_file, f"{sandbox_id}:/tmp/code.py"),
                    (input_file, f"{sandbox_id}:/tmp/input.json"),
                    (executor_file, f"{sandbox_id}:/tmp/executor.py"),
                ]:
                    sp.run(
                        ["docker", "cp", src, dst],
                        check=True,
                        capture_output=True
                    )

                # Install dependencies inside container if needed
                if dependencies:
                    dep_str = " ".join(dependencies)
                    sp.run(
                        [
                            "docker", "exec", sandbox_id,
                            "pip", "install", "--quiet", *dependencies
                        ],
                        capture_output=True,
                        timeout=120
                    )

                # Execute in container
                proc = sp.run(
                    ["docker", "exec", sandbox_id, "python", "/tmp/executor.py"],
                    capture_output=True,
                    timeout=timeout
                )

                # Parse result
                if proc.returncode == 0:
                    output = json.loads(proc.stdout.decode('utf-8'))
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
                        error_message=f"Container execution failed: {proc.stderr.decode('utf-8')}",
                        execution_time_ms=0
                    )

        except sp.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output_schema={},
                error_message=f"Execution timed out after {timeout} seconds",
                execution_time_ms=timeout * 1000
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
import json
import time
import traceback

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
        'execution_time_ms': int((time.time() - start_time) * 1000) if 'start_time' in dir() else 0,
        'output_schema': {},
        'row_count': 0,
        'sample': [],
        'stats': {}
    }
    print(json.dumps(output))
'''
