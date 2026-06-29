# LLM Client Abstraction — Subagent-Driven Development Progress

## Tasks
- [ ] Task 1-4 (Combined): Build `LLMClient` core class at `backend/core/llm_client.py`
  - Scaffold (imports, ProviderCircuitBreaker, LLMClient init + helpers)
  - Implement `generate()` with retry, failover, CB
  - Implement `generate_with_tools()` with retry, failover, CB
  - Expose circuit breaker metrics
- [ ] Task 5: Wire `agent_orchestrator.py` to use `LLMClient`
- [ ] Task 6: Wire `auto_delegation_service.py` to use `LLMClient`
- [ ] Task 7: Wire `reincarnation_service.py` to use `LLMClient`
- [ ] Task 8: Unit tests for `LLMClient`
- [ ] Task 9: Regression test run

## Ledger
