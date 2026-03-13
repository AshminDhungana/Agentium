# Agentium Implementation Roadmap

**Project:** Agentium — Personal AI Agent Nation  
**Version:** 1.2.0-alpha  
**Architecture:** Dual-Storage (PostgreSQL + ChromaDB) with hierarchical agent orchestration  
**Status:** Phase 12 ✅ Complete | Phase 13 🚧 In Progress  
_Last Updated: 2026-03-13 · Maintainer: Ashmin Dhungana_

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
| 13    | Autonomous Agent Orchestration | 🚧 In Progress |
| 14    | Frontend Reliability & Browser | 🔮 Planned     |
| 15    | Platform Hardening & Admin     | 🔮 Planned     |
| 16    | Database & Advanced AI Logic   | 🔮 Planned     |
| 17    | DevSecOps & Polish             | 🔮 Planned     |

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
- [ ] Checkpoint diff view (compare branches)
- [ ] Channel health monitoring and message logs
- [ ] Channel-specific settings (rate limits, filters)

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
- [ ] Live screenshot stream UI for browser tasks (frontend not fully wired)

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
- [ ] Speaker identification for multi-user voice sessions (not production-ready)

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

- [ ] **Complexity Analyzer** (`backend/services/auto_delegation_service.py`) — score tasks 1–10 on creation; map: 1–3 → `3xxxx` TaskAgent, 4–6 → `2xxxx` LeadAgent, 7–10 → Council deliberation
- [ ] **Sub-task Breakdown** — for score ≥ 7, decompose via LLM mini-call; persist sub-tasks with `parent_task_id` FK and dependency order in new `task_dependencies` junction table
- [ ] **Capability-Aware Assignment** — rank candidate agents by `(1 - error_rate) × (1 / current_load)` using `CapabilityRegistry`
- [ ] **Auto-Escalation Timer** — Celery beat every 60 s: tasks stuck in `in_progress` beyond `escalation_timeout` (default 300 s) → re-assign to next tier or trigger Council micro-vote
- [ ] **Dependency Graph Parallelizer** — build DAG from `task_dependencies`; dispatch independent branches as parallel Celery `group()` tasks
- [ ] **Priority Queue Rebalancer** — on `CRITICAL` / `SOVEREIGN` task arrival, re-sort the Celery queue without losing in-flight tasks
- [ ] **Smart Retry Router** — on failure, re-dispatch to a different agent of the same tier; never retry on an agent with `CB_OPEN`
- [ ] **Cost-Aware Delegation** — if `idle_budget < 20%`, force simple tasks to local Ollama regardless of tier preference

#### Alembic Migration — `007_task_delegation.py`

- [ ] `task_dependencies` table: `task_id` (FK), `depends_on_task_id` (FK), `dependency_type` (`sequential | parallel`), `created_at`
- [ ] `complexity_score` (Integer, nullable) on `tasks`
- [ ] `escalation_timeout_seconds` (Integer, default 300) on `tasks`
- [ ] `delegation_metadata` (JSONB) on `tasks`

#### API Routes

- [ ] `POST /tasks/auto-delegate` — force re-delegation with optional `force_tier`
- [ ] `GET /tasks/{id}/delegation-log` — return delegation decision trail from `delegation_metadata`
- [ ] `GET /tasks/{id}/dependency-graph` — return DAG as `{ nodes, edges }` for frontend rendering

#### Frontend

- [ ] `AutoDelegationPanel.tsx` — complexity score badge, tier assignment rationale, candidate agents ranked by score
- [ ] Manual override dropdown — calls `POST /tasks/auto-delegate`
- [ ] DAG viewer using React-Flow; nodes colored by status, edges labeled sequential vs parallel
- [ ] Escalation countdown timer on in-progress tasks (amber → red as timeout approaches)
- [ ] Extend `TaskCard.tsx` — add complexity score pill and "delegated by AI" vs "manually assigned" label

---

### 13.2 Self-Healing & Auto-Recovery System

**Purpose:** Detect failures and recover automatically without human intervention.

#### Backend

