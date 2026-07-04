# ADR-003: Celery over asyncio for Background Task Processing

## Status

Accepted (2026-07-04)

## Context

Agentium performs a significant amount of work outside the HTTP request/response cycle: periodic health checks of external channels, auto-scaling based on queue depth, self-healing routines (crash detection, circuit breaker escalation), anomaly detection, knowledge consolidation, task delegation, and federation heartbeats. These operations share three critical characteristics:

1. **Scheduling**: Many tasks must run at fixed intervals (e.g., crash detection every 30 seconds, anomaly detection every 5 minutes, knowledge consolidation weekly).
2. **Distributed execution**: Tasks may need to run on different machines to isolate failure or for load distribution.
3. **Durability**: If the web server restarts, in-flight tasks should survive, and results should be retrievable.

Before adopting Celery, the system explored Python's built-in `asyncio` and `async def` for background work. While `asyncio` works perfectly for FastAPI's WSGI/ASGI request handling, it does not natively provide task scheduling, distributed queuing, or result persistence. Building a custom background task system on top of `asyncio` would require re-implementing scheduling, queueing, retries, and distributed state — a significant engineering burden equivalent to half a new product.

## Decision

Adopt **Celery** (broker and backend: Redis) as the exclusive framework for all background task processing. Use `asyncio` only for the FastAPI web layer's request handling, not for business logic background work.

### Architecture

Three Docker services form the task infrastructure:

| Service | Role | Celery Component |
|---------|------|-----------------|
| `celery-worker` | Processes background tasks | Celery Worker (autoscaling, prefork) |
| `celery-beat` | Triggers periodic tasks | Celery Beat Scheduler (APScheduler) |
| `redis` | Message broker and result store | Broker + Result Backend |

### Why Celery Exclusively

| Feature | Celery | Pure asyncio |
|---------|--------|-------------|
| **Task scheduling** | ✅ Celery Beat with cron-like schedules | ❌ Manual `asyncio.sleep` loops; async scheduling libraries exist but are immature |
| **Distributed workers** | ✅ Out of the box; multiple workers, multiple machines | ❌ No built-in; must implement own protocol |
| **Task queueing** | ✅ Redis-backed `ack`/`unack` | ❌ In-memory only (lost on restart unless wired to Redis) |
| **Result tracking** | ✅ `AsyncResult` objects, result backends | ❌ Manual state machine or external key-value store |
| **Retries** | ✅ `@task(bind=True, max_retries=N, countdown=...)` | ❌ Manual `try/except` + `asyncio.sleep` block |
| **Exponential backoff** | ✅ Built-in retry with custom countdown | ❌ Manual calculation |
| **Dead letter queue** | ✅ Result backend captures failures | ❌ Manual |
| **Task inspection** | ✅ Flower, `celery inspect active` | ❌ Debug via logs only |
| **Priority queues** | ✅ Queue routing by priority | ❌ Manual heap or separate queues |
| **Serialization** | JSON (configurable) | N/A (object in memory) |

### Why Not Alternatives

| Alternative | Rejected Because |
|-------------|-----------------|
| **Prefect / Dagster** | Orchestration platforms, not task queues. Over-engineered for simple periodic tasks. They introduce their own infrastructure (databases, UI, agents) that would be redundant with Celery+Redis. |
| **Temporal / Cadence** | Industry-grade workflow engines. Heavy operational overhead, proprietary UIs, and the complexity of "temporal" programming model (event sourcing) is unjustified for Agentium's task graph. |
| **Apache Airflow** | Data pipeline orchestrator, not a general task queue. Overhead of a full DAG definition language for simple Celery tasks. |
| **Native `asyncio` + Redis** | Possible, but would require implementing ~1,500 lines of equivalent `Celery` infrastructure. Time sink, risk of bugs. Celery is battle-tested in production at scale. |
| **Rq (Redis Queue)** | Simpler, mature. Rejected at the time of initial design because Celery had broader ecosystem, richer beat scheduling, and better community support for the project's specific requirements (broadcasting, WebSocket integration, task chains). In retrospect, either would have worked. |

### When to Use asyncio

- **FastAPI request handlers**: Database queries, external HTTP calls, WebSocket operations.
- **`ConstitutionalGuard`**: `Tier 2` check is `async` by nature (remote ChromaDB + Redis).
- Do **not** use `asyncio` for background business logic (task delegation, heartbeat tasks). Route those through Celery.

### Testing Mode

In test mode, `CELERY_TASK_ALWAYS_EAGER=True` forces all Celery tasks to run synchronously in the calling thread. This ensures tests remain deterministic and do not require a real Redis or live worker.

## Consequences

### Positive

1. **Mature, battle-tested infrastructure**: Celery+Redis has been in production for over a decade, with well-understood failure modes and a vast community.
2. **Declarative scheduling**: Adding a new periodic task is a one-line entry in `celery_app.conf.beat_schedule`.
3. **Scalable**: Horizontal scaling is trivial — add more Celery worker containers and Celery's distributed queue distributes tasks automatically.
4. **Observability**: Flower provides a UI for monitoring tasks, and `celery inspect active` works out of the box.
5. **Rich retry semantics**: Exponential backoff with max retries is a one-liner in the `@celery_app.task()` decorator.

### Negative

1. **Task naming inconsistency**: The system currently uses two naming conventions: `agentium.tasks.task_executor.*` for business logic and `agentium.celery_app.*` for Celery-native tasks (e.g., `broadcast_channel_health`, `federation_heartbeat`). This is an architectural debt (see Phase 18.3 Celery Task Naming Convention audit).
2. **Serialization overhead**: All arguments and results must be JSON-serialisable. Custom objects must be flattened. The `pickle` serializer was rejected due to security.
3. **Redis as a single point of failure**: If Redis goes down, the broker and result backend are unavailable. However, the web server (FastAPI) remains functional, and critical paths (e.g., direct DB writes) do not depend on Redis.
4. **Celery beat can drift**: Long-running periodic tasks can overlap or drift if not properly configured `ack_late=True` and `prefetch_multiplier=1`. The system uses `expires` options where critical.
5. **Startup dependency**: Celery worker and beat containers must start after Redis is ready. The `docker-compose.yml` handles this with `depends_on` and `healthcheck`, but on rapid restarts, the worker may crash and restart.
6. **Memory bloat in long-running workers**: Celery workers can accumulate memory over time. The system partially mitigates this by using `max_tasks_per_child` and periodic restarts, but this is an ongoing tuning concern.
