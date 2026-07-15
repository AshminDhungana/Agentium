# Agentium Implementation Roadmap

**Project:** Agentium — Personal AI Agent Nation  
**Version:** 0.0.9-alpha  
**Architecture:** Dual-Storage (PostgreSQL + ChromaDB) with hierarchical agent orchestration  
**Status:** Phase 17 ✅ Complete | Phase 18 🚧 In Progress  
_Last Updated: 2026-05-21 · Maintainer: Ashmin Dhungana_

---

## Vision

Build a self-governing AI ecosystem where agents operate under constitutional law, make decisions through democratic voting, and manage their own lifecycle — all while being transparent, auditable, and sovereign.

---

## Progress Overview

| Phase | Name                           | Status         |
| ----- | ------------------------------ | -------------- |
| 0     | Foundation Infrastructure      | ✅ Complete    |
| 1     | Knowledge Infrastructure       | ✅ Complete    |
| 2     | Governance Core                | ✅ Complete    |
| 3     | Agent Lifecycle Management     | ✅ Complete    |
| 4     | Multi-Channel Integration      | ✅ Complete    |
| 5     | AI Model Integration           | ✅ Complete    |
| 6     | Advanced Execution Ecosystem   | ✅ Complete    |
| 7     | Frontend Development           | ✅ Complete    |
| 8     | Testing & Reliability          | ✅ Complete    |
| 9     | Production Readiness           | ✅ Complete    |
| 10    | Advanced Intelligence          | ✅ Complete    |
| 11    | Ecosystem Expansion            | ✅ Complete    |
| 12    | SDK & External Interface       | ✅ Complete    |
| 13    | Autonomous Agent Orchestration | ✅ Complete    |
| 14    | Frontend Reliability & Browser | ✅ Complete    |
| 15    | Platform Hardening & Admin     | ✅ Complete    |
| 16    | Database & Advanced AI Logic   | ✅ Complete    |
| 17    | DevSecOps & Polish             | ✅ Complete    |
| 18    | Complete System Testing        | ✅ Complete    |
| 19    | Additional Features            | 🚧 In Progress |
| 20    | Migrate Embedding Model        | Not Done        |
| End   | Summery_todo.md                | Not Done        |
| New   | Final Checklist todo.md        | Not Done        |

---

## Phase 0: Foundation Infrastructure ✅

- [x] PostgreSQL 15 with proper schemas and foreign key constraints
- [x] Agent hierarchy models (0xxxx / 1xxxx / 2xxxx / 3xxxx)
- [x] Indexes on `agent_type`, `status`, `agentium_id`
- [x] Constitution model with version control
- [x] Alembic migrations
- [x] Voting entity models with vote tallying
- [x] Audit log system with immutable records
- [x] Docker Compose orchestration with health checks and network isolation
- [x] Core entity models: `agents.py`, `constitution.py`, `voting.py`, `audit.py`, `user.py`, `base.py`

---

## Phase 1: Knowledge Infrastructure ✅

- [x] ChromaDB client with persistent storage; embedding model: `all-MiniLM-L6-v2` (384-dim)
- [x] Collections: `constitution_articles`, `agent_ethos`, `task_learnings`, `domain_knowledge`
- [x] `store_knowledge()`, `query_similar()`, `update_knowledge()`, `delete_knowledge()`
- [x] Metadata filtering by `agent_id`, `knowledge_type`, `timestamp`
- [x] RAG pipeline: query embedding → similarity search → context window construction
- [x] Constitutional context injection into every agent prompt
- [x] Knowledge deduplication (cosine similarity > 0.95 → skip)
- [x] Post-task learning: store outcomes as new knowledge
- [x] Top-K retrieval with relevance threshold (0.7 minimum)

---

## Phase 2: Governance Core ✅

- [x] Constitutional Guard (Tier 1 SQL + Tier 2 semantic LLM); verdicts: ALLOW / BLOCK / VOTE_REQUIRED
- [x] Rate limiting: max 100 Tier 2 checks/hour; constitutional cache (5 min TTL)
- [x] Voting Service: proposal types, quorum logic (51% / 75% / 90%), delegation chains, auto-tally
- [x] Amendment Service: full lifecycle propose → vote → ratify → archive; lineage tracking
- [x] Original Constitution protection (never deletable)

---

## Phase 3: Agent Lifecycle Management ✅

- [x] Pre-spawn constitutional check and post-spawn ethos initialization
- [x] Pre/post-task rituals: freshness check, ethos alignment, outcome logging, ethos compression
- [x] Auto-termination: idle > 7 days → Council vote → liquidation
- [x] Emergency agent slot (Head can spawn one 1xxxx emergency agent)
- [x] Agent Orchestrator: intent routing, circuit breaker, multi-model failover, metrics
- [x] Monitoring: background patrols, alert levels INFO → EMERGENCY, alert channels

---

## Phase 4: Multi-Channel Integration ✅

- [x] Channels: WhatsApp (bridge), Telegram, Discord, Slack, Signal, Google Chat, Teams, iMessage, Zalo, Matrix
- [x] Unified message ingestion, channel-specific rate limiting, message persistence and replay
- [x] Unified Inbox — all channels in one thread view (`UnifiedInbox.tsx`)
- [x] Loop prevention, media normalization (object storage)

---

## Phase 5: AI Model Integration ✅

- [x] Provider support: OpenAI, Anthropic, Groq, Ollama, any OpenAI-compatible endpoint
- [x] Automatic failover on rate limit or timeout; token budget enforcement per tier
- [x] Streaming via WebSocket; dynamic model discovery
- [x] A/B testing framework (`ab_testing.py`); financial burn dashboard

---

## Phase 6: Advanced Execution Ecosystem ✅

- [x] Tool Creation Service: Council approval workflow, schema validation, sandboxing
- [x] Acceptance Criteria Service: machine-validatable task success conditions
- [x] Context Ray Tracing: role-based visibility, sibling isolation for critics
- [x] Checkpointing & Time-Travel: phase boundaries, restore, branch, `CheckpointTimeline.tsx`
- [x] Remote Code Executor: sandboxed Docker, PII isolation, `RemoteExecutionRecord`
- [x] MCP Server Integration: tier-based tool approval, per-invocation audit logging, `ToolRegistry.tsx`, revocation
- [ ] Real-time MCP tool usage stats; revoked tools unavailable in < 1 second

---

## Phase 7: Frontend Development ✅

- [x] Pages: Login, Signup, Dashboard, Agents, Tasks, Chat, Settings, Monitoring, Constitution, Channels, Models, Voting, Sovereign Dashboard
- [x] Agent Tree, Voting Interface, Constitution Editor, Critic Dashboard, Checkpoint Timeline, Financial Burn Dashboard, Voice Indicator, Unified Inbox
- [ ] Drag-and-drop agent reassignment
- [x] Checkpoint diff view (compare branches)
- [x] Channel health monitoring and message logs
- [x] Channel-specific settings (rate limits, filters)

---

## Phase 8: Testing & Reliability ✅

- [x] 87.8% error catch rate via critic layer; 92.1% overall task success rate
- [x] Zero data loss on container restart; graceful degradation when Vector DB unavailable
- [x] Performance targets hit: constitutional check < 50 ms, routing < 100 ms, API p95 < 500 ms
- [x] 1,000 tasks/hour throughput; 100 concurrent dashboard users

---

## Phase 9: Production Readiness ✅

- [x] Audit logs: 90-day hot retention; weekly Vector DB reindex; task cold storage after 30 days
- [x] PostgreSQL: daily full backup (7-day rotation); vector snapshot (4-week rotation); PITR (30 days)
- [x] JWT + RBAC (Sovereign / Council / Lead / Task); rate limiting per IP; XSS sanitization; MFA; HTTPS
- [x] Kubernetes manifests, Helm charts, Prometheus + Grafana, GitHub Actions CI/CD (amd64 / arm64)
- [ ] Query optimization and slow query logging
- [ ] Connection pool tuning
- [ ] Git versioning backups for config files
- [ ] Audit trail for privilege escalations
- [ ] DDoS hardening at application layer

---

## Phase 10: Advanced Intelligence ✅

### 10.1 Browser Control

- [x] Research, form-filling, price monitoring, social posting, e-commerce via Playwright (headless Chromium)
- [x] URL whitelist/blacklist, SSRF prevention, content filtering, screenshot audit logging
- [x] Per-session memory / cookie isolation
- [x] Live screenshot stream UI for browser tasks (CDP Page.startScreencast capture + View Live gating wired; browser tasks 1–6 complete)

### 10.2 Advanced RAG

- [x] Source attribution and confidence scoring per fact
- [x] Contradiction detection across sources
- [x] Automatic fact-checking against Vector DB
- [x] Cross-document citation graph
- [x] Confidence decay on stale knowledge entries

### 10.3 Voice Interface

- [x] Speech-to-text (OpenAI Whisper); text-to-speech (OpenAI TTS)
- [x] WebSocket streaming (real-time voice → agent → voice)
- [x] Voice bridge (`voice-bridge/`) — local STT/TTS support
- [x] Voice channels: phone (Twilio), Discord voice
- [x] Speaker identification for multi-user voice sessions

### 10.4 Autonomous Learning

- [x] Task outcome analysis, best-practice extraction, anti-pattern detection
- [x] Knowledge consolidation (daily background task)
- [x] Learning decay — reduce weight of outdated patterns
- [x] Cross-agent learning sharing (federated knowledge pool)

---

## Phase 11: Ecosystem Expansion ✅

- [x] **11.1 Multi-User RBAC** — `primary_sovereign`, `deputy_sovereign`, `observer` roles; time-limited delegation; observer read-only enforcement; `RBACManagement.tsx`
- [x] **11.2 Federation** — federated instances, tasks, votes; signed JWT exchange; federated knowledge sync and voting; `FederationPage.tsx`
- [x] **11.3 Plugin Marketplace** — Council-verified plugins; sandboxed execution; revenue share ledger; `ToolMarketplacePage.tsx`
- [x] **11.4 Mobile Apps** — device registration, push (FCM/APNs), iOS/Android stubs, offline mode, voice commands
- [x] **11.5 Scalability** — expanded agent ID length; Kubernetes horizontal scaling; virtual list rendering; ChromaDB sharding strategy

---

## Phase 12: SDK & External Interface ✅

- [x] Python SDK (`pip install agentium-sdk`): `AgentiumClient`, async-first, `asyncio` + `httpx`
- [x] TypeScript SDK (`npm install @agentium/sdk`): full type safety, auto-generated from OpenAPI spec
- [x] All SDK calls produce identical audit trails (`X-SDK-Source` header)
- [x] Outbound webhooks: task events, votes, constitutional changes; HMAC-SHA256; exponential backoff retry
- [x] Fully annotated OpenAPI 3.1 spec at `/docs`; developer portal with code samples (curl / Python / TypeScript)

---

## Phase 13: Autonomous Agent Orchestration 🚧

**Goal:** Maximum automation for large-scale agent management — self-healing, predictive scaling, and continuous self-improvement — without human intervention on routine operations.

**Version target:** 1.2.0-alpha  
**Builds on:** circuit breaker (`agent_orchestrator.py`), partial `auto_scale_check` stub (`task_executor.py`), Celery beat schedule, ChromaDB RAG pipeline, checkpoint service, voting service.

### What Already Exists — Do Not Rewrite

