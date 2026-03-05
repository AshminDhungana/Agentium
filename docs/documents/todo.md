# Agentium Implementation Roadmap

**Project:** Agentium — Personal AI Agent Nation  
**Version:** 0.7.0-alpha  
**Architecture:** Dual-Storage (PostgreSQL + ChromaDB) with hierarchical agent orchestration  
**Status:** Phase 7 ✅ Complete | Phase 8 Testing Next  
_Last Updated: 2026-02-19 · Maintainer: Ashmin Dhungana_

---

## Vision

Build a self-governing AI ecosystem where agents operate under constitutional law, make decisions through democratic voting, and manage their own lifecycle — all while being transparent, auditable, and sovereign.

---

## Progress Overview

| Phase | Name                       | Status      |
| ----- | -------------------------- | ----------- |
| 0     | Foundation Infrastructure  | ✅ Complete |
| 1     | Knowledge Infrastructure   | ✅ Complete |
| 2     | Governance Core            | ✅ Complete |
| 3     | Agent Lifecycle Management | 🚧 90%      |
| 4     | Multi-Channel Integration  | 🚧 90%      |
| 5     | AI Model Integration       | 🚧 90%      |
| 6     | Advanced Features          | ✅ Complete |
| 7     | Frontend Development       | ✅ Complete |
| 8     | Testing & Reliability      | ⬜ Next     |
| 9     | Production Readiness       | ⬜ Pending  |
| 10    | Advanced Intelligence      | ⬜ Pending  |
| 11    | Ecosystem Expansion        | 🔮 Future   |
| 12    | SDK & External Interface   | 🔮 Future   |

---

## Phase 0: Foundation Infrastructure ✅

**Goal:** Rock-solid database and containerization foundation.

### Database

- [x] PostgreSQL 15 with proper schemas
- [x] Agent hierarchy models (0xxxx / 1xxxx / 2xxxx / 3xxxx)
- [x] Foreign key constraints enforcing parent-child relationships
- [x] Indexes on `agent_type`, `status`, `agentium_id`
- [x] Constitution model with version control
- [x] Alembic migrations
- [x] Voting entity models with vote tallying
- [x] Audit log system with immutable records

### Containerization

- [x] Docker Compose orchestration
- [x] PostgreSQL, Redis, ChromaDB services with persistent volumes
- [x] Health checks and network isolation for all services

### Core Entity Models

- [x] `backend/models/entities/agents.py` — Full hierarchy support
- [x] `backend/models/entities/constitution.py` — Versioning
- [x] `backend/models/entities/voting.py` — Democratic mechanics
- [x] `backend/models/entities/audit.py` — Immutable logging
- [x] `backend/models/entities/user.py` — Multi-user RBAC
- [x] `backend/models/entities/base.py` — Common patterns

---

## Phase 1: Knowledge Infrastructure ✅

**Goal:** Dual-storage where structured data lives in PostgreSQL and collective knowledge in ChromaDB.

### 1.1 Vector Database

- [x] ChromaDB on port 8001
- [x] Sentence embeddings via `all-MiniLM-L6-v2`
- [x] Metadata filtering by `agent_id`, `knowledge_type`, `timestamp`
- [x] Collection management: constitution, learnings, rejected
- [x] Similarity search with configurable thresholds

### 1.2 Knowledge Service — `backend/services/knowledge_service.py`

- [x] Constitution semantic search
- [x] Knowledge submission with moderation queue
- [x] Council approval workflow
- [x] Auto-categorization (constitution, task_learning, domain_knowledge)
- [x] RAG context injection into agent prompts
- [x] Duplicate detection

### 1.3 Initialization Protocol — `backend/services/initialization_service.py`

Genesis flow:

1. [x] System detects first boot
2. [x] Head of Council (0xxxx) instantiated
3. [x] Council Members (1xxxx) spawned
4. [x] Democratic vote for Country Name
5. [x] Constitution template loaded with name
6. [x] Vector DB indexes constitution
7. [x] Genesis log stored in `docs_ministry/genesis_log.md`

Anti-tyranny: requires 3 Council votes minimum; original constitution always retrievable.

### 1.4 Knowledge Governance