- [ ] **Circuit Breaker → Council Auto-Escalation** — when `CB_OPEN` transitions, immediately enqueue a `EMERGENCY` micro-vote via `VotingService`; currently silent
- [ ] **Exponential Backoff** — replace fixed 60 s retry in `execute_task_async` with `min(2 ** retry_count, 60)` seconds (1 → 2 → 4 → 8 → 16 → 32 → 60 cap)
- [ ] **Agent Crash Detection** (`backend/services/reincarnation_service.py`) — Celery beat every 30 s: agents with `status = 'working'` and `last_heartbeat_at > 2 min` → mark crashed, emit `agent_crashed` WebSocket event
- [ ] **State Restoration from Checkpoint** — on crash, call `CheckpointService.get_latest(agent_id)`; restore `ethos`, `current_task_id`, `context_window_snapshot`
- [ ] **Agent Reincarnation** — spawn replacement via `AgentFactory` with restored state; re-queue interrupted task in `ASSIGNED` status
- [ ] **Graceful Degradation Mode** — if all API providers have `CB_OPEN`: pause tasks with `priority < HIGH`, continue CRITICAL/SOVEREIGN on local Ollama, emit `system_mode_change` WebSocket banner
- [ ] **Critical Path Protection** — tag tasks that are DAG ancestors of CRITICAL/SOVEREIGN leaves; reserve one agent slot permanently for these chains
- [ ] **Self-Diagnostic Routine** — daily Celery beat: check DB connection pool, Redis ping, ChromaDB collection counts, disk usage, stale task count; auto-propose constitutional amendment if repeated violations detected
- [ ] **DB Connection Pool Auto-Recovery** — wrap `CelerySessionLocal` in `tenacity` retry loop (5 attempts, 2 s wait) on `OperationalError`
- [ ] **Heartbeat Task** — Celery beat every 60 s: each active agent writes `last_heartbeat_at = utcnow()`

#### Alembic

- [ ] Add `last_heartbeat_at` (DateTime, nullable) column to `agents` table

#### Beat Schedule Additions to `celery_app.py`

- [ ] `agent-heartbeat` — 60 s
- [ ] `crash-detection` — 30 s
- [ ] `self-diagnostic-daily` — 86400 s
- [ ] `critical-path-guardian` — 120 s

#### Frontend

- [ ] Self-Healing Events feed in `MonitoringPage.tsx` — reincarnation events, circuit state changes, degradation activations
- [ ] System mode banner: normal (hidden) / degraded (amber) / critical (red) — driven by `system_mode_change` WebSocket event
- [ ] "One-Click Rollback" button per healing action — calls `POST /admin/rollback/{audit_id}`

---

### 13.3 Predictive Auto-Scaling

**Purpose:** Anticipate workload changes and scale proactively, not reactively.

#### Backend

- [ ] **Time-Series Store** (`backend/services/predictive_scaling.py`) — every 5 min, snapshot `pending_task_count`, `active_agent_count`, `avg_task_duration_seconds`, `token_spend_last_5m` to Redis sorted set; retain 7 days, auto-trim
- [ ] **Load Predictor** — weighted moving average (`[0.5, 0.3, 0.2]`) over time-series; output: `next_1h`, `next_6h`, `next_24h` predictions
- [ ] **Pre-Spawn Decision** — if `next_1h_prediction > current_capacity × 0.8`: call `AgentLifecycleService.spawn_agent(tier=3)` immediately; log to `AuditLog`
- [ ] **Pre-Liquidation Decision** — if `next_6h_prediction < current_agents × 0.3` AND agent idle > 30 min: trigger existing auto-termination path
- [ ] **Fix `auto_scale_check` stub** — replace `# In production: actually spawn agents` comment with real `AgentLifecycleService.spawn_agent(tier=3, count=recommended_agents, db=db)` call
- [ ] **Resource-Aware Scheduler** — check Redis memory and PG connection pool before spawning; if either > 85%, delay non-critical dispatch 30 s
- [ ] **Token Budget Guard** — daily cap via `DAILY_TOKEN_BUDGET_USD` env var (default `10.00`); at 80% downgrade new task allocations to cheapest model; at 100% pause non-CRITICAL tasks, emit `budget_exceeded` WebSocket event
- [ ] **Time-Based Policy** — read `BUSINESS_HOURS_TZ`, `BUSINESS_HOURS_START`, `BUSINESS_HOURS_END` env vars; outside hours, cap active task agents at 2

#### Beat Schedule Additions

- [ ] `load-metrics-snapshot` — 300 s
- [ ] `predictive-scaling-check` — 300 s

#### API Routes (`backend/api/routes/scaling.py` — new file)

- [ ] `GET /predictions/load` — return `{ next_1h, next_6h, next_24h, current_capacity, recommendation }`
- [ ] `GET /scaling/history` — last 100 scaling decisions from `AuditLog`
- [ ] `POST /scaling/override` — `{ action: 'spawn' | 'liquidate', count, tier }` (admin only)

#### Frontend — `ScalingDashboard.tsx` (new page at `/scaling`)

- [ ] Four KPI cards: Active Agents, Pending Tasks, Token Spend Today (USD), Capacity %
- [ ] Load Prediction Chart (Recharts `LineChart`): actual 24 h history + predicted `next_1h` + `next_6h` series
- [ ] Scaling Events Timeline: spawn/liquidate events with rationale; click to expand AuditLog entry
- [ ] Manual Override Panel: "Spawn N Agents" / "Liquidate N Idle Agents" controls + tier selector
- [ ] Budget Gauge: radial gauge amber at 80%, red at 100%
- [ ] Poll `GET /predictions/load` every 60 s; subscribe to `scaling_event` WebSocket

