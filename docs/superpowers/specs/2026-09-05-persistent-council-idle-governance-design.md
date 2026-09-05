# Persistent Council & Idle Governance — Design Specification

**Date:** 2026-09-05  
**Status:** Draft  
**Related TODO Section:** 6.4 — Persistent Council & Idle Governance

---

## 1. Overview

This design completes the **Persistent Council & Idle Governance** subsystem (Section 6.4 of the verification backlog). It adds the missing Health Monitor agent, implements hybrid token budgeting for idle tasks, strengthens isolation guarantees, and enhances scheduled maintenance tasks.

### Current State (Implemented)
- 3 eternal agents: Head (00001), System Optimizer (10001), Strategic Planner (10002)
- `EnhancedIdleGovernanceEngine` with eternal loop (10s interval)
- Scheduled tasks: idle detection (daily), auto-liquidation (6h), resource rebalancing (hourly)
- Per-agent cooldowns, system-wide task deduplication
- Token budget (`idle_budget`) with DB-persisted limits from `ModelUsageLog`
- Pauses idle work when user tasks arrive (`_pause_idle_work`)

### Gaps to Address
| TODO Item | Gap |
|-----------|-----|
| 6.4.1 | Council agents activate during idle periods ✅ |
| 6.4.2 | System Optimizer runs maintenance tasks ⚠️ (stubs only) |
| 6.4.3 | Strategic Planner schedules future work ⚠️ (stubs only) |
| 6.4.4 | **Health Monitor agent missing** ❌ |
| 6.4.5 | Idle governance doesn't interfere with active tasks ⚠️ (soft pause only) |
| 6.4.6 | Token budget respects `DAILY_TOKEN_BUDGET_USD` ⚠️ (local-only, no cost-justified API) |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PERSISTENT COUNCIL (Eternal)                    │
├──────────────────┬────────────────────────────┬────────────────────────┤
│  00001           │  10001                     │  10002                 │
│  Head of Council │  System Optimizer          │  Strategic Planner     │
│  (Overseer)      │  (Storage, Vectors,        │  (Prediction,          │
│                  │   Archival, Cache)         │   Scheduling, Planning)│
└──────────────────┴────────────────────────────┴────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         HEALTH MONITOR (NEW: 10003)                     │
│  Agent Liveness  │  System Resources  │  Channel Health  │  Anomalies  │
│  Auto-Recovery   │  Alerting          │  Predictive API*   │             │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ENHANCED IDLE GOVERNANCE ENGINE                      │
│  • Eternal loop (10s) + Scheduled tasks (daily/6h/hourly)             │
│  • Hybrid token budget (local-first, cost-justified API)              │
│  • Medium isolation: priority yielding, max 1 idle task, TTL          │
│  • Per-agent cooldowns, system-wide deduplication                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 Persistent Council — Add Health Monitor (10003)

**File:** `backend/services/persistent_council.py`

#### New Agent Spec
```python
COUNCIL_3_SPEC = {
    'agentium_id': '10003',
    'name': 'Health Monitor',
    'description': 'Persistent council member focused on system health, anomaly detection, and automated recovery.',
    'specialization': 'health_monitoring',
    'persistent_role': PersistentAgentRole.HEALTH_MONITOR.value
}
```

#### Ethos: "The Order of the Vigilant Watch"
- **Mission:** "I am the Watcher in the Void. I see what others miss. I heal before the Sovereign knows there's a wound."
- **Core Values:** Vigilance, Prevention, Transparency, Automated Recovery
- **Behavioral Rules:**
  1. Monitor agent heartbeats every 60s; detect stalled/crashed agents
  2. Check system resources (CPU, memory, disk, DB pool, Redis) every 10min
  3. Deep-validate channel/bridge connectivity every 15min
  4. Correlate anomalies across agents/tasks/channels every 30min
  5. Execute auto-recovery: restart agents, rebalance load, trigger overflow review
  6. Alert on critical findings via system_alert WebSocket events
  7. **Cost-justified API**: Daily predictive analysis to forecast failures