- [x] Submissions trigger Council vote (50% quorum)
- [x] Rejected knowledge stored in `rejected/` collection
- [x] Retention policy: 365-day auto-archive unless pinned
- [x] Orphaned knowledge cleanup on agent liquidation

---

## Phase 2: Governance Core ✅

**Goal:** Constitutional enforcement, democratic voting, and hierarchical orchestration.

### 2.1 Message Bus — `backend/services/message_bus.py`

- [x] Task → Lead → Council → Head message routing
- [x] Broadcast capabilities (Head → all subordinates)
- [x] Message persistence across container restarts
- [x] Rate limiting (5 msg/sec per agent)
- [x] Hierarchical validation (prevents level-skipping)
- [ ] Rate limit enforcement under load _(to test)_
- [ ] Message persistence after restart _(to test)_

### 2.2 Agent Orchestrator — `backend/services/agent_orchestrator.py`

- [x] Route messages through agent hierarchy
- [x] Validate agent existence before routing
- [x] Inject constitutional context from Vector DB
- [x] Log all routing decisions to audit trail
- [x] WebSocket event broadcasting on routing
- [x] Metrics: routing latency, message volume, error rates, p95
- [x] Circuit breaker for failing agents (CLOSED → OPEN → HALF_OPEN)

### 2.3 Constitutional Guard — `backend/core/constitutional_guard.py`

Two-tier check system:

```
Agent Action Request
    ↓
Tier 1: PostgreSQL (Hard Rules)
  ├─ Explicit blacklists (shell commands)
  ├─ Permission tables
  └─ Resource quotas
    ↓
Tier 2: Vector DB (Semantic Interpretation)
  ├─ Grey area violation detection
  └─ Contextual precedent checking
    ↓
Decision: ALLOW / BLOCK / VOTE_REQUIRED
```

- [x] Load active constitution from PostgreSQL
- [x] Redis caching (5 min constitution, 30 min embeddings)
- [x] Semantic check via ChromaDB (≥70% → BLOCK, 40–70% → VOTE_REQUIRED)
- [x] Trigger Council vote if action affects >3 agents
- [x] Human-readable legal citations ("Article 4, Section 2")
- [x] Violation severity classification (LOW / MEDIUM / HIGH / CRITICAL)

### 2.4 Voting Service — `backend/services/persistent_council.py`

Vote types: constitutional amendments, resource allocation, knowledge approval/rejection, operational decisions, agent liquidation.

- [x] Dynamic quorum calculation
- [x] Vote delegation with circular prevention
- [x] Abstention tracking
- [x] Timeout handling (auto-fail if quorum not met)
- [ ] 60% quorum requirement verification _(to test)_
- [ ] Concurrent voting session handling _(to test)_

### 2.5 Amendment Service — `backend/services/amendment_service.py`

Pipeline:

1. [x] Council member proposes amendment (Markdown diff)
2. [x] 48-hour debate window in `docs_ministry/debates/`
3. [x] Democratic vote (60% quorum)
4. [x] If passed: update PostgreSQL + Vector DB, broadcast via Message Bus
5. [x] Requires 2 Council sponsors
6. [x] Automatic rollback if vote fails

- [ ] Diff visualization in frontend

---

## Phase 3: Agent Lifecycle Management 🚧 (90%)

**Goal:** Dynamic spawning, liquidation, and idle governance with capability management.

### 3.1 Reincarnation Service — `backend/services/reincarnation_service.py`

ID ranges:

```
Head:    00001–09999
Council: 10001–19999
Lead:    20001–29999
Task:    30001–99999
```

- [x] `spawn_task_agent(parent_id, name, capabilities)`
- [x] `promote_to_lead(agent_id)`
- [x] `liquidate_agent(agent_id, reason)`
- [x] `get_available_capacity()`
- [x] `reincarnate_agent(agent_id)`
- [ ] 10,000 concurrent spawn requests _(to test)_
- [ ] ID pool exhaustion handling _(to test)_

### 3.2 Idle Governance — `backend/services/idle_governance.py`

- [x] Detect idle agents (>7 days no activity)
- [x] Resource rebalancing (redistribute work from idle agents)
- [x] Archive messages/tasks to cold storage
- [x] Knowledge transfer to Council curation queue
- [x] Scheduled: daily idle scan, 6-hour liquidation, hourly rebalancing
- [ ] Track: average agent lifetime, idle termination rate, utilization after rebalancing

