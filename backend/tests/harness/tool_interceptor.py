"""Tool interceptor for tracking tool calls with LoopDetector integration."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    tool: str
    args: Dict[str, Any]
    result: Any
    duration_ms: float
    signature: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ToolInterceptor:
    """Wraps LoopDetector and tracks all tool calls for test assertions."""

    def __init__(self, detector):
        self._detector = detector
        self._call_history: List[ToolCallRecord] = []
        self._call_counts: Dict[str, int] = {}

    def wrap(self, tool_name: str, tool_func: Callable) -> Callable:
        """Wrap a tool function with LoopDetector and call tracking."""

        # Get the LoopDetector's wrapper - it expects a function with signature (name, args)
        if hasattr(self._detector, 'wrap_executor'):
            # The detector's wrap_executor expects a function with signature (name, args)
            async def detector_compatible_wrapper(name: str, args: Dict[str, Any]) -> Any:
                return await tool_func(args)

            wrapped_func = self._detector.wrap_executor(detector_compatible_wrapper)
        else:
            wrapped_func = lambda name, args: tool_func(args)

        async def tracked_wrapper(args: Dict[str, Any]) -> Any:
            start = time.time()
            signature = f"{tool_name}:{hash(str(sorted(args.items())))}"

            try:
                result = await wrapped_func(tool_name, args)
                duration_ms = (time.time() - start) * 1000

                # Record the call
                record = ToolCallRecord(
                    tool=tool_name,
                    args=args,
                    result=result,
                    duration_ms=duration_ms,
                    signature=signature
                )
                self._call_history.append(record)
                self._call_counts[signature] = self._call_counts.get(signature, 0) + 1

                return result
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                record = ToolCallRecord(
                    tool=tool_name,
                    args=args,
                    result={"error": str(e)},
                    duration_ms=duration_ms,
                    signature=signature
                )
                self._call_history.append(record)
                self._call_counts[signature] = self._call_counts.get(signature, 0) + 1
                raise

        return tracked_wrapper

    def get_call_history(self) -> List[ToolCallRecord]:
        """Get all recorded tool calls."""
        return self._call_history

    def get_call_count(self, signature: str) -> int:
        """Get call count for a specific signature."""
        return self._call_counts.get(signature, 0)

    def get_detector_stats(self) -> Dict[str, Any]:
        """Get stats from the underlying LoopDetector."""
        if hasattr(self._detector, 'get_stats'):
            return self._detector.get_stats()
        return {
            "total_calls": len(self._call_history),
            "unique_signatures": len(self._call_counts),
            "call_counts": self._call_counts
        }

    def reset(self):
        """Reset call history."""
        self._call_history.clear()
        self._call_counts.clear()