---

### 13.4 Continuous Self-Improvement Engine

**Purpose:** System that learns from its own operations and measurably improves over time.

#### Backend

- [ ] **Real-Time Learning Write** (extend `rag_service.py`) — immediately after `task.complete()` in `execute_task_async`, extract and write a learning record to ChromaDB `task_learnings`; remove any 6-hour delay
- [ ] **Auto Knowledge Consolidation** — weekly Celery beat: cluster `task_learnings` embeddings with cosine similarity > 0.92; merge pairs into single entry with `confidence × 1.05`; delete originals
- [ ] **Anti-Pattern Early Warning** — on every task failure, query `task_learnings` for similar past failures; if ≥ 3 similar failures within 7 days, emit `pattern_warning` WebSocket event
- [ ] **Auto-Tool Generation** (`backend/services/self_improvement_service.py`) — detect tool call patterns repeated ≥ 5 times with > 90% success rate; auto-generate composite tool via `ToolCreationService.create_from_pattern()`
- [ ] **Auto Constitutional Amendment** — when `ConstitutionalGuard` returns `VOTE_REQUIRED` for the same action type ≥ 3 times in 24 h: auto-submit amendment via `VotingService.propose_amendment()` with `proposed_by = 'SYSTEM_IMPROVEMENT_ENGINE'`
- [ ] **Performance Optimization Loop** — weekly Celery task: query tasks with `duration_seconds > p95`; submit slow prompt + outcome to meta-LLM for condensation suggestion; store in `AuditLog` for human review (do not auto-apply)
- [ ] **Cross-Agent Knowledge Sharing** — extend `federation.py`: `POST /federation/knowledge-share` ingests payload into local `task_learnings` with `source = 'federated'` and cosine deduplication
- [ ] **Learning Impact Tracker** — Redis hash `agentium:learning:impact`; 7-day rolling success rate delta; expose via `GET /improvements/impact`

#### Beat Schedule Additions

- [ ] `knowledge-consolidation-weekly` — 604800 s
- [ ] `anti-pattern-scan` — 3600 s

#### API Routes (`backend/api/routes/improvements.py` — new file)

- [ ] `GET /improvements/impact` — learning impact metrics (success rate delta, tools generated, amendments auto-proposed)
- [ ] `GET /improvements/patterns` — detected anti-patterns with recurrence count
- [ ] `POST /improvements/consolidate` — manual trigger of knowledge consolidation (admin only)

#### Frontend — `LearningImpactDashboard.tsx` (new component)

- [ ] Success Rate Trend (Recharts `AreaChart`) — 30-day rolling rate with "learning event" vertical markers
- [ ] Auto-Generated Tools list: name, trigger pattern, usage count, success rate
- [ ] Anti-Pattern Warnings feed: pattern description, recurrence count, amendment status
- [ ] Knowledge Base Stats: total learnings, federated contributions, consolidations run

---

### 13.5 Workflow Automation Pipeline

**Purpose:** End-to-end repeatable workflows defined once, executed automatically on schedule, event, or demand.

#### Backend — New Models (`backend/models/entities/workflow.py`)

- [ ] `Workflow` entity: `id`, `agentium_id`, `name`, `description`, `template_json` (JSONB), `version` (int), `is_active`, `created_by_agent_id`, `schedule_cron`, `created_at`, `updated_at`
- [ ] `WorkflowExecution` entity: `id`, `workflow_id`, `status` (`pending | running | paused | completed | failed`), `current_step_index`, `context_data` (JSONB), `started_at`, `completed_at`, `triggered_by`
- [ ] `WorkflowStep` entity: `id`, `workflow_id`, `step_index`, `step_type` (`task | condition | parallel | human_approval | delay`), `config` (JSONB), `on_success_step`, `on_failure_step`

#### Alembic Migration — `008_workflow_engine.py`

- [ ] Create `workflows`, `workflow_executions`, `workflow_steps` tables with indexes on `workflow_id`, `status`, `is_active`
- [ ] Create `workflow_versions` audit table for version history snapshots

#### Backend — Workflow Engine (`backend/services/workflow_engine.py`)

- [ ] **Step Executor** — iterate steps: Celery task dispatch for `task` steps, sandboxed `eval()` for `condition` steps, Celery `group()` for `parallel` steps, WebSocket pause for `human_approval` steps
- [ ] **Conditional Branching** — config: `{ "field": "last_task_output.status", "operator": "eq", "value": "success", "on_true": 3, "on_false": 5 }`; only `context_data` in eval scope, no builtins
- [ ] **Cron Scheduler** — on startup, register all `schedule_cron` workflows as dynamic Celery beat entries; de-register and re-register on update
- [ ] **ETA Calculator** — use last 10 execution durations to estimate current run ETA
- [ ] **Workflow Versioning** — on update, increment `version`, archive current `template_json` to `workflow_versions`
- [ ] **Auto-Documentation** — on completion, LLM-generate a natural language summary of what was done; append to `Workflow.description` and store in `task_learnings`

