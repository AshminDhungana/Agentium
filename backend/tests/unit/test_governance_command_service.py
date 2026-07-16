"""
Offline unit tests for GovernanceCommandService.detect_command.

These tests exercise the deterministic parser ONLY — no database, no services.
"""

from backend.services.governance_command_service import GovernanceCommandService


def test_detect_spawn_task_agent_with_name():
    cmd = GovernanceCommandService.detect_command("spawn a task agent named Scout")
    assert cmd is not None
    assert cmd.kind == "spawn_task_agent"
    assert cmd.name == "Scout"


def test_detect_spawn_lead_agent():
    cmd = GovernanceCommandService.detect_command("Create a lead agent called Operations")
    assert cmd is not None
    assert cmd.kind == "spawn_lead_agent"
    assert cmd.name == "Operations"


def test_detect_create_task():
    cmd = GovernanceCommandService.detect_command("create a task: summarize Q3 report")
    assert cmd is not None
    assert cmd.kind == "create_task"
    assert "Q3 report" in cmd.description


def test_no_command_for_small_talk():
    assert GovernanceCommandService.detect_command("hello there") is None
    assert GovernanceCommandService.detect_command("") is None
