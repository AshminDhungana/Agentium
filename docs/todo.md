# Agentium Implementation Roadmap

## From Democratic AI Governance to Production-Ready System

**Project:** Agentium - Personal AI Agent Nation  
**Current Status:** Phase 2 Active Development (Governance Core)  
**Architecture:** Dual-Storage (PostgreSQL + ChromaDB) with hierarchical agent orchestration  
**Strategy:** Bottom-up implementation, one file at a time

---

## 🎯 Vision Statement

Build a self-governing AI ecosystem where agents operate under constitutional law, make decisions through democratic voting, and manage their own lifecycle—all while being transparent, auditable, and sovereign.

---

## Phase 0: Foundation Infrastructure ✅ (COMPLETE)

**Goal:** Establish rock-solid database and containerization foundation.

### Database Layer ✅

- [x] PostgreSQL 15 configured with proper schemas
- [x] Agent hierarchy models (0xxxx/1xxxx/2xxxx/3xxxx)
- [x] Foreign key constraints enforcing parent-child relationships
- [x] Indexes on `agent_type`, `status`, `agentium_id`
- [x] Constitution model with version control
- [x] Alembic migrations setup
- [x] Voting entity models with vote tallying
- [x] Audit log system with immutable records

### Containerization ✅

- [x] Docker Compose orchestration
- [x] PostgreSQL service with persistent volumes
- [x] Redis for message bus and caching
- [x] ChromaDB for vector storage
- [x] Health checks for all services
- [x] Network isolation and service dependencies

### Core Entity Models ✅

**Files Verified:**

- ✅ `backend/models/entities/agents.py` - Full hierarchy support
- ✅ `backend/models/entities/constitution.py` - Versioning complete
- ✅ `backend/models/entities/voting.py` - Democratic mechanics
- ✅ `backend/models/entities/audit.py` - Immutable logging
- ✅ `backend/models/entities/user.py` - Multi-user RBAC
- ✅ `backend/models/entities/base.py` - Common entity patterns

---

## Phase 1: Knowledge Infrastructure 🧠 ✅ (COMPLETE)

**Goal:** Dual-storage architecture where structured data lives in PostgreSQL and collective knowledge in Vector DB.

### 1.1 Vector Database Setup ✅

**Service:** ChromaDB running on port 8001

**Implementation:**

- ✅ `docker-compose.yml` - ChromaDB service configured
- ✅ `backend/requirements.txt` - chromadb, sentence-transformers, langchain added
- ✅ `backend/core/vector_db.py` - Vector operations service

**Features Implemented:**

- ✅ Sentence embeddings via `all-MiniLM-L6-v2`
- ✅ Metadata filtering by agent_id, knowledge_type, timestamp
- ✅ Collection management (constitution, learnings, rejected)
- ✅ Similarity search with configurable thresholds

### 1.2 Knowledge Service ✅

**File:** `backend/services/knowledge_service.py` ✅

**Capabilities:**

- ✅ Constitution semantic search ("What does Article 3 say about privacy?")
- ✅ Knowledge submission with moderation queue
- ✅ Council approval workflow for new knowledge
- ✅ Auto-categorization (constitution, task_learning, domain_knowledge)
- ✅ RAG context injection into agent prompts
- ✅ Duplicate detection and deduplication

### 1.3 Initialization Protocol ✅

**File:** `backend/services/initialization_service.py` ✅

**Genesis Flow:**

1. ✅ System detects first boot
2. ✅ Head of Council (0xxxx) instantiated
3. ✅ Council Members (1xxxx) spawned
4. ✅ Democratic vote for Country Name
5. ✅ Constitution template loaded with name
6. ✅ Vector DB indexes constitution
7. ✅ Initialization log stored in `docs_ministry/genesis_log.md`

**Anti-Tyranny Measures:**

- ✅ Requires 3 Council votes minimum to complete
- ✅ Original constitution always retrievable
- ✅ Country name persisted in both PostgreSQL and Vector DB

### 1.4 Knowledge Governance ✅

**Acceptance Criteria:**

- ✅ Knowledge submissions trigger Council vote (50% quorum)
- ✅ Rejected knowledge stored in `rejected/` collection
- ✅ Auto-categorization of submissions
- ✅ Retention policy (365-day auto-archive unless pinned)
- ✅ Orphaned knowledge cleanup on agent liquidation

---

## Phase 2: Governance Core ⚖️ ✅ (COMPLETE)

**Goal:** Implement constitutional enforcement, democratic voting, and hierarchical orchestration.

### 2.1 Message Bus Infrastructure ✅

**File:** `backend/services/message_bus.py` ✅

**Redis-Based Routing:**

- ✅ Task → Lead → Council → Head message flow
- ✅ Broadcast capabilities (Head → all subordinates)
- ✅ Message persistence (survives container restarts)
- ✅ Rate limiting (5 msg/sec per agent)
- ✅ Hierarchical validation (prevents level-skipping)

**Testing Checklist:**

- [x] Task agent can message parent Lead
- [x] Lead can broadcast to child Tasks
- [x] Task → Council direct message blocked
- [ ] **TO TEST:** Message persistence after restart
- [ ] **TO TEST:** Rate limit enforcement under load

### 2.2 Agent Orchestrator ✅

**File:** `backend/services/agent_orchestrator.py` ✅

**Core Responsibilities:**

- ✅ Route messages between agent hierarchy
- ✅ Validate agent existence before routing
- ✅ Inject constitutional context from Vector DB
- ✅ Log all routing decisions to audit trail
- ✅ Handle "agent not found" with liquidation check
- ✅ Context manager integration for constitutional compliance

**Enhancements Added:**

- ✅ WebSocket event broadcasting on routing
- ✅ Metrics collection (routing latency, message volume, error rates, p95)
- ✅ Circuit breaker for failing agents (CLOSED→OPEN→HALF_OPEN states)