#### API Routes (`backend/api/routes/workflows.py` — new file)

- [ ] `GET /workflows` — list with pagination
- [ ] `POST /workflows` — create from template JSON
- [ ] `GET /workflows/{id}` — detail with steps
- [ ] `PUT /workflows/{id}` — update (auto-increments version)
- [ ] `POST /workflows/{id}/execute` — trigger immediate execution
- [ ] `GET /workflows/{id}/executions` — execution history
- [ ] `GET /workflows/{id}/executions/{eid}` — live execution state
- [ ] `POST /workflows/{id}/executions/{eid}/approve` — approve `human_approval` step
- [ ] `GET /workflows/{id}/executions/{eid}/eta` — estimated completion time
- [ ] `GET /workflows/{id}/versions` — version history
- [ ] `POST /workflows/{id}/rollback` — rollback to prior version (admin)

#### Frontend

- [ ] **`WorkflowsPage.tsx`** (new page at `/workflows`) — library list: name, version, last run status, next scheduled run, action buttons (Run Now / Edit / Duplicate / Archive)
- [ ] **`WorkflowDesigner.tsx`** (new page at `/workflows/:id`) — drag-and-drop canvas; step type tiles; config drawer per node; conditional edges labeled "✓ True" / "✗ False"; version history sidebar with JSON diff viewer
- [ ] **`WorkflowExecutionMonitor.tsx`** (new page at `/workflows/:id/executions/:eid`) — live step highlighting; human approval modal with approve/reject buttons; ETA countdown badge; bottleneck detection (steps exceeding median duration)

---

### 13.6 Intelligent Event Processing

**Purpose:** Automatically react to external webhooks, threshold breaches, and scheduled polls — translating signals into tasks and workflows without manual dispatch.

#### Backend — New Models (`backend/models/entities/event_trigger.py`)

- [ ] `EventTrigger` entity: `id`, `name`, `trigger_type` (`webhook | schedule | threshold | api_poll`), `config` (JSONB), `target_workflow_id` (FK nullable), `target_agent_id` (FK nullable), `is_active`, `last_fired_at`, `fire_count`
- [ ] `EventLog` entity: `id`, `trigger_id`, `event_payload` (JSONB), `status` (`processed | dead_letter | duplicate`), `correlation_id` (UUID), `created_at`

#### Alembic Migration — `009_event_triggers.py`

- [ ] Create `event_triggers` and `event_logs` tables

#### Backend — Event Processor (`backend/services/event_processor.py`)

- [ ] **Webhook Receiver** (`POST /events/webhook/{trigger_id}`) — HMAC-SHA256 validation; 24 h Redis deduplication by `correlation_id`; enqueue `process_event` Celery task
- [ ] **Threshold Monitor** — Celery beat every 60 s: evaluate `config.metric` expressions against live Redis metrics from 13.3; respect `config.cooldown_seconds`
- [ ] **External API Poller** — Celery beat every `config.poll_interval_seconds`: `GET config.url`; compare response hash to last known hash in Redis; fire on change
- [ ] **Event Correlation Engine** — group `EventLog` entries with same `correlation_id` prefix within 60 s window; submit as single consolidated task
- [ ] **Dead Letter Queue** — events failing processing 3 times → `dead_letter` status; expose for manual review
- [ ] **Circuit Breaker for Events** — if a trigger fires > `config.max_fires_per_minute` (default 10) per minute, pause trigger for `config.pause_duration_seconds`

#### Beat Schedule Additions

- [ ] `threshold-event-check` — 60 s
- [ ] `external-api-poll` — 60 s

#### API Routes (`backend/api/routes/events.py` — new file)

- [ ] `GET /events/triggers` — list all triggers
- [ ] `POST /events/triggers` — create trigger
- [ ] `PUT /events/triggers/{id}` — update trigger
- [ ] `DELETE /events/triggers/{id}` — deactivate
- [ ] `POST /events/webhook/{trigger_id}` — public receiver (HMAC only, no Bearer)
- [ ] `GET /events/logs` — paginated log filtered by `status`, `trigger_id`
- [ ] `GET /events/dead-letters` — dead letter queue viewer
- [ ] `POST /events/dead-letters/{id}/retry` — manual retry

#### Frontend — `EventTriggerManager.tsx` (new page at `/events`)

- [ ] Trigger list: name, type badge, last fired, fire count, active toggle
- [ ] Trigger creation form: type selector drives dynamic config fields (webhook → generated URL + HMAC secret; threshold → metric/operator/value dropdowns; api_poll → URL/headers/interval fields)
- [ ] Event Log tab: scrollable log with status badges; click to expand full payload JSON

---

### 13.7 Zero-Touch Operations Dashboard

