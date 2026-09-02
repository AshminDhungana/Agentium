# Provider Error Handling — Design Specification

**Date:** 2026-09-02  
**Status:** Draft  
**Related TODO:** Section 5.6 (Model Provider & LLM Integration)

---

## 1. Problem Statement

The current LLM integration lacks robust provider error handling:

- **5.6.1** — 429 rate-limit errors don't respect `Retry-After` headers; only generic exponential backoff
- **5.6.2** — 5xx provider errors retry but without provider-specific guidance
- **5.6.3** — Invalid API keys produce generic error messages, not actionable guidance
- **5.6.4** — Provider timeouts can crash the request path without graceful degradation

---

## 2. Design Approach: Hybrid (Centralized Failover + Provider-Aware Retry Hints)

**Decision:** Approach 2 from brainstorming — `LLMClient` remains the single orchestrator for failover across configs; each provider implements `get_retry_hints(exception)` to return provider-specific retry guidance (including parsed `Retry-After` headers).

### Why Hybrid?

| Concern | Centralized (LLMClient) | Decentralized (Providers) | Hybrid (Chosen) |
|---------|------------------------|---------------------------|-----------------|
| Failover logic | ✅ Single place | ❌ Duplicated | ✅ Single place |
| Retry-After parsing | ❌ Generic only | ✅ Full access | ✅ Provider parses, client uses |
| Policy consistency | ✅ Guaranteed | ❌ Risk of drift | ✅ Client enforces floor |
| Extensibility | ❌ Hard to add provider logic | ✅ Easy | ✅ Add method to new providers |

---

## 3. New Types

### 3.1 `ProviderRetryHints` (in `backend/core/llm_client.py`)

```python
@dataclass
class ProviderRetryHints:
    """Provider-specific retry guidance extracted from an exception."""
    should_retry: bool                    # True if this error is retryable
    retry_after: Optional[float] = None   # Seconds from Retry-After header (if any)
    error_tier: ErrorTier = ErrorTier.UNKNOWN
    is_permanent: bool = False            # True for invalid key, quota exhausted
```

### 3.2 `ProviderErrorResult` (in `backend/core/llm_client.py`)

```python
@dataclass 
class ProviderErrorResult:
    """Structured result when all retries + fallbacks exhausted."""
    success: bool = False
    error: str = ""
    error_tier: ErrorTier = ErrorTier.UNKNOWN
    attempted_configs: List[str] = field(default_factory=list)
    errors_per_config: Dict[str, List[str]] = field(default_factory=dict)
    total_attempts: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

---

## 4. Provider Interface Extension

### 4.1 `BaseModelProvider.get_retry_hints()` (in `backend/services/model_provider.py`)

```python
class BaseModelProvider(ABC):
    # ... existing methods ...

    def get_retry_hints(self, exc: Exception) -> ProviderRetryHints:
        """
        Extract provider-specific retry hints from an exception.
        Default implementation delegates to LLMClient.classify_error().
        Subclasses override to parse SDK response headers.
        """
        from backend.core.llm_client import LLMClient
        tier = LLMClient.classify_error(exc)
        return ProviderRetryHints(
            should_retry=tier in (ErrorTier.TRANSIENT, ErrorTier.RATE_LIMITED),
            error_tier=tier,
            is_permanent=tier == ErrorTier.PERMANENT_KEY_FAILURE,
        )
