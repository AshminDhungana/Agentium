"""
Unified LLM Client for Agentium.

Centralises:
  - retry with exponential backoff
  - provider failover
  - per-provider circuit breaker integration
  - automatic token / cost tracking

All service modules should use LLMClient instead of calling
ModelService directly.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from backend.services.model_provider import ModelService
from backend.services.api_key_manager import api_key_manager

logger = logging.getLogger(__name__)


# Circuit breaker constants
_CB_CLOSED = "closed"
_CB_OPEN = "open"
_CB_HALF_OPEN = "half_open"
_CB_FAILURE_THRESHOLD = 5
_CB_RECOVERY_SECONDS = 60


class ProviderCircuitBreaker:
    """Per-provider circuit breaker (independent of AgentOrchestrator CBs)."""

    def __init__(self) -> None:
        self.state = _CB_CLOSED
        self.consecutive_failures = 0
        self.last_failure_at: Optional[datetime] = None
        self.total_success = 0
        self.total_failure = 0

    def record_success(self) -> None:
        self.state = _CB_CLOSED
        self.consecutive_failures = 0
        self.total_success += 1

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_at = datetime.utcnow()
        self.total_failure += 1
        if self.consecutive_failures >= _CB_FAILURE_THRESHOLD:
            self.state = _CB_OPEN

    def can_execute(self) -> bool:
        if self.state == _CB_CLOSED:
            return True
        if self.state == _CB_OPEN:
            if self.last_failure_at and (
                datetime.utcnow() - self.last_failure_at
            ).total_seconds() > _CB_RECOVERY_SECONDS:
                self.state = _CB_HALF_OPEN
                self.consecutive_failures = 0
                return True
            return False
        return True

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "total_success": self.total_success,
            "total_failure": self.total_failure,
        }


class LLMClient:
    """Unified client for all LLM interactions."""

    _circuit_breakers: Dict[str, ProviderCircuitBreaker] = {}

    def __init__(self, db: Optional[Session] = None, *,
                 max_retries: int = 3,
                 base_retry_delay: float = 1.0,
                 max_retry_delay: float = 30.0):
        self.db = db
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cb(self, config_id: str) -> ProviderCircuitBreaker:
        if config_id not in LLMClient._circuit_breakers:
            LLMClient._circuit_breakers[config_id] = ProviderCircuitBreaker()
        return LLMClient._circuit_breakers[config_id]

    def _is_rate_limit(self, error: Exception) -> bool:
        msg = str(error).lower()
        return "rate limit" in msg or "429" in msg

    def _is_retryable(self, error: Exception) -> bool:
        msg = str(error).lower()
        if self._is_rate_limit(error):
            return True
        retryable_keywords = [
            "timeout", "connection", "temporarily",
            "server error", "503", "502", "504"
        ]
        return any(kw in msg for kw in retryable_keywords)

    async def _delay(self, attempt: int) -> None:
        """Full-jitter backoff: random in [0, min(max_delay, base*2**attempt)]."""
        upper = min(self.max_retry_delay, self.base_retry_delay * (2 ** attempt))
        delay = random.uniform(0, upper)
        logger.debug("LLMClient backoff: attempt=%d sleep=%.2fs (jitter)", attempt, delay)
        await asyncio.sleep(delay)

    async def _track_tokens_and_cost(
        self, result: Dict[str, Any], config_id: str, agentium_id: str
    ) -> None:
        try:
            cost = result.get("cost_usd", 0.0)
            tokens = result.get("tokens_used", 0)
            try:
                api_key_manager.record_spend(config_id, cost, tokens, db=self.db)
            except Exception:
                try:
                    api_key_manager.record_spend(config_id, cost, tokens)
                except Exception:
                    pass
            try:
                from backend.services.idle_governance import token_optimizer
                token_optimizer.update_token_count(
                    agent_id=agentium_id, tokens_used=tokens
                )
            except Exception:
                pass
        except Exception as exc:
            logger.debug("Token tracking failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        agent,
        user_message: str,
        *,
        user_id: str = "sovereign",
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        max_retries: Optional[int] = None,
        fallback_configs: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a response from an LLM with retry, failover, and CB integration."""
        _max_retries = max_retries if max_retries is not None else self.max_retries
        configs_to_try: List[Optional[str]] = [config_id] if config_id else []
        if fallback_configs:
            for fb in fallback_configs:
                if fb not in configs_to_try:
                    configs_to_try.append(fb)

        if not configs_to_try:
            if agent and getattr(agent, "preferred_config_id", None):
                configs_to_try = [agent.preferred_config_id]
            else:
                configs_to_try = [None]

        last_error: Optional[Exception] = None
        agentium_id = getattr(agent, "agentium_id", "system")

        for attempt_config_id in configs_to_try:
            if attempt_config_id:
                cb = self._get_cb(attempt_config_id)
                if not cb.can_execute():
                    logger.warning(
                        "LLMClient: Circuit breaker OPEN for config %s, skipping",
                        attempt_config_id,
                    )
                    continue

            for attempt in range(_max_retries + 1):
                try:
                    result = await ModelService.generate_with_agent(
                        agent=agent,
                        user_message=user_message,
                        user_id=user_id,
                        config_id=attempt_config_id,
                        system_prompt_override=system_prompt_override,
                        **kwargs,
                    )
                    effective_config_id = attempt_config_id or "default"
                    cb = self._get_cb(effective_config_id)
                    cb.record_success()
                    await self._track_tokens_and_cost(result, effective_config_id, agentium_id)
                    result["provider_config_id"] = effective_config_id
                    return result

                except Exception as exc:
                    last_error = exc
                    effective_config_id = attempt_config_id or "default"
                    cb = self._get_cb(effective_config_id)
                    is_rl = self._is_rate_limit(exc)
                    if is_rl:
                        logger.warning(
                            "LLMClient.generate: Rate limit on config %s (attempt %d/%d)",
                            attempt_config_id, attempt + 1, _max_retries + 1,
                        )
                    cb.record_failure()
                    if attempt < _max_retries and (is_rl or self._is_retryable(exc)):
                        await self._delay(attempt)
                        continue
                    else:
                        break

        if last_error:
            raise RuntimeError(
                f"LLMClient.generate exhausted all {len(configs_to_try)} provider(s) "
                f"and {_max_retries} retries. Last error: {last_error}"
            ) from last_error
        raise RuntimeError("LLMClient.generate: No providers available and no error captured")

    async def generate_with_tools(
        self,
        agent,
        user_message: str,
        *,
        db,
        config_id: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        agent_tier: Optional[str] = None,
        task_id: Optional[str] = None,
        max_tool_iterations: int = 10,
        max_retries: Optional[int] = None,
        fallback_configs: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Tool-aware generation with retry, failover, and CB integration."""
        _max_retries = max_retries if max_retries is not None else self.max_retries
        configs_to_try: List[Optional[str]] = [config_id] if config_id else []
        if fallback_configs:
            for fb in fallback_configs:
                if fb not in configs_to_try:
                    configs_to_try.append(fb)

        if not configs_to_try:
            if agent and getattr(agent, "preferred_config_id", None):
                configs_to_try = [agent.preferred_config_id]
            else:
                configs_to_try = [None]

        last_error: Optional[Exception] = None
        agentium_id = getattr(agent, "agentium_id", "system")

        for attempt_config_id in configs_to_try:
            if attempt_config_id:
                cb = self._get_cb(attempt_config_id)
                if not cb.can_execute():
                    logger.warning(
                        "LLMClient: Circuit breaker OPEN for config %s, skipping",
                        attempt_config_id,
                    )
                    continue

            for attempt in range(_max_retries + 1):
                try:
                    result = await ModelService.generate_with_agent_tools(
                        agent=agent,
                        user_message=user_message,
                        db=db,
                        config_id=attempt_config_id,
                        system_prompt_override=system_prompt_override,
                        agent_tier=agent_tier,
                        task_id=task_id,
                        max_tool_iterations=max_tool_iterations,
                        **kwargs,
                    )
                    effective_config_id = attempt_config_id or "default"
                    cb = self._get_cb(effective_config_id)
                    cb.record_success()
                    await self._track_tokens_and_cost(result, effective_config_id, agentium_id)
                    result["provider_config_id"] = effective_config_id
                    return result

                except Exception as exc:
                    last_error = exc
                    effective_config_id = attempt_config_id or "default"
                    cb = self._get_cb(effective_config_id)
                    is_rl = self._is_rate_limit(exc)
                    if is_rl:
                        logger.warning(
                            "LLMClient.generate_with_tools: Rate limit on config %s "
                            "(attempt %d/%d)",
                            attempt_config_id, attempt + 1, _max_retries + 1,
                        )
                    cb.record_failure()
                    if attempt < _max_retries and (is_rl or self._is_retryable(exc)):
                        await self._delay(attempt)
                        continue
                    else:
                        break

        if last_error:
            raise RuntimeError(
                f"LLMClient.generate_with_tools exhausted all {len(configs_to_try)} provider(s) "
                f"and {_max_retries} retries. Last error: {last_error}"
            ) from last_error
        raise RuntimeError(
            "LLMClient.generate_with_tools: No providers available and no error captured"
        )

    def get_circuit_breaker_metrics(self, config_id: Optional[str] = None) -> Dict[str, Any]:
        """Return CB metrics for one config or all configured configs."""
        if config_id:
            cb = self._get_cb(config_id)
            return {config_id: cb.get_metrics()}
        return {
            cid: cb.get_metrics()
            for cid, cb in LLMClient._circuit_breakers.items()
        }

    @classmethod
    def reset_circuit_breaker(cls, config_id: str) -> None:
        """Manually reset a circuit breaker (e.g. from admin endpoint)."""
        if config_id in cls._circuit_breakers:
            cls._circuit_breakers[config_id] = ProviderCircuitBreaker()