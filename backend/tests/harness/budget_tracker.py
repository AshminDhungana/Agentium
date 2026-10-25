"""Budget tracker for monitoring token spend against daily budget."""

import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime, date


@dataclass
class BudgetStatus:
    """Current budget status."""
    spent_usd: float
    budget_usd: float
    percentage: float
    warning_triggered: bool
    pause_triggered: bool
    last_updated: str


class BudgetTracker:
    """Tracks token usage and budget consumption in real-time."""

    def __init__(self, token_optimizer, daily_budget_usd: float = 10.0):
        self._optimizer = token_optimizer
        self._daily_budget_usd = daily_budget_usd
        self._spent_usd = 0.0
        self._warning_threshold = 0.8  # 80%
        self._pause_threshold = 1.0    # 100%
        self._warning_triggered = False
        self._pause_triggered = False
        self._usage_history = []

        # Try to hook into token optimizer's record_usage
        self._hook_optimizer()

    def _hook_optimizer(self):
        """Hook into token optimizer to track usage automatically."""
        if hasattr(self._optimizer, 'record_usage'):
            original_record = self._optimizer.record_usage

            async def tracked_record_usage(*args, **kwargs):
                result = await original_record(*args, **kwargs)
                # Extract token counts from args/kwargs
                input_tokens = kwargs.get('input_tokens', args[1] if len(args) > 1 else 0)
                output_tokens = kwargs.get('output_tokens', args[2] if len(args) > 2 else 0)
                model = kwargs.get('model', args[0] if len(args) > 0 else 'unknown')
                await self.record_usage(model, input_tokens, output_tokens)
                return result

            self._optimizer.record_usage = tracked_record_usage

    async def record_usage(self, model: str, input_tokens: int, output_tokens: int):
        """Record token usage and update budget."""
        # Calculate cost using optimizer's pricing
        cost = 0.0
        if hasattr(self._optimizer, '_calculate_cost'):
            try:
                cost = self._optimizer._calculate_cost({
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                    "model": model
                })
            except:
                # Fallback: estimate cost
                cost = self._estimate_cost(model, input_tokens, output_tokens)
        else:
            cost = self._estimate_cost(model, input_tokens, output_tokens)

        self._spent_usd += cost
        self._usage_history.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Check thresholds
        percentage = (self._spent_usd / self._daily_budget_usd) * 100
        self._warning_triggered = percentage >= (self._warning_threshold * 100)
        self._pause_triggered = percentage >= (self._pause_threshold * 100)

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost based on model (fallback pricing)."""
        # Rough estimates per 1M tokens
        pricing = {
            "claude-3-opus": (15.0, 75.0),
            "claude-3-sonnet": (3.0, 15.0),
            "claude-3-haiku": (0.25, 1.25),
            "claude-3.5-sonnet": (3.0, 15.0),
            "gpt-4o": (5.0, 15.0),
            "gpt-4o-mini": (0.15, 0.60),
        }
        input_rate, output_rate = pricing.get(model, (3.0, 15.0))
        return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    def get_status(self) -> BudgetStatus:
        """Get current budget status."""
        percentage = (self._spent_usd / self._daily_budget_usd) * 100 if self._daily_budget_usd > 0 else 0
        return BudgetStatus(
            spent_usd=self._spent_usd,
            budget_usd=self._daily_budget_usd,
            percentage=percentage,
            warning_triggered=self._warning_triggered,
            pause_triggered=self._pause_triggered,
            last_updated=datetime.utcnow().isoformat()
        )

    def get_status_dict(self) -> Dict[str, Any]:
        """Get status as dictionary (for ScenarioResult)."""
        status = self.get_status()
        return {
            "spent_usd": status.spent_usd,
            "budget_usd": status.budget_usd,
            "percentage": status.percentage,
            "warning_triggered": status.warning_triggered,
            "pause_triggered": status.pause_triggered
        }

    def reset(self):
        """Reset budget tracking (e.g., for new day)."""
        self._spent_usd = 0.0
        self._warning_triggered = False
        self._pause_triggered = False
        self._usage_history.clear()

    def is_paused(self) -> bool:
        """Check if budget pause is triggered."""
        return self._pause_triggered

    def is_warning(self) -> bool:
        """Check if budget warning is triggered."""
        return self._warning_triggered