| Component                      | Location                  | Phase 13 Extends It By…                                          |
| ------------------------------ | ------------------------- | ---------------------------------------------------------------- |
| Circuit breaker (per-agent)    | `agent_orchestrator.py`   | Auto-escalate `OPEN` state → Council micro-vote                  |
| `auto_scale_check` Celery task | `task_executor.py`        | Actually call `AgentLifecycleService.spawn_agent()` — stub today |
| Celery beat schedule           | `celery_app.py`           | Add 12 new beat entries for predictive scaling, learning, events |
| Constitutional Guard (2-tier)  | `constitutional_guard.py` | Feed repeated violations → auto-propose amendments               |
| Checkpoint service             | `services/checkpoints.py` | Use as reincarnation anchor for crashed agents                   |
| ChromaDB RAG pipeline          | `rag_service.py`          | Real-time learning writes immediately after task completion      |
| Monitoring service             | `monitoring_service.py`   | Expand into zero-touch ops dashboard with anomaly detection      |
| Voting service                 | `voting_service.py`       | Support auto-proposed amendments and micro-votes from automation |

---

### 13.1 Automatic Task Delegation Engine

**Purpose:** Eliminate manual task routing — every task is automatically scored, broken down, and assigned to the correct agent tier.

#### Backend

- [x] **Complexity Analyzer** (`backend/services/auto_delegation_service.py`) — score tasks 1–10 on creation; map: 1–3 → `3xxxx` TaskAgent, 4–6 → `2xxxx` LeadAgent, 7–10 → Council deliberation
- [x] **Sub-task Breakdown** — for score ≥ 7, decompose via LLM mini-call; persist sub-tasks with `parent_task_id` FK and dependency order in new `task_dependencies` junction table
- [x] **Capability-Aware Assignment** — rank candidate agents by `(1 - error_rate) × (1 / current_load)` using `CapabilityRegistry`
- [x] **Auto-Escalation Timer** — Celery beat every 60 s: tasks stuck in `in_progress` beyond `escalation_timeout` (default 300 s) → re-assign to next tier or trigger Council micro-vote
- [x] **Dependency Graph Parallelizer** — build DAG from `task_dependencies`; dispatch independent branches as parallel Celery `group()` tasks
- [x] **Priority Queue Rebalancer** — on `CRITICAL` / `SOVEREIGN` task arrival, re-sort the Celery queue without losing in-flight tasks
- [x] **Smart Retry Router** — on failure, re-dispatch to a different agent of the same tier; never retry on an agent with `CB_OPEN`
- [x] **Cost-Aware Delegation** — if `idle_budget < 20%`, force simple tasks to local Ollama regardless of tier preference

#### Alembic Migration — `009_task_delegation.py`

- [x] `task_dependencies` table: `task_id` (FK), `depends_on_task_id` (FK), `dependency_type` (`sequential | parallel`), `created_at`
- [x] `complexity_score` (Integer, nullable) on `tasks`
- [x] `escalation_timeout_seconds` (Integer, default 300) on `tasks`
- [x] `delegation_metadata` (JSONB) on `tasks`

#### API Routes

- [x] `POST /tasks/auto-delegate` — force re-delegation with optional `force_tier`
- [x] `GET /tasks/{id}/delegation-log` — return delegation decision trail from `delegation_metadata`
- [x] `GET /tasks/{id}/dependency-graph` — return DAG as `{ nodes, edges }` for frontend rendering

#### Frontend

- [x] `AutoDelegationPanel.tsx` — complexity score badge, tier assignment rationale, candidate agents ranked by score
- [x] Manual override dropdown — calls `POST /tasks/auto-delegate`
- [x] DAG viewer using React-Flow; nodes colored by status, edges labeled sequential vs parallel
- [x] Escalation countdown timer on in-progress tasks (amber → red as timeout approaches)
- [x] Extend `TaskCard.tsx` — add complexity score pill and "delegated by AI" vs "manually assigned" label

---

### 13.2 Self-Healing & Auto-Recovery System

**Purpose:** Detect failures and recover automatically without human intervention.

#### Backend

- [x] **Circuit Breaker → Council Auto-Escalation** — when `CB_OPEN` transitions, immediately enqueue a `EMERGENCY` micro-vote via `VotingService`; currently silent
- [x] **Exponential Backoff** — replace fixed 60 s retry in `execute_task_async` with `min(2 ** retry_count, 60)` seconds (1 → 2 → 4 → 8 → 16 → 32 → 60 cap)
- [x] **Agent Crash Detection** (`backend/services/reincarnation_service.py`) — Celery beat every 30 s: agents with `status = 'working'` and `last_heartbeat_at > 2 min` → mark crashed, emit `agent_crashed` WebSocket event
- [x] **State Restoration from Checkpoint** — on crash, call `CheckpointService.get_latest(agent_id)`; restore `ethos`, `current_task_id`, `context_window_snapshot`
- [x] **Agent Reincarnation** — spawn replacement via `AgentFactory` with restored state; re-queue interrupted task in `ASSIGNED` status
- [x] **Graceful Degradation Mode** — if all API providers have `CB_OPEN`: pause tasks with `priority < HIGH`, continue CRITICAL/SOVEREIGN on local Ollama, emit `system_mode_change` WebSocket banner
- [x] **Critical Path Protection** — tag tasks that are DAG ancestors of CRITICAL/SOVEREIGN leaves; reserve one agent slot permanently for these chains
- [x] **Self-Diagnostic Routine** — daily Celery beat: check DB connection pool, Redis ping, ChromaDB collection counts, disk usage, stale task count; auto-propose constitutional amendment if repeated violations detected
- [x] **DB Connection Pool Auto-Recovery** — wrap `CelerySessionLocal` in `tenacity` retry loop (5 attempts, 2 s wait) on `OperationalError`
- [x] **Heartbeat Task** — Celery beat every 60 s: each active agent writes `last_heartbeat_at = utcnow()`

#### Alembic

- [x] Add `last_heartbeat_at` (DateTime, nullable) column to `agents` table

#### Beat Schedule Additions to `celery_app.py`

- [x] `agent-heartbeat` — 60 s
- [x] `crash-detection` — 30 s
- [x] `self-diagnostic-daily` — 86400 s
- [x] `critical-path-guardian` — 120 s

#### Frontend

- [x] Self-Healing Events feed in `MonitoringPage.tsx` — reincarnation events, circuit state changes, degradation activations
- [x] System mode banner: normal (hidden) / degraded (amber) / critical (red) — driven by `system_mode_change` WebSocket event
- [x] "One-Click Rollback" button per healing action — calls `POST /admin/rollback/{audit_id}`

---

### 13.3 Predictive Auto-Scaling

**Purpose:** Anticipate workload changes and scale proactively, not reactively.

#### Backend

- [x] **Time-Series Store** (`backend/services/predictive_scaling.py`) — every 5 min, snapshot `pending_task_count`, `active_agent_count`, `avg_task_duration_seconds`, `token_spend_last_5m` to Redis sorted set; retain 7 days, auto-trim
- [x] **Load Predictor** — weighted moving average (`[0.5, 0.3, 0.2]`) over time-series; output: `next_1h`, `next_6h`, `next_24h` predictions
- [x] **Pre-Spawn Decision** — if `next_1h_prediction > current_capacity × 0.8`: call `AgentLifecycleService.spawn_agent(tier=3)` immediately; log to `AuditLog`
- [x] **Pre-Liquidation Decision** — if `next_6h_prediction < current_agents × 0.3` AND agent idle > 30 min: trigger existing auto-termination path
- [x] **Fix `auto_scale_check` stub** — replace `# In production: actually spawn agents` comment with real `AgentLifecycleService.spawn_agent(tier=3, count=recommended_agents, db=db)` call
- [x] **Resource-Aware Scheduler** — check Redis memory and PG connection pool before spawning; if either > 85%, delay non-critical dispatch 30 s
- [x] **Token Budget Guard** — daily cap via `DAILY_TOKEN_BUDGET_USD` env var (default `10.00`); at 80% downgrade new task allocations to cheapest model; at 100% pause non-CRITICAL tasks, emit `budget_exceeded` WebSocket event
- [x] **Time-Based Policy** — read `BUSINESS_HOURS_TZ`, `BUSINESS_HOURS_START`, `BUSINESS_HOURS_END` env vars; outside hours, cap active task agents at 2

#### Beat Schedule Additions

- [x] `load-metrics-snapshot` — 300 s
- [x] `predictive-scaling-check` — 300 s

#### API Routes (`backend/api/routes/scaling.py` — new file)

- [x] `GET /predictions/load` — return `{ next_1h, next_6h, next_24h, current_capacity, recommendation }`
- [x] `GET /scaling/history` — last 100 scaling decisions from `AuditLog`
- [x] `POST /scaling/override` — `{ action: 'spawn' | 'liquidate', count, tier }` (admin only)

#### Frontend — `ScalingDashboard.tsx` (new page at `/scaling`)

- [x] Four KPI cards: Active Agents, Pending Tasks, Token Spend Today (USD), Capacity %
- [x] Load Prediction Chart (Recharts `LineChart`): actual 24 h history + predicted `next_1h` + `next_6h` series
- [x] Scaling Events Timeline: spawn/liquidate events with rationale; click to expand AuditLog entry
- [x] Manual Override Panel: "Spawn N Agents" / "Liquidate N Idle Agents" controls + tier selector
- [x] Budget Gauge: radial gauge amber at 80%, red at 100%
- [x] Poll `GET /predictions/load` every 60 s; subscribe to `scaling_event` WebSocket

---

### 13.4 Continuous Self-Improvement Engine

**Purpose:** System that learns from its own operations and measurably improves over time.

#### Backend

- [x] **Learning Impact Tracker** — Redis hash `agentium:learning:impact`; 7-day rolling success rate delta; expose via `GET /improvements/impact`

#### Beat Schedule Additions

- [x] `knowledge-consolidation-weekly` — 604800 s
- [x] `anti-pattern-scan` — 3600 s

#### API Routes (`backend/api/routes/improvements.py` — new file)

- [x] `GET /improvements/impact` — learning impact metrics (success rate delta, tools generated, amendments auto-proposed)
- [x] `GET /improvements/patterns` — detected anti-patterns with recurrence count
- [x] `POST /improvements/consolidate` — manual trigger of knowledge consolidation (admin only)

#### Frontend — `LearningImpactDashboard.tsx` (new component)

- [x] Success Rate Trend (Recharts `AreaChart`) — 30-day rolling rate with "learning event" vertical markers
- [x] Auto-Generated Tools list: name, trigger pattern, usage count, success rate
- [x] Anti-Pattern Warnings feed: pattern description, recurrence count, amendment status
- [x] Knowledge Base Stats: total learnings, federated contributions, consolidations run

---

### 13.5 Workflow Automation Pipeline

**Purpose:** End-to-end repeatable workflows defined once, executed automatically on schedule, event, or demand.

#### Backend — New Models (`backend/models/entities/workflow.py`)

- [x] `Workflow` entity: `id`, `agentium_id`, `name`, `description`, `template_json` (JSONB), `version` (int), `is_active`, `created_by_agent_id`, `schedule_cron`, `created_at`, `updated_at`
- [x] `WorkflowExecution` entity: `id`, `workflow_id`, `status` (`pending | running | paused | completed | failed`), `current_step_index`, `context_data` (JSONB), `started_at`, `completed_at`, `triggered_by`
- [x] `WorkflowStep` entity: `id`, `workflow_id`, `step_index`, `step_type` (`task | condition | parallel | human_approval | delay`), `config` (JSONB), `on_success_step`, `on_failure_step`

#### Alembic Migration — `008_workflow_engine.py`

- [x] Create `workflows`, `workflow_executions`, `workflow_steps` tables with indexes on `workflow_id`, `status`, `is_active`
- [x] Create `workflow_versions` audit table for version history snapshots