```

### 4.2 `OpenAICompatibleProvider.get_retry_hints()`

Parses `Retry-After` from:
- `openai.RateLimitError.response.headers["Retry-After"]`
- `openai.APIStatusError.response.headers["Retry-After"]` (covers 5xx)

Handles both formats:
- Seconds: `"5"` → `5.0`
- HTTP-date: `"Wed, 02 Sep 2026 12:00:00 GMT"` → seconds until that time

### 4.3 `AnthropicProvider.get_retry_hints()`

Parses from:
- `anthropic.RateLimitError.retry_after` (SDK-native, seconds)
- `response.headers["Retry-After"]` / `headers["retry-after"]` (fallback)

### 4.4 Future Providers

Any new provider (Gemini, Cohere, etc.) implements `get_retry_hints()` for its SDK's error types.

---

## 5. LLMClient Integration

### 5.1 Updated `_delay()` Method

```python
async def _delay(self, attempt: int, retry_after: Optional[float] = None) -> None:
    """Full-jitter backoff with optional Retry-After floor (hybrid strategy)."""
    base_delay = min(self.max_retry_delay, self.base_retry_delay * (2 ** attempt))
    upper = max(base_delay, retry_after or 0)  # Hybrid: max of both
    delay = random.uniform(0, upper)
    logger.debug("LLMClient backoff: attempt=%d retry_after=%.2f sleep=%.2fs", 
                 attempt, retry_after or 0, delay)
    await asyncio.sleep(delay)
```

### 5.2 Updated Retry Loop (both `generate()` and `generate_with_tools()`)

```python
for attempt in range(_max_retries + 1):
    try:
        result = await ModelService.generate_with_agent(...)
        cb.record_success()
        await self._track_tokens_and_cost(...)
        return result
    except Exception as exc:
        last_error = exc
        effective_config_id = attempt_config_id or "default"
        
        # Get provider-specific retry hints
        provider = await ModelService.get_provider(user_id, attempt_config_id)
        hints = provider.get_retry_hints(exc) if provider else ProviderRetryHints(
            should_retry=False, error_tier=self.classify_error(exc))
        
        tier = hints.error_tier
        is_rl = tier is ErrorTier.RATE_LIMITED
        
        # Rate-limit tracking for dashboard
        if is_rl:
            await provider_rate_limiter.record_rate_limited(effective_config_id)
        
        # Permanent key failure: immediate rotation, no retry
        if tier is ErrorTier.PERMANENT_KEY_FAILURE:
            api_key_manager.mark_key_failed(...)
            cb.record_failure()
            break
        
        cb.record_failure()
        
        # Retry if attempts remain AND error is retryable
        if attempt < _max_retries and hints.should_retry:
            await self._delay(attempt, hints.retry_after)
            continue
        else:
            break
```

### 5.3 Exhaustion Handling

When all configs and retries exhausted, raise a `ProviderExhaustedError` exception that carries the structured `ProviderErrorResult` as an attribute — preserving backward compatibility (callers catching `RuntimeError` still work) while exposing rich error details.

```python
class ProviderExhaustedError(RuntimeError):
    """Raised when all provider configs and retries are exhausted."""
    def __init__(self, message: str, result: ProviderErrorResult):
        super().__init__(message)
        self.result = result  # ProviderErrorResult with full details


# In the retry loop:
if last_error:
    error_result = ProviderErrorResult(
        error=str(last_error),
        error_tier=self.classify_error(last_error),
        attempted_configs=configs_to_try,
        errors_per_config=collected_errors,
        total_attempts=sum(len(errs) for errs in collected_errors.values()),
    )
    raise ProviderExhaustedError(
        f"All {len(configs_to_try)} provider configs exhausted after {error_result.total_attempts} attempts. Last error: {last_error}",
        error_result
    )