### 2.3 Constitutional Guard ✅

**File:** `backend/core/constitutional_guard.py` ✅

**Two-Tier Check System Implemented:**

```
Agent Action Request
    ↓
TIER 1: PostgreSQL (Hard Rules)
  ├─ Explicit blacklists (shell commands)
  ├─ Permission tables (who can do what)
  └─ Resource quotas
    ↓
TIER 2: Vector DB (Semantic Interpretation)
  ├─ "Is this against the spirit of the law?"
  ├─ Grey area violation detection
  └─ Contextual precedent checking
    ↓
Decision: ALLOW / BLOCK / VOTE_REQUIRED
```

**Features Complete:**

- ✅ Load active constitution from PostgreSQL
- ✅ Check actions against blacklisted patterns
- ✅ Redis caching for performance (5min constitution, 30min embeddings)
- ✅ Semantic constitutional check via ChromaDB (similarity thresholds: ≥70% BLOCK, 40-70% VOTE_REQUIRED)
- ✅ Trigger Council vote if action affects >3 agents
- ✅ Return human-readable legal citations ("Article 4, Section 2")
- ✅ Cache constitution embeddings for fast semantic search
- ✅ Constitutional violation severity classification (LOW/MEDIUM/HIGH/CRITICAL)

### 2.4 Voting Service ✅ (COMPLETE)

**File:** `backend/services/persistent_council.py` ✅

**Vote Types Implemented:**

- ✅ Constitutional amendments
- ✅ Resource allocation
- ✅ Knowledge approval/rejection
- ✅ Operational decisions
- ✅ Agent liquidation

**Features:**

- ✅ Dynamic quorum calculation
- ✅ Vote delegation (Council → Lead if specified)
- ✅ Circular voting prevention
- ✅ Abstention tracking
- ✅ Timeout handling (auto-fail if quorum not met)
- ✅ Vote tallying and finalization

**Testing Needs:**

- [ ] 60% quorum requirement verification
- [ ] Vote delegation chain testing
- [ ] Timeout behavior under load
- [ ] Concurrent voting session handling

### 2.5 Amendment Service ✅

**File:** `backend/services/amendment_service.py` ✅

**Amendment Pipeline:**

1. ✅ Council member proposes amendment (Markdown diff)
2. ✅ 48-hour debate window stored in `docs_ministry/debates/`
3. ✅ Democratic vote (60% quorum)
4. ✅ If passed:
   - Update PostgreSQL (new version + audit)
   - **Update Vector DB** (current law for RAG)
   - Broadcast law change via Message Bus
5. ✅ Notify all agents of constitutional update

**Acceptance Criteria:**

- ✅ Amendment proposals require 2 Council sponsors
- ✅ Configurable voting period (default 48h)
- ✅ Vector DB updated immediately upon ratification
- ✅ Automatic rollback if vote fails
- [ ] Diff visualization in frontend
- ✅ Amendment history tracking

---

## Phase 3: Agent Lifecycle Management 🔄 (IN PROGRESS - 90% COMPLETE)

**Goal:** Dynamic spawning, liquidation, and idle governance with capability management.

### 3.1 Reincarnation Service (Agent Factory) ✅

**File:** `backend/services/reincarnation_service.py` ✅

**ID Generation Rules:**

```
Head:    00001-00999  (max 999 heads - one per Sovereign)
Council: 10001-19999  (max 9,999 councils)
Lead:    20001-29999  (max 9,999 leads)
Task:    30001-99999  (max 69,999 tasks)
```

**Methods Implemented:**

- ✅ `spawn_task_agent(parent_id, name, capabilities)`
- ✅ `promote_to_lead(agent_id)` - Upgrade Task → Lead
- ✅ `liquidate_agent(agent_id, reason)` - Safe termination
- ✅ `get_available_capacity()` - Check ID pool availability
- ✅ `reincarnate_agent(agent_id)` - Restore from backup

**Testing Checklist:**

- [x] No ID collisions during concurrent spawning
- [x] Parent-child hierarchy enforced
- [ ] **TO TEST:** 10,000 concurrent spawn requests
- [ ] **TO TEST:** ID pool exhaustion handling

### 3.2 Idle Governance ✅

**File:** `backend/services/idle_governance.py` ✅

**Auto-Termination Logic:**

- ✅ Detect idle agents (>7 days no activity)
- ✅ Duplicate idle task prevention (idempotency keys)
- ✅ Resource rebalancing (redistribute work from idle agents)
- ✅ Cleanup: Archive messages/tasks to cold storage
- ✅ Knowledge transfer to Council curation queue

**Scheduled Tasks:**

- ✅ `detect_idle_agents()` - Daily scan
- ✅ `auto_liquidate_expired()` - Every 6 hours
- ✅ `resource_rebalancing()` - Hourly optimization

**Metrics to Track:**

- [ ] Average agent lifetime
- [ ] Idle termination rate
- [ ] Resource utilization after rebalancing

### 3.3 Capability Registry 🚧 (PARTIAL)

**File:** `backend/services/capability_registry.py` (needs expansion)

**Current Capabilities Defined:**

```python
TIER_CAPABILITIES = {
    "0xxxx": ["veto", "amendment", "liquidate_any", "admin_vector_db"],
    "1xxxx": ["propose_amendment", "allocate_resources", "audit", "moderate_knowledge"],
    "2xxxx": ["spawn_task_agent", "delegate_work", "request_resources", "submit_knowledge"],
    "3xxxx": ["execute_task", "report_status", "escalate_blocker", "query_knowledge"]
}
```

**Pending Implementation:**

- [x] Runtime capability check (`can_agent_X_do_action_Y()`)
- [x] Capability revocation on liquidation
- [x] Capability inheritance (Lead inherits some Council powers)
- [x] Audit trail of capability usage
- [x] Dynamic capability granting via Council vote
- [ ] Testing