### 3.3 Capability Registry — `backend/services/capability_registry.py` 🚧

```python
TIER_CAPABILITIES = {
    "0xxxx": ["veto", "amendment", "liquidate_any", "admin_vector_db"],
    "1xxxx": ["propose_amendment", "allocate_resources", "audit", "moderate_knowledge"],
    "2xxxx": ["spawn_task_agent", "delegate_work", "request_resources", "submit_knowledge"],
    "3xxxx": ["execute_task", "report_status", "escalate_blocker", "query_knowledge"]
}
```

- [x] Runtime capability check
- [x] Capability revocation on liquidation
- [x] Capability inheritance (Lead inherits some Council powers)
- [x] Audit trail of capability usage
- [x] Dynamic capability granting via Council vote
- [ ] Testing

---

## Phase 4: Multi-Channel Integration 🚧 (90%)

**Goal:** Connect Agentium to external messaging platforms.

Each channel maps to a dedicated Task Agent (3xxxx), all reporting to a "Communications Council" Lead Agent (2xxxx).

### Channels

- [x] WebSocket, WhatsApp, Telegram, Discord, Slack, Signal, Google Chat, iMessage, Microsoft Teams, Zalo, Matrix

### Key Files

- [x] `backend/services/channel_manager.py`
- [x] `backend/services/channels/base.py`, `whatsapp.py`, `slack.py`
- [x] `backend/models/entities/channels.py`
- [x] `backend/api/routes/channels.py`
- [x] `backend/api/websocket.py` — events: `agent_spawned`, `task_escalated`, `vote_initiated`, `constitutional_violation`, `message_routed`, `knowledge_submitted`, `knowledge_approved`, `amendment_proposed`, `agent_liquidated`

### Pending

- [ ] Channel failure recovery
- [ ] Message format translation (text → rich media)
- [ ] Rate limiting per platform
- [ ] Channel health monitoring and per-channel message logs

---

## Phase 5: AI Model Integration 🚧 (90%)

**Goal:** Multi-provider AI with fallback and optimization.

### 5.1 Model Provider — `backend/services/model_provider.py`

- [x] OpenAI, Anthropic, Groq, Local (Ollama/LM Studio), Universal (any OpenAI-compatible endpoint)
- [x] Multi-provider API key management, automatic fallback, health monitoring, token usage + cost tracking

### 5.2 API Manager — `backend/services/api_manager.py`

- [x] Context window management, token counting (tiktoken), conversation history pruning, system prompt caching
- [x] Per-provider rate limits, circuit breaker, exponential backoff
- [ ] Model-specific prompt templates
- [ ] Cost budget enforcement
- [ ] A/B testing different models for same task

### 5.3 Universal Model Provider — `backend/services/universal_model_provider.py`

- [x] Custom base URL, dynamic model discovery, auth header customization, response format normalization
- Supports: Ollama, LM Studio, vLLM, custom fine-tuned models, third-party aggregators

### 5.4 API Key Resilience — `backend/services/api_key_manager.py` ⬜

Failover chain: Primary (OpenAI) → Secondary (Anthropic) → Tertiary (Groq) → Local (Ollama) → Alert all channels

```python
class APIKeyRecord(BaseEntity):
    provider: str           # "openai", "anthropic", "groq"
    key_hash: str
    priority: int           # 1=primary, 2=secondary, etc.
    status: str             # "active", "failed", "rate_limited", "exhausted"
    failure_count: int
    last_failure_at: Optional[datetime]
    cooldown_until: Optional[datetime]
    monthly_budget_usd: Optional[float]
    current_spend_usd: float = 0.0
```

- [ ] Failover completes in <500ms
- [ ] Auto-recovery after cooldown
- [ ] Real-time provider health on frontend
- [ ] Budget enforcement per key
- [ ] Zero-downtime key rotation

---

## Phase 6: Advanced Features ✅

### 6.1 Tool Creation Service — `backend/services/tool_creation_service.py`