#### Backend — Workflow Engine (`backend/services/workflow_engine.py`)

- [x] **Step Executor** — iterate steps: Celery task dispatch for `task` steps, sandboxed `eval()` for `condition` steps, Celery `group()` for `parallel` steps, WebSocket pause for `human_approval` steps
- [x] **Conditional Branching** — config: `{ "field": "last_task_output.status", "operator": "eq", "value": "success", "on_true": 3, "on_false": 5 }`; only `context_data` in eval scope, no builtins
- [x] **Cron Scheduler** — on startup, register all `schedule_cron` workflows as dynamic Celery beat entries; de-register and re-register on update
- [x] **ETA Calculator** — use last 10 execution durations to estimate current run ETA
- [x] **Workflow Versioning** — on update, increment `version`, archive current `template_json` to `workflow_versions`
- [x] **Auto-Documentation** — on completion, LLM-generate a natural language summary of what was done; append to `Workflow.description` and store in `task_learnings`

#### API Routes (`backend/api/routes/workflows.py` — new file)

- [x] `GET /workflows` — list with pagination
- [x] `POST /workflows` — create from template JSON
- [x] `GET /workflows/{id}` — detail with steps
- [x] `PUT /workflows/{id}` — update (auto-increments version)
- [x] `POST /workflows/{id}/execute` — trigger immediate execution
- [x] `GET /workflows/{id}/executions` — execution history
- [x] `GET /workflows/{id}/executions/{eid}` — live execution state
- [x] `POST /workflows/{id}/executions/{eid}/approve` — approve `human_approval` step
- [x] `GET /workflows/{id}/executions/{eid}/eta` — estimated completion time
- [x] `GET /workflows/{id}/versions` — version history
- [x] `POST /workflows/{id}/rollback` — rollback to prior version (admin)

#### Frontend

- [x] **`WorkflowsPage.tsx`** (new page at `/workflows`) — library list: name, version, last run status, next scheduled run, action buttons (Run Now / Edit / Duplicate / Archive)
- [x] **`WorkflowDesigner.tsx`** (new page at `/workflows/:id`) — drag-and-drop canvas; step type tiles; config drawer per node; conditional edges labeled "✓ True" / "✗ False"; version history sidebar with JSON diff viewer
- [x] **`WorkflowExecutionMonitor.tsx`** (new page at `/workflows/:id/executions/:eid`) — live step highlighting; human approval modal with approve/reject buttons; ETA countdown badge; bottleneck detection (steps exceeding median duration)

---

### 13.6 Intelligent Event Processing ✅

**Purpose:** Automatically react to external webhooks, threshold breaches, and scheduled polls — translating signals into tasks and workflows without manual dispatch.

#### Backend — New Models (`backend/models/entities/event_trigger.py`)

- [x] `EventTrigger` entity: `id`, `name`, `trigger_type` (`webhook | schedule | threshold | api_poll`), `config` (JSONB), `target_workflow_id` (FK nullable), `target_agent_id` (FK nullable), `is_active`, `last_fired_at`, `fire_count`
- [x] `EventLog` entity: `id`, `trigger_id`, `event_payload` (JSONB), `status` (`processed | dead_letter | duplicate`), `correlation_id` (UUID), `created_at`

#### Alembic Migration — `004_event_triggers.py`

- [x] Create `event_triggers` and `event_logs` tables

#### Backend — Event Processor (`backend/services/event_processor.py`)

- [x] **Webhook Receiver** (`POST /events/webhook/{trigger_id}`) — HMAC-SHA256 validation; 24 h Redis deduplication by `correlation_id`; enqueue `process_event` Celery task
- [x] **Threshold Monitor** — Celery beat every 60 s: evaluate `config.metric` expressions against live Redis metrics from 13.3; respect `config.cooldown_seconds`
- [x] **External API Poller** — Celery beat every `config.poll_interval_seconds`: `GET config.url`; compare response hash to last known hash in Redis; fire on change
- [x] **Event Correlation Engine** — group `EventLog` entries with same `correlation_id` prefix within 60 s window; submit as single consolidated task
- [x] **Dead Letter Queue** — events failing processing 3 times → `dead_letter` status; expose for manual review
- [x] **Circuit Breaker for Events** — if a trigger fires > `config.max_fires_per_minute` (default 10) per minute, pause trigger for `config.pause_duration_seconds`

#### Beat Schedule Additions

- [x] `threshold-event-check` — 60 s
- [x] `external-api-poll` — 60 s

#### API Routes (`backend/api/routes/events.py` — new file)

- [x] `GET /events/triggers` — list all triggers
- [x] `POST /events/triggers` — create trigger
- [x] `PUT /events/triggers/{id}` — update trigger
- [x] `DELETE /events/triggers/{id}` — deactivate
- [x] `POST /events/webhook/{trigger_id}` — public receiver (HMAC only, no Bearer)
- [x] `GET /events/logs` — paginated log filtered by `status`, `trigger_id`
- [x] `GET /events/dead-letters` — dead letter queue viewer
- [x] `POST /events/dead-letters/{id}/retry` — manual retry

#### Frontend — `EventTriggerManager.tsx` (tab in SovereignDashboard)

- [x] Trigger list: name, type badge, last fired, fire count, active toggle
- [x] Trigger creation form: type selector drives dynamic config fields (webhook → generated URL + HMAC secret; threshold → metric/operator/value dropdowns; api_poll → URL/headers/interval fields)
- [x] Event Log tab: scrollable log with status badges; click to expand full payload JSON

---

### 13.7 Zero-Touch Operations Dashboard

**Purpose:** Single unified view of all autonomous systems with automated incident response for known failure patterns.

#### Backend — Extend `monitoring_service.py`

- [x] **Metrics Aggregator** (`GET /monitoring/aggregated`) — combine agent health, circuit breaker states, scaling events (24 h), learning impact delta, workflow success rates, event trigger fire rates; cache in Redis for 10 s
- [x] **Anomaly Detector** — Celery beat every 5 min: compute Z-score for `task_duration`, `error_rate`, `token_spend_per_hour` vs 7-day baseline; if Z-score > 2.5, create `ViolationReport` severity `major` and push via WebSocket
- [x] **Automated Incident Response** — `KNOWN_PATTERNS` dict: on match, call `fix_fn()` automatically; log to `AuditLog` with `action = 'auto_remediated'`
- [x] **SLA Monitor** — track time-to-resolution for tasks with `escalation_timeout_seconds`; compute SLA compliance rate; expose `GET /monitoring/sla`
- [x] **Capacity Planner** — include `capacity_forecast` in `/monitoring/aggregated`: 7-day agent count recommendation from historical volume

#### Beat Schedule Additions

- [x] `anomaly-detection` — 300 s
- [x] `sla-monitor` — 60 s

#### API Routes (extend `monitoring_routes.py`)

- [x] `GET /monitoring/aggregated` — unified metrics snapshot
- [x] `GET /monitoring/sla` — SLA compliance metrics
- [x] `GET /monitoring/anomalies` — active anomalies list
- [x] `POST /monitoring/chaos-test` — inject controlled failure (admin, rate-limited 1/hour)
- [x] `POST /admin/rollback/{audit_id}` — revert automated action by audit ID (admin)

#### Frontend — Extend `MonitoringPage.tsx`

- [x] **Unified Status Row** — five health rings (Agents / Tasks / Workflows / Events / Budget) using existing `HealthRing` component; data from `GET /monitoring/aggregated`
- [x] **Anomaly Feed** — live list with Z-score, affected metric, auto-remediation status badge (`auto-fixed | pending | escalated`)
- [x] **Automated Incident Log** — table of `auto_remediated` AuditLog entries; "Rollback" button per row calling `POST /admin/rollback/{audit_id}`
- [x] **SLA Dashboard** — gauge per task priority with compliance rate; 30-day trend sparkline
- [x] **Cost Analytics** — bar chart of daily token spend by provider; projected monthly cost; budget utilization %
- [x] **Chaos Engineering Panel** — "Inject Failure" button (admin) with type selector (`agent_crash | api_timeout | db_connection_loss`); shows test results inline
- [x] Subscribe to WebSocket event types: `anomaly_detected`, `auto_remediated`, `sla_breach`, `budget_warning`

---

### Phase 13 — Migrations & Celery Beat Summary

#### Alembic Migrations

| File                     | Purpose                                                                                               |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| `007_task_delegation.py` | `task_dependencies`, `complexity_score`, `escalation_timeout_seconds`, `delegation_metadata` on tasks |
| `008_workflow_engine.py` | `workflows`, `workflow_executions`, `workflow_steps`, `workflow_versions`                             |
| `009_event_triggers.py`  | `event_triggers`, `event_logs`                                                                        |

#### New Celery Beat Entries (add to `celery_app.py`)

```python
'agent-heartbeat':                { 'task': '...heartbeat',             'schedule': 60.0    },
'crash-detection':                { 'task': '...crash_detection',       'schedule': 30.0    },
'self-diagnostic-daily':          { 'task': '...self_diagnostic',       'schedule': 86400.0 },
'critical-path-guardian':         { 'task': '...critical_path_check',   'schedule': 120.0   },
'load-metrics-snapshot':          { 'task': '...metrics_snapshot',      'schedule': 300.0   },
'predictive-scaling-check':       { 'task': '...predictive_scale',      'schedule': 300.0   },
'knowledge-consolidation-weekly': { 'task': '...consolidate_learnings', 'schedule': 604800.0},
'anti-pattern-scan':              { 'task': '...anti_pattern_scan',     'schedule': 3600.0  },
'threshold-event-check':          { 'task': '...threshold_event_check', 'schedule': 60.0    },
'external-api-poll':              { 'task': '...external_api_poll',     'schedule': 60.0    },
'anomaly-detection':              { 'task': '...anomaly_detection',     'schedule': 300.0   },
'sla-monitor':                    { 'task': '...sla_monitor',           'schedule': 60.0    },
```

#### New Frontend Routes (add to `App.tsx`)

| Path                             | Component                      |
| -------------------------------- | ------------------------------ |
| `/scaling`                       | `ScalingDashboard.tsx`         |
| `/workflows`                     | `WorkflowsPage.tsx`            |
| `/workflows/:id`                 | `WorkflowDesigner.tsx`         |
| `/workflows/:id/executions/:eid` | `WorkflowExecutionMonitor.tsx` |
| `/events`                        | `EventTriggerManager.tsx`      |

#### Implementation Order

1. **13.2 Self-Healing** first — heartbeat and crash detection are required by 13.3 for accurate agent counts
2. **13.1 Task Delegation** — `task_dependencies` table (Migration 007) is required by 13.5
3. **13.3 Predictive Scaling** — fix `auto_scale_check` stub now that 13.2 heartbeats provide accurate capacity data
4. **13.6 Event Processing** — independent; can be built in parallel
5. **13.4 Self-Improvement** — depends on real-time learning data from 13.1 completions
6. **13.5 Workflow Engine** — depends on 13.1, 13.2, and 13.6 being stable
7. **13.7 Zero-Touch Dashboard** — aggregates metrics from all prior sub-phases

#### Phase 13 — Success Criteria

- [ ] Task created, complexity-scored, broken into sub-tasks, and assigned to correct tier without a single manual action
- [ ] Simulated agent crash detected, reincarnated from checkpoint, interrupted task resumed within 3 minutes
- [ ] Load predictor pre-spawns agents before simulated surge; no pending task waits > 60 s for an agent
- [ ] Task success rate improvement ≥ 5% measurable in `GET /improvements/impact` after 7 days
- [ ] 5-step workflow with conditional branching and one human-approval gate executes end-to-end from cron trigger
- [ ] External webhook fires → task created and dispatched within 10 seconds
- [ ] Zero-Touch Dashboard shows all 5 health rings green under normal operating conditions
- [ ] Daily token budget guard prevents overspend: CRITICAL tasks continue, normal tasks pause

