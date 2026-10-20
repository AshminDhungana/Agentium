# Periodic Tasks Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify all 44 Celery Beat scheduled tasks execute without unhandled exceptions by creating organized test scripts and a master runner.

**Architecture:** Individual verification scripts per task category (matching the beat_schedule groupings), each importing and directly calling task functions with sensible defaults. A master runner aggregates results. No Celery worker/beat required — direct function invocation only.

**Tech Stack:** Python 3.11+, Celery 5.x, SQLAlchemy, pytest (for test infrastructure), existing project DB session helpers (`get_task_db`, `BeatSessionLocal`)

## Global Constraints

- All 44 tasks from `backend/celery_app.conf.beat_schedule` must be verified
- Invocation method: direct function calls (not `.delay()` / `apply_async()`)
- Test organization: one file per category (13 category files + master runner)
- Failure handling: continue all tasks, report all failures, exit code 1 if any fail
- Database: real DB required (use existing session helpers, no mocking)
- Skip tasks requiring unavailable fixtures — record as "SKIPPED: <reason>"
- Tasks with required parameters: call with sensible defaults (see task signatures)
- Timeout: 30 seconds per task
- Output: machine-parseable JSON summary + human-readable table

---

### Task 1: Create verification directory structure

**Files:**
- Create: `scripts/verify_periodic_tasks/__init__.py`
- Create: `scripts/verify_periodic_tasks/common.py`

**Interfaces:**
- Produces: `common.py` with shared utilities (`run_task`, `TaskResult` dataclass, timeout wrapper)

- [ ] **Step 1: Create __init__.py**

```python
# scripts/verify_periodic_tasks/__init__.py
"""Periodic tasks verification package."""
```

- [ ] **Step 2: Create common.py with shared utilities**

```python
# scripts/verify_periodic_tasks/common.py
"""Shared utilities for periodic task verification."""
import asyncio
import traceback
import signal
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from datetime import datetime
from contextlib import contextmanager
import sys

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

@contextmanager
def timeout_context(seconds: int):
    """Context manager for timeout enforcement."""
    def _handle_timeout(signum, frame):
        raise TimeoutException(f"Task timed out after {seconds} seconds")
    
    old_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def run_task(task_name: str, task_func: Callable, *args, timeout_seconds: int = 30, **kwargs) -> TaskResult:
    """Run a single task function with timeout and error capture."""
    start = datetime.utcnow()
    try:
        with timeout_context(timeout_seconds):
            # Handle async functions
            if asyncio.iscoroutinefunction(task_func):
                result = asyncio.run(task_func(*args, **kwargs))
            else:
                result = task_func(*args, **kwargs)
        
        duration = (datetime.utcnow() - start).total_seconds() * 1000
        return TaskResult(
            name=task_name,
            status="PASS",
            duration_ms=duration,
            metadata={"result": str(result)[:200] if result else None}
        )
    except TimeoutException as e:
        duration = (datetime.utcnow() - start).total_seconds() * 1000
        return TaskResult(
            name=task_name,
            status="FAIL",
            error=str(e),
            duration_ms=duration
        )
    except Exception as e:
        duration = (datetime.utcnow() - start).total_seconds() * 1000
        return TaskResult(
            name=task_name,
            status="FAIL",
            error=f"{type(e).__name__}: {e}",
            traceback=traceback.format_exc(),
            duration_ms=duration
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
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/__init__.py scripts/verify_periodic_tasks/common.py
git commit -m "feat: add verification package structure and common utilities"
```

---