- [x] Agents propose tools (Python code) with security validation and Council approval
- [x] AST parsing, sandboxed execution, dynamic loading
- [x] Approval flow: Head (0xxxx) auto-approves; Council/Lead require vote; Task agents denied
- [x] Tool versioning, deprecation workflow, usage analytics

### 6.2 Critic Agents ✅

New agent types operating outside the democratic chain with absolute veto authority:

- `CodeCritic` (4xxxx) — syntax, security, logic
- `OutputCritic` (5xxxx) — validates against user intent
- `PlanCritic` (6xxxx) — validates execution DAG soundness

When rejected, task retries within the same team (max 5 retries before Council escalation).

```python
class CritiqueReview(BaseEntity):
    task_id: str
    critic_type: str   # "code", "output", "plan"
    verdict: str       # "PASS", "REJECT", "ESCALATE"
    rejection_reason: Optional[str]
    retry_count: int
    max_retries: int = 5
```

- [x] `backend/models/entities/critics.py`, `backend/services/critic_agents.py`, `backend/api/routes/critics.py`
- [x] Critics use different AI models than executors (orthogonal failure modes)

### 6.3 Acceptance Criteria Service — `backend/services/acceptance_criteria.py`

Success criteria declared before work begins; voted on alongside the plan.

```python
@dataclass
class AcceptanceCriterion:
    metric: str          # "sql_syntax_valid", "result_schema_matches"
    threshold: Any
    validator: str       # "code" | "output" | "plan"
    is_mandatory: bool = True
```

- [x] `AcceptanceCriteriaService.evaluate_criteria()` — sql_syntax, result_not_empty, length, contains, boolean
- [x] `CritiqueReview` stores `criteria_results`, `criteria_evaluated`, `criteria_passed`
- [x] 42 unit tests (all passing)

### 6.4 Context Ray Tracing — `backend/services/message_bus.py`

Role-based context visibility via `ContextRayTracer`:

- Planners (Head/Council): user intent, constraints, high-level goals
- Executors (Lead/Task): step-by-step plan, prior step outputs only
- Critics: execution results + acceptance criteria only
- Siblings: no cross-visibility

- [x] `get_agent_role()`, `is_visible_to()`, `filter_messages()`, `apply_scope()`, `build_context()`
- [x] `context_scope`: FULL / SUMMARY (200 chars) / SCHEMA_ONLY
- [x] 57 unit tests (all passing)

### 6.5 Checkpointing — `backend/services/checkpoint_service.py`

```python
class ExecutionCheckpoint(BaseEntity):
    session_id: str
    phase: str       # "plan_approved", "execution_complete", "critique_passed"
    agent_states: JSON
    artifacts: List[str]
    parent_checkpoint_id: Optional[str]  # For branching
    is_active: bool
```

- [x] Auto-created at phase boundaries; supports branching, time-travel, 90-day auto-cleanup

### 6.6 Remote Code Execution ✅ — `backend/services/remote_executor/`

**Principle:** Raw data never enters agent context.

```
Agent (Brain) → Writes Code → Security Guard → Docker Sandbox → Executor → Summary (schema + stats only)
```

- [x] `execution_guard.py` — multi-layer validation (regex + AST + syntax)
- [x] `sandbox.py` — Docker lifecycle management
- [x] `executor.py` — in-container execution with DataFrame analysis
- [x] `service.py` — orchestrator (validate → sandbox → execute → summarize)
- [x] 6 API endpoints, 27 test cases, DB migration
- [x] Non-root Docker image, separate network, resource limits, auto-restart

### 6.7 MCP Server Integration ✅ — `backend/services/mcp_governance.py`

MCP tools enter the same approval pipeline as agent-created tools. Every invocation audited by Constitutional Guard.

Tool tiers:

```
Tier 1 — Pre-Approved: safe read-only APIs, non-destructive queries
Tier 2 — Restricted:   email sending, file writes, external webhooks (Head approval per use)
Tier 3 — Forbidden:    financial transactions, credentials, raw shell execution
```

```python
class MCPTool(BaseEntity):
    name: str
    server_url: str
    tier: str                           # "pre_approved", "restricted", "forbidden"
    constitutional_article: Optional[str]
    approved_by_council: bool = False
    audit_log: List[Dict]
```