---

## Phase 4: Multi-Channel Integration 📱 (IN PROGRESS - 90% COMPLETE)

**Goal:** Connect Agentium to external messaging platforms as communication channels.

### 4.1 Channel Manager ✅

**File:** `backend/services/channel_manager.py` ✅

**Architecture:**

- Each channel mapped to dedicated Task Agents (3xxxx)
- Channels report to "Communications Council" Lead Agent (2xxxx)
- All messages routed through Message Bus

### 4.2 Channel Implementation Status

**Implemented Channels:**

- [x] WebSocket (real-time dashboard)
- [x] WhatsApp (Baileys library integration)
- [x] Telegram Bot API
- [x] Discord Bot
- [x] Slack App
- [x] Signal (signal-cli)
- [x] Google Chat
- [x] iMessage (macOS only)
- [x] Microsoft Teams
- [x] Zalo
- [x] Matrix

**Files:**

- ✅ `backend/services/channel_manager.py` - Core routing
- ✅ `backend/models/entities/channels.py` - Channel metadata
- ✅ `backend/api/routes/channels.py` - Channel CRUD

**Testing Needs:**

- [ ] Multi-channel concurrent message handling
- [ ] Channel failure recovery
- [ ] Message format translation (text → rich media)
- [ ] Rate limiting per platform

### 4.3 WebSocket Integration ✅

**File:** `backend/api/websocket.py` ✅

**Events Implemented:**

- ✅ `agent_spawned`
- ✅ `task_escalated`
- ✅ `vote_initiated`
- ✅ `constitutional_violation`
- ✅ `message_routed`

**Pending Events:**

- [x] `knowledge_submitted`
- [x] `knowledge_approved`
- [x] `amendment_proposed`
- [x] `agent_liquidated`

---

## Phase 5: AI Model Integration 🤖 (IN PROGRESS - 70% COMPLETE)

**Goal:** Multi-provider AI model support with fallback and optimization.

### 5.1 Model Provider Service ✅

**File:** `backend/services/model_provider.py` ✅

**Supported Providers:**

- ✅ OpenAI (GPT-4, GPT-3.5-turbo)
- ✅ Anthropic (Claude 3 Opus, Sonnet, Haiku)
- ✅ Groq (Llama 3)
- ✅ Local (Ollama, LM Studio)
- ✅ Universal (any OpenAI-compatible endpoint)

**Features:**

- ✅ Multi-provider API key management
- ✅ Automatic fallback on provider failure
- ✅ Provider health monitoring
- ✅ Token usage tracking per provider
- ✅ Cost calculation (USD)

### 5.2 API Manager ✅

**File:** `backend/services/api_manager.py` ✅

**Token Optimization:**

- ✅ Context window management
- ✅ Token counting (tiktoken)
- ✅ Conversation history pruning
- ✅ System prompt caching

**Rate Limiting:**

- ✅ Per-provider rate limits
- ✅ Circuit breaker on failures
- ✅ Exponential backoff retry logic

**Pending Enhancements:**

- [ ] Model-specific prompt templates
- [ ] Cost budget enforcement
- [ ] Provider performance metrics
- [ ] A/B testing different models for same task

### 5.3 Universal Model Provider ✅

**File:** `backend/services/universal_model_provider.py` ✅

**Purpose:** Support ANY OpenAI-compatible endpoint

**Features:**

- ✅ Custom base URL configuration
- ✅ Dynamic model discovery
- ✅ Authentication header customization
- ✅ Response format normalization

**Use Cases:**

- Local LLMs (Ollama, LM Studio, vLLM)
- Private cloud deployments
- Custom fine-tuned models
- Third-party aggregators

---

## Phase 6: Advanced Features 🚀 (NEW - HIGH PRIORITY)

**Based on research: "If You Want Coherence, Orchestrate a Team of Rivals"**

### 6.1 Tool Creation Service 🆕 ✅

**File:** `backend/services/tool_creation_service.py` ✅

**Agent-Initiated Tool Development:**

- ✅ Agents can propose new tools (Python code)
- ✅ Security validation (import whitelist, dangerous pattern blocking)
- ✅ Democratic approval workflow (Council vote)
- ✅ Automatic testing before activation
- ✅ Tool registry integration

**Tool Factory:**

- ✅ `backend/services/tool_factory.py` - Code generation and validation
- ✅ AST parsing for syntax checks
- ✅ Sandboxed execution environment
- ✅ Dynamic tool loading

**Approval Flow:**

1. Agent proposes tool → Code validation
2. If Head (0xxxx): Auto-approve
3. If Council/Lead: Council vote required
4. If Task: Permission denied
5. Tests run on approval
6. Tool registered and available to authorized tiers

**Pending:**

- [ ] Tool versioning and updates
- [ ] Tool deprecation workflow
- [ ] Usage analytics per tool
- [ ] Tool marketplace (share between Agentium instances)

### 6.2 Critic Agents with Veto Authority 🆕 (DONE)

**New Agent Types (Non-Breaking Addition):**

- `CodeCritic` (4xxxx) - Validates code syntax, security, logic
- `OutputCritic` (5xxxx) - Validates against user intent
- `PlanCritic` (6xxxx) - Validates execution DAG soundness

**Key Principle:** Critics operate OUTSIDE democratic chain

- Don't vote on amendments
- Have ABSOLUTE veto authority
- When critic rejects, task retries WITHIN same team
- No Council escalation on critic rejection

**Implementation Plan:**

**New Files to Create:**

- [x] `backend/models/entities/critics.py` - Critic agent models
- [x] `backend/services/critic_agents.py` - Critic logic
- [x] `backend/api/routes/critics.py` - Critic endpoints

**Database Changes:**