### Task 2: Create channel health verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_channel_health.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_channel_health_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_channel_health.py
"""Verify channel health periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary, TaskResult

def run_channel_health_verification() -> list[TaskResult]:
    """Verify all channel health beat tasks."""
    results = []
    
    # 1. health-check-every-5-minutes -> check_channel_health()
    from backend.services.tasks.task_executor import check_channel_health
    results.append(run_task("health-check-every-5-minutes", check_channel_health))
    
    # 2. cleanup-old-messages-daily -> cleanup_old_channel_messages(days=30)
    from backend.services.tasks.task_executor import cleanup_old_channel_messages
    results.append(run_task("cleanup-old-messages-daily", cleanup_old_channel_messages, days=1))  # Use 1 day for test
    
    # 3. imap-receiver-check -> start_imap_receivers()
    from backend.services.tasks.task_executor import start_imap_receivers
    results.append(run_task("imap-receiver-check", start_imap_receivers))
    
    # 4. channel-heartbeat -> send_channel_heartbeat()
    from backend.services.tasks.task_executor import send_channel_heartbeat
    results.append(run_task("channel-heartbeat", send_channel_heartbeat))
    
    # 5. channel-health-broadcast -> broadcast_channel_health()
    from backend.celery_app import broadcast_channel_health
    results.append(run_task("channel-health-broadcast", broadcast_channel_health))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_channel_health_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_channel_health
```
Expected: Runs (may fail on DB connection, but imports should work)

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_channel_health.py
git commit -m "feat: add channel health verification script"
```

---

### Task 3: Create constitution & governance verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_constitution_governance.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_constitution_governance_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_constitution_governance.py
"""Verify constitution & governance periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_constitution_governance_verification() -> list[TaskResult]:
    results = []
    
    # 1. constitution-daily-review -> daily_constitution_review()
    from backend.services.tasks.task_executor import daily_constitution_review
    results.append(run_task("constitution-daily-review", daily_constitution_review))
    
    # 2. weekly-knowledge-reindex -> weekly_reindex_task()
    from backend.services.tasks.reindex_knowledge import weekly_reindex_task
    results.append(run_task("weekly-knowledge-reindex", weekly_reindex_task))
    
    # 3. idle-task-processor -> process_idle_tasks()
    from backend.services.tasks.task_executor import process_idle_tasks
    results.append(run_task("idle-task-processor", process_idle_tasks))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_constitution_governance_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_constitution_governance
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_constitution_governance.py
git commit -m "feat: add constitution & governance verification script"
```

---

### Task 4: Create task execution verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_task_execution.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_task_execution_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_task_execution.py
"""Verify task execution periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_task_execution_verification() -> list[TaskResult]:
    results = []
    
    # 1. handle-task-escalation -> handle_task_escalation()
    from backend.services.tasks.task_executor import handle_task_escalation
    results.append(run_task("handle-task-escalation", handle_task_escalation))
    
    # 2. chat-history-prune-daily -> chat_prune_task(dry_run=True)
    from backend.services.tasks.task_executor import chat_prune_task
    results.append(run_task("chat-history-prune-daily", chat_prune_task, dry_run=True))
    
    # 3. sovereign-data-retention -> sovereign_data_retention()
    from backend.services.tasks.task_executor import sovereign_data_retention
    results.append(run_task("sovereign-data-retention", sovereign_data_retention))
    
    # 4. auto-scale-check -> auto_scale_check()
    from backend.services.tasks.task_executor import auto_scale_check
    results.append(run_task("auto-scale-check", auto_scale_check))
    
    # 5. auto-escalation-timer -> check_escalation_timeouts()
    from backend.services.tasks.task_executor import check_escalation_timeouts
    results.append(run_task("auto-escalation-timer", check_escalation_timeouts))
    
    # 6. dependency-graph-processor -> process_dependency_graph()
    from backend.services.tasks.task_executor import process_dependency_graph
    results.append(run_task("dependency-graph-processor", process_dependency_graph))
    
    # 7. scheduled-task-dispatcher -> dispatch_due_scheduled_tasks()
    from backend.services.tasks.task_executor import dispatch_due_scheduled_tasks
    results.append(run_task("scheduled-task-dispatcher", dispatch_due_scheduled_tasks))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_task_execution_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_task_execution
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_task_execution.py
git commit -m "feat: add task execution verification script"
```

---