---

## Phase 14: Frontend Reliability & Browser 🔮

**Goal:** Harden the frontend runtime and complete browser task visibility.

### 14.1 Live Screenshot Stream for Browser Tasks

- [x] **Backend** — extend `browser.py`: emit screenshot frames as base64 via WebSocket event `browser_frame` at configurable FPS (default 2); add `GET /browser/sessions/{id}/stream` endpoint for polling fallback
- [x] **Frontend** — `BrowserTaskViewer.tsx`: subscribe to `browser_frame` WebSocket events; render frames in an `<img>` tag with smooth replacement; show URL bar, page title, and action log alongside screenshot
- [x] Add to `TaskCard.tsx`: "View Live" button when `task_type = 'browser'` and status is `in_progress`; opens `BrowserTaskViewer` in a modal or slide-over panel

### 14.2 WebSocket Reconnection Logic

- [x] **Frontend** (`frontend/src/store/websocketStore.ts`) — implement exponential backoff reconnection: attempt after 1 s, 2 s, 4 s, 8 s, max 30 s; cap total attempts at 10 before showing manual reconnect prompt
- [x] Show non-intrusive reconnection banner ("Reconnecting…") during disconnection; dismiss automatically on successful reconnect
- [x] On reconnect, re-subscribe to all active WebSocket topics and replay any missed events from a server-side event buffer (Redis list, last 100 events per client, 60 s TTL)
- [x] **Backend** — add `GET /ws/replay?since=<timestamp>` endpoint to serve buffered events; integrate with existing `manager.broadcast`

### 14.3 Global Frontend Error Boundaries

- [x] Create `ErrorBoundary.tsx` — React class component implementing `componentDidCatch`; renders a styled fallback UI with "Retry" button and collapsible error details
- [x] Wrap every route-level page component in `ErrorBoundary` (update `App.tsx` router)
- [x] Add per-widget `ErrorBoundary` around all dashboard cards so one widget failure does not crash the page
- [x] Send caught errors to backend `POST /frontend/errors` endpoint (new route); log to `AuditLog` with category `SYSTEM`; display count in `MonitoringPage.tsx` error feed

---

## Phase 15: Platform Hardening & Admin 🔮

**Goal:** Close remaining security, observability, and operational gaps.

### 15.1 Audit Trail for Privilege Escalations

- [x] **Backend** — on every `PATCH /users/{id}/role` or capability grant call, write an `AuditLog` entry with `category = SECURITY`, `level = WARNING`, capturing `actor_id`, `target_user_id`, `old_role`, `new_role`, `expires_at`, `ip_address`
- [x] Add `GET /audit/privilege-escalations` route: paginated, filterable by `actor_id`, `target_id`, date range
- [x] **Frontend** — add "Privilege Escalation Log" tab to `RBACManagement.tsx`; table with actor, target, role change delta, timestamp, expiry; export to CSV button

### 15.2 Real-Time MCP Tool Stats & Sub-Second Revocation

- [x] **Backend** — track per-tool invocation count, average latency, last-used timestamp, error rate in a Redis hash (`agentium:mcp:stats:{tool_id}`) updated on every invocation in `audit_tool_invocation()`
- [x] `GET /mcp-tools/stats` — return live stats for all tools from Redis (not DB); response time < 50 ms
- [x] Revocation path: on `revoke_mcp_tool(tool_id)`, write to Redis SET `agentium:mcp:revoked` with no TTL; check this set before every invocation in `get_approved_tools()` — eliminates DB roundtrip, achieving < 1 s revocation
- [x] **Frontend** — extend `ToolRegistry.tsx`: add stats columns (invocations / avg latency / error rate) to the tool table; live-update via WebSocket event `mcp_stats_update` (emit every 30 s from Celery beat)

### 15.3 Channel Health Monitoring, Logs & Settings

- [x] **Backend** — `GET /channels/{id}/health` — return: connection status, last message timestamp, error count (last 24 h), circuit breaker state, rate limit utilization
- [x] `GET /channels/{id}/logs` — paginated `ExternalMessage` history with filters for `status`, `sender_id`, date range
- [x] `PATCH /channels/{id}/settings` — update per-channel rate limit, auto-create-tasks flag, default agent assignment, content filters
- [x] Celery beat every 5 min: emit `channel_health_update` WebSocket event for all active channels
- [x] **Frontend** — build full channel management UI in `ChannelsPage.tsx`:
  - Health tab: status badge, last message time, error count, circuit breaker indicator per channel
  - Logs tab: scrollable message history with status filtering and sender search
  - Settings tab: rate limit slider, auto-task toggle, default agent dropdown, content filter keyword list

### 15.4 Speaker Identification for Voice System

- [x] **Backend** — extend `audio.py`: on each audio chunk, run speaker embedding extraction (use `pyannote.audio` speaker diarization or a lightweight ECAPA-TDNN model); map embedding to registered speaker profile in `speaker_profiles` DB table
- [x] New `speaker_profiles` table: `id`, `user_id` (FK nullable), `name`, `embedding` (float array stored as JSONB), `created_at`
- [x] `POST /audio/speakers/register` — enroll a new speaker from an audio sample; compute and store embedding
- [x] `GET /audio/speakers` — list registered speaker profiles
- [x] On identification, attach `speaker_id` to incoming `ExternalMessage` before routing to agent; include in task context
- [x] **Frontend** — add "Speaker Profiles" section to voice settings; "Register Voice" button with microphone recording UI; list of enrolled speakers with delete option

---

## Phase 16: Database & Advanced AI Logic 🔮

**Goal:** Optimize data layer performance and deepen AI reasoning capabilities.

### 16.1 Database Connection Pool Tuning & Slow Query Logging

- [x] **Connection Pool Tuning** — configure `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle` in `backend/core/database.py` based on expected concurrency (start: `pool_size=20, max_overflow=10, pool_recycle=1800`)
- [x] Add `pool_pre_ping=True` to main app engine (already done for Celery engine — replicate)
- [x] **Slow Query Logging** — enable PostgreSQL `log_min_duration_statement = 500` via `docker-compose.yml` command args; parse logs in a Celery task and write summaries to `AuditLog` with category `SYSTEM`
- [x] Add `GET /admin/slow-queries` endpoint: return top 20 slowest queries from last 24 h, aggregated from PG `pg_stat_statements` view
- [x] **Frontend** — add "Slow Queries" tab to `MonitoringPage.tsx`: table of query hash, call count, avg duration, last seen; link to explain plan documentation

### 16.2 Learning Decay for Outdated Knowledge Patterns

- [x] **Backend** — extend `rag_service.py`: add `decay_score` (float, default 1.0) to ChromaDB metadata on every `task_learnings` document
- [x] Weekly Celery beat task `decay-learnings`: for each document, compute age in days since `last_validated_at`; apply `decay_score = max(0.1, decay_score × 0.95 ^ days_since_validation)` for documents older than 30 days
- [x] Modify `query_similar()` to multiply cosine similarity by `decay_score` before ranking, so stale knowledge naturally sinks below fresh knowledge
- [x] When a task completes successfully and a learning was retrieved, reset `last_validated_at = utcnow()` and `decay_score = min(1.0, decay_score + 0.1)` — validation boosts confidence

### 16.3 Cross-Document Citation Graph for RAG

- [x] **Backend** — on every RAG retrieval, record `{ source_doc_id, cited_by_doc_id, task_id, timestamp }` to a PostgreSQL `citation_edges` table (Migration 010)
- [x] `GET /knowledge/citation-graph?root={doc_id}&depth={n}` — return graph as `{ nodes, edges }` BFS-traversed up to depth `n` (default 2)
- [x] Use citation frequency to boost `query_similar()` ranking: documents cited more often receive a `citation_boost` multiplier (cap at 1.3×)
- [x] **Frontend** — add "Citation Graph" tab to knowledge management page (or constitution page): force-directed D3 graph; click node to expand one more hop; node size = citation frequency

### 16.4 Git Versioning Backups for Config Files

- [x] **Backend** — new service `backend/services/config_versioning.py`: on any write to constitution articles, model configs, plugin configs, or channel settings, commit a snapshot to a bare Git repo at `/data/config-repo`
- [x] Use `gitpython` library; commit message format: `[auto] {entity_type}/{entity_id} updated by {actor_id} at {timestamp}`
- [x] `GET /admin/config-history/{entity_type}/{entity_id}` — return list of Git commits for that entity
- [x] `POST /admin/config-restore/{entity_type}/{entity_id}?commit={sha}` — restore entity to a specific commit's snapshot (admin only)
- [x] Mount `/data/config-repo` as a named Docker volume in `docker-compose.yml` for persistence across container restarts

---

## Phase 17: DevSecOps & Polish 🔮

**Goal:** Harden the application against abuse, and elevate the UI to production-quality across all surfaces.

### 17.1 Application-Layer DDoS Hardening

- [x] **Rate Limiting Enhancement** — move from IP-only rate limiting to layered limits: per-IP (existing), per-user (authenticated), per-endpoint category (auth endpoints stricter than read endpoints)
- [x] Add `slowapi` (or custom FastAPI middleware) for endpoint-specific limits: `POST /auth/*` → 5 req/min; `POST /tasks` → 30 req/min; general API → 200 req/min
- [x] **Payload Size Limits** — enforce max request body size (default 1 MB) via FastAPI middleware; separate larger limit for file upload endpoints
- [x] **Suspicious Pattern Detection** — Celery beat every 5 min: query request logs for IPs with > 100 4xx responses in 5 min → auto-add to Redis blocklist (`agentium:blocked:ips`) with 1 h TTL
- [x] Nginx config (`nginx.conf`): add `limit_req_zone` and `limit_conn_zone` directives as a first line of defense before FastAPI
- [x] `GET /admin/blocked-ips` — list currently blocked IPs with TTL; `DELETE /admin/blocked-ips/{ip}` — manual unblock

### 17.2 System-Wide UI Polish

- [x] **Dark Mode Consistency** — audit all pages for hardcoded `bg-white`, `text-black`, `border-gray-*` without `dark:` variants; replace with semantic tokens using the existing dark mode system
- [x] **Animations & Transitions** — add `transition-all duration-200` to all interactive elements (buttons, cards, modals, dropdowns) where missing; add skeleton loading states to all data-fetching components that don't already have them
- [x] **Empty States** — design and implement empty state illustrations/messages for: agent list (no agents), task list (no tasks), inbox (no messages), knowledge base (no documents), workflow list (no workflows)
- [x] **Toast Notifications** — standardize success/error/info toasts across all forms (currently inconsistent between pages); use a single shared `useToast()` hook
- [x] **Loading Consistency** — replace all ad-hoc `Loader2` spinners with a unified `<LoadingSpinner size="sm|md|lg" />` component

### 17.3 Mobile Responsiveness for Complex Pages

- [x] Audit breakpoints for: `TasksPage.tsx`, `AgentTree.tsx`, `VotingPage.tsx`, `MonitoringPage.tsx`, `ConstitutionPage.tsx` — all currently desktop-first
- [x] `TasksPage.tsx` — collapse table view to card view below `md:` breakpoint; slide-over for task details instead of inline expansion
- [x] `AgentTree.tsx` — horizontal scroll for deep hierarchies on mobile; collapsible tier groups
- [x] `VotingPage.tsx` — stack vote cards vertically on mobile; move amendment diff to expandable accordion
- [x] `MonitoringPage.tsx` — stack metric cards to 1-column grid below `sm:`; health rings resize to 40px
- [x] New `WorkflowDesigner.tsx` (Phase 13.5) — canvas uses touch events (`onTouchStart/Move/End`) for drag-and-drop on tablet; view-only mode on phone