```

---

## 6. Clear Error Messages (5.6.3)

| Error Type | Message Template |
|------------|------------------|
| Invalid API key (401/403) | `"Invalid API key for provider {provider} (config: {config_id}). Please update your model configuration in Settings → Models."` |
| Quota exhausted (402) | `"Quota exhausted for provider {provider} (config: {config_id}). Check your billing or add a fallback model config."` |
| Rate limited (429) | `"Rate limited by {provider}. Provider suggests retry after {retry_after:.0f}s. Consider adding a fallback model config."` |
| Timeout | `"Request to {provider} timed out after {timeout}s. The provider may be overloaded. Retrying..."` |
| 5xx Server Error | `"{provider} returned {status_code}: {message}. Retrying..."` |
| All exhausted | `"All {n} provider configs exhausted after {total_attempts} attempts. Last error: {error}. See logs for per-config details."` |

---

## 7. Timeout Handling (5.6.4)

- **Configuration:** Each `UserModelConfig` has `timeout_seconds` (default 60s)
- **SDK Timeout:** Passed to `AsyncOpenAI(timeout=...)` and `AsyncAnthropic(timeout=...)`
- **Behavior:** SDK raises `APITimeoutError` / `APIConnectionError` → classified as `TRANSIENT` → retried with backoff
- **No Crash:** Exception caught in retry loop, logged, retried or failed over — never bubbles up unhandled

---

## 8. Circuit Breaker Integration

Existing `ProviderCircuitBreaker` in `LLMClient` continues to work:

- `record_success()` / `record_failure()` called on each attempt
- `can_execute()` checked before trying a config (delegates to `api_key_manager.is_config_healthy()`)
- After 5 consecutive failures → `OPEN` state → config skipped for 60s → `HALF_OPEN` → test request

---

## 9. Testing Requirements

| Test ID | Description | Expected |
|---------|-------------|----------|
| TE-01 | OpenAI 429 with `Retry-After: 5` | Delay ≥ 5s (jittered) |
| TE-02 | Anthropic `retry_after=3` | Delay ≥ 3s (jittered) |
| TE-03 | No Retry-After header | Full-jitter exponential backoff |
| TE-04 | 401 Invalid key | Immediate failover, no retry, clear message |
| TE-05 | 503 Service Unavailable | Retried with backoff, max 3 attempts |
| TE-06 | All configs exhausted | Raises `ProviderExhaustedError` with `ProviderErrorResult` attached |
| TE-07 | Timeout after 60s | Classified TRANSIENT, retried |
| TE-08 | Clear error messages | Verify message templates match Section 6 |

---

## 10. Files to Modify

| File | Changes |
|------|---------|
| `backend/core/llm_client.py` | Add `ProviderRetryHints`, `ProviderErrorResult`; update `_delay()`, retry loops, error messages |
| `backend/services/model_provider.py` | Add `get_retry_hints()` to `BaseModelProvider`, `OpenAICompatibleProvider`, `AnthropicProvider` |
| `backend/tests/core/test_llm_client.py` | Add tests TE-01 through TE-08 |

---

## 11. Backward Compatibility

- **No breaking changes** to public APIs
- `LLMClient.generate()` / `generate_with_tools()` raise `ProviderExhaustedError` (subclass of `RuntimeError`) on exhaustion — existing `except RuntimeError` handlers continue to work
- **New capability:** Callers can catch `ProviderExhaustedError` and access `.result` (`ProviderErrorResult`) for structured error details (attempted configs, per-config errors, total attempts, timestamps)
- **Migration:** New code should catch `ProviderExhaustedError` for rich error handling; old code catching `RuntimeError` works unchanged

---

## 12. Rollout Plan

1. Add types and provider methods (no behavior change)
2. Update `LLMClient._delay()` and retry loops
3. Add error message improvements
4. Write tests
5. Verify with integration tests against real providers (OpenAI, Anthropic)
6. Deploy behind feature flag if needed

---

## 13. Acceptance Criteria

- [ ] 429 errors respect `Retry-After` header (hybrid with exponential backoff)
- [ ] 5xx errors retried gracefully with backoff
- [ ] Invalid API key returns clear, actionable error message
- [ ] Provider timeout doesn't crash; retried/failed over gracefully
- [ ] All exhaustion cases raise `ProviderExhaustedError` with `ProviderErrorResult` attached
- [ ] Tests pass (unit + integration)
- [ ] No regression in existing failover/circuit breaker behavior
- [ ] Backward compatibility: existing `except RuntimeError` handlers still catch exhaustion