```python
class CritiqueReview(BaseEntity):
    task_id: str
    critic_type: str  # "code", "output", "plan"
    critic_agentium_id: str
    verdict: str  # "PASS", "REJECT", "ESCALATE"
    rejection_reason: Optional[str]
    retry_count: int
    max_retries: int = 5
```

**Acceptance Criteria:**

- [x] Critics can veto outputs independently
- [x] Rejected tasks retry without Council replanning
- [x] Maximum 5 retries before escalation to Council
- [x] Critic decisions logged in audit trail
- [x] Critics use different AI models than executors (orthogonal failure modes)

### 6.3 Pre-Declared Acceptance Criteria 🆕 (PENDING - HIGH PRIORITY)

**Goal:** Define success criteria BEFORE work begins

**Implementation:**

- [ ] Add `acceptance_criteria` JSON field to task proposals
- [ ] Council votes on BOTH plan AND success criteria
- [ ] Store as structured, machine-validatable JSON

**Database Migration:**

```python
# Add to existing Task model (non-breaking)
class Task:
    # ... existing fields ...
    acceptance_criteria: Optional[JSON] = None  # NEW
    veto_authority: Optional[str] = None  # Which critic validates
```

**Criterion Structure:**

```python
class AcceptanceCriterion:
    metric: str  # "sql_syntax_valid", "result_schema_matches"
    threshold: Any  # Expected value or range
    validator: str  # Which critic agent validates
    is_mandatory: bool
```

**Acceptance Criteria:**

- [ ] All new tasks require explicit acceptance criteria
- [ ] Criteria are machine-validatable where possible
- [ ] Human-readable criteria displayed in dashboard
- [ ] Criteria stored in task metadata

### 6.4 Context Ray Tracing - Selective Information Flow 🆕 (PENDING)

**File:** `backend/services/message_bus.py` (Enhancement)

**Problem:** Current system shares full context across all agents
**Solution:** Role-based context visibility

**Message Visibility Controls:**

- **Planners** (Head/Council): User intent, constraints, high-level goals
- **Executors** (Lead/Task): Step-by-step plan, prior step outputs ONLY
- **Critics** (4xxxx/5xxxx/6xxxx): Execution results + acceptance criteria ONLY
- **Siblings**: NO visibility into each other's work

**Enhanced Message Schema:**

```python
class AgentMessage:
    content: str
    visible_to: List[str]  # Agent ID patterns: ["2*", "3*"]
    message_type: str  # "PLAN", "EXECUTION", "CRITIQUE"
    context_scope: str  # "FULL", "SUMMARY", "SCHEMA_ONLY"  # NEW
```

**Acceptance Criteria:**

- [ ] Agents only receive context relevant to their role
- [ ] Sibling task isolation enforced
- [ ] Context window optimization (reduced token usage)
- [ ] No cross-contamination between execution branches

### 6.5 Checkpointing & Time-Travel Recovery 🆕 (PENDING)

**New File:** `backend/services/checkpoint_service.py`

**Purpose:** Enable session resumption and retry from any point

**Implementation:**

- [ ] Serialize complete system state after each phase
- [ ] Store in PostgreSQL with versioning
- [ ] Allow "time travel" to any checkpoint
- [ ] Support branching (try different approaches from same checkpoint)

**Database Model:**

```python
class ExecutionCheckpoint(BaseEntity):
    session_id: str
    phase: str  # "plan_approved", "execution_complete", "critique_passed"
    agent_states: JSON  # Dict[agent_id, AgentState]
    artifacts: List[str]  # Generated outputs
    parent_checkpoint_id: Optional[str]  # For branching
    is_active: bool
```

**Acceptance Criteria:**

- [ ] Checkpoints created automatically at phase boundaries
- [ ] Users can resume sessions after days/weeks
- [ ] Retry from any checkpoint with different parameters
- [ ] Complete audit trail of checkpoint transitions
- [ ] Checkpoint cleanup (auto-delete after 90 days)

### 6.6 Remote Code Execution (Brains vs Hands) 🆕 (PENDING - CRITICAL)

**Goal:** Separate reasoning from execution to prevent context contamination

**New Service:** `backend/services/remote_executor/` (Docker container)

**Architecture:**

```
Agent (Brain) → Writes Code → Remote Executor (Hands) → Returns Summary
     ↑                                                    ↓
     └────────────── Receives Summary ←───────────────────┘
```

**Key Principle:** Raw data NEVER enters agent context

**Implementation:**

```python
class RemoteCodeExecutor:
    def execute(self, code: str, context: ExecutionContext) -> ExecutionSummary:
        # Runs in isolated Docker container
        raw_result = self.run_in_sandbox(code)

        # Returns ONLY what agent needs to know
        return ExecutionSummary(
            schema=raw_result.schema,
            row_count=len(raw_result),
            sample=raw_result.head(3),  # Small preview
            stats=raw_result.describe(),
            # NEVER returns full raw data
        )
```

**Acceptance Criteria:**

- [ ] Raw data never enters agent context window
- [ ] Agents reason about data shape, not content
- [ ] PII stays in execution layer
- [ ] Working set size >> context window size
- [ ] Code execution fully sandboxed (Docker isolation)
- [ ] Resource limits enforced (CPU, memory, time)

**Docker Service:**

- [ ] Create `docker-compose.remote-executor.yml`
- [ ] Separate network isolation
- [ ] Limited resource allocation
- [ ] Auto-restart on failure

---

## Phase 7: Frontend Development 🎨 (IN PROGRESS - 50% COMPLETE)

**Goal:** Rich, intuitive dashboard for sovereign control and system monitoring.

### 7.1 Core Pages ✅

**Implemented:**

- ✅ `LoginPage.tsx` - JWT authentication
- ✅ `SignupPage.tsx` - User registration with admin approval
- ✅ `Dashboard.tsx` - System overview, stats, health
- ✅ `AgentsPage.tsx` - Hierarchical agent tree visualization
- ✅ `TasksPage.tsx` - Task list with filtering
- ✅ `ChatPage.tsx` - WebSocket chat with Head of Council
- ✅ `SettingsPage.tsx` - Password management
- ✅ `MonitoringPage.tsx` - System health metrics