- [x] `propose_mcp_server()`, `audit_tool_invocation()`, `get_approved_tools(agent_tier)`, `revoke_mcp_tool()`
- [x] Frontend: `ToolRegistry.tsx` — browse, filter, propose, view invocation logs
- [ ] Every invocation logged with `agent_id`, timestamp, input hash
- [ ] Tier 3 blocked before reaching MCP client
- [ ] Real-time usage stats; revoked tools unavailable in <1s

---

## Phase 7: Frontend Development ✅

### Pages

- [x] Login, Signup, Dashboard, Agents, Tasks, Chat, Settings, Monitoring, Constitution, Channels, Models, Voting

### Key Components

- [x] **Agent Tree** (`AgentTree.tsx`) — collapsible hierarchy, real-time status, color coding by type, spawn/terminate modals
- [x] **Voting Interface** (`VotingPage.tsx`) — active votes with countdowns, amendment diff viewer, real-time tally, delegation, history
- [x] **Constitution Editor** (`ConstitutionPage.tsx`) — article navigation, amendment highlighting, semantic search, diff editor, PDF export
- [x] **Critic Dashboard** (`TasksPage.tsx` → CriticsTab) — per-critic stats, review panels, retry history, performance metrics
- [x] **Checkpoint Timeline** (`CheckpointTimeline.tsx`) — visual phases, restore/branch from checkpoint, state inspector
- [x] **Financial Burn Dashboard** (`FinancialBurnDashboard.tsx`) — token usage vs limits, provider breakdown, 7-day spend history

### Pending

- [ ] Drag-and-drop agent reassignment
- [ ] Checkpoint diff view (compare branches)
- [ ] Channel health monitoring and message logs
- [ ] Channel-specific settings (rate limits, filters)

---

## Phase 8: Testing & Reliability ⬜

### Functional Tests

- [ ] Concurrent agent spawning (1,000 simultaneous)
- [ ] 10,000 messages routed without loss
- [ ] Message persistence after container restart
- [ ] Rate limit enforcement under load
- [ ] Hierarchical validation (reject Task → Council direct message)
- [ ] Quorum calculation accuracy (1, 5, 100 Council members)
- [ ] Concurrent voting sessions
- [ ] Vote delegation chain (A → B → C)
- [ ] Blacklist enforcement (block `rm -rf /`)
- [ ] Semantic violation detection (grey area cases)
- [ ] Cache invalidation on constitution update

### Performance Targets

- [ ] Constitutional check <50ms (SQL), <200ms (semantic)
- [ ] Message routing <100ms
- [ ] API response <500ms (p95)
- [ ] WebSocket event delivery <50ms
- [ ] 100 concurrent dashboard users
- [ ] 1,000 tasks/hour throughput

### Reliability Targets (from research)

- [ ] 87.8% error catch rate via critic layer
- [ ] 92.1% overall task success rate
- [ ] <7.9% residual errors requiring human intervention
- [ ] Zero data loss on container restart
- [ ] Graceful degradation when Vector DB unavailable

---

## Phase 9: Production Readiness ⬜

### Monitoring — `backend/services/monitoring_service.py`

- [x] Background tasks: constitutional patrol (5 min), stale task detection (daily), resource rebalancing (hourly), council health check (weekly), critic queue monitor (1 min)
- [x] Alert levels: INFO, WARNING, CRITICAL, EMERGENCY, CRITIC_VETO
- [x] Alert channels: WebSocket, email, webhook, Slack/Discord

### Memory & Data Management

- [x] Audit logs: 90-day hot retention, then archive
- [x] Constitution: keep last 10 versions; original never deleted
- [x] Vector DB: weekly reindex, duplicate cleanup
- [x] Tasks/messages: cold storage after 30 days
- [x] Chat retention: last 50 messages always kept; older than 7 days removed
- [ ] Query optimization (slow query log)
- [ ] Connection pool tuning

### Backup & Recovery

- [x] PostgreSQL: daily full backup (7-day rotation)
- [x] Vector DB: weekly snapshot (4-week rotation)
- [x] Agent state restoration from checkpoints
- [ ] Point-in-time recovery (last 30 days)
- [ ] Git versioning for config files