**Purpose:** Single unified view of all autonomous systems with automated incident response for known failure patterns.

#### Backend — Extend `monitoring_service.py`

- [ ] **Metrics Aggregator** (`GET /monitoring/aggregated`) — combine agent health, circuit breaker states, scaling events (24 h), learning impact delta, workflow success rates, event trigger fire rates; cache in Redis for 10 s
- [ ] **Anomaly Detector** — Celery beat every 5 min: compute Z-score for `task_duration`, `error_rate`, `token_spend_per_hour` vs 7-day baseline; if Z-score > 2.5, create `ViolationReport` severity `major` and push via WebSocket
- [ ] **Automated Incident Response** — `KNOWN_PATTERNS` dict: on match, call `fix_fn()` automatically; log to `AuditLog` with `action = 'auto_remediated'`
- [ ] **SLA Monitor** — track time-to-resolution for tasks with `escalation_timeout_seconds`; compute SLA compliance rate; expose `GET /monitoring/sla`
- [ ] **Capacity Planner** — include `capacity_forecast` in `/monitoring/aggregated`: 7-day agent count recommendation from historical volume

#### Beat Schedule Additions

- [ ] `anomaly-detection` — 300 s
- [ ] `sla-monitor` — 60 s

#### API Routes (extend `monitoring_routes.py`)

- [ ] `GET /monitoring/aggregated` — unified metrics snapshot
- [ ] `GET /monitoring/sla` — SLA compliance metrics
- [ ] `GET /monitoring/anomalies` — active anomalies list
- [ ] `POST /monitoring/chaos-test` — inject controlled failure (admin, rate-limited 1/hour)
- [ ] `POST /admin/rollback/{audit_id}` — revert automated action by audit ID (admin)

#### Frontend — Extend `MonitoringPage.tsx`

- [ ] **Unified Status Row** — five health rings (Agents / Tasks / Workflows / Events / Budget) using existing `HealthRing` component; data from `GET /monitoring/aggregated`
- [ ] **Anomaly Feed** — live list with Z-score, affected metric, auto-remediation status badge (`auto-fixed | pending | escalated`)
- [ ] **Automated Incident Log** — table of `auto_remediated` AuditLog entries; "Rollback" button per row calling `POST /admin/rollback/{audit_id}`
- [ ] **SLA Dashboard** — gauge per task priority with compliance rate; 30-day trend sparkline
- [ ] **Cost Analytics** — bar chart of daily token spend by provider; projected monthly cost; budget utilization %
- [ ] **Chaos Engineering Panel** — "Inject Failure" button (admin) with type selector (`agent_crash | api_timeout | db_connection_loss`); shows test results inline
- [ ] Subscribe to WebSocket event types: `anomaly_detected`, `auto_remediated`, `sla_breach`, `budget_warning`

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

- [ ] **Backend** — extend `browser.py`: emit screenshot frames as base64 via WebSocket event `browser_frame` at configurable FPS (default 2); add `GET /browser/sessions/{id}/stream` endpoint for polling fallback
- [ ] **Frontend** — `BrowserTaskViewer.tsx`: subscribe to `browser_frame` WebSocket events; render frames in an `<img>` tag with smooth replacement; show URL bar, page title, and action log alongside screenshot
- [ ] Add to `TaskCard.tsx`: "View Live" button when `task_type = 'browser'` and status is `in_progress`; opens `BrowserTaskViewer` in a modal or slide-over panel

### 14.2 WebSocket Reconnection Logic

- [ ] **Frontend** (`frontend/src/store/websocketStore.ts`) — implement exponential backoff reconnection: attempt after 1 s, 2 s, 4 s, 8 s, max 30 s; cap total attempts at 10 before showing manual reconnect prompt
- [ ] Show non-intrusive reconnection banner ("Reconnecting…") during disconnection; dismiss automatically on successful reconnect
- [ ] On reconnect, re-subscribe to all active WebSocket topics and replay any missed events from a server-side event buffer (Redis list, last 100 events per client, 60 s TTL)
- [ ] **Backend** — add `GET /ws/replay?since=<timestamp>` endpoint to serve buffered events; integrate with existing `manager.broadcast`

### 14.3 Global Frontend Error Boundaries

- [ ] Create `ErrorBoundary.tsx` — React class component implementing `componentDidCatch`; renders a styled fallback UI with "Retry" button and collapsible error details
- [ ] Wrap every route-level page component in `ErrorBoundary` (update `App.tsx` router)
- [ ] Add per-widget `ErrorBoundary` around all dashboard cards so one widget failure does not crash the page
- [ ] Send caught errors to backend `POST /frontend/errors` endpoint (new route); log to `AuditLog` with category `SYSTEM`; display count in `MonitoringPage.tsx` error feed

---

## Phase 15: Platform Hardening & Admin 🔮

**Goal:** Close remaining security, observability, and operational gaps.