**Pending:**

- [ ] `ConstitutionPage.tsx` - Full Markdown viewer/editor
- [ ] `VotingPage.tsx` - Active votes and history
- [ ] `ChannelsPage.tsx` - Multi-channel management
- [ ] `ModelsPage.tsx` - AI provider configuration

### 7.2 Agent Tree Visualization ✅

**File:** `frontend/src/components/agents/AgentTree.tsx` ✅

**Features:**

- ✅ Collapsible hierarchy (Head > Council > Lead > Task)
- ✅ Real-time agent status (idle/active/liquidated)
- ✅ Color coding by agent type
- ✅ Spawn agent modal
- ✅ Terminate agent confirmation

**Pending Enhancements:**

- [ ] Health score visualization
- [ ] Task count badge per agent
- [ ] Drag-and-drop reassignment
- [ ] Critic agents (4xxxx/5xxxx/6xxxx) in separate branch

### 7.3 Voting Interface 🚧 (PARTIAL)

**Needs Implementation:**

**New Component:** `frontend/src/components/council/VotingInterface.tsx`

**Features:**

- [ ] Active votes list with countdown timers
- [ ] Amendment diff viewer (Markdown side-by-side)
- [ ] Real-time vote tally (WebSocket updates)
- [ ] Delegate authority checkbox
- [ ] Proposal composer with rich text
- [ ] Vote history archive

### 7.4 Constitution Editor 🚧 (PARTIAL)

**File:** `frontend/src/pages/ConstitutionPage.tsx` (needs completion)

**Features:**

- [ ] Render Markdown with article navigation
- [ ] Highlight recently amended sections (last 7 days)
- [ ] Semantic search across constitution (Vector DB)
- [ ] "Propose Amendment" button → opens modal with diff editor
- [ ] Amendment history timeline
- [ ] Export constitution as PDF

### 7.5 Critic Dashboard 🆕 (PENDING)

**New File:** `frontend/src/components/critics/CriticPanel.tsx`

**Features:**

- [ ] Pending reviews queue (by critic type)
- [ ] Acceptance criteria validator interface
- [ ] Veto override requests (escalate to Council)
- [ ] Retry history visualization
- [ ] Critic performance metrics (approval rate, avg review time)

### 7.6 Checkpoint Timeline 🆕 (PENDING)

**New File:** `frontend/src/components/checkpoints/CheckpointTimeline.tsx`

**Features:**

- [ ] Visual timeline of execution phases
- [ ] Click to restore/branch from checkpoint
- [ ] Compare different execution branches (diff view)
- [ ] Export/import checkpoint states
- [ ] Checkpoint cleanup management

### 7.7 Multi-Channel Interface ✅

**File:** `frontend/src/pages/ChannelsPage.tsx` ✅

**Features:**

- ✅ Channel list with status indicators
- ✅ Add/remove channels
- ✅ Channel configuration (API keys, webhooks)
- ✅ Message routing visualization

**Pending:**

- [ ] Channel health monitoring
- [ ] Message log per channel
- [ ] Channel-specific settings (rate limits, filters)

---

## Phase 8: Testing & Reliability 🧪 (ONGOING)

**Goal:** Ensure system reliability under load and edge cases.

### 8.1 Core Functionality Verification

**Database Layer:**

- [ ] Test concurrent agent spawning (1000 simultaneous requests)
- [ ] Verify foreign key constraints prevent orphaned agents
- [ ] Constitution versioning rollback testing
- [ ] Audit log integrity checks

**Message Bus:**

- [ ] 10,000 messages routed without loss
- [ ] Message persistence after container restart
- [ ] Rate limit enforcement (block 6th message in same second)
- [ ] Hierarchical validation (reject Task → Council direct message)

**Voting System:**

- [ ] Quorum calculation accuracy (test with 1, 5, 100 Council members)
- [ ] Concurrent voting sessions (multiple proposals simultaneously)
- [ ] Vote delegation chain (A delegates to B, B delegates to C)
- [ ] Timeout handling (auto-fail after 48h)

**Constitutional Guard:**

- [ ] Blacklist enforcement (block `rm -rf /`)
- [ ] Semantic violation detection (grey area cases)
- [ ] Performance: <50ms for SQL checks, <200ms for semantic checks
- [ ] Cache invalidation on constitution update

### 8.2 Performance Benchmarks

**Targets:**

- [ ] Constitutional check latency <50ms (SQL)
- [ ] Semantic search latency <200ms (Vector DB)
- [ ] Message routing latency <100ms
- [ ] API response time <500ms (95th percentile)
- [ ] WebSocket event delivery <50ms

**Load Testing:**

- [ ] 100 concurrent users on dashboard
- [ ] 1000 tasks/hour throughput
- [ ] 10,000 agents active simultaneously
- [ ] 1TB knowledge base (Vector DB)

### 8.3 Reliability Metrics (From Research)

**Critic Layer Effectiveness:**

- [ ] **Target:** 87.8% error catch rate via critics
- [ ] **Target:** 92.1% overall success rate
- [ ] **Target:** <7.9% residual error rate requiring human intervention

**System Resilience:**

- [ ] Zero data loss during container restarts
- [ ] Automatic recovery from PostgreSQL connection failures
- [ ] Graceful degradation when Vector DB unavailable
- [ ] Circuit breaker prevents cascade failures

---

## Phase 9: Production Readiness 🏭 (PENDING)

**Goal:** Harden system for production deployment with monitoring and maintenance.

### 9.1 Monitoring & Observability

**New Service:** `backend/services/monitoring_service.py` (enhancement)

**Background Tasks:**