### Security

- [x] JWT authentication with configurable token rotation
- [x] RBAC: Sovereign, Council, Lead, Task
- [x] Rate limiting per IP
- [x] Input sanitization (XSS pattern stripping)
- [ ] MFA
- [ ] HTTPS enforcement
- [ ] Audit trail for privilege escalations

### Access Control

- **Admin users:** full system access, view all tasks
- **Standard users:** view and interact with own tasks only

### Agent Emergency Protocol

- If all agents occupied: Head initiates optimization, terminates idle agents
- If no agents available: Head may create one temporary emergency agent (1xxxx ID space), terminated after task completion
- **Only one active Head of Council at any time**

---

## Phase 10: Advanced Intelligence ⬜

### 10.1 Browser Control (Playwright/Puppeteer)

- [ ] Research, form filling, price monitoring, social posting, e-commerce
- [ ] URL whitelist/blacklist, content filtering, screenshot audit logging

### 10.2 Advanced RAG

- [ ] Source attribution and confidence scoring per fact
- [ ] Contradiction detection across sources
- [ ] Automatic fact-checking against Vector DB

### 10.3 Voice Interface

- [ ] Speech-to-text (Whisper), text-to-speech (ElevenLabs/Coqui)
- [ ] Voice channels (phone, Discord voice), speaker identification

### 10.4 Autonomous Learning

- [ ] Task outcome analysis (what worked, what failed)
- [ ] Best-practice extraction from successes
- [ ] Anti-pattern detection from failures
- [ ] Knowledge consolidation (merge similar learnings)

---

## Phase 11: Ecosystem Expansion 🔮

### 11.1 Multi-User RBAC

- [ ] Primary Sovereign (full control), Deputy Sovereign (limited veto), Observer (read-only)
- [ ] Sovereign capability delegation with time-limited grants

### 11.2 Federation

- [ ] Cross-instance task delegation and knowledge sharing
- [ ] Federated voting on shared issues
- Use cases: company departments, research teams, distributed governance

### 11.3 Plugin Marketplace

- [ ] Third-party tool submissions with verified registry
- [ ] Plugin types: channels, specialized critics, AI providers, knowledge sources

### 11.4 Mobile Apps

- [ ] iOS (Swift) and Android (Kotlin)
- [ ] Push notifications, voice commands, offline mode (cached constitution + task queue)

### 11.5 Scalability (50K → 50M+ agents)

- [ ] Expand agent ID length in database
- [ ] Update frontend rendering for large-scale hierarchies
- [ ] Horizontal scalability readiness

---

## Phase 12: SDK & External Interface 🔮

**Philosophy:** External callers get the full power of Agentium, but never bypass the Constitution.

### 12.1 Python SDK — `sdk/python/agentium/`

```python
from agentium import SovereignClient, StatefulSession

client = SovereignClient(
    host="http://localhost:8000",
    api_key="<SOVEREIGN_API_KEY>",
    constitution_version="v1.2.4"  # Pinned — breaks if constitution changes
)

session = StatefulSession(client)
response = session.delegate(
    task="Analyze Q3 reports and summarize findings",
    constraints={"max_cost_usd": 5.00, "privacy_level": "internal"},
    acceptance_criteria={"format": "markdown", "max_length_words": 1000}
)

print(response.result, response.audit_trail, response.cost_usd)
```

- [ ] `SovereignClient`, `StatefulSession`, `delegate()`, `get_audit_trail()`, `get_constitution()`, `propose_amendment()`, `list_agents()`
- [ ] Streaming + async/await support
- [ ] `pip install agentium-sdk`

### 12.2 TypeScript SDK — `sdk/typescript/`

```typescript
import { AgentiumClient, StatefulSession } from "@agentium/sdk";

const session = new StatefulSession(new AgentiumClient({ host, apiKey }));
const response = await session.delegate({
  task: "...",
  constraints: { privacyLevel: "internal" },
});
```

- [ ] `npm install @agentium/sdk`

### 12.3 Governance Rules for SDK Callers

SDK callers **can**: submit tasks, query status and audit trail, propose amendments, read constitution/knowledge base, stream task progress.  
SDK callers **cannot**: bypass Constitutional Guard, skip critic validation, access Tier 3 MCP tools directly, impersonate higher tiers, suppress audit logging.

