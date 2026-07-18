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