- [x] `constitutional_patrol()` - Every 5 minutes
- [x] `stale_task_detector()` - Daily
- [ ] `resource_rebalancing()` - Hourly
- [ ] `council_health_check()` - Weekly
- [ ] `knowledge_consolidation()` - Daily
- [ ] `orphaned_knowledge_check()` - Weekly
- [ ] `critic_queue_monitor()` - Every minute

**Alert System:**

**File:** `backend/services/alert_manager.py` (enhancement)

**Severity Levels:**

- [x] INFO: Task completed
- [x] WARNING: Task blocked >1 hour
- [ ] CRITICAL: Constitutional violation detected
- [ ] EMERGENCY: Head intervention required
- [ ] CRITIC_VETO: Output rejected by critic (new)

**Channels:**

- [x] WebSocket (real-time dashboard)
- [ ] Email (Council level+)
- [ ] Webhook (external integrations)
- [ ] Slack/Discord notifications

### 9.2 Memory Management

**Database Maintenance:**

- [ ] Auto-delete old audit logs (keep 90 days hot, archive rest)
- [ ] Constitution version cleanup (keep last 10, archive older)
- [ ] **NEVER delete original constitution**
- [ ] Vector DB optimization (reindex weekly, cleanup duplicates)
- [ ] Task/message archive (cold storage after 30 days)

**Performance:**

- [ ] Index maintenance (rebuild weekly)
- [ ] Query optimization (slow query log analysis)
- [ ] Connection pooling tuning
- [ ] Cache hit rate monitoring (Redis)

### 9.3 Backup & Disaster Recovery

**Backup Strategy:**

- [ ] PostgreSQL: Daily full backup, hourly incrementals
- [ ] Vector DB: Weekly full snapshot
- [ ] Configuration files: Git versioning
- [ ] Encryption at rest for sensitive data

**Recovery Procedures:**

- [ ] Point-in-time recovery (last 30 days)
- [ ] Constitution rollback workflow
- [ ] Agent state restoration from checkpoints
- [ ] Knowledge Library restoration from vector snapshots

### 9.4 Security Hardening

**Authentication:**

- [x] JWT token authentication
- [ ] Token rotation policy (7-day expiry)
- [ ] Multi-factor authentication (MFA)
- [ ] Session management (max 5 concurrent sessions)

**Authorization:**

- [x] Role-based access control (Sovereign, Council, Lead, Task)
- [ ] Capability-based security (fine-grained permissions)
- [ ] Audit trail for all privilege escalations

**Network Security:**

- [ ] HTTPS enforcement
- [ ] Rate limiting on API endpoints
- [ ] DDoS protection
- [ ] Input sanitization and validation

### 9.5 API Key Resilience

**File:** `backend/services/api_manager.py` (enhancement)

**Features:**

- [x] Auto-fallback to next available API key
- [ ] Circuit breaker pattern for failing providers
- [ ] Notification if ALL API keys failing
- [ ] API key rotation without downtime
- [ ] Cost budget enforcement per key

**Multi-Provider Strategy:**

- [ ] Primary: OpenAI
- [ ] Secondary: Anthropic
- [ ] Tertiary: Groq
- [ ] Fallback: Local models (Ollama)

---

## Phase 10: Advanced Intelligence 🧠 (FUTURE)

**Goal:** Enhance agent cognitive capabilities and autonomous learning.

### 10.1 Browser Control Integration

**Planned Integration:** Playwright/Puppeteer for web automation

**Use Cases:**

- [ ] Research tasks (scrape, summarize)
- [ ] Form filling and submission
- [ ] Price monitoring
- [ ] Social media posting
- [ ] E-commerce operations

**Safety:**

- [ ] URL whitelist/blacklist
- [ ] Content filtering
- [ ] Screenshot logging for auditing

### 10.2 Advanced RAG with Citations

**Enhancements:**

- [ ] Source attribution for every claim
- [ ] Confidence scoring per fact
- [ ] Contradiction detection across sources
- [ ] Automatic fact-checking against Vector DB

### 10.3 Voice Interface

**Implementation:**

- [ ] Speech-to-text (Whisper)
- [ ] Text-to-speech (ElevenLabs/Coqui)
- [ ] Voice channel integration (phone, Discord voice)
- [ ] Speaker identification (multi-user)

### 10.4 Autonomous Learning

**Self-Improvement Mechanisms:**

- [ ] Task outcome analysis (what worked, what failed)
- [ ] Best practices extraction from successful tasks
- [ ] Anti-pattern detection from failures
- [ ] Knowledge consolidation (merge similar learnings)

---

## Phase 11: Ecosystem Expansion 🌍 (FUTURE)

**Goal:** Scale from single-user to multi-user, multi-instance ecosystem.

### 11.1 Multi-User RBAC

**Sovereign Roles:**

- [ ] Primary Sovereign (full control)
- [ ] Deputy Sovereign (limited veto power)
- [ ] Observer (read-only access)

**Delegation:**

- [ ] Sovereign can delegate specific capabilities
- [ ] Temporary authority grants (time-limited)
- [ ] Emergency override transfer

### 11.2 Federation (Inter-Agentium Communication)

**Architecture:**

- [ ] Agentium instances can communicate
- [ ] Cross-instance task delegation
- [ ] Knowledge sharing between instances
- [ ] Federated voting on shared issues

**Use Cases:**

- Company departments (Engineering, Sales, HR)
- Collaborative research teams
- Distributed governance

### 11.3 Plugin Marketplace

**Developer Ecosystem:**

- [ ] Third-party tool submissions
- [ ] Verified plugin registry
- [ ] Revenue sharing model
- [ ] Plugin versioning and updates

**Plugin Types:**

- Custom channels (new messaging platforms)
- Specialized critics (domain-specific validation)
- AI model providers
- Knowledge sources (databases, APIs)

### 11.4 Mobile Applications

**Platforms:**