- [ ] SDK API keys issued per external system, scoped to specific tiers, revocable via Council vote
- [ ] Identical audit trails to direct API calls
- [ ] Constitution version pinning raises error on mismatch

---

## Success Metrics

### Performance

- [ ] 10,000 messages routed/hour without loss
- [ ] Constitutional check: <50ms (SQL), <200ms (semantic)
- [ ] Vote quorum reached <24h average
- [ ] Zero agent ID collisions during concurrent spawning
- [ ] Vector DB query precision >85%

### Reliability

- [ ] 87.8% error catch rate via critics
- [ ] 92.1% overall success rate
- [ ] Checkpoint recovery from any decision point
- [ ] Context isolation (raw data never touches agent context)

### Governance

- [ ] Full amendment lifecycle (propose → debate → vote → enact)
- [ ] Emergency Head override logged and auditable
- [ ] Automatic liquidation of dormant agents (>30 days)
- [ ] Duplicate knowledge rejection rate <5%

---

## Implementation Priority

### 🔥 This Week

1. Constitutional Guard — semantic checking (Tier 2)
2. Critic Agent Framework — 4xxxx/5xxxx/6xxxx types
3. Acceptance Criteria Service

### ⚡ Next 2 Weeks

4. Context Ray Tracing — role-based context visibility
5. Remote Code Executor — Docker sandbox deployment
6. Checkpoint Service
7. API Key Resilience (Phase 5.4)

### 📅 Next Month

8. Amendment Service — complete pipeline
9. MCP Server Integration (Phase 6.7)
10. Voting UI
11. Constitution Editor

### 🔄 Ongoing

- Multi-channel integration and testing
- Load testing and reliability benchmarks
- Memory management and automated cleanup

### 🔮 Future

- Agentium SDK (Phase 12)
- Federation (Phase 11.2)

---

## Infrastructure Stack

```
ChromaDB   — Vector Storage  (port 8001)
Redis      — Message Bus + Cache  (port 6379)
PostgreSQL — Entity Storage  (port 5432)
Celery     — Background Tasks
FastAPI    — API Gateway  (port 8000)
React      — Frontend  (port 3000)
Docker     — Remote Executor (sandboxed)
```

---

## Documentation Needed

**For developers:** API docs (OpenAPI/Swagger), architecture diagrams (Mermaid), DB schema, agent communication protocols, production deployment guide.

**For users:** Constitution writing guide, amendment tutorial, multi-channel setup, troubleshooting, best practices.

**For contributors:** `CONTRIBUTING.md`, code style guide, testing guidelines, PR and issue templates.

---

## Known Issues & Technical Debt

**High Priority**

- [ ] Constitutional Guard semantic checking not implemented
- [ ] Critic agents not implemented
- [ ] Checkpoint service missing
- [ ] API Key Resilience service (Phase 5.4) not formalized
- [ ] Amendment service not created

**Medium Priority**

- [ ] WebSocket reconnection logic needs improvement
- [ ] Message Bus rate limiting not fully tested
- [ ] Vector DB index optimization needed
- [ ] Frontend error boundaries incomplete
- [ ] MCP Tool Registry UI not built

**Low Priority**

- [ ] UI polish (animations, transitions, dark mode consistency)
- [ ] Mobile responsiveness
- [ ] Accessibility (ARIA labels, keyboard navigation)

---

## Changelog

### v0.7.0-alpha _(current)_

- ✅ Knowledge Infrastructure (Vector DB + RAG)
- ✅ Initialization Protocol with democratic country naming
- ✅ Tool Creation Service with approval workflow
- ✅ Multi-channel integration (WhatsApp, Telegram)
- ✅ Agent Orchestrator with constitutional context injection
- 🚧 Constitutional Guard (needs semantic enhancement)
- 🚧 Voting Service (needs frontend integration)

### v0.1.0-alpha

- ✅ Foundation: PostgreSQL, Redis, Docker Compose
- ✅ Entity models: Agents, Constitution, Voting, Audit
- ✅ Basic frontend: Dashboard, Agent Tree, Task List
- ✅ Multi-provider AI model support
