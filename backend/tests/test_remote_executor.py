"""Tests for remote code execution service.

Covers:
- ExecutionGuard: security validation
- RemoteExecutorService: blocked code detection
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from backend.core.security.execution_guard import ExecutionGuard, SecurityCheckResult
from backend.services.remote_executor.executor import ExecutionResult, execute_code


# ──────────────────────────────────────────────────
# ExecutionGuard Tests
# ──────────────────────────────────────────────────

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
        assert len(result.violations) == 0

    def test_stdlib_imports_pass(self):
        """Test that standard library imports pass."""
        guard = ExecutionGuard()
        code = """
import json
import re
import math
import datetime
import collections
"""
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is True

    def test_dangerous_os_system_blocked(self):
        """Test that os.system() is blocked."""
        guard = ExecutionGuard()
        code = "import os; os.system('rm -rf /')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert result.severity == "critical"
        assert any("Dangerous" in v for v in result.violations)

    def test_dangerous_subprocess_blocked(self):
        """Test that subprocess calls are blocked."""
        guard = ExecutionGuard()
        code = "import subprocess; subprocess.run(['ls'])"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False

    def test_dangerous_eval_blocked(self):
        """Test that eval() is blocked."""
        guard = ExecutionGuard()
        code = "eval('1+1')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False

    def test_dangerous_exec_blocked(self):
        """Test that exec() is blocked."""
        guard = ExecutionGuard()
        code = "exec('print(1)')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False

    def test_disallowed_import_blocked(self):
        """Test that disallowed imports are blocked."""
        guard = ExecutionGuard()
        code = "import requests; r = requests.get('https://example.com')"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert any("requests" in v for v in result.violations)

    def test_head_tier_can_use_restricted(self):
        """Test that Head tier (0xxxx) can use restricted imports."""
        guard = ExecutionGuard()
        code = "import requests"
        result = guard.validate_code(code, "0xxxx")
        assert result.passed is True

    def test_unknown_import_blocked(self):
        """Test that completely unknown imports are blocked."""
        guard = ExecutionGuard()
        code = "import some_weird_package"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert any("UNKNOWN" in v for v in result.violations)

    def test_syntax_error_detected(self):
        """Test that syntax errors are caught."""
        guard = ExecutionGuard()
        code = "def foo(\n  invalid syntax here"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert any("SYNTAX" in v for v in result.violations)

    def test_multiple_violations(self):
        """Test handling multiple violations."""
        guard = ExecutionGuard()
        code = """
import os
os.system('rm -rf /')
import requests
import unknown_pkg
"""
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is False
        assert len(result.violations) >= 2
        assert result.severity == "critical"

    def test_recommendation_generated(self):
        """Test that recommendations are generated for violations."""
        guard = ExecutionGuard()
        code = "import os; os.system('test')"
        result = guard.validate_code(code, "3xxxx")
        assert result.recommendation is not None
        assert len(result.recommendation) > 0

    def test_from_import_validated(self):
        """Test that 'from X import Y' is validated."""
        guard = ExecutionGuard()
        code = "from collections import defaultdict"
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is True

    def test_data_science_imports_allowed(self):
        """Test that data science imports pass."""
        guard = ExecutionGuard()
        code = """
import numpy as np
import pandas as pd
"""
        result = guard.validate_code(code, "3xxxx")
        assert result.passed is True

    def test_empty_code_passes(self):
        """Test that empty code passes syntax check but produces nothing."""
        guard = ExecutionGuard()
        result = guard.validate_code("", "3xxxx")
        assert result.passed is True


# ──────────────────────────────────────────────────
# ExecutionResult Tests
# ──────────────────────────────────────────────────

class TestExecutionResult:
    """Test execution result serialization."""

    def test_to_dict_basic(self):
        """Test basic to_dict output."""
        result = ExecutionResult(
            success=True,
            output_schema={"name": "object", "age": "int64"},
            row_count=2,
            sample=[{"name": "Alice", "age": 25}],
            stats={"age": {"mean": 27.5}},
            execution_time_ms=150,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["row_count"] == 2
        assert d["execution_time_ms"] == 150

    def test_to_dict_truncates_output(self):
        """Test that stdout/stderr are truncated at 1000 chars."""
        result = ExecutionResult(
            success=True,
            output_schema={},
            stdout="x" * 2000,
            stderr="y" * 2000,
        )
        d = result.to_dict()
        assert len(d["stdout"]) == 1000
        assert len(d["stderr"]) == 1000

    def test_failed_result(self):
        """Test failed execution result."""
        result = ExecutionResult(
            success=False,
            output_schema={},
            error_message="Division by zero",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error_message"] == "Division by zero"


# ──────────────────────────────────────────────────
# In-Container Executor Tests
# ──────────────────────────────────────────────────

class TestInContainerExecutor:
    """Test the execute_code function (runs locally, not in Docker)."""

    def test_simple_computation(self):
        """Test executing simple math."""
        code = "result = 2 + 2"
        result = execute_code(code)
        assert result.success is True
        assert result.row_count == 1

    def test_dict_result(self):
        """Test executing code that returns a dict."""
        code = "result = {'a': 1, 'b': 2, 'c': 3}"
        result = execute_code(code)
        assert result.success is True
        assert result.row_count == 3

    def test_list_result(self):
        """Test executing code that returns a list."""
        code = "result = [1, 2, 3, 4, 5]"
        result = execute_code(code)
        assert result.success is True
        assert result.row_count == 5

    def test_no_result_variable(self):
        """Test code without a result variable."""
        code = "x = 42"
        result = execute_code(code)
        assert result.success is True
        assert result.row_count == 0

    def test_runtime_error_caught(self):
        """Test that runtime errors are caught."""
        code = "result = 1 / 0"
        result = execute_code(code)
        assert result.success is False
        assert result.error_message is not None
        assert "ZeroDivisionError" in result.error_message

    def test_input_data_available(self):
        """Test that input_data is available in code."""
        code = "result = input_data['value'] * 2"
        result = execute_code(code, input_data={"value": 21})
        assert result.success is True

    def test_stdout_captured(self):
        """Test that print output is captured."""
        code = 'print("hello world")\nresult = 42'
        result = execute_code(code)
        assert result.success is True
        assert "hello world" in result.stdout


# ──────────────────────────────────────────────────
# RemoteExecutorService Tests
# ──────────────────────────────────────────────────

class TestRemoteExecutorService:
    """Test main remote executor service."""

    @pytest.mark.asyncio
    async def test_execute_blocked_code(self):
        """Test that dangerous code is blocked before sandbox creation."""
        from backend.services.remote_executor.service import RemoteExecutorService

        service = RemoteExecutorService(db_session=None)
        code = "import os; os.system('rm -rf /')"

        result = await service.execute(
            code=code,
            agent_id="30001",
            timeout_seconds=300,
        )

        assert result["status"] == "blocked"
        assert result["security_result"]["passed"] is False
        assert result["security_result"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_execute_valid_code_blocked_by_docker(self):
        """Test valid code returns failure when Docker is unavailable."""
        from backend.services.remote_executor.service import RemoteExecutorService

        service = RemoteExecutorService(db_session=None)
        code = """
import json
result = {"message": "hello"}
"""
        result = await service.execute(
            code=code,
            agent_id="30001",
            timeout_seconds=60,
        )

        # Without Docker, sandbox creation fails
        assert result["status"] == "failed"
        assert result["error"] is not None