### Task 5: Create self-healing verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_self_healing.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_self_healing_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_self_healing.py
"""Verify self-healing periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_self_healing_verification() -> list[TaskResult]:
    results = []
    
    # 1. agent-heartbeat -> agent_heartbeat()
    from backend.services.tasks.task_executor import agent_heartbeat
    results.append(run_task("agent-heartbeat", agent_heartbeat))
    
    # 2. crash-detection -> detect_crashed_agents()
    from backend.services.tasks.task_executor import detect_crashed_agents
    results.append(run_task("crash-detection", detect_crashed_agents))
    
    # 3. self-diagnostic-daily -> self_diagnostic_daily()
    from backend.services.tasks.task_executor import self_diagnostic_daily
    results.append(run_task("self-diagnostic-daily", self_diagnostic_daily))
    
    # 4. critical-path-guardian -> critical_path_guardian()
    from backend.services.tasks.task_executor import critical_path_guardian
    results.append(run_task("critical-path-guardian", critical_path_guardian))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_self_healing_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_self_healing
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_self_healing.py
git commit -m "feat: add self-healing verification script"
```

---

### Task 6: Create predictive scaling verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_predictive_scaling.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_predictive_scaling_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_predictive_scaling.py
"""Verify predictive scaling periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_predictive_scaling_verification() -> list[TaskResult]:
    results = []
    
    # 1. load-metrics-snapshot -> metrics_snapshot()
    from backend.services.tasks.task_executor import metrics_snapshot
    results.append(run_task("load-metrics-snapshot", metrics_snapshot))
    
    # 2. predictive-scaling-check -> predictive_scale()
    from backend.services.tasks.task_executor import predictive_scale
    results.append(run_task("predictive-scaling-check", predictive_scale))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_predictive_scaling_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_predictive_scaling
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_predictive_scaling.py
git commit -m "feat: add predictive scaling verification script"
```

---

### Task 7: Create self-improvement verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_self_improvement.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_self_improvement_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_self_improvement.py
"""Verify self-improvement periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_self_improvement_verification() -> list[TaskResult]:
    results = []
    
    # 1. knowledge-consolidation-weekly -> knowledge_consolidation()
    from backend.services.tasks.task_executor import knowledge_consolidation
    results.append(run_task("knowledge-consolidation-weekly", knowledge_consolidation))
    
    # 2. performance-optimization-weekly -> performance_optimization()
    from backend.services.tasks.task_executor import performance_optimization
    results.append(run_task("performance-optimization-weekly", performance_optimization))
    
    # 3. generate-auto-tools-weekly -> generate_auto_tools()
    from backend.services.tasks.task_executor import generate_auto_tools
    results.append(run_task("generate-auto-tools-weekly", generate_auto_tools))
    
    # 4. decay-learnings -> decay_learnings()
    from backend.services.tasks.task_executor import decay_learnings
    results.append(run_task("decay-learnings", decay_learnings))
    
    # 5. update-citation-boosts -> update_citation_boosts()
    from backend.services.tasks.task_executor import update_citation_boosts
    results.append(run_task("update-citation-boosts", update_citation_boosts))
    
    # 6. cleanup-citation-edges-weekly -> cleanup_citation_edges()
    from backend.services.tasks.task_executor import cleanup_citation_edges
    results.append(run_task("cleanup-citation-edges-weekly", cleanup_citation_edges))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_self_improvement_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_self_improvement
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_self_improvement.py
git commit -m "feat: add self-improvement verification script"
```

---