### 15.1 Audit Trail for Privilege Escalations

- [ ] **Backend** — on every `PATCH /users/{id}/role` or capability grant call, write an `AuditLog` entry with `category = SECURITY`, `level = WARNING`, capturing `actor_id`, `target_user_id`, `old_role`, `new_role`, `expires_at`, `ip_address`
- [ ] Add `GET /audit/privilege-escalations` route: paginated, filterable by `actor_id`, `target_id`, date range
- [ ] **Frontend** — add "Privilege Escalation Log" tab to `RBACManagement.tsx`; table with actor, target, role change delta, timestamp, expiry; export to CSV button

### 15.2 Real-Time MCP Tool Stats & Sub-Second Revocation

- [ ] **Backend** — track per-tool invocation count, average latency, last-used timestamp, error rate in a Redis hash (`agentium:mcp:stats:{tool_id}`) updated on every invocation in `audit_tool_invocation()`
- [ ] `GET /mcp-tools/stats` — return live stats for all tools from Redis (not DB); response time < 50 ms
- [ ] Revocation path: on `revoke_mcp_tool(tool_id)`, write to Redis SET `agentium:mcp:revoked` with no TTL; check this set before every invocation in `get_approved_tools()` — eliminates DB roundtrip, achieving < 1 s revocation
- [ ] **Frontend** — extend `ToolRegistry.tsx`: add stats columns (invocations / avg latency / error rate) to the tool table; live-update via WebSocket event `mcp_stats_update` (emit every 30 s from Celery beat)

### 15.3 Channel Health Monitoring, Logs & Settings

- [ ] **Backend** — `GET /channels/{id}/health` — return: connection status, last message timestamp, error count (last 24 h), circuit breaker state, rate limit utilization
- [ ] `GET /channels/{id}/logs` — paginated `ExternalMessage` history with filters for `status`, `sender_id`, date range
- [ ] `PATCH /channels/{id}/settings` — update per-channel rate limit, auto-create-tasks flag, default agent assignment, content filters
- [ ] Celery beat every 5 min: emit `channel_health_update` WebSocket event for all active channels
- [ ] **Frontend** — build full channel management UI in `ChannelsPage.tsx`:
  - Health tab: status badge, last message time, error count, circuit breaker indicator per channel
  - Logs tab: scrollable message history with status filtering and sender search
  - Settings tab: rate limit slider, auto-task toggle, default agent dropdown, content filter keyword list

### 15.4 Speaker Identification for Voice System

- [ ] **Backend** — extend `audio.py`: on each audio chunk, run speaker embedding extraction (use `pyannote.audio` speaker diarization or a lightweight ECAPA-TDNN model); map embedding to registered speaker profile in `speaker_profiles` DB table
- [ ] New `speaker_profiles` table: `id`, `user_id` (FK nullable), `name`, `embedding` (float array stored as JSONB), `created_at`
- [ ] `POST /audio/speakers/register` — enroll a new speaker from an audio sample; compute and store embedding
- [ ] `GET /audio/speakers` — list registered speaker profiles
- [ ] On identification, attach `speaker_id` to incoming `ExternalMessage` before routing to agent; include in task context
- [ ] **Frontend** — add "Speaker Profiles" section to voice settings; "Register Voice" button with microphone recording UI; list of enrolled speakers with delete option

---

## Phase 16: Database & Advanced AI Logic 🔮

**Goal:** Optimize data layer performance and deepen AI reasoning capabilities.

### 16.1 Database Connection Pool Tuning & Slow Query Logging

- [ ] **Connection Pool Tuning** — configure `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle` in `backend/core/database.py` based on expected concurrency (start: `pool_size=20, max_overflow=10, pool_recycle=1800`)
- [ ] Add `pool_pre_ping=True` to main app engine (already done for Celery engine — replicate)
- [ ] **Slow Query Logging** — enable PostgreSQL `log_min_duration_statement = 500` via `docker-compose.yml` command args; parse logs in a Celery task and write summaries to `AuditLog` with category `SYSTEM`
- [ ] Add `GET /admin/slow-queries` endpoint: return top 20 slowest queries from last 24 h, aggregated from PG `pg_stat_statements` view
- [ ] **Frontend** — add "Slow Queries" tab to `MonitoringPage.tsx`: table of query hash, call count, avg duration, last seen; link to explain plan documentation

### 16.2 Learning Decay for Outdated Knowledge Patterns

- [ ] **Backend** — extend `rag_service.py`: add `decay_score` (float, default 1.0) to ChromaDB metadata on every `task_learnings` document
- [ ] Weekly Celery beat task `decay-learnings`: for each document, compute age in days since `last_validated_at`; apply `decay_score = max(0.1, decay_score × 0.95 ^ days_since_validation)` for documents older than 30 days
- [ ] Modify `query_similar()` to multiply cosine similarity by `decay_score` before ranking, so stale knowledge naturally sinks below fresh knowledge
- [ ] When a task completes successfully and a learning was retrieved, reset `last_validated_at = utcnow()` and `decay_score = min(1.0, decay_score + 0.1)` — validation boosts confidence

