# Agent Execution Wait Timer (Phase 19.2)

Agents can now pause their execution and wait for an external process (typically a Docker sandbox execution) to complete.

## Usage

```python
# 1. Agent executes code via RemoteExecutorService
executor = RemoteExecutorService(db)
result = await executor.execute(
    code="...",
    agent_id="30001",
    task_id=task.id,
    timeout_seconds=300,
)

execution_id = result["execution_id"]  # e.g., "exec_abc123def"
estimated_duration = 60  # seconds, agent's estimate

# 2. Agent enters WAIT state
orchestrator = AgentOrchestrator(db)
condition = orchestrator.enter_wait(
    task_id=task.id,
    strategy="execution",
    config={"execution_id": execution_id},
    poll_interval_seconds=20,   # per spec: check at most every 20s
    timeout_seconds=estimated_duration,
    actor_id="30001",
)

# 3. Task status becomes WAITING
# 4. Celery Beat polls every 20s (poll-execution-conditions)
# 5. When execution COMPLETES/FAILS, task resumes IN_PROGRESS or FAILS
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `poll_interval_seconds` | 20 | Check interval for this specific condition |
| `timeout_seconds` | Required | Hard deadline after which condition expires |
| `max_attempts` | 60 | Maximum poll iterations before expiry |

## Strategies

The `execution` strategy joins the existing wait strategies:
- `http_poll` — Poll HTTP endpoint
- `redis_key` — Wait for Redis key
- `timeout` — Pure time-based wait
- `webhook` — External webhook resolution
- `manual` — Manual API resolution
- **`execution` — Wait for RemoteExecutionRecord completion** (NEW)

## Monitoring

Check Celery Beat logs:
```
poll_execution_conditions: {"resolved": 2, "expired": 0, "errors": 0, "skipped": 5}
```

WebSocket event on resolution:
```json
{
  "type": "wait_resolved",
  "task_id": "...",
  "task_agentium": "T00001",
  "condition_id": "...",
  "strategy": "execution",
  "resolved_at": "2026-07-09T12:34:56.789"
}
```