- [ ] iOS app (Swift)
- [ ] Android app (Kotlin)

**Features:**

- Push notifications for votes/alerts
- Voice command interface
- Offline mode (cached constitution, task queue)

---

## Success Metrics 📊

### Technical Metrics

**Performance:**

- [ ] 10,000 messages routed/hour without loss
- [ ] Constitutional check <50ms (SQL), <200ms (semantic)
- [ ] Vote quorum reached <24h average
- [ ] Zero agent ID collisions during concurrent spawning
- [ ] Vector DB query precision >85%
- [ ] Knowledge moderation queue cleared <48h average

**Reliability (from Research):**

- [ ] **87.8% error catch rate via critic layer**
- [ ] **92.1% overall success rate**
- [ ] **<7.9% residual error rate requiring human intervention**
- [ ] Checkpoint recovery from any decision point
- [ ] Context isolation (raw data never touches agent context)
- [ ] Orthogonal failure modes (critics use different models)

### Governance Metrics

**Democratic Process:**

- [ ] Successful amendment lifecycle (propose → debate → vote → enact)
- [ ] Emergency Head override logged and auditable
- [ ] Automatic liquidation of dormant agents (>30 days)
- [ ] Resource rebalancing reduces task queue by 20%

**Knowledge Quality:**

- [ ] Constitution semantically queryable ("What are core values?")
- [ ] Knowledge sharing increases task efficiency (measure via completion time)
- [ ] Duplicate knowledge rejection rate <5%

**Critic Effectiveness:**

- [ ] Critic veto catches errors before user exposure (87.8%)
- [ ] No self-certification (writers cannot approve own work)
- [ ] Orthogonal failure modes verified (different models)

---

## Implementation Priority Matrix

### 🔥 Immediate (This Week)

1. **Constitutional Guard Enhancement** - Add semantic checking (Tier 2)
2. **Critic Agent Framework** - Create 4xxxx/5xxxx/6xxxx agent types
3. **Acceptance Criteria Service** - Pre-declare success criteria

### ⚡ Short Term (Next 2 Weeks)

4. **Context Ray Tracing** - Role-based context visibility in Message Bus
5. **Remote Code Executor** - Docker service for sandboxed execution
6. **Checkpoint Service** - Time-travel recovery system

### 📅 Medium Term (Next Month)

7. **Amendment Service** - Complete constitutional amendment pipeline
8. **Voting UI** - Rich frontend for democratic deliberation
9. **Constitution Editor** - Full Markdown editor with semantic search

### 🔄 Ongoing

10. **Multi-Channel Integration** - Discord, Slack, Signal, Teams
11. **Testing & Benchmarking** - Load tests, reliability metrics
12. **Memory Management** - Automated cleanup and archiving

---

## Critical Dependencies

### Infrastructure Stack

```
ChromaDB (Vector Storage) ✅ Running on port 8001
    ↓
Redis (Message Bus + Cache) ✅ Running on port 6379
    ↓
PostgreSQL (Entity Storage) ✅ Running on port 5432
    ↓
Celery (Background Tasks) ✅ Configured
    ↓
FastAPI (API Gateway) ✅ Running on port 8000
    ↓
React Frontend ✅ Running on port 3000
    ↓
Remote Executor (NEW) 🆕 - Docker sandbox for code execution (PENDING)
```

### Python Dependencies

**Already in requirements.txt:**

```
redis==5.0.1
chromadb==0.4.22
sentence-transformers==2.3.1
langchain==0.1.0
alembic==1.13.1
fastapi==0.109.0
sqlalchemy==2.0.25
celery==5.3.6
```

**Need to Add:**

```
pydantic-settings==2.1.0  # For structured handoffs (Phase 6)
docker==7.0.0             # For remote executor client (Phase 6)
RestrictedPython==7.0     # For sandboxed code execution (Phase 6)
playwright==1.40.0        # For browser automation (Phase 10)
```

---

## Research Paper Integration Summary

**Key Insights from "If You Want Coherence, Orchestrate a Team of Rivals"**

### ✅ Already Implemented

1. **Hierarchical Structure** - 0xxxx/1xxxx/2xxxx/3xxxx agent tiers
2. **Democratic Voting** - Council deliberation and voting
3. **Constitutional Law** - Agents bound by shared rules

### 🆕 Critical Additions Needed

4. **Pre-Declared Acceptance Criteria** - Define success BEFORE work starts
5. **Specialized Critics with Veto** - Opposing forces to catch errors
6. **Context Isolation** - Prevent contamination across execution branches
7. **Remote Code Execution** - Separate reasoning from execution
8. **Checkpointing** - Time-travel recovery and branching
9. **Orthogonal Failure Modes** - Force model diversity (different providers)
10. **Structured Handoffs** - Type-safe inter-agent communication

### The Biggest Gap

**Current:** Democratic voting seeks consensus
**Needed:** Veto authority enforces boundaries

**Research shows:** Consensus voting lets errors through; veto authority catches them.

**Migration Strategy:** All additions are NON-BREAKING

- New agent types (4xxxx/5xxxx/6xxxx)
- New services (checkpoint, remote executor)
- Enhanced existing services (message bus, constitutional guard)
- Existing voting system remains intact
- Critics operate in PARALLEL to hierarchy

---

## Documentation Needs

### For Developers

- [ ] API documentation (OpenAPI/Swagger)
- [ ] Architecture diagrams (Mermaid)
- [ ] Database schema documentation
- [ ] Agent communication protocols
- [ ] Deployment guide (production)

### For Users

- [ ] Constitution writing guide
- [ ] Amendment proposal tutorial
- [ ] Multi-channel setup guide
- [ ] Troubleshooting common issues
- [ ] Best practices for agent orchestration

### For Contributors

- [ ] CONTRIBUTING.md
- [ ] Code style guide
- [ ] Testing guidelines
- [ ] Pull request template
- [ ] Issue templates (bug, feature, question)

