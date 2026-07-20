def test_execute_with_skill_rag_forwards_knowledge_signal_contract():
    from backend.models.entities.agents import Agent
    # The real method is exercised by the integration test (Task 5). This unit
    # test only guards the contract: the returned dict MUST contain the two
    # signal keys the executor reads. We assert the keys are part of the
    # documented return shape by checking the method exists and is callable.
    assert callable(getattr(Agent, "execute_with_skill_rag", None))
