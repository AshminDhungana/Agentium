"""
Loop & Runaway Detection Service.

Detects:
- Repeating identical tool calls (same tool + same args)
- Budget exhaustion (token count or cost)
"""

import json
import hashlib
import inspect
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Any, Dict, Optional, List, Tuple
from collections import deque

from backend.core.exceptions import LoopDetectedError, BudgetExhaustedError


class BudgetTracker:
    """Tracks cumulative token usage and cost using Decimal for precision."""

    def __init__(self, budget_usd: Optional[float], budget_tokens: Optional[int]):
        self.budget_usd = Decimal(str(budget_usd)) if budget_usd is not None else None
        self.budget_tokens = budget_tokens
        self.cumulative_prompt_tokens = 0
        self.cumulative_completion_tokens = 0
        self.cumulative_cost_usd = Decimal('0')

    def add_usage(self, prompt_tokens: int, completion_tokens: int, cost_usd: float):
        self.cumulative_prompt_tokens += prompt_tokens
        self.cumulative_completion_tokens += completion_tokens
        self.cumulative_cost_usd += Decimal(str(cost_usd))

    def check(self) -> None:
        if self.budget_usd is not None and self.budget_usd > 0:
            if self.cumulative_cost_usd > self.budget_usd:
                raise BudgetExhaustedError(
                    "cost", float(self.cumulative_cost_usd), float(self.budget_usd)
                )
        if self.budget_tokens is not None and self.budget_tokens > 0:
            total_tokens = self.cumulative_prompt_tokens + self.cumulative_completion_tokens
            if total_tokens > self.budget_tokens:
                raise BudgetExhaustedError(
                    "tokens", total_tokens, self.budget_tokens
                )


class LoopDetector:
    """
    Detects runaway tool-calling patterns.

    Wraps a tool executor to intercept and analyze each call before execution.
    """

    def __init__(
        self,
        *,
        max_identical_calls: int = 3,
        max_call_history: int = 50,
        budget_usd: Optional[float] = None,
        budget_tokens: Optional[int] = None,
        track_per_tool: bool = True,
    ):
        self.max_identical_calls = max_identical_calls
        self.max_call_history = max_call_history
        self.track_per_tool = track_per_tool

        # Ring buffer of (tool_name, args_hash) tuples
        self._call_history: deque[Tuple[str, str]] = deque(maxlen=max_call_history)

        # Per-signature call count (tool_name + args_hash)
        self._signature_counts: Dict[Tuple[str, str], int] = {}

        self._budget = BudgetTracker(budget_usd, budget_tokens)

    def _make_signature(self, tool_name: str, args: Dict[str, Any]) -> Tuple[str, str]:
        """Create a deterministic signature for a tool call."""
        # Sort keys for consistent hashing regardless of arg order
        args_json = json.dumps(args, sort_keys=True, separators=(",", ":"))
        args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:16]
        return (tool_name, args_hash)

    def wrap_executor(self, tool_executor: Callable) -> Callable:
        """Return a wrapped executor that runs detection before delegating."""
        is_async = inspect.iscoroutinefunction(tool_executor)

        if is_async:
            async def wrapped_executor(name: str, args: Dict[str, Any]) -> Any:
                signature = self._make_signature(name, args)
                self._call_history.append(signature)

                # Increment count for this signature
                self._signature_counts[signature] = self._signature_counts.get(signature, 0) + 1

                if self._signature_counts[signature] > self.max_identical_calls:
                    tool_name = signature[0]
                    raise LoopDetectedError(
                        tool_name=tool_name,
                        identical_count=self._signature_counts[signature],
                        max_allowed=self.max_identical_calls,
                    )
                return await tool_executor(name, args)
            return wrapped_executor
        else:
            def wrapped_executor(name: str, args: Dict[str, Any]) -> Any:
                signature = self._make_signature(name, args)
                self._call_history.append(signature)

                # Increment count for this signature
                self._signature_counts[signature] = self._signature_counts.get(signature, 0) + 1

                if self._signature_counts[signature] > self.max_identical_calls:
                    tool_name = signature[0]
                    raise LoopDetectedError(
                        tool_name=tool_name,
                        identical_count=self._signature_counts[signature],
                        max_allowed=self.max_identical_calls,
                    )
                return tool_executor(name, args)
            return wrapped_executor

    def check_budget(self, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
        """Check budget after an LLM turn. Raises BudgetExhaustedError if exceeded."""
        self._budget.add_usage(prompt_tokens, completion_tokens, cost_usd)
        self._budget.check()

    def get_stats(self) -> Dict[str, Any]:
        """Return detection statistics for logging/debugging."""
        return {
            "total_calls": len(self._call_history),
            "unique_signatures": len(set(self._call_history)),
            "max_consecutive_identical": max(self._signature_counts.values()) if self._signature_counts else 0,
            "budget": {
                "cost_usd": float(self._budget.cumulative_cost_usd),
                "tokens": self._budget.cumulative_prompt_tokens + self._budget.cumulative_completion_tokens,
                "limit_usd": float(self._budget.budget_usd) if self._budget.budget_usd is not None else None,
                "limit_tokens": self._budget.budget_tokens,
            }
        }