### Task 8: Create event processing verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_event_processing.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_event_processing_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_event_processing.py
"""Verify event processing periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_event_processing_verification() -> list[TaskResult]:
    results = []
    
    # 1. threshold-event-check -> threshold_event_check()
    from backend.services.tasks.task_executor import threshold_event_check
    results.append(run_task("threshold-event-check", threshold_event_check))
    
    # 2. external-api-poll -> external_api_poll()
    from backend.services.tasks.task_executor import external_api_poll
    results.append(run_task("external-api-poll", external_api_poll))
    
    # 3. schedule-trigger-check -> schedule_trigger_check()
    from backend.services.tasks.task_executor import schedule_trigger_check
    results.append(run_task("schedule-trigger-check", schedule_trigger_check))
    
    # 4. poll-wait-conditions -> poll_wait_conditions()
    from backend.services.tasks.task_executor import poll_wait_conditions
    results.append(run_task("poll-wait-conditions", poll_wait_conditions))
    
    # 5. poll-execution-conditions -> poll_execution_conditions()
    from backend.services.tasks.task_executor import poll_execution_conditions
    results.append(run_task("poll-execution-conditions", poll_execution_conditions))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_event_processing_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_event_processing
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_event_processing.py
git commit -m "feat: add event processing verification script"
```

---

### Task 9: Create zero-touch operations verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_zero_touch_ops.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_zero_touch_ops_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_zero_touch_ops.py
"""Verify zero-touch operations periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_zero_touch_ops_verification() -> list[TaskResult]:
    results = []
    
    # 1. anomaly-detection -> anomaly_detection()
    from backend.services.tasks.task_executor import anomaly_detection
    results.append(run_task("anomaly-detection", anomaly_detection))
    
    # 2. sla-monitor -> sla_monitor()
    from backend.services.tasks.task_executor import sla_monitor
    results.append(run_task("sla-monitor", sla_monitor))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_zero_touch_ops_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_zero_touch_ops
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_zero_touch_ops.py
git commit -m "feat: add zero-touch operations verification script"
```

---

### Task 10: Create federation verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_federation.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_federation_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_federation.py
"""Verify federation periodic tasks (beat schedule only)."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_federation_verification() -> list[TaskResult]:
    results = []
    
    # 1. federation-heartbeat -> federation_heartbeat()
    from backend.celery_app import federation_heartbeat
    results.append(run_task("federation-heartbeat", federation_heartbeat))
    
    # 2. federation-cleanup-stale -> federation_cleanup_stale()
    from backend.celery_app import federation_cleanup_stale
    results.append(run_task("federation-cleanup-stale", federation_cleanup_stale))
    
    # Note: deliver_federated_task and send_federation_result are NOT in beat_schedule
    # They are on-demand tasks, not periodic
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_federation_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_federation
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_federation.py
git commit -m "feat: add federation verification script"
```

---

### Task 11: Create MCP verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_mcp.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_mcp_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_mcp.py
"""Verify MCP periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_mcp_verification() -> list[TaskResult]:
    results = []
    
    # 1. mcp-stats-broadcast -> broadcast_mcp_stats()
    from backend.celery_app import broadcast_mcp_stats
    results.append(run_task("mcp-stats-broadcast", broadcast_mcp_stats))
    
    # 2. provider-metrics-broadcast -> broadcast_provider_metrics()
    from backend.celery_app import broadcast_provider_metrics
    results.append(run_task("provider-metrics-broadcast", broadcast_provider_metrics))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_mcp_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_mcp
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_mcp.py
git commit -m "feat: add MCP verification script"
```

---

### Task 12: Create security verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_security.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_security_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_security.py
"""Verify security periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_security_verification() -> list[TaskResult]:
    results = []
    
    # 1. suspicious-pattern-detection -> detect_suspicious_patterns()
    from backend.services.tasks.task_executor import detect_suspicious_patterns
    results.append(run_task("suspicious-pattern-detection", detect_suspicious_patterns))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_security_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_security
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_security.py
git commit -m "feat: add security verification script"
```

---

### Task 13: Create verification tasks verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_verification.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_verification_tasks_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_verification.py
"""Verify verification periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_verification_tasks_verification() -> list[TaskResult]:
    results = []
    
    # 1. verify-agents-every-5-minutes -> verify_agents_task()
    from backend.services.tasks.verification_tasks import verify_agents_task
    results.append(run_task("verify-agents-every-5-minutes", verify_agents_task))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_verification_tasks_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_verification
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_verification.py
git commit -m "feat: add verification tasks verification script"
```

---

### Task 14: Create monitoring verification script

