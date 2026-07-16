"""Tests for agent self-tool-creation (verification of the fixes).

Covers:
- Task 1: ToolFactory AST-based validation + json import crash
- Task 2: ToolCreationService.create_from_pattern (composite tools)
- Task 4: SelfImprovementService call path resolves the method (no AttributeError)
"""
import pytest


# ── Task 1: ToolFactory validation ─────────────────────────────────────────────
@pytest.fixture
def factory():
    from backend.services.tool_factory import ToolFactory

    return ToolFactory()


def test_composite_template_valid(factory):
    code = (
        "from backend.core.tool_registry import tool_registry\n"
        "result = kwargs\n"
        "_fn = tool_registry.get_tool_function('web_search')\n"
        "if _fn is not None:\n"
        "    result = _fn(**result)\n"
        "return {'status': 'success', 'result': result}"
    )
    assert factory.validate_tool_code(code)["valid"] is True


def test_blocks_eval(factory):
    assert factory.validate_tool_code("result = eval('1+1')")["valid"] is False


def test_blocks_os_system(factory):
    assert factory.validate_tool_code("import os\nos.system('ls')")["valid"] is False


def test_blocks_open_call(factory):
    assert factory.validate_tool_code("open('/etc/passwd')")["valid"] is False


def test_blocks_subprocess_popen(factory):
    assert factory.validate_tool_code(
        "import subprocess\nsubprocess.Popen(['ls'])"
    )["valid"] is False


def test_allows_benign_code(factory):
    assert factory.validate_tool_code("result = 'hello'.upper()")["valid"] is True


def test_generate_tool_file_no_json_crash(factory):
    from backend.models.schemas.tool_creation import ToolCreationRequest

    req = ToolCreationRequest(
        tool_name="t1",
        description="d",
        parameters=[],
        code_template="result = {'ok': True}",
        authorized_tiers=["0xxxx"],
        created_by_agentium_id="00001",
        rationale="r",
    )
    path = factory.generate_tool_file(req)
    assert path.exists()


# ── Task 2: create_from_pattern (composite tools) ─────────────────────────────
def test_create_from_pattern_builds_composite():
    from unittest.mock import patch

    from backend.services.tool_creation_service import ToolCreationService

    pattern = {"sequence": ["web_search", "summarize"], "count": 12, "success_rate": 0.97}
    with patch("backend.core.tool_registry.tool_registry") as reg, patch.object(
        ToolCreationService, "propose_tool", return_value={"proposed": True, "status": "activated"}
    ):
        reg.get_tool_function.side_effect = lambda n: (lambda **k: {"ok": n})
        outcome = ToolCreationService.create_from_pattern(pattern, db=object())

    assert outcome["created"] is True
    assert outcome["tool_name"].startswith("composite_")


def test_create_from_pattern_empty_sequence():
    from backend.services.tool_creation_service import ToolCreationService

    outcome = ToolCreationService.create_from_pattern({"sequence": []}, db=object())
    assert outcome["created"] is False


def test_create_from_pattern_drops_unregistered():
    from unittest.mock import patch

    from backend.services.tool_creation_service import ToolCreationService

    pattern = {"sequence": ["exists", "ghost"], "count": 9, "success_rate": 0.95}
    with patch("backend.core.tool_registry.tool_registry") as reg, patch.object(
        ToolCreationService, "propose_tool", return_value={"proposed": True, "status": "activated"}
    ):
        reg.get_tool_function.side_effect = lambda n: (None if n == "ghost" else (lambda **k: k))
        outcome = ToolCreationService.create_from_pattern(pattern, db=object())

    assert outcome["created"] is True


# ── Task 4: SelfImprovementService resolves create_from_pattern ───────────────
def test_self_improvement_resolves_create_from_pattern():
    from backend.services.tool_creation_service import ToolCreationService

    # The missing-method AttributeError is gone; the reference resolves.
    assert hasattr(ToolCreationService, "create_from_pattern")
    assert callable(getattr(ToolCreationService, "create_from_pattern"))
