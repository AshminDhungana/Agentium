from unittest.mock import MagicMock

from backend.models.entities.user_config import ProviderType
from backend.services.prompt_template_manager import PromptTemplateManager


def test_workspace_hint_in_system_prompt():
    mgr = PromptTemplateManager()
    assert hasattr(mgr, "WORKSPACE_HINT")
    sp, _, _ = mgr.build_system_prompt(
        provider=ProviderType.OPENAI,
        model_name="gpt-4",
        task_description="create a file",
        agent_ethos=None,
        agent_tier=3,
    )
    assert "agentium-workspace" in sp


def test_working_method_injected_into_prompt_6_7():
    """Task 6.7: the Ethos working_method (with Knowledge Retrieval /
    Knowledge Update steps) must be surfaced in every agent's system prompt
    so the steps are part of the standard loop, not optional behavior."""
    mgr = PromptTemplateManager()
    ethos = MagicMock()
    ethos.mission_statement = "M"
    ethos.specialization = "general"
    ethos.behavioral_rules = "[]"
    ethos.working_method = (
        "2. Knowledge Retrieval: query ChromaDB before acting. "
        "5. Knowledge Update: store learnings to ChromaDB."
    )
    sp, _, _ = mgr.build_system_prompt(
        provider=ProviderType.OPENAI,
        model_name="gpt-4",
        task_description="do a task",
        agent_ethos=ethos,
        agent_tier=3,
    )
    assert "Your Standard Working Method" in sp
    assert "Knowledge Retrieval" in sp
    assert "Knowledge Update" in sp


def test_missing_working_method_does_not_inject_block():
    """When an Ethos has no working_method, no SOP block is appended."""
    mgr = PromptTemplateManager()
    ethos = MagicMock()
    ethos.mission_statement = "M"
    ethos.specialization = "general"
    ethos.behavioral_rules = "[]"
    ethos.working_method = ""
    sp, _, _ = mgr.build_system_prompt(
        provider=ProviderType.OPENAI,
        model_name="gpt-4",
        task_description="do a task",
        agent_ethos=ethos,
        agent_tier=3,
    )
    assert "Your Standard Working Method" not in sp