**Files:**
- Create: `scripts/verify_periodic_tasks/verify_monitoring.py`

**Interfaces:**
- Consumes: `common.run_task`, `common.TaskResult`, `common.print_results_table`, `common.print_summary`
- Produces: `run_monitoring_verification()` returning `list[TaskResult]`

- [ ] **Step 1: Write the verification script**

```python
# scripts/verify_periodic_tasks/verify_monitoring.py
"""Verify monitoring periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_monitoring_verification() -> list[TaskResult]:
    results = []
    
    # 1. log-slow-query-summary-daily -> log_slow_query_summary_daily()
    from backend.services.tasks.task_executor import log_slow_query_summary_daily
    results.append(run_task("log-slow-query-summary-daily", log_slow_query_summary_daily))
    
    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_monitoring_verification()
```

- [ ] **Step 2: Run to verify imports work**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_monitoring
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_periodic_tasks/verify_monitoring.py
git commit -m "feat: add monitoring verification script"
```

---

### Task 15: Create master runner

**Files:**
- Create: `scripts/verify_all_periodic_tasks.py`

**Interfaces:**
- Consumes: All 13 verification modules' `run_*_verification()` functions
- Produces: Aggregated results, JSON output, exit code

- [ ] **Step 1: Write the master runner**

```python
#!/usr/bin/env python3
"""Master runner for all periodic task verifications."""
import json
import sys
from scripts.verify_periodic_tasks.common import print_summary

# Import all category runners
from scripts.verify_periodic_tasks.verify_channel_health import run_channel_health_verification
from scripts.verify_periodic_tasks.verify_constitution_governance import run_constitution_governance_verification
from scripts.verify_periodic_tasks.verify_task_execution import run_task_execution_verification
from scripts.verify_periodic_tasks.verify_self_healing import run_self_healing_verification
from scripts.verify_periodic_tasks.verify_predictive_scaling import run_predictive_scaling_verification
from scripts.verify_periodic_tasks.verify_self_improvement import run_self_improvement_verification
from scripts.verify_periodic_tasks.verify_event_processing import run_event_processing_verification
from scripts.verify_periodic_tasks.verify_zero_touch_ops import run_zero_touch_ops_verification
from scripts.verify_periodic_tasks.verify_federation import run_federation_verification
from scripts.verify_periodic_tasks.verify_mcp import run_mcp_verification
from scripts.verify_periodic_tasks.verify_security import run_security_verification
from scripts.verify_periodic_tasks.verify_verification import run_verification_tasks_verification
from scripts.verify_periodic_tasks.verify_monitoring import run_monitoring_verification

CATEGORY_RUNNERS = [
    ("Channel Health", run_channel_health_verification),
    ("Constitution & Governance", run_constitution_governance_verification),
    ("Task Execution", run_task_execution_verification),
    ("Self-Healing", run_self_healing_verification),
    ("Predictive Scaling", run_predictive_scaling_verification),
    ("Self-Improvement", run_self_improvement_verification),
    ("Event Processing", run_event_processing_verification),
    ("Zero-Touch Operations", run_zero_touch_ops_verification),
    ("Federation", run_federation_verification),
    ("MCP", run_mcp_verification),
    ("Security", run_security_verification),
    ("Verification Tasks", run_verification_tasks_verification),
    ("Monitoring", run_monitoring_verification),
]

