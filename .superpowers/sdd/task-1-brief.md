# Task Brief: Build LLMClient Core Class

## Context
This is Task 1-4 (combined) of the LLM Client Abstraction plan for Phase 18.3 of the Agentium project. We are extracting duplicated provider retry/failover logic from three service files into a single `LLMClient` class at `backend/core/llm_client.py`. This combined task builds the entire `llm_client.py` file from scratch.

## Files
- **Create**: `backend/core/llm_client.py`

## Requirements

### Part A: Scaffold (ProviderCircuitBreaker + LLMClient init + internal helpers)
Create the file with all imports and the `ProviderCircuitBreaker` class:
- States: `closed`, `open`, `half_open`
- Threshold: 5 consecutive failures → `open`
- Recovery: 60 seconds → `half_open`
- Methods: `record_success()`, `record_failure()`, `can_execute()`, `get_metrics()`

Create `LLMClient` class with:
- Init: `db`, `max_retries=3`, `base_retry_delay=1.0`, `max_retry_delay=30.0`
- Class-level `_circuit_breakers: Dict[str, ProviderCircuitBreaker] = {}`
- Internal helpers: `_get_cb()`, `_is_rate_limit()`, `_is_retryable()`, `_delay()`, `_track_tokens_and_cost()`

### Part B: Implement `generate()`
Signature:
```python
async def generate(
    self, agent, user_message: str, *,
    user_id: str = "sovereign",
    config_id: Optional[str] = None,
    system_prompt_override: Optional[str] = None,
    max_retries: Optional[int] = None,
    fallback_configs: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
```

Behavior:
1. Build `configs_to_try` list from `config_id` + `fallback_configs`
2. If no configs, resolve from `agent.preferred_config_id` or use `None`
3. For each config in the list:
   - Check circuit breaker (skip if OPEN)
   - For each retry attempt:
     - Call `ModelService.generate_with_agent()`
     - On success: record CB success, call `_track_tokens_and_cost()`, add `provider_config_id` to result
     - On failure: record CB failure, check if retryable, delay with exponential backoff if so, else move to next fallback
4. If all exhausted: raise `RuntimeError` with last error

### Part C: Implement `generate_with_tools()`
Signature:
```python
async def generate_with_tools(
    self, agent, user_message: str, *,
    db, config_id: Optional[str] = None,
    system_prompt_override: Optional[str] = None,
    agent_tier: Optional[str] = None,
    task_id: Optional[str] = None,
    max_tool_iterations: int = 10,
    max_retries: Optional[int] = None,
    fallback_configs: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
```

Behavior: Same retry/failover/CB pattern as `generate()`, but calls `ModelService.generate_with_agent_tools()` instead. Also forwards `agent_tier`, `task_id`, `max_tool_iterations`.

### Part D: Expose Circuit Breaker Metrics
Methods:
```python
def get_circuit_breaker_metrics(self, config_id: Optional[str] = None) -> Dict[str, Any]:
    # Return CB metrics for one or all configs

@classmethod
def reset_circuit_breaker(cls, config_id: str) -> None:
    # Manually reset a circuit breaker
```

## Global Constraints
- No new dependencies — use `asyncio.sleep` for delay, no `tenacity` needed
- Maintain backward compatibility — `ModelService` methods are NOT removed
- All errors from LLM calls should be handled and either retried or re-raised as `RuntimeError`
- Token tracking: on success, call `api_key_manager.record_spend()` and `token_optimizer.update_token_count()`

## Verification
After writing the file, verify:
```bash
cd backend && python -c "from core.llm_client import LLMClient, ProviderCircuitBreaker; print('OK')"
```
Expected: `OK` (no import errors)

## Commit
Commit after verification:
```bash
git add backend/core/llm_client.py
git commit -m "feat(core): add LLMClient with retry, failover, circuit breaker, and token tracking"
```
