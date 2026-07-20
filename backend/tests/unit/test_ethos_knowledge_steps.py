"""Task 6 (6.7): every agent type's working_method must carry explicit
Knowledge Retrieval and Knowledge Update steps."""


def test_working_methods_have_explicit_knowledge_steps():
    from backend.models.entities.agents import DEFAULT_WORKING_METHODS
    for agent_type, text in DEFAULT_WORKING_METHODS.items():
        assert "Knowledge Retrieval" in text, f"{agent_type} missing retrieval step"
        assert "Knowledge Update" in text, f"{agent_type} missing update step"
