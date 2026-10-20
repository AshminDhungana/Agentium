"""Shared utilities for periodic task verification."""
import asyncio
import traceback
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from datetime import datetime
import sys
import threading
import time

@dataclass
class TaskResult:
    name: str
    status: str  # "PASS", "FAIL", "SKIPPED"
    error: Optional[str] = None
    traceback: Optional[str] = None
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

class TimeoutException(Exception):
    pass

def run_task(task_name: str, task_func: Callable, *args, timeout_seconds: int = 30, **kwargs) -> TaskResult:
    """Run a single task function with timeout and error capture."""
    start = datetime.utcnow()
    result_container = {"result": None, "error": None, "traceback": None}

    def target():
        try:
            # Handle async functions
            if asyncio.iscoroutinefunction(task_func):
                result_container["result"] = asyncio.run(task_func(*args, **kwargs))
            else:
                result_container["result"] = task_func(*args, **kwargs)
        except Exception as e:
            result_container["error"] = e
            result_container["traceback"] = traceback.format_exc()

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)

    duration = (datetime.utcnow() - start).total_seconds() * 1000

    if thread.is_alive():
        # Thread timed out - we can't kill it, but we can return failure
        return TaskResult(
            name=task_name,
            status="FAIL",
            error=f"Task timed out after {timeout_seconds} seconds",
            duration_ms=duration
        )

    if result_container["error"]:
        return TaskResult(
            name=task_name,
            status="FAIL",
            error=f"{type(result_container['error']).__name__}: {result_container['error']}",
            traceback=result_container["traceback"],
            duration_ms=duration
        )

    return TaskResult(
        name=task_name,
        status="PASS",
        duration_ms=duration,
        metadata={"result": str(result_container["result"])[:200] if result_container["result"] else None}
    )

def print_results_table(results: list[TaskResult]) -> None:
    """Print formatted results table."""
    print(f"\n{'Task Name':<45} {'Status':<8} {'Duration':>10}  Error")
    print("-" * 100)
    for r in results:
        err_display = (r.error[:60] + "...") if r.error and len(r.error) > 60 else (r.error or "")
        print(f"{r.name:<45} {r.status:<8} {r.duration_ms:>9.1f}ms  {err_display}")

def print_summary(results: list[TaskResult]) -> dict:
    """Print summary and return counts."""
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIPPED")
    total = len(results)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'='*60}")

    if failed > 0:
        print("\nFAILED TASKS:")
        for r in results:
            if r.status == "FAIL":
                print(f"  - {r.name}: {r.error}")
                if r.traceback:
                    print(f"    Traceback:\n{r.traceback}")

    return {"passed": passed, "failed": failed, "skipped": skipped, "total": total}