### 17.4 Accessibility (ARIA Labels & Keyboard Navigation)

> **Status (2026-07-15):** Accessibility audit **completed** as part of a dedicated remediation pass. All items below are implemented and verified by automated axe-core tests (see `frontend/src/test/a11y.ts` + `frontend/src/test/a11yBrowser.tsx`, the `npm run test:a11y` browser gate, and the `frontend-a11y.yml` CI workflow). Page-level color-contrast still requires a live-backend audit (pages fire API calls on mount and could not be rendered in isolated tests).

- [x] **ARIA Labels** — audit all icon-only buttons (pencil, trash, settings gear, expand/collapse) and add `aria-label` attributes; audit all form inputs for associated `<label>` elements
- [x] **Keyboard Navigation** — ensure all interactive elements are reachable via Tab; a global `:focus-visible` ring is applied in `src/index.css`; modal focus trap + focus restore implemented in `src/components/ui/Modal.tsx` (+ `useFocusTrap`); all modals standardized on the shared primitive
- [x] **Screen Reader** — add `role="status"` and `aria-live="polite"` to real-time updating regions (task status, WebSocket event feed, vote tallies, nav unread badge, message log); add `role="alert"` to error messages (present in DelegateTaskModal payload errors and elsewhere)
- [x] **Color Contrast** — run `axe-core` audit against a real Chromium layout (color-contrast rule enabled); fixed `dark:text-*-500 → dark:text-*-400` and light `*-600 → *-700` violations across 9 shared components, covered by `*.a11y.browser.test.tsx`
- [x] Add `skipToContent` link as the first focusable element on every page
- [x] **CI gate** — `npm run test:a11y` wired into `.github/workflows/frontend-a11y.yml` so contrast/ARIA regressions fail the build

## Phase 18: Complete System Testing & Production Readiness 🔮

**Goal:** Validate the entire Agentium platform end-to-end across all 17 prior phases, resolve remaining technical debt, ship a clean and documented codebase, and confirm every acceptance criterion before public release.

---

### 18.1 End-to-End Integration Test Suite

**Purpose:** Automated tests that exercise the full agent lifecycle, governance pipeline, orchestration engine, and all Phase 13–17 features in a single harness.

#### Backend — Test Infrastructure (`backend/tests/integration/`)

- [x] **Test Fixture Factory** (`conftest.py`) — pytest fixtures for: a seeded PostgreSQL database with all migrations applied, a live ChromaDB instance, Redis flushed to a known state, Celery worker in eager mode (`CELERY_TASK_ALWAYS_EAGER=True`), and a mock AI provider returning deterministic responses
- [x] **Agent Lifecycle Suite** (`test_agent_lifecycle.py`) — spawn → assign task → complete task → verify ethos update → idle 7-day simulation → auto-termination Council vote; assert every state transition writes an `AuditLog` entry with correct `category` and `level`
- [x] **Governance Pipeline Suite** (`test_governance.py`) — constitutional check ALLOW / BLOCK / VOTE_REQUIRED paths; amendment propose → vote → ratify lifecycle; assert original constitution is never deletable via any API surface
- [x] **Orchestration Suite** (`test_orchestration.py`) — auto-delegation complexity scoring 1–10 maps to correct tier; sub-task DAG dispatches independent branches in parallel; simulated `last_heartbeat_at > 2 min` triggers crash detection and reincarnation from checkpoint; predictive scaling pre-spawns agents before a simulated surge
- [x] **Workflow Engine Suite** (`test_workflow_engine.py`) — 5-step workflow with `task → condition → parallel → human_approval → task`; cron trigger via `schedule_cron`; version increment on update; rollback to prior version; ETA estimation within 20% of actual
- [x] **RAG Pipeline Suite** (`test_rag.py`) — store → query → deduplication (cosine ≥ 0.95 skips); decay score applied at query time; citation graph BFS to depth 2 returns correct `{ nodes, edges }`; retrieved context is injected into agent prompt
- [x] **Multi-Channel Suite** (`test_channels.py`) — mock inbound message per channel type (Telegram, Discord, Slack, WhatsApp); verify loop prevention; assert `speaker_id` is attached to `ExternalMessage` after speaker identification
- [x] **Security Suite** (`test_security.py`) — expired JWT returns 401; observer role cannot mutate agents or tasks (403); rate limit returns 429 after threshold; HMAC-SHA256 webhook validation rejects tampered payload; XSS payload in task `description` is sanitized before storage

#### CI Integration

- [x] Add `pytest-cov` to `requirements-dev.txt`; enforce minimum 80% line coverage on `backend/services/`; fail CI build below threshold
- [x] Add `pytest-asyncio` for all async FastAPI route tests using `httpx.AsyncClient` with `ASGITransport`
- [x] GitHub Actions job `integration-tests`: spin up `docker-compose -f docker-compose.test.yml up -d` (PostgreSQL + Redis + ChromaDB); run full suite; upload HTML coverage report as CI artifact
- [x] Create `docker-compose.test.yml` — ephemeral containers with no persistent volumes; `TESTING=true` env var disables external AI provider calls and activates mock responses

---

### 18.2 Feature Verification & Regression Testing

**Purpose:** Systematically confirm each phase's acceptance criteria still holds after all cross-phase modifications, and close the remaining open items from Phases 6, 7, and 13.

#### Outstanding Items from Prior Phases

- [x] **Phase 6 — MCP Revocation Sub-Second** — revoke a tool via `DELETE /mcp-tools/{id}/approve`; invoke the same tool within 1 second; confirm `403 Tool revoked` response sourced from Redis SET (`agentium:mcp:revoked`), not a DB query; assert no `SELECT` issued to PostgreSQL during revocation check
- [x] **Phase 7 — Drag-and-Drop Agent Reassignment** — implement in `AgentTree.tsx` via `react-dnd`; on drop, call `PATCH /agents/{id}/parent` with `new_parent_id`; run constitutional guard check before persisting; display validation toast on BLOCK verdict
- [x] **Phase 7 — Checkpoint Diff View** — implement `CheckpointDiffViewer.tsx` using Monaco Editor diff API (`createDiffEditor`); add `GET /checkpoints/{id}/diff?compare_to={id2}` backend route returning a unified diff of `context_window_snapshot` JSON; wire "Compare Branches" button in `CheckpointTimeline.tsx`
- [x] **Phase 13 — Success Criteria Walkthrough** — execute all 8 listed success criteria from §Phase 13 manually in staging; document pass/fail result per criterion; open a tracked GitHub Issue for any failure before marking Phase 18 complete

#### Performance Regression Gate

- [x] Run `locust` load test at 1,000 concurrent users for 5 minutes against staging; assert: constitutional check p95 < 50 ms, task routing p95 < 100 ms, API p95 < 500 ms — matching Phase 8 targets
- [x] Celery throughput: assert ≥ 1,000 tasks/hour under the `locust` task-submission scenario; compare against Phase 8 baseline
- [x] ChromaDB `query_similar()` with 10,000 seeded documents: assert p95 < 200 ms; measure with `pytest-benchmark` and commit baseline to `benchmarks/`

---

### 18.3 Code Refactoring & Technical Debt Elimination

**Purpose:** Consolidate duplicated logic, replace all remaining stubs with real implementations, and enforce consistent architectural patterns across all phases.

#### Backend

- [x] **Service Layer DB Session Audit** — scan all `backend/services/` files for duplicated session-handling boilerplate; extract into a single `@with_db_session` decorator in `backend/core/dependencies.py` and apply uniformly
- [x] **Rate Limiting Consolidation** — merge Phase 17.1 `slowapi` endpoint limits, Phase 2 constitutional cache TTL logic, and Phase 4 per-channel rate limits into a unified `RateLimitMiddleware` class in `backend/core/middleware.py`; remove all redundant per-route rate limit decorators
- [x] **LLM Client Abstraction** — extract duplicated provider retry and failover logic from `agent_orchestrator.py`, `auto_delegation_service.py`, and `reincarnation_service.py` into a shared `LLMClient` class at `backend/core/llm_client.py`; wire circuit breaker integration and token tracking inside the client
- [x] **Celery Task Naming Convention** — audit all Celery task definitions for consistent `agentium.{module}.{task_name}` naming; update `celery_app.py` beat schedule entries to match; fix any autodiscovery gaps causing tasks to run under incorrect names
- [x] **Alembic Downgrade Coverage** — run `alembic check` against the live database; write missing `downgrade()` functions for any migration that only implements `upgrade()`; verify full round-trip `downgrade base → upgrade head` on a clean DB
- [x] **Pydantic v2 Migration** — replace deprecated `@validator` decorators with `@field_validator` and `.dict()` calls with `.model_dump()` across all `backend/schemas/` files; resolve all `PydanticDeprecatedSince20` warnings
- [x] **Error Response Standardization** — define typed exception classes in `backend/core/exceptions.py` mapped to HTTP status codes; replace all bare `raise HTTPException(...)` calls throughout routes with typed exceptions; enforce uniform response shape `{ "error": str, "code": str, "detail": dict | None }`

#### Frontend

- [x] **API Client Consolidation** — audit `frontend/src/` for inline `fetch()` or `axios` calls outside `frontend/src/services/api.ts`; migrate all to typed request/response generics in the central API module
- [x] **Hook Deduplication** — merge overlapping `useWebSocket`, `usePolling`, and `useAutoRefresh` hooks into a single `useRealtimeData<T>(endpoint, wsEvent, pollIntervalMs)` hook in `frontend/src/hooks/`
- [x] **Dark Mode — Phase 13–15 New Pages** — audit `WorkflowDesigner.tsx`, `WorkflowExecutionMonitor.tsx`, `EventTriggerManager.tsx`, `ScalingDashboard.tsx`, and `LearningImpactDashboard.tsx` for hardcoded `bg-white` / `text-black` / `border-gray-*` without `dark:` variants; apply Phase 17.2 semantic token system
- [x] **Mobile Responsiveness — Phase 13–15 New Pages** — apply Phase 17.3 breakpoint patterns to `WorkflowsPage`, `WorkflowDesigner`, `ScalingDashboard`, and `EventTriggerManager`; collapse complex layouts below `md:`; test on 375px viewport
- [x] **Shared Component Enforcement** — replace all remaining ad-hoc `Loader2` spinner usages with `<LoadingSpinner>`; replace ad-hoc toast calls with `useToast()`; verify no page introduced after Phase 17 bypasses these shared components

---

### 18.4 Codebase Documentation

**Purpose:** Ensure every public service, route, model, and component is self-documenting so a new contributor can onboard without prior context.

#### Backend

- [x] **Service Docstrings** — every public method in `backend/services/` must have a Google-style docstring with `Args`, `Returns`, and `Raises` sections; add `interrogate` to CI (`interrogate backend/services/ --fail-under=90`)
- [x] **OpenAPI Enrichment** — add `summary`, `description`, `response_model`, and example `responses` annotations to every route missing them; confirm `/docs` renders complete documentation for all 80+ endpoints with sample request/response bodies
- [x] **Architecture Decision Records** — write `docs/adr/` entries (one Markdown file each) for: dual-storage rationale (PostgreSQL + ChromaDB), constitutional guard two-tier design, Celery over asyncio for background work, agent ID numbering scheme (`0xxxx / 1xxxx / 2xxxx / 3xxxx`), RAG decay scoring algorithm
- [x] **`CONTRIBUTING.md`** — document: local dev setup (`docker-compose up`), migration workflow (`alembic upgrade head`), test execution (`pytest`), and a full environment variable reference table with defaults and descriptions for all vars in `backend/.env.example`
- [x] **`ARCHITECTURE.md`** — Mermaid diagram of the full stack: services, data flows, WebSocket event bus, Celery beat task schedule, and all external integrations; include agent hierarchy visualization