- **Restrictions:** No direct host access (proxy through Head), no spawning, no constitution edits, no task execution
- **Capabilities:** Deep system introspection, automated remediation, alert escalation, predictive modeling

#### Initialization
Added to `initialize_persistent_council()` after Council Member 2:
```python
# 5. Initialize Council Member 3 (10003) — Health Monitor
council_3 = PersistentCouncilService._initialize_council_member(
    db, PersistentCouncilService.COUNCIL_3_SPEC, head.id, force_recreate
)
results['council_members'].append(council_3.agentium_id)
```

---

### 3.2 Health Monitor Idle Tasks

**New File:** `backend/services/idle_tasks/health_monitor.py`

```python
class HealthMonitorIdleTask:
    """Idle tasks for the Health Monitor agent (10003)."""
    
    TASK_TYPES = [
        TaskType.AGENT_HEALTH_SCAN,        # Every 5 min (cooldown)
        TaskType.SYSTEM_RESOURCE_CHECK,    # Every 10 min
        TaskType.CHANNEL_DEEP_HEALTH,      # Every 15 min
        TaskType.ANOMALY_CORRELATION,      # Every 30 min
        TaskType.AUTO_RECOVERY_ACTION,     # On detection
        TaskType.PREDICTIVE_HEALTH_API,    # Daily (cost-justified)
    ]
```

| Task Type | Description | Frequency | Cost Justification |
|-----------|-------------|-----------|-------------------|
| `AGENT_HEALTH_SCAN` | Check `last_heartbeat_at`, detect stalled/crashed agents, auto-reassign orphaned tasks | 5 min cooldown | Local DB queries — $0 |
| `SYSTEM_RESOURCE_CHECK` | CPU, memory, disk, DB pool, Redis queue depth; trigger auto-scale if >80% | 10 min cooldown | Local — $0 |
| `CHANNEL_DEEP_HEALTH` | Test bridge connectivity (round-trip), verify message delivery, auto-reconnect | 15 min cooldown | Local — $0 |
| `ANOMALY_CORRELATION` | Cross-reference metrics using isolation forest; detect systemic issues | 30 min cooldown | Local ML (sklearn) — $0 |
| `AUTO_RECOVERY_ACTION` | Restart stalled agents, rebalance load, trigger overflow review | Event-driven | Local — $0 |
| `PREDICTIVE_HEALTH_API` | **Cost-justified**: LLM analyzes patterns, predicts failures, recommends preemptive actions | Daily | API allowed iff `estimated_savings > estimated_cost * 1.5` |

#### Integration with Idle Governance Engine
In `_assign_idle_work()`, Health Monitor (10003) gets priority for system-wide tasks:
```python
if agent.agentium_id == '10003':
    # Health Monitor gets first pick of system-wide health tasks
    available_system = self._get_available_system_tasks()
    if available_system:
        task_type = available_system[0]
    else:
        task_type = TaskType.PREDICTIVE_HEALTH_API  # Daily predictive
```

---

### 3.3 Hybrid Token Budget for Idle Tasks

**Files:** `backend/services/token_optimizer.py`, `backend/services/idle_governance.py`

#### Policy
- **Default:** All idle tasks use local models (`idle_model_key = "local:kimi-2.5-7b"`) — zero cost
- **Exception:** Task may request API if it proves **net token savings**:
  ```python
  def can_use_api_for_idle_task(
      task_type: str, 
      estimated_api_cost_usd: float, 
      estimated_tokens_saved: int
  ) -> bool:
      avg_cost_per_token = idle_budget.daily_cost_limit / idle_budget.daily_token_limit
      savings_value = estimated_tokens_saved * avg_cost_per_token
      return savings_value > estimated_api_cost_usd * 1.5  # 50% safety margin
  ```