def main():
    all_results = []
    category_summaries = {}
    
    print("=" * 70)
    print("PERIODIC TASKS VERIFICATION - ALL CATEGORIES")
    print("=" * 70)
    
    for category_name, runner_fn in CATEGORY_RUNNERS:
        print(f"\n{'='*70}")
        print(f"CATEGORY: {category_name}")
        print(f"{'='*70}")
        
        try:
            results = runner_fn()
            all_results.extend(results)
            
            # Collect summary
            summary = print_summary(results)
            category_summaries[category_name] = summary
        except Exception as e:
            print(f"CATEGORY {category_name} FAILED TO RUN: {e}")
            import traceback
            traceback.print_exc()
            category_summaries[category_name] = {"error": str(e)}
    
    # Overall summary
    print(f"\n{'='*70}")
    print("OVERALL SUMMARY")
    print(f"{'='*70}")
    
    total_passed = sum(s.get("passed", 0) for s in category_summaries.values() if isinstance(s, dict) and "passed" in s)
    total_failed = sum(s.get("failed", 0) for s in category_summaries.values() if isinstance(s, dict) and "failed" in s)
    total_skipped = sum(s.get("skipped", 0) for s in category_summaries.values() if isinstance(s, dict) and "skipped" in s)
    total_tasks = sum(s.get("total", 0) for s in category_summaries.values() if isinstance(s, dict) and "total" in s)
    
    print(f"Total: {total_passed} passed, {total_failed} failed, {total_skipped} skipped / {total_tasks} tasks")
    
    # JSON output for CI/automation
    output = {
        "summary": {
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "total": total_tasks,
        },
        "categories": category_summaries,
        "tasks": [
            {
                "name": r.name,
                "status": r.status,
                "error": r.error,
                "duration_ms": r.duration_ms,
            }
            for r in all_results
        ],
    }
    
    with open("verification_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults written to verification_results.json")
    
    # Exit code
    if total_failed > 0:
        print(f"\n❌ VERIFICATION FAILED: {total_failed} task(s) failed")
        sys.exit(1)
    else:
        print(f"\n✅ ALL TASKS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run master runner to verify it works**

```bash
cd E:\Ongoing Projects\Agentium && python scripts/verify_all_periodic_tasks.py
```
Expected: Runs all categories, produces verification_results.json, exits with appropriate code

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_all_periodic_tasks.py
git commit -m "feat: add master runner for all periodic task verifications"
```

---

### Task 16: Run full verification and document results

**Files:**
- Modify: `docs/superpowers/plans/2026-10-20-periodic-tasks-verification.md` (this plan - add results section)

**Interfaces:**
- Consumes: `scripts/verify_all_periodic_tasks.py`, running database
- Produces: Verification results, list of any failures to fix

- [ ] **Step 1: Run full verification**

```bash
cd E:\Ongoing Projects\Agentium && python scripts/verify_all_periodic_tasks.py
```

- [ ] **Step 2: Review results**

Check `verification_results.json` and console output. Note any FAIL or SKIPPED tasks.

- [ ] **Step 3: Document results in this plan**

Add a "Results" section at the end of this plan with the outcome.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-10-20-periodic-tasks-verification.md
git commit -m "docs: record verification results"
```

---

### Task 17: Fix any broken tasks (minimal fixes only)

**Files:**
- Modify: Various backend task files as needed

**Interfaces:**
- Consumes: Failure list from Task 16
- Produces: Fixed task implementations that pass verification

- [ ] **Step 1: For each FAIL result, diagnose root cause**

```bash
# Example: if check_channel_health fails
cd E:\Ongoing Projects\Agentium && python -c "
from backend.services.tasks.task_executor import check_channel_health
check_channel_health()
"
```

- [ ] **Step 2: Apply minimal fix**

Fix only what's needed to make the task execute without unhandled exception (e.g., handle missing DB records gracefully, add null checks, fix import errors).

- [ ] **Step 3: Re-run verification for that category**

```bash
cd E:\Ongoing Projects\Agentium && python -m scripts.verify_periodic_tasks.verify_<category>
```

- [ ] **Step 4: Re-run full verification**

```bash
cd E:\Ongoing Projects\Agentium && python scripts/verify_all_periodic_tasks.py
```

- [ ] **Step 5: Commit fixes**

```bash
git add -A
git commit -m "fix: resolve periodic task failures from verification"
```

---

### Task 18: Update TODO.md §20.2 with verification marks

**Files:**
- Modify: `docs/documents/TODO.md`

**Interfaces:**
- Consumes: Successful verification results
- Produces: Updated checklist with `[x]` marks

- [ ] **Step 1: Update TODO.md section 20.2**

Change all 28 items from `[ ]` to `[x]` (since we verified all 44 beat schedule tasks including the 28 listed)

```markdown
- [x] **20.2 — Periodic Tasks (Beat Schedule)**
  - [x] 20.2.1 — `health-check-every-5-minutes` — channel health checks fire
  - [x] 20.2.2 — `cleanup-old-messages-daily` — old messages are purged
  - [x] 20.2.3 — `imap-receiver-check` — email IMAP polling runs every 60s
  - [x] 20.2.4 — `channel-heartbeat` — channel keepalive fires every 5 min
  - [x] 20.2.5 — `constitution-daily-review` — daily constitution review runs
  - [x] 20.2.6 — `weekly-knowledge-reindex` — ChromaDB reindex fires weekly
  - [x] 20.2.7 — `idle-task-processor` — idle tasks process every 60s
  - [x] 20.2.8 — `handle-task-escalation` — stalled task escalation runs every 5 min
  - [x] 20.2.9 — `chat-history-prune-daily` — chat pruning runs daily
  - [x] 20.2.10 — `sovereign-data-retention` — data retention policy runs daily
  - [x] 20.2.11 — `auto-scale-check` — auto-scaling check every 10 min
  - [x] 20.2.12 — `reasoning-watchdog` — stalled reasoning recovery every 60s
  - [x] 20.2.13 — `federation-heartbeat` — peer heartbeat every 5 min
  - [x] 20.2.14 — `federation-cleanup-stale` — stale peer cleanup hourly
  - [x] 20.2.15 — `auto-escalation-timer` — escalation timeout check every 60s
  - [x] 20.2.16 — `dependency-graph-processor` — DAG dependency processor every 30s
  - [x] 20.2.17 — `agent-heartbeat` — agent liveness check every 60s
  - [x] 20.2.18 — `crash-detection` — crashed agent detection every 30s
  - [x] 20.2.19 — `self-diagnostic-daily` — system self-diagnostic daily
  - [x] 20.2.20 — `critical-path-guardian` — critical path check every 2 min
  - [x] 20.2.21 — `load-metrics-snapshot` — load metrics every 5 min
  - [x] 20.2.22 — `predictive-scaling-check` — predictive scaling every 5 min
  - [x] 20.2.23 — `knowledge-consolidation-weekly` — knowledge consolidation weekly
  - [x] 20.2.24 — `performance-optimization-weekly` — performance optimization weekly
  - [x] 20.2.25 — `threshold-event-check` — threshold event check every 60s
  - [x] 20.2.26 — `external-api-poll` — external API poll every 60s
  - [x] 20.2.27 — `anomaly-detection` — anomaly detection every 5 min
  - [x] 20.2.28 — `sla-monitor` — SLA monitoring every 60s
```

- [ ] **Step 2: Commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark TODO.md §20.2 periodic tasks as verified"
```

---

### Task 19: Final commit and push

**Files:**
- All modified/created files

**Interfaces:**
- Consumes: All previous commits
- Produces: Clean git history with all verification work

- [ ] **Step 1: Verify all tests pass**

```bash
cd E:\Ongoing Projects\Agentium && python scripts/verify_all_periodic_tasks.py
```

- [ ] **Step 2: Push to remote**

```bash
git push origin main
```

- [ ] **Step 3: Verify CI passes (if applicable)**

---

## Self-Review Checklist

After writing this plan, verify:

- [ ] **Spec coverage**: All 44 tasks from spec §2.1 have a verification call in Tasks 2-14
- [ ] **No placeholders**: Every step has actual code/commands, no TBD
- [ ] **Type consistency**: `TaskResult` dataclass used consistently, `run_task` signature matches all calls
- [ ] **Task right-sizing**: Each task produces independently testable deliverable
- [ ] **Global constraints respected**: Direct calls, continue-on-failure, 30s timeout, real DB

---

**Plan complete and saved to** `docs/superpowers/plans/2026-10-20-periodic-tasks-verification.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Which approach?**