#### Frontend

- [x] **Component JSDoc** — every component in `frontend/src/components/` must have a JSDoc block documenting its `Props` interface, a usage example, and any WebSocket event types it subscribes to
- [x] **Storybook Setup** — add `@storybook/react` to dev dependencies; create stories for all shared components: `LoadingSpinner`, `ErrorBoundary`, `HealthRing`, `AgentCard`, `TaskCard`, `VoteCard`, `Toast`; add `npm run storybook` to `package.json`
- [x] **`README.md` Rewrite** — update root `README.md` to reflect v1.2.0-alpha feature set; include architecture overview, quick-start (`docker-compose up`), links to `/docs` (OpenAPI) and SDK packages (`agentium-sdk`, `@agentium/sdk`), and a link to the roadmap

---

### 18.5 Code Cleanup & Production Hardening

**Purpose:** Remove all development artifacts, placeholder values, and debug code before release.

#### Cleanup

- [x] **`TODO` / `FIXME` Audit** — run `grep -rn "TODO\|FIXME\|HACK\|XXX" backend/ frontend/`; for each hit: resolve inline, convert to a GitHub Issue with a link comment, or document rationale; target zero unresolved hits inside `backend/services/` and `frontend/src/components/`
- [x] **Placeholder Comment Removal** — remove all `# In production:`, `# TODO: replace with real implementation`, `# Stub`, and equivalent comments that describe missing functionality (the implementation must be complete before the comment is removed)
- [x] **Debug Artifact Purge** — grep for `print()` in Python and `console.log()` in TypeScript outside test files; replace with `logging.getLogger(__name__).debug()` and `logger.debug()` respectively; remove all hardcoded `localhost` URLs outside configuration files
- [x] **Secret Hygiene** — run `detect-secrets scan --baseline .secrets.baseline`; add baseline check to CI; fail build on any newly detected secret
- [x] **Dependency Audit** — run `pip-audit` against `requirements.txt` and `npm audit` against `frontend/package.json`; resolve all HIGH and CRITICAL CVEs; document accepted LOW / MEDIUM risks in `SECURITY.md`
- [x] **Dead Code Elimination** — run `vulture backend/ --min-confidence 80` to detect unused Python functions and variables; run `ts-prune` on the frontend; remove all confirmed dead code with no external references
- [x] **Docker Image Hardening** — switch `Dockerfile` to a non-root user (`USER agentium:agentium`); pin all base image tags to digests (`python:3.11-slim@sha256:...`); run `docker scout cves` and resolve HIGH / CRITICAL findings; verify final image size is minimized via multi-stage build

#### Final Smoke Test

- [x] Deploy to a clean staging environment via `docker-compose up --build` with no pre-existing volumes; confirm all containers reach `healthy` status within 60 seconds
- [x] Verify all 5 monitoring health rings (`Agents / Tasks / Workflows / Events / Budget`) show green in `MonitoringPage.tsx` under no-load conditions
- [x] Confirm `/docs` OpenAPI spec loads without errors and all endpoints are fully documented with example payloads
- [x] Run `npx lighthouse-ci` in CI against the staging frontend; enforce ≥ 90 score on Performance, Accessibility, and Best Practices
- [x] Execute `alembic downgrade base && alembic upgrade head` against the staging database to verify full migration reversibility with no data errors

---

### Phase 18 — Success Criteria

- [x] Integration test suite passes in CI with ≥ 80% line coverage on `backend/services/`; zero test skips
- [x] All 8 Phase 13 acceptance criteria verified as passing end-to-end in staging
- [x] Outstanding Phase 6 and Phase 7 items (MCP revocation timing, agent reassignment, checkpoint diff) implemented and covered by integration tests
- [x] Zero unresolved `TODO` / `FIXME` / `HACK` comments in `backend/services/` and `frontend/src/components/`
- [x] Every public service method and every API route has a docstring or JSDoc block; `interrogate` reports ≥ 90% coverage
- [x] `pip-audit` and `npm audit` report no HIGH or CRITICAL CVEs
- [x] Lighthouse score ≥ 90 on Performance, Accessibility, and Best Practices on the staging frontend
- [x] Full migration round-trip (`downgrade base → upgrade head`) succeeds on a clean database with no errors

---

## Infrastructure Stack

```
ChromaDB   — Vector Storage            (port 8001)
Redis      — Message Bus + Cache       (port 6379)
PostgreSQL — Entity Storage            (port 5432)
Celery     — Background Tasks
FastAPI    — API Gateway               (port 8000)
React      — Frontend                  (port 3000)
Docker     — Remote Executor (sandboxed)
Playwright — Browser Control
Whisper    — Speech-to-Text
OpenAI TTS — Text-to-Speech
```



---

## Additional Features (To be Added Later)

### 19.0 Known Issues & Technical Debt

**High Priority (actively blocking)**

- [x] `auto_scale_check` Celery task only logs scaling intent — does not actually call `AgentLifecycleService.spawn_agent()` — agents are never auto-spawned
- [x] WebSocket reconnection logic lacks exponential backoff; clients disconnect permanently on transient network issues
- [x] Frontend has no global error boundaries — one crashing component brings down the full page

**Medium Priority**

- [x] Browser task live screenshot stream UI (route + CDP capture + View Live gating + browserApi types all complete; see Phase 14.1)
- [x] Checkpoint diff view (branch comparison) — root cause: `GET /checkpoints/compare` was shadowed by the path-param `GET /{checkpoint_id}` route (declared after it), so it 404'd; fixed by declaring `/compare` first. Also added recursive nested diffs + Monaco side-by-side/inline toggle & copy. Frontend `BranchDiffView.tsx` consumes `/compare`; `CheckpointDiffViewer.tsx` uses `/{id}/diff`. Removed the dead `compare_branches()` service method (route diffs inline).
- [x] Channel health monitoring, logs, and settings UI incomplete
- [x] Speaker identification integrated (ECAPA-TDNN via SpeechBrain, injectable backend, liveness seam, min-duration guard)

**Low Priority**

- [x] UI dark mode inconsistencies on newer pages (Workflows, Events pages not yet built)
- [x] Mobile responsiveness gaps on complex pages (Tasks, Voting, Monitoring)
- [x] Accessibility audit not done (ARIA labels, keyboard navigation, color contrast) — completed 2026-07-15
- [x] PostgreSQL slow query logging enabled (pg_stat_statements extension created at startup + in test DB; shared_preload_libraries set in dev & test compose)
- [x] Connection pool sizes set to defaults — not tuned for production load (env-tunable via DATABASE_POOL_SIZE/_MAX_OVERFLOW/_TIMEOUT/_RECYCLE; Celery engines shared)
- [ ] Config files not version-controlled via Git

### 19.1 Multi-Select Checkbox Card (Chat-Window Only)

When the system needs structured input from a user inside the **chat window**, it renders an inline multi-select checkbox card directly in the message thread. The user can select multiple options at once and confirm with a single click, keeping the conversation compact.

**Status:** ✅ Implemented (2026-07-11). Implemented as one `StructuredInputCard` component (N=1..3 questions); the card is a `ChatMessage` with `message_type='input_card'` + `metadata.card`; external channels use `render_external_text()`.

This interaction is **exclusive to the chat window**. When the user is on an external channel such as WhatsApp, SMS, or email, the system falls back to a plain text message listing numbered options and asks for a comma-separated reply.

### 19.1.1 Multi-Question Elicitation Card (Chat-Window Only)

An extension of the multi-select checkbox card that lets the Head of Council (or any agent) ask **a small batch of questions in a single turn**, instead of one question per card. This reduces back-and-forth when the agent needs a few related pieces of information to proceed (e.g. destination, budget, dates) — without recreating the cognitive overload of a long form.

**Status:** ✅ Implemented (2026-07-11). Same `StructuredInputCard` component; questions ordered in payload array order (backend orders easy→hard), hard cap 3 enforced by the Pydantic schema, `>3` chunked via `chunk_questions` sharing a `card_group_id`.

**Batching rule (informed by form-UX research):**

- **Maximum 2–3 questions per card.** Cognitive load research shows people process small chunks (2–3 items) far more reliably than longer batches; beyond that, completion and accuracy drop.
- If the agent has **4 or more** pieces of information to collect, it must **split them across two or more sequential cards** rather than cramming them into one. Each card still follows the 2–3 question cap.
- Within a card, questions are ordered **easiest → hardest** (the "foot-in-the-door" pattern) — quick/low-effort picks first, anything requiring thought or sensitive input last.

**Behavior:**

- The card renders **inline** in the chat thread, with each question as its own block in a single-column layout — no side-by-side fields.
- Each question independently has its own option set (single-select or multi-select, configurable per question).
- Every question's **last option is "Other / Type your own"**, styled identically to the rest (not a visually separate fallback) — selecting it reveals an inline text field scoped to that question.
- A small **"x of y answered"** counter sits at the top of the card, giving lightweight progress visibility without a full step-by-step progress bar (since all questions are visible at once, not paged).
- A single **Confirm** button at the bottom submits all answers (selected options + typed text) together as one structured response.
- Confirm stays disabled until every **required** question has an answer; optional questions can be left blank or explicitly skipped.
- If the user types a free-text message in the main chat box instead of using the card, the entire card auto-dismisses and the message is processed as a normal reply.
- Only one active multi-question card may exist at a time; a new request replaces any unanswered one.
- Once confirmed, the card collapses into a read-only summary bubble listing each question with its chosen/typed answer.
- If a second card immediately follows the first (because the agent split a longer batch), it appears as a new inline card directly below the now-collapsed summary, continuing the conversation rhythm rather than feeling like a fresh interruption.

**Visual Design:**

- Same Tailwind dark-mode system as the single-question card: rounded container, subtle border, indigo accents for selected states.
- Questions are separated by light divider lines within the same card, not individual bordered boxes — keeps it feeling like one compact form, not stacked cards.
- Labels sit above their input (not beside it), left-aligned — reduces visual scanning effort.
- The inline "type your own" field appears directly beneath its question when selected, with a thin indigo outline matching the selected-state style.

**Data Payload:**

The backend triggers the card with a structured payload containing an array of questions (**hard cap: 3**). Each question includes: question text, input type (`single_select` / `multi_select`), a required flag, and an array of options (id, label, value) — with an implicit final "Other" option mapping to a free-text value rather than a fixed id. An optional shared expiration timer can apply to the whole card. If the agent's planning layer generates more than 3 questions, it must chunk them into multiple sequential payloads rather than exceeding the cap.

**External channels (WhatsApp, SMS, email):**

- Falls back to a single plain-text message listing all questions numbered sequentially, with lettered options under each (e.g. `1. Where to? a) Tokyo b) Paris c) Other (type your answer)`), asking for one reply line per question.
- The 2–3 question cap and easy→hard ordering still apply, since these channels have even less room for cognitive overhead than the in-app card.

---


### Behavior

