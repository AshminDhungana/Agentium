"""In-container code execution handler.

This module is designed to run INSIDE the sandbox container.
It executes user code, analyses results, and returns structured summaries.
Raw data NEVER leaves this module – only schema, stats, and small samples.
"""
import sys
import json
import time
import traceback
from typing import Any, Dict, List
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr


class ExecutionResult:
    """Result of code execution – contains summary only."""

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

    # Sample (max 3 rows) – convert to dict
    sample_rows = min(3, row_count)
    sample = df.head(sample_rows).to_dict('records')

    # Stats (describe for numeric columns)
    try:
        stats_df = df.describe()
        stats = {col: stats_df[col].to_dict() for col in stats_df.columns}
    except Exception:
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

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the code
            exec(code, {}, local_vars)  # noqa: S102 – sandboxed execution

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

        # No result variable – just executed for side effects
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
import json

data = {'name': ['Alice', 'Bob', 'Charlie'], 'age': [25, 30, 35]}
result = data
"""

    result = execute_code(test_code)
    print(json.dumps(result.to_dict(), indent=2))