### 16.3 Cross-Document Citation Graph for RAG

- [ ] **Backend** — on every RAG retrieval, record `{ source_doc_id, cited_by_doc_id, task_id, timestamp }` to a PostgreSQL `citation_edges` table (Migration 010)
- [ ] `GET /knowledge/citation-graph?root={doc_id}&depth={n}` — return graph as `{ nodes, edges }` BFS-traversed up to depth `n` (default 2)
- [ ] Use citation frequency to boost `query_similar()` ranking: documents cited more often receive a `citation_boost` multiplier (cap at 1.3×)
- [ ] **Frontend** — add "Citation Graph" tab to knowledge management page (or constitution page): force-directed D3 graph; click node to expand one more hop; node size = citation frequency

### 16.4 Git Versioning Backups for Config Files

- [ ] **Backend** — new service `backend/services/config_versioning.py`: on any write to constitution articles, model configs, plugin configs, or channel settings, commit a snapshot to a bare Git repo at `/data/config-repo`
- [ ] Use `gitpython` library; commit message format: `[auto] {entity_type}/{entity_id} updated by {actor_id} at {timestamp}`
- [ ] `GET /admin/config-history/{entity_type}/{entity_id}` — return list of Git commits for that entity
- [ ] `POST /admin/config-restore/{entity_type}/{entity_id}?commit={sha}` — restore entity to a specific commit's snapshot (admin only)
- [ ] Mount `/data/config-repo` as a named Docker volume in `docker-compose.yml` for persistence across container restarts

---

## Phase 17: DevSecOps & Polish 🔮

**Goal:** Harden the application against abuse, and elevate the UI to production-quality across all surfaces.

### 17.1 Application-Layer DDoS Hardening

- [ ] **Rate Limiting Enhancement** — move from IP-only rate limiting to layered limits: per-IP (existing), per-user (authenticated), per-endpoint category (auth endpoints stricter than read endpoints)
- [ ] Add `slowapi` (or custom FastAPI middleware) for endpoint-specific limits: `POST /auth/*` → 5 req/min; `POST /tasks` → 30 req/min; general API → 200 req/min
- [ ] **Payload Size Limits** — enforce max request body size (default 1 MB) via FastAPI middleware; separate larger limit for file upload endpoints
- [ ] **Suspicious Pattern Detection** — Celery beat every 5 min: query request logs for IPs with > 100 4xx responses in 5 min → auto-add to Redis blocklist (`agentium:blocked:ips`) with 1 h TTL
- [ ] Nginx config (`nginx.conf`): add `limit_req_zone` and `limit_conn_zone` directives as a first line of defense before FastAPI
- [ ] `GET /admin/blocked-ips` — list currently blocked IPs with TTL; `DELETE /admin/blocked-ips/{ip}` — manual unblock

### 17.2 System-Wide UI Polish

- [ ] **Dark Mode Consistency** — audit all pages for hardcoded `bg-white`, `text-black`, `border-gray-*` without `dark:` variants; replace with semantic tokens using the existing dark mode system
- [ ] **Animations & Transitions** — add `transition-all duration-200` to all interactive elements (buttons, cards, modals, dropdowns) where missing; add skeleton loading states to all data-fetching components that don't already have them
- [ ] **Empty States** — design and implement empty state illustrations/messages for: agent list (no agents), task list (no tasks), inbox (no messages), knowledge base (no documents), workflow list (no workflows)
- [ ] **Toast Notifications** — standardize success/error/info toasts across all forms (currently inconsistent between pages); use a single shared `useToast()` hook
- [ ] **Loading Consistency** — replace all ad-hoc `Loader2` spinners with a unified `<LoadingSpinner size="sm|md|lg" />` component

### 17.3 Mobile Responsiveness for Complex Pages

- [ ] Audit breakpoints for: `TasksPage.tsx`, `AgentTree.tsx`, `VotingPage.tsx`, `MonitoringPage.tsx`, `ConstitutionPage.tsx` — all currently desktop-first
- [ ] `TasksPage.tsx` — collapse table view to card view below `md:` breakpoint; slide-over for task details instead of inline expansion
- [ ] `AgentTree.tsx` — horizontal scroll for deep hierarchies on mobile; collapsible tier groups
- [ ] `VotingPage.tsx` — stack vote cards vertically on mobile; move amendment diff to expandable accordion
- [ ] `MonitoringPage.tsx` — stack metric cards to 1-column grid below `sm:`; health rings resize to 40px
- [ ] New `WorkflowDesigner.tsx` (Phase 13.5) — canvas uses touch events (`onTouchStart/Move/End`) for drag-and-drop on tablet; view-only mode on phone