- The card appears **inline** in the message thread, not as a centered modal overlay.
- The user may select **one or more** options via checkboxes.
- The **Confirm** button submits all selected values at once and dynamically shows the selection count.
- If the question is optional, a **Skip** button is shown.
- Once confirmed, the card collapses into a read-only summary bubble listing the selected labels.
- If the user types a free-text message instead of interacting with the card, the card auto-dismisses and the text input is processed normally.
- Only **one active checkbox card** may exist at a time; a new request replaces any previous unanswered card.

---

### Visual Design

The card uses the existing Tailwind dark-mode design system with a rounded container, subtle border, and indigo accent colors for selected states. Selected options highlight with a tinted background and border. The Confirm button remains disabled when no options are selected on a required question.

---

### Data Payload

The backend triggers the card with a structured payload containing the question text, a required flag, and an array of options each with an ID, display label, and internal value. An optional expiration timer can be included after which the card enters an expired state if left unanswered.


## 19.3 Outbound Rate-Limit Resilience & Graceful API-Key-Failure Handling ✅ DONE (2026-07-13)

> **Status:** All 26 steps complete and merged to `main` (fast-forward `2e1c36d..d709155`). Integration suite `test_provider_resilience.py` (16 passed) and unit `test_provider_rate_limiter.py` (7 passed) green; sustained load report at `backend/tests/load/PROVIDER_LOAD_REPORT.md`.

**Goal:** Agentium never crashes, stalls, or silently drops a task when a provider throttles (429), rejects a key (401/403), or goes down. A bad key or a burst of 429s must never take down a worker or the queue — the task fails over to another key/provider, or is marked `FAILED` with a clear reason, while every other task keeps running.
 
Work through the steps below **in order** — each one is a single, self-contained task, and later steps assume earlier ones are done.
 
---
 
### Step 1 — Trace the current failure path
- Files: `backend/services/agent_orchestrator.py`, `backend/services/task_executor.py`
- Trace `AgentOrchestrator._execute_task_inner()` up through whatever actually invokes `execute_task()` on the Celery side. List every catch block currently in that path.
- Force `LLMClient.generate_with_tools()` to raise (simulate all keys exhausted) and record whether: (a) the worker crashes/hangs, (b) the `Task` row gets marked `FAILED`, (c) an `AuditLog` entry is written, (d) the worker picks up the next task.
- ✅ Done when: you have a written yes/no answer for all four checks. This is the baseline Step 12 fixes against.

### Step 2 — Add jitter to backoff
- File: `backend/core/llm_client.py`, function `_delay()`
- Replace `min(base_retry_delay * 2**attempt, max_retry_delay)` with full-jitter: `random.uniform(0, min(max_retry_delay, base_retry_delay * 2**attempt))`.
- ✅ Done when: two concurrent retries against the same failure no longer produce identical delay values.

### Step 3 — Classify errors into three tiers
- File: `backend/core/llm_client.py`
- Add `classify_error()` returning:
  - `TRANSIENT` (timeout/502/503/504) → retry same key, backoff+jitter
  - `RATE_LIMITED` (429) → rotate key/provider, backoff+jitter
  - `PERMANENT_KEY_FAILURE` (401/403/402, "invalid api key", "insufficient_quota") → rotate immediately, no backoff, mark key unhealthy
- Prefer typed SDK exceptions (`openai.RateLimitError`, `anthropic.AuthenticationError`, etc.) over string matching; use substring matching only where no typed exception exists.
- ✅ Done when: every existing call to `_is_rate_limit()` / `_is_retryable()` is replaced by `classify_error()`.

### Step 4 — Make permanent key failures skip straight to the next config
- File: `backend/core/llm_client.py`
- When `classify_error()` returns `PERMANENT_KEY_FAILURE`, advance to the next entry in `configs_to_try` immediately — don't spend a retry attempt on a key that can't succeed.
- ✅ Done when: a simulated 401 on the primary key causes the very next call to go straight to the secondary key with no delay.

### Step 5 — Cap the combined retry budget across layers
- Files: `backend/core/llm_client.py`, `celery_app.py`
- Audit every Celery task calling into `LLMClient`/`ModelService`. Some already define their own `max_retries=3`/`5` on top of `LLMClient`'s internal retries. Set one explicit combined ceiling.
- ✅ Done when: you can state the max possible number of provider calls for one task, end to end, as a fixed number.

### Step 6 — Add rate-limit fields to the data model
- File: `backend/models/entities/user_config.py`
- Add to `UserModelConfig`: `requests_per_minute` (int, default `60`), `tokens_per_minute` (optional int), `max_concurrent_requests` (int, sensible default). Write the Alembic migration.
- Using requests-per-minute (not per-second) as the unit keeps every provider's real-world limit a whole number — the slowest tier some providers allow (1 request every 2 seconds) is `30` in this unit, and the fastest (2500/sec) is `150000`. No fractional values anywhere in config or UI.
- ✅ Done when: migration runs cleanly and existing rows backfill to `requests_per_minute = 60`.

### Step 7 — Add the rate-limit field to the model page (where the API key is entered)
- Files: the model-configuration page/form where a provider API key is added or edited (frontend) + its backend route
- Add an input labeled "Rate limit (requests per minute)" pre-filled with `60`, with the hint "check your provider's plan page — e.g. 1 request every 2 seconds = 30/min." Wire it to `requests_per_minute` from Step 6.
- Below the input box, add a small line of helper text that updates live as the user types, showing the same value converted to per-second (e.g. typing `30` shows "≈ 0.5 requests/second" underneath; typing `120` shows "≈ 2 requests/second"). This is read-only, computed client-side (`value / 60`), and never sent to the backend — it's purely so the user can sanity-check the number against how their provider documents its limit.
- The value the user enters is the value displayed back to them on that same page (no unit conversion visible in the stored/saved value) — always requests/minute, both on input and whenever the configured limit is shown elsewhere (key list, settings, dashboard). Only the live helper text under the box is per-second.
- ✅ Done when: saving with the field untouched stores `60`; entering `30` stores `30`, shows "≈ 0.5 requests/second" live under the box while typing, and the model page shows "30 requests/minute" for that key afterward.

### Step 8 — Build the per-provider token bucket
- File: `backend/services/model_provider.py` (reuse the Lua pattern in `backend/core/middleware.py::RateLimitMiddleware._LUA_ADMIT`)
- Before every SDK call, acquire a token from a Redis-backed bucket keyed by `provider_config_id`. Convert the config's `requests_per_minute` into a smooth per-second refill rate internally (`requests_per_minute / 60.0`) — do **not** just drop `requests_per_minute` tokens at the start of each minute and then block for 60 seconds; that would let a burst of 30 requests fire back-to-back instead of spread evenly. The stored/displayed unit stays requests/minute; only the internal refill math is per-second.
- Wait if no token is available.
- ✅ Done when: a config set to `30` requests/minute actually sends calls roughly 2 seconds apart, not 30 at once followed by a 1-minute stall.

### Step 9 — Add a concurrency cap alongside the rate limiter
- File: `backend/services/model_provider.py`
- Add an in-process `asyncio.Semaphore` per provider config, plus a Redis-backed counter for cross-worker/cross-replica concurrency, using `max_concurrent_requests` from Step 6.
- ✅ Done when: concurrency for any provider config never exceeds its configured max, verified across two worker processes at once.

### Step 10 — Read provider rate-limit headers and correct the bucket
- File: `backend/services/model_provider.py`
- Add `parse_rate_limit_headers(provider, headers)` reading `anthropic-ratelimit-requests-remaining`/`-reset` or `x-ratelimit-remaining-requests`/`x-ratelimit-reset-requests`. If remaining ≤ a configurable threshold (default 2), pause new calls on that config until the reported reset time. This only tightens the effective rate — never loosens it past the `requests_per_minute` value from Step 7.
- ✅ Done when: a mock provider returning low-remaining headers on a *success* response causes the next call to wait, with no 429 involved.

### Step 11 — Bound and cool down auto-scaling
- File: `backend/services/task_executor.py`, function `auto_scale_check()`
- Add a max-live-agents ceiling and a minimum cooldown between auto-scale rounds (today it spawns 3 agents every time pending count exceeds 10, uncapped).
- ✅ Done when: a sustained backlog no longer produces unbounded agent growth.

### Step 12 — Catch total exhaustion and fail the task cleanly
- File: wherever Step 1 found the gap (likely `execute_task`/`_execute_task_inner`)
- Add `try/except` around the LLM-call section catching the `RuntimeError` from full exhaustion, setting `Task.status = FAILED` with a structured reason (`rate_limited`, `all_keys_invalid`, `provider_unreachable`), writing an `AuditLog` entry, and returning cleanly.
- ✅ Done when: repeating Step 1's forced-exception test now shows all four checks passing.

### Step 13 — Wire the local (Ollama) fallback into the failover chain
- Files: `backend/services/api_key_manager.py`, `backend/core/llm_client.py`
- Confirm whether `fallback_configs` is ever auto-populated with a local/offline config when all remote keys fail. If not, add that wiring.
- ✅ Done when: killing all remote keys in a test still produces a completed (if slower) task via Ollama.

### Step 14 — Audit every call site for real fallback lists
- Files: `agent_orchestrator.py`, chat routes, any other caller of `LLMClient.generate()`/`generate_with_tools()`
- Ensure every call site passes a real `fallback_configs` list (other keys of the same provider + at least one other provider), not just a bare `config_id`.
- ✅ Done when: no call site relies on a single key with nothing to fall back to.

### Step 15 — Add a user-facing degradation message
- Files: wherever task results surface to chat/external channels
- When all configs/retries are exhausted, return "The AI provider is temporarily unavailable or rate-limited; this task has been queued for retry" instead of a raw `RuntimeError`/500.
- ✅ Done when: a forced total-exhaustion test shows this message in the UI/channel, not a stack trace.

### Step 16 — Merge the two health-tracking systems
- Files: `llm_client.py` (`ProviderCircuitBreaker`), `api_key_manager.py`
- Merge the in-process circuit breaker (keyed by `config_id`) with `APIKeyManager`'s DB-backed cooldown/health state (keyed by key ID) into one source of truth.
- ✅ Done when: both layers always report the same health status for the same key at the same time.

### Step 17 — Reuse SDK client instances
- File: `backend/services/model_provider.py`
- Construct one `openai.AsyncOpenAI(...)`/`anthropic.AsyncAnthropic(...)` per provider config and reuse it instead of building a new client on every call.
- ✅ Done when: client construction happens once per config, not once per request.

### Step 18 — Expose per-provider metrics on the dashboard
- Files: `monitoring_routes.py`, `celery_app.py` (reuse the `broadcast_mcp_stats`/`broadcast_channel_health` pattern)
- Broadcast outbound requests/minute, current concurrency, 429 rate, circuit-breaker state, and key health per provider config — same requests/minute unit used everywhere else.
- ✅ Done when: the dashboard shows live numbers for at least one real provider config.