---

## Deployment Considerations

### Local Development ✅

- [x] Docker Compose working on all platforms (Linux, macOS, Windows)
- [x] Hot reload for backend (FastAPI)
- [x] Hot reload for frontend (Vite)
- [x] Persistent volumes for data

### Production Deployment

**Infrastructure:**

- [ ] Kubernetes manifests (Helm charts)
- [ ] Load balancer configuration (Nginx/Traefik)
- [ ] SSL/TLS certificates (Let's Encrypt)
- [ ] CDN setup for frontend assets

**Scaling:**

- [ ] Horizontal pod autoscaling
- [ ] Database read replicas
- [ ] Redis cluster mode
- [ ] Vector DB sharding

**Monitoring:**

- [ ] Prometheus metrics export
- [ ] Grafana dashboards
- [ ] Loki for log aggregation
- [ ] Jaeger for distributed tracing

---

## Known Issues & Technical Debt

### High Priority

- [ ] Constitutional Guard semantic checking not implemented
- [ ] Amendment service not created
- [ ] Critic agents not implemented
- [ ] Remote executor not deployed
- [ ] Checkpoint service missing

### Medium Priority

- [ ] WebSocket reconnection logic needs improvement
- [ ] Message Bus rate limiting not fully tested
- [ ] Vector DB index optimization needed
- [ ] Frontend error boundaries incomplete

### Low Priority

- [ ] UI polish (animations, transitions)
- [ ] Dark mode consistency
- [ ] Mobile responsiveness
- [ ] Accessibility (ARIA labels, keyboard navigation)

---

## Version History

**Current Version:** 0.2.0-alpha

**Changelog:**

### v0.2.0-alpha (Current)

- ✅ Knowledge Infrastructure complete (Vector DB + RAG)
- ✅ Initialization Protocol with democratic country naming
- ✅ Tool Creation Service with approval workflow
- ✅ Multi-channel integration (WhatsApp, Telegram)
- ✅ Agent Orchestrator with constitutional context injection
- 🚧 Constitutional Guard (needs semantic enhancement)
- 🚧 Voting Service (needs frontend integration)

### v0.1.0-alpha (Initial)

- ✅ Foundation: PostgreSQL, Redis, Docker Compose
- ✅ Entity models: Agents, Constitution, Voting, Audit
- ✅ Basic frontend: Dashboard, Agent Tree, Task List
- ✅ Multi-provider AI model support

---

## Next Review Date

**Scheduled:** After Phase 6.2 (Critic Agents) completion

**Focus Areas:**

1. Verify critic veto authority working
2. Measure error catch rate (target 87.8%)
3. Test context isolation effectiveness
4. Benchmark performance under load

---

_Last Updated: 2026-02-12_  
_Maintainer: Ashmin Dhungana_  
_Status: Active Development - Phase 2 & 6 In Progress_

---

## Quick Reference: File Locations

### Backend Core

- Entity Models: `backend/models/entities/`
- Services: `backend/services/`
- API Routes: `backend/api/routes/`
- Core Logic: `backend/core/`

### Frontend

- Pages: `frontend/src/pages/`
- Components: `frontend/src/components/`
- Services: `frontend/src/services/`
- Stores: `frontend/src/store/`

### Configuration

- Docker: `docker-compose.yml`
- Environment: `.env`
- Requirements: `backend/requirements.txt`
- Package: `frontend/package.json`

---

# ✅ Final Verification & System Checklist

## 0. Rough Ideas (What to do and What to check)

1. Multi-Channel Integration (Messaging Platforms)
   Add support for WhatsApp, Telegram, Slack, Discord, Signal, Google Chat, iMessage, Microsoft Teams, Zalo, and Matrix to enable local-first AI agents across communication platforms.
   Priority order:
   Easy: Telegram, Discord, Slack (API-first)
   Moderate: WhatsApp (Baileys), Signal (signal-cli), Google Chat, Matrix
   Hard: iMessage (macOS only), Microsoft Teams (enterprise complexity), Zalo (limited API)
   Architecture: Map each channel to Task Agents (3xxxx) under a "Communications Council" Lead Agent (2xxxx).

## 1. Access & Permissions

- Verify that the **Head of Council** has full system access.
- Verify **Browser Control** functionality.

## 2. System Testing

- Perform complete system testing.
- Ensure all modules and workflows are functioning correctly.

## 3. Memory Management

### Database & Vector Database

- Implement proper memory management.
- Delete very old data records and outdated data versions.
- **Do NOT delete the original constitution.**

### Additional Requirements

- Tools to connect to the MCP server.
- Automatic fallback system:
  - Switch to the next available API key if the current API key fails.
- Send notifications if **none of the API keys** respond:
  - In the frontend.
  - In running/background channels.

## 4. Ethos & Message History Management

- Verify that message history is stored and accessed correctly.
- The message history represents the **Ethos** and must:
  - Be updated
  - Be editable
  - Be minimized/summarized for efficiency

### Ethos Update Workflow

1. Read the Constitution.
2. Update individual Ethos.
3. While working:
   - Log what the agent is doing.
   - Log what has been completed.
   - Log what remains.
4. Apply this workflow to all agents.

## 5. API Request Validation

- Ensure that the **Ethos content is always included** in every API request.

**End of Roadmap**

Memory optimization:

1. Older chats will be removed after a certain period of time. i.e 7 days
2. A database of all tasks that were assigned by user and what were complited will be stored in database
3. The database of all tasks that are complited will be removed after a certain period of time. i.e 7 days (expection: The orginal constitution that was stored will not be removed in any way)
4. The vector database will be optimized, old knowledge will be viewed and kept uptodate and dublicated will be removed.
5. New tasks will not be assigned to the agent if the agent is not available.
6. Optimizatin of all system without loos of functionality, and loss of imported information.