### 17.4 Accessibility (ARIA Labels & Keyboard Navigation)

- [ ] **ARIA Labels** — audit all icon-only buttons (pencil, trash, settings gear, expand/collapse) and add `aria-label` attributes; audit all form inputs for associated `<label>` elements
- [ ] **Keyboard Navigation** — ensure all interactive elements are reachable via Tab; add `focus:ring-2 focus:ring-blue-500` to all focusable elements that are missing it; modals should trap focus while open (`focus-trap-react` or custom)
- [ ] **Screen Reader** — add `role="status"` and `aria-live="polite"` to real-time updating regions (task status, WebSocket event feed, vote tallies); add `role="alert"` to error messages
- [ ] **Color Contrast** — run `axe-core` or `lighthouse --accessibility` audit; fix all elements below WCAG AA ratio (4.5:1 for text, 3:1 for UI components)
- [ ] Add `skipToContent` link as the first focusable element on every page

---

## 🧭 What's Left — Priority Queue

### 🔴 High Priority

1. **13.2** Agent crash detection and reincarnation service (`reincarnation_service.py`)
2. **13.1** Task complexity analyzer and sub-task breakdown (`auto_delegation_service.py`)
3. **13.3** Fix `auto_scale_check` stub — wire real `AgentLifecycleService.spawn_agent()` call
4. **14.2** WebSocket reconnection with exponential backoff and server-side event buffer
5. **14.3** Global frontend error boundaries wrapping all route-level pages
6. **15.3** Channel health monitoring, message logs, and per-channel settings UI

### 🟡 Medium Priority

7. **13.6** Event trigger system (webhook receiver, threshold monitor, dead-letter queue)
8. **13.4** Real-time learning writes and anti-pattern early warning
9. **14.1** Live screenshot stream for browser tasks
10. **15.1** Privilege escalation audit trail
11. **15.2** Real-time MCP tool stats and sub-second revocation via Redis
12. **13.5** Workflow automation pipeline (engine + designer UI)
13. **7.x** Checkpoint diff view (branch comparison)
14. **7.x** Drag-and-drop agent reassignment
15. **15.4** Speaker identification for multi-user voice sessions
16. **6.x** Real-time MCP usage stats; revoked tools unavailable in < 1 s

### 🟢 Low Priority

17. **13.7** Zero-Touch Operations Dashboard (depends on 13.1–13.6)
18. **16.1** Connection pool tuning and slow query logging
19. **16.2** Learning decay for outdated knowledge patterns
20. **16.3** Cross-document citation graph for RAG
21. **16.4** Git versioning backups for config files
22. **17.1** Application-layer DDoS hardening
23. **17.2** System-wide UI polish (dark mode consistency, animations, empty states)
24. **17.3** Mobile responsiveness for complex pages
25. **17.4** Accessibility (ARIA labels, keyboard navigation, color contrast)
26. **9.x** Audit trail for privilege escalations (→ moved to Phase 15.1)

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

## Known Issues & Technical Debt

**High Priority (actively blocking)**

- [ ] `auto_scale_check` Celery task only logs scaling intent — does not actually call `AgentLifecycleService.spawn_agent()` — agents are never auto-spawned
- [ ] WebSocket reconnection logic lacks exponential backoff; clients disconnect permanently on transient network issues
- [ ] Frontend has no global error boundaries — one crashing component brings down the full page

**Medium Priority**

- [ ] Browser task live screenshot stream UI not built (route exists, frontend viewer missing)
- [ ] Checkpoint diff view (branch comparison) not built
- [ ] Channel health monitoring, logs, and settings UI incomplete
- [ ] Speaker identification not production-ready (framework in place, model not integrated)

**Low Priority**

- [ ] UI dark mode inconsistencies on newer pages (Workflows, Events pages not yet built)
- [ ] Mobile responsiveness gaps on complex pages (Tasks, Voting, Monitoring)
- [ ] Accessibility audit not done (ARIA labels, keyboard navigation, color contrast)
- [ ] PostgreSQL slow query logging not enabled
- [ ] Connection pool sizes set to defaults — not tuned for production load
- [ ] Config files not version-controlled via Git

---

## Changelog

### v1.2.0-alpha _(in progress)_

- 🚧 Phase 13: Autonomous Agent Orchestration — planning complete, implementation starting with 13.2 Self-Healing
- 🔮 Phase 14–17: Frontend Reliability, Platform Hardening, Database Optimization, DevSecOps

### v1.1.0-alpha _(current stable)_

- ✅ Phase 11: Multi-User RBAC, Federation, Plugin Marketplace, Mobile API — all implemented and tested
- ✅ Phase 12: Python SDK, TypeScript SDK, Outbound Webhooks, Developer Portal

### v0.7.0-alpha

- ✅ Phases 0–10: Foundation through Advanced Intelligence (Browser, RAG, Voice, Autonomous Learning)
