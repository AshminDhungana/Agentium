# backend/tests/unit/test_execution_guard_writes.py
"""The execution guard must permit file writes inside the isolated sandbox.

Generated artifacts (websites, reports, etc.) are produced by agents via
plain ``open(..., 'w')`` / ``pathlib`` writes. The sandbox has a read-only
rootfs, so writes are contained to /tmp and /workspace — blocking them would
make the host-workspace feature non-functional. This test locks that contract.
"""
import pytest

from backend.core.security.execution_guard import ExecutionGuard


@pytest.fixture
def guard():
    return ExecutionGuard()


def test_write_open_is_allowed(guard):
    code = "open('widget.html', 'w').write('<h1>hi</h1>')"
    res = guard.validate_code(code, agent_tier="3xxxx")
    assert res.passed is True, res.violations
    assert not any("open" in v for v in res.violations)


def test_pathlib_write_is_allowed(guard):
    code = "from pathlib import Path; Path('out.csv').write_text('a,b')"
    res = guard.validate_code(code, agent_tier="3xxxx")
    assert res.passed is True, res.violations


def test_subprocess_still_blocked(guard):
    code = "import subprocess; subprocess.run(['ls'])"
    res = guard.validate_code(code, agent_tier="3xxxx")
    assert res.passed is False
    assert any("subprocess" in v for v in res.violations)


def test_rm_rf_still_blocked(guard):
    code = "import os; os.system('rm -rf /')"
    res = guard.validate_code(code, agent_tier="3xxxx")
    assert res.passed is False