### Step 19 — Alert before exhaustion
- File: `api_key_manager.py`
- Extend the existing "notify on total key failure" alert to also fire at a configurable warning threshold (e.g. 80% of a provider's configured rate).
- ✅ Done when: driving a config to 80% of its configured rate produces a warning alert before any failure.

### Step 20 — Build the mock-provider test harness
- File: new `backend/tests/integration/test_provider_resilience.py`
- Stand up a fake OpenAI-compatible endpoint that can be told to return, on command: 429 + `Retry-After`, 401, 403, 503, low-remaining headers on success, or normal success. Point a test `UserModelConfig` at it.
- ✅ Done when: the harness can be told which response to return next and tests can assert against it.

### Step 21 — Test: 429 burst
- Drive N concurrent task executions against the mock provider set to always 429.
- ✅ Done when: backoff has jitter (no synchronized retry timestamps), rotation to a fallback key occurs, and every task completes.

### Step 22 — Test: invalid/expired key
- Set the primary key to always fail with 401.
- ✅ Done when: no repeated retries against it, immediate rotation to the next config, key marked unhealthy, task completes via fallback.

### Step 23 — Test: total exhaustion
- Fail every configured key/provider.
- ✅ Done when: the worker doesn't crash, the task is marked `FAILED` with a reason, an `AuditLog` entry exists, and the worker immediately continues with the next queued task.

### Step 24 — Test: default and user-configured rate limits are respected
- Add a key with no rate value (expect `60`/min default) and a key with an explicit low value (e.g. `30`/min, matching "1 request every 2 seconds"). Drive concurrent load at each.
- ✅ Done when: requests are spaced evenly across each minute at the configured rate, and the `30`/min key never receives a 429.

### Step 25 — Test: header-based correction
- Mock provider returns success responses with `remaining-requests` near zero.
- ✅ Done when: Agentium pauses new calls on that config until the reported reset time, without needing an actual 429.

### Step 26 — Extend the load test
- File: `backend/tests/load/locustfile.py`
- Drive provider-facing load specifically (not just Agentium's own REST API). Record RPS actually reaching the mock provider, queue depth (`pending_count`), retry counts, and worker stability over a sustained run.
- ✅ Done when: a sustained run report exists showing all four metrics.
---
 
## Definition of done
 
- [x] All 26 steps above checked off.
- [x] A 429 burst produces zero failed tasks.
- [x] An invalid key rotates immediately with no wasted retries.
- [x] A total provider outage marks the task `FAILED` cleanly — worker keeps processing everything else.
- [x] A key with no configured rate limit never exceeds 60 requests/minute; a key configured for 30/minute never gets a 429 under load.
- [x] Low-remaining headers pause calls before a 429 happens.
- [x] Circuit breaker and key-health state never disagree.
- [x] Per-provider requests/minute, concurrency, 429-rate, and health are visible on the dashboard, and match what's shown on the model page.

---

## 20. Migrate Embedding Model — `all-MiniLM-L6-v2` → `BAAI/bge-base-en-v1.5`

**Goal:** Move the RAG/ChromaDB pipeline from `all-MiniLM-L6-v2` (384-dim) to `BAAI/bge-base-en-v1.5` (768-dim) with zero downtime, zero data loss, and no silent retrieval-quality regression. The two models are not interchangeable at the vector level — a 384-dim and a 768-dim vector can't be compared — so this is a re-embed-and-cutover, not a config flip.

Work through the steps below **in order** — each one is a single, self-contained task, and later steps assume earlier ones are done.

---

### Step 1 — Locate every embedding touchpoint
- Files: repo-wide
- Run `grep -rn "all-MiniLM-L6-v2\|SentenceTransformer\|384" backend/ frontend/ docker-compose*.yml` to build a fixed inventory of every place the model name or dimension is hardcoded — client init, config, `.env.example`, tests, migrations, docs.
- ✅ Done when: a complete file/line list exists; every later step operates against this list, not memory.

### Step 2 — Decide the collection strategy: parallel collections vs in-place rebuild
- A 384-dim and a 768-dim vector are incompatible at the index level — ChromaDB can't mix them in one collection. Choose: (a) create parallel `*_v2` collections and cut over per-collection with zero downtime, or (b) wipe and rebuild in place during a maintenance window. Given "Zero data loss on container restart" is already a hard requirement elsewhere in this roadmap, (a) is the safer default.
- ✅ Done when: the choice is written down (a short ADR note is fine) before any code changes start.

### Step 3 — Make the embedding model a config value, not a literal
- File: wherever the ChromaDB/embedding client reads its model name (per Step 1's inventory) + `.env.example`
- Add `EMBEDDING_MODEL` and `EMBEDDING_DIM` env vars, defaulting to the current values. The client reads these instead of a hardcoded string — this is what makes Step 11's per-collection flag and any rollback possible without a redeploy.
- ✅ Done when: changing the env var (not the code) changes which model the client loads.

### Step 4 — Update dependencies and bake the model into the image
- File: `requirements.txt`, `Dockerfile`
- Confirm the pinned `sentence-transformers` version supports `BAAI/bge-base-en-v1.5` (bump if not). Add a build-time step (`RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"`) so the ~440MB model is baked into the image rather than downloaded on first request inside a running container.
- ✅ Done when: a container started with no network access serves an embedding request successfully on the first call.

### Step 5 — Share the model cache across containers
- File: `docker-compose.yml`
- Add a named volume for the HuggingFace cache (`HF_HOME`) mounted into every container that loads the model (backend, worker), so it isn't independently re-downloaded per container in this multi-container setup.
- ✅ Done when: `docker-compose up` on a clean host downloads the model once total, not once per service; a restart triggers no re-download.

### Step 6 — Apply the query-vs-passage prefix correctly
- Files: wherever `query_similar()` builds a query embedding, and wherever `store_knowledge()` builds a document embedding
- Unlike MiniLM's symmetric encoding, `bge-base-en-v1.5` is instruction-tuned asymmetrically: prefix **queries** with `"Represent this sentence for searching relevant passages: "` before embedding; leave stored **passages/documents** unprefixed. Getting this backwards silently degrades retrieval quality even though the model itself is stronger — it won't error, it'll just retrieve worse.
- ✅ Done when: a unit test asserts the prefix is applied on the query path and absent on the storage path.

### Step 7 — Create parallel v2 collections
- Following Step 2: add creation logic for `constitution_articles_v2`, `agent_ethos_v2`, `task_learnings_v2`, `domain_knowledge_v2` at 768-dim, alongside the existing v1 collections.
- ✅ Done when: the app can create, read, and write both v1 and v2 collections side by side without error.

### Step 8 — Backfill: re-embed all existing documents into v2
- New file: `backend/scripts/reembed_knowledge.py`
- Iterate every document in each v1 collection, re-embed its content with the new model (correct prefixing per Step 6), write it into the matching v2 collection, preserving all metadata (`agent_id`, `knowledge_type`, `timestamp`, `decay_score`).
- ✅ Done when: a staging dry run shows matching document counts between each v1/v2 pair, with metadata intact.

### Step 9 — Re-tune the dedup similarity threshold
- File: the knowledge dedup check (cosine similarity > 0.95 → skip)
- Similarity score distributions differ between models — a threshold tuned for MiniLM doesn't automatically transfer. Run a small labeled set of known-duplicate and known-distinct pairs through `bge-base-en-v1.5` and pick a new threshold from actual scores, not the old number.
- ✅ Done when: the new threshold is documented and backed by that evaluation set.

### Step 10 — Re-tune the top-K relevance threshold
- File: RAG retrieval config (currently 0.7 minimum relevance)
- Same reasoning as Step 9: validate against a labeled relevant/irrelevant sample before trusting the old cutoff under the new model's score distribution.
- ✅ Done when: a new minimum-relevance value is set and documented.

### Step 11 — Feature-flag the active version per collection
- Add an `EMBEDDING_ACTIVE_VERSION` setting (v1/v2), read at query time by `query_similar()`, so each collection can be cut over — or rolled back — independently without a redeploy.
- ✅ Done when: toggling the flag for one collection changes which version is queried, with no other collection affected.

### Step 12 — Cut over in order of increasing blast radius
- Recommended order: `task_learnings` → `domain_knowledge` → `agent_ethos` → `constitution_articles` last, since the Constitutional Guard depends on it. Give each a soak period before moving to the next.
- ✅ Done when: this order is written into the rollout plan — not "flip everything at once."

### Step 13 — Re-verify the Constitutional Guard against v2
- File: wherever the Tier 2 semantic check queries `constitution_articles` for context
- Confirm it respects Step 11's active-version flag, then re-run the existing constitutional test cases against the v2 collection and confirm verdicts (ALLOW/BLOCK/VOTE_REQUIRED) are unchanged.
- ✅ Done when: all existing constitutional test cases pass against v2 with the same verdicts as v1.

### Step 14 — Point the weekly reindex job at v2
- File: the Celery beat task that performs the weekly Vector DB reindex
- Update it to target v2 collections once cut over, and make sure it doesn't keep reindexing a v1 collection that's scheduled for deletion.
- ✅ Done when: the reindex job runs cleanly against v2 only, post-cutover, for every migrated collection.

### Step 15 — Re-baseline the latency benchmark
- File: `benchmarks/` (the Phase 18 `pytest-benchmark` baseline: `query_similar()` at 10,000 seeded docs, p95 < 200ms)
- A larger 768-dim model is slower to encode and index; don't assume the old threshold still holds. Re-run and commit a new baseline. If it regresses meaningfully, evaluate ONNX-quantized inference (`optimum[onnxruntime]`) for the encode step before accepting a slower p95.
- ✅ Done when: a new committed baseline exists with an explicit pass/fail threshold for CI going forward.

### Step 16 — Recompute storage and memory sizing
- 768-dim float32 vectors are 2x the size of the old 384-dim ones. Recompute expected ChromaDB disk/memory footprint at current + projected document counts, and update resource requests/limits in `docker-compose.yml` accordingly.
- ✅ Done when: updated resource limits are committed and sized for the new footprint, not left at old defaults.

### Step 17 — Update CI and the test fixture factory
- Files: `docker-compose.test.yml`, `conftest.py`, the `integration-tests` GitHub Actions job
- Make sure the CI ChromaDB instance and fixtures default to `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`, so the test suite exercises the real migration path rather than the old model.
- ✅ Done when: the integration suite is green using `bge-base-en-v1.5` as the CI default.

### Step 18 — Retire v1 once soak is complete
- After a full soak period on v2 with no rollback triggered: drop the v1 collections, remove the `all-MiniLM-L6-v2` code path and any 384-dim-specific logic, and archive or delete `reembed_knowledge.py`.
- ✅ Done when: `grep -rn "all-MiniLM-L6-v2\|384-dim" backend/` returns zero hits outside the changelog/ADR history.

### Step 19 — Update the docs
- Files: `docs/adr/` (add a new ADR for the model choice and migration approach from Step 2), `ARCHITECTURE.md`, root `README.md`, `CONTRIBUTING.md`'s env var table
- Update every place that names the embedding model or vector dimension so nothing still documents `all-MiniLM-L6-v2` / 384-dim as current state.
- ✅ Done when: a repo-wide doc search shows only the new model/dimension as current.

### Step 20 — Rehearse the rollback
- Before declaring this done: deliberately flip one v2 collection back to v1 mid-soak using Step 11's flag, confirm queries keep working correctly, then flip it forward again.
- ✅ Done when: a rollback has actually been exercised once in staging — not just theoretically possible.

---

## 20. Definition of done

- [ ] All 20 steps above checked off.
- [ ] Every collection (`constitution_articles`, `agent_ethos`, `task_learnings`, `domain_knowledge`) is fully re-embedded in v2 with matching document counts and intact metadata.
- [ ] Query embeddings use the `bge` search-query prefix; stored document embeddings do not.
- [ ] Dedup (cosine > threshold) and top-K relevance thresholds are re-validated for the new model, not inherited from MiniLM unchanged.
- [ ] Constitutional Guard verdicts on the existing test set are unchanged after cutover to v2.
- [ ] p95 `query_similar()` latency has a new committed benchmark baseline at 10,000 docs.
- [ ] Resource limits (memory/disk) are sized for 768-dim vectors, not left at 384-dim defaults.
- [ ] A rollback was actually rehearsed in staging, not just designed.
- [ ] No remaining references to `all-MiniLM-L6-v2` or 384-dim outside historical docs/changelog.

---

## Changelog

### v0.19.0-alpha \_(in progress)