#### Budget Tracking Extensions
```python
# In IdleBudgetManager.get_status()
{
    "daily_cost_limit_usd": 5.0,
    "cost_used_today_usd": 2.30,
    "idle_api_cost_today_usd": 0.15,
    "idle_tokens_saved_today": 45000,
    "idle_net_savings_usd": 0.85,
    "api_calls_allowed_remaining": 3,
    "data_source": "api_usage_logs"
}
```

#### Idle Task Execution Flow
```python
async def _execute_idle_work(self, db, agents):
    for agent in agents:
        task = self.current_idle_tasks[agent.agentium_id]
        
        if task.task_type == TaskType.PREDICTIVE_HEALTH_API:
            # Check cost justification
            est_cost = estimate_llm_cost(task)
            est_savings = estimate_tokens_saved_by_predictive_planning()
            
            if not can_use_api_for_idle_task(task.task_type, est_cost, est_savings):
                # Fall back to local model
                task.task_type = TaskType.PREDICTIVE_PLANNING_LOCAL
                logger.info(f"Predictive health: API not cost-justified, using local model")
        
        # ... execute with appropriate model ...
```

---

### 3.4 Medium Isolation Guarantees

**File:** `backend/services/idle_governance.py`

| Mechanism | Implementation |
|-----------|----------------|
| **Max 1 concurrent idle task** | `self._idle_semaphore = asyncio.Semaphore(1)` in `__init__`; acquire in `_execute_idle_work` |
| **Priority yielding** | Idle tasks call `await asyncio.sleep(0)` at yield points; check `self._get_pending_user_tasks(db)` every 5s |
| **TTL auto-cancel** | Each idle task gets `max_duration_seconds=300`; tracked in `task.started_at`; auto-fail if exceeded |
| **CPU priority** | `os.nice(10)` at start of idle task execution (Unix); lower thread priority on Windows |
| **DB connection reservation** | Idle tasks use dedicated connection pool (`pool_size=2`) separate from user request pool |
| **Immediate preemption** | On user task arrival: `_pause_idle_work()` sets `task.status=INTERRUPTED`, cancels LLM stream via `asyncio.CancelledError`, releases resources |

#### Preemption Flow
```python
async def _pause_idle_work(self, db: Session, reason: str):
    for task_id in self.current_idle_tasks.values():
        task = db.query(Task).filter_by(id=task_id).first()
        if task and task.status == TaskStatus.IN_PROGRESS:
            task.status = TaskStatus.INTERRUPTED
            task.completion_summary = f"Preempted: {reason}"
            # Cancel the executing coroutine
            if task_id in self._running_idle_tasks:
                self._running_idle_tasks[task_id].cancel()
    logger.warning(f"⏸️ Idle work preempted: {reason}")
```

---

### 3.5 Scheduled Task Enhancements

| Task | Current | Enhanced |
|------|---------|----------|
| **Idle detection** | Daily scan for agents idle >7 days | + Real-time index on `last_idle_action_at`; Health Monitor feeds real-time data |
| **Auto-liquidation** | Every 6h, liquidate agents idle >7 days with no tasks | + Health Monitor can recommend early liquidation for unhealthy agents (crash loops, repeated failures) |
| **Resource rebalancing** | Hourly, based on task count | + Weight by CPU/memory/token usage; predictive scaling hints from Strategic Planner |
| **NEW: Constitution review** | — | Daily: Health Monitor validates constitutional compliance of all agents; logs violations |
| **NEW: Predictive scaling** | — | Strategic Planner forecasts load (next 24h), pre-spawns agents if queue depth predicted > threshold |
| **NEW: Health Monitor self-check** | — | Every hour: Health Monitor validates its own operation; alerts if stuck |

#### New Scheduled Tasks in Engine
```python
# In __init__
self.CONSTITUTION_REVIEW_INTERVAL = 86400      # 24 hours
self.PREDICTIVE_SCALING_INTERVAL = 3600        # 1 hour
self.HEALTH_MONITOR_SELF_CHECK_INTERVAL = 3600 # 1 hour

# In _run_scheduled_tasks
if (self.last_constitution_review is None or 
    (now - self.last_constitution_review).total_seconds() >= self.CONSTITUTION_REVIEW_INTERVAL):
    await self.review_constitution_compliance(db)
    self.last_constitution_review = now

if (self.last_predictive_scaling is None or 
    (now - self.last_predictive_scaling).total_seconds() >= self.PREDICTIVE_SCALING_INTERVAL):
    await self.predictive_scaling_check(db)
    self.last_predictive_scaling = now
```

---

## 4. Data Flow

### Idle Task Assignment
```
1. Idle loop wakes (every 10s)
   │
   ├─► Check pending user tasks → if any: pause idle, sleep 5s
   │
   ├─► Get available persistent agents (status=ACTIVE, is_persistent=True)
   │
   ├─► For each agent: _assign_idle_work()
   │     ├─ Check per-agent cooldown (60s)
   │     ├─ Check system-wide task cooldown (5min)
   │     ├─ Select task type by role:
   │     │     00001 → PREFERENCE_OPTIMIZATION (30min) or per-agent tasks
   │     │     10001 → VECTOR_MAINTENANCE, STORAGE_DEDUPE, AUDIT_ARCHIVAL, CACHE_OPTIMIZATION
   │     │     10002 → PREDICTIVE_PLANNING, CONSTITUTION_REFINE, ETHOS_OPTIMIZATION
   │     │     10003 → AGENT_HEALTH_SCAN, SYSTEM_RESOURCE_CHECK, CHANNEL_DEEP_HEALTH, ANOMALY_CORRELATION
   │     ├─ Create Task record (is_idle_task=True, status=IN_PROGRESS)
   │     └─ Update agent.status = IDLE_WORKING
   │
   └─► _execute_idle_work() with semaphore(1), TTL=300s, yield points
```

### Token Budget Decision
```
Idle task wants API model
       │
       ▼
Estimate API cost (from pricing_sync_service)
       │
       ▼
Estimate tokens saved (historical data + task type)
       │
       ▼
savings_value = tokens_saved * (daily_cost_limit / daily_token_limit)
       │
       ▼
savings_value > api_cost * 1.5 ?
       │
       ├─ YES → Allow API, track in idle_budget.idle_api_cost_today_usd
       │
       └─ NO  → Use local model, log justification
```

### Preemption on User Activity
```
User task arrives
       │
       ▼
token_optimizer.record_activity() → idle_mode_active check
       │
       ▼
If idle_mode_active: enter_idle_mode() NOT called (already idle)
       │
       ▼
_next process_intent() call → _get_pending_user_tasks() returns non-empty
       │
       ▼
_idle_loop() → _pause_idle_work() called
       │
       ├─ Set all idle tasks to INTERRUPTED
       ├─ Cancel running coroutines
       ├─ Release semaphore
       └─ Broadcast idle_paused event
```

---

## 5. Error Handling

| Scenario | Handling |
|----------|----------|
| Health Monitor crashes | Head (00001) detects via `last_heartbeat_at`; spawns replacement 10003 |
| Idle task exceeds TTL | Auto-fail task, log timeout, release semaphore, agent → ACTIVE |
| API cost exceeds budget | `can_use_api_for_idle_task()` returns False; fallback to local |
| DB connection pool exhausted | Idle tasks use reserved pool; if exhausted, skip cycle, log warning |
| Constitutional violation during idle | Constitutional Guard blocks action; audit log; agent → SUSPENDED |
| LLM stream cancellation on preemption | Catch `asyncio.CancelledError`, cleanup resources, mark task INTERRUPTED |

---

## 6. Testing Strategy

### Unit Tests
- `test_persistent_council.py`: Verify all 4 agents created with correct specs/ethos
- `test_health_monitor_tasks.py`: Mock DB, verify each task type executes correctly
- `test_token_budget_hybrid.py`: Test cost-justification logic with various scenarios
- `test_isolation.py`: Simulate user task arrival during idle work; verify preemption

### Integration Tests
- `test_idle_governance_e2e.py`: Full cycle — idle → work → user task → preemption → resume
- `test_token_budget_persistence.py`: Restart engine, verify budget loads from DB
- `test_auto_liquidation.py`: Create idle agents, verify liquidation after threshold

### Metrics Validation
- Idle task CPU < 5% during user activity (load test)
- Token cost of idle governance < $0.50/day (net positive)
- Health Monitor detection latency < 30s (inject crash, measure)
- Auto-recovery success rate > 90% (chaos testing)

---

## 7. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Idle task CPU impact during user activity | < 5% | `htop` / `psutil` during load test |
| Token cost of idle governance / day | < $0.50 (net positive) | `idle_budget.get_status()` |
| Health Monitor detection latency | < 30s for agent crash | Timestamp diff: crash → alert |
| Auto-recovery success rate | > 90% | Chaos test: kill agents, count recoveries |
| Zero idle-task interference incidents | 0 per week | Audit log: `INTERRUPTED` tasks vs user task latency |

---

## 8. Implementation Phases

| Phase | Deliverable | Files Modified/Created | Est. Effort |
|-------|-------------|------------------------|-------------|
| **1** | Add Health Monitor agent (10003) + ethos | `persistent_council.py` | 2h |
| **2** | Health Monitor idle task module | `idle_tasks/health_monitor.py` (new) | 4h |
| **3** | Hybrid token budget logic | `token_optimizer.py`, `idle_governance.py` | 3h |
| **4** | Medium isolation mechanisms | `idle_governance.py` | 3h |
| **5** | Scheduled task enhancements | `idle_governance.py` | 2h |
| **6** | Integration tests + metrics dashboard | `test_idle_governance.py`, `MonitoringPage.tsx` | 4h |

**Total Estimated Effort:** ~18 hours

---

## 9. Rollback Plan

If issues arise post-deployment:
1. **Disable Health Monitor**: Set `is_persistent=False` for 10003 in DB
2. **Revert to local-only**: Set `idle_cost_multiplier = 0.0`, disable `can_use_api_for_idle_task`
3. **Disable preemption**: Remove semaphore/TTL logic, revert to soft pause
4. **Feature flags**: Add `IDLE_GOVERNANCE_HEALTH_MONITOR_ENABLED`, `IDLE_GOVERNANCE_HYBRID_BUDGET_ENABLED` env vars

---

## 10. Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Add Health Monitor (10003)? | **Yes** — completes the triad |
| Health Monitor tasks? | **Agent liveness, system resources, channel health, anomaly correlation, auto-recovery, predictive API** |
| Token budget policy? | **Hybrid** — local-first, cost-justified API with 50% margin |
| Isolation level? | **Medium** — semaphore(1), TTL=300s, yield points, preemption on user task |

---

## 11. Appendix: File Inventory

### New Files
- `backend/services/idle_tasks/health_monitor.py`

### Modified Files
- `backend/services/persistent_council.py` — Add COUNCIL_3_SPEC, ethos, initialization
- `backend/services/idle_governance.py` — Hybrid budget, isolation, scheduled tasks, Health Monitor integration
- `backend/services/token_optimizer.py` — `can_use_api_for_idle_task()`, extended budget status
- `backend/models/entities/agents.py` — Verify `HEALTH_MONITOR` enum exists (already present)

### Test Files (to create)
- `tests/test_persistent_council.py`
- `tests/test_health_monitor_tasks.py`
- `tests/test_token_budget_hybrid.py`
- `tests/test_isolation.py`
- `tests/test_idle_governance_e2e.py`