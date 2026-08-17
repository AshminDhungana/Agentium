# Design Spec: Key Entity Models Verification (TODO §3.3)

> **Purpose**: Comprehensive verification of all 10 key entity models in the Agentium system
> **Scope**: Unit tests + Integration tests for model behavior, persistence, relationships, and state machines
> **Related**: TODO.md §3.3, Database & Migrations section

---

## 1. Overview

This spec defines the test strategy for verifying all 10 key entity models listed in TODO §3.3:

| # | Model Group | Models | TODO Items |
|---|-------------|--------|------------|
| 1 | Governance | `Agent`, `Constitution`, `Ethos`, `Voting`/`VoteRecord`/`Proposal` | 3.3.1, 3.3.3, 3.3.8 |
| 2 | Task & Scheduling | `Task`, `ScheduledTask`, `Checkpoint`, `Workflow` | 3.3.2, 3.3.6, 3.3.7 |
| 3 | User & Audit | `User`/`UserModelConfig`/`UserPreference`, `AuditLog`/`ViolationReport` | 3.3.4, 3.3.5 |
| 4 | Tool & Channel | `MCPTool`/`ToolVersion`/`ToolStagingArea`, `Channel`/`ChannelMessage` | 3.3.9, 3.3.10 |

**Verification Level**: Both unit tests (model logic, state machines) + integration tests (DB persistence, FK constraints, cascades)

---

## 2. Architecture Decisions

### 2.1 Test Organization: Domain-Grouped (4 Test Files)

```
backend/tests/
├── unit/models/
│   ├── test_governance_models.py
│   ├── test_task_scheduling_models.py
│   ├── test_user_audit_models.py
│   └── test_tool_channel_models.py
└── integration/models/
    ├── test_governance_integration.py
    ├── test_task_scheduling_integration.py
    ├── test_user_audit_integration.py
    └── test_tool_channel_integration.py
```

**Rationale**: 
- Clear separation by system domain
- Shared fixtures per domain (e.g., governance fixtures: sample_agent, sample_constitution)
- Parallel execution across domains in CI
- Easy to navigate and maintain

### 2.2 Test Patterns

| Pattern | Applied To |
|---------|-----------|
| **State Machine Tests** | All models with status enums (Agent, Task, ScheduledTask, Channel, AmendmentVoting, TaskDeliberation) |
| **CRUD + Relationship Tests** | All models with foreign keys |
| **Immutability Tests** | `AuditLog`, `ConstitutionViolation` (verify no UPDATE/DELETE possible) |
| **Serialization Tests** | All `to_dict()` methods |
| **Factory/Builder Tests** | Models with `__init__` logic (ID generation, auto-fields) |
| **Domain Logic Tests** | Business methods: `spawn_child()`, `cast_vote()`, `calculate_next_run()`, `compress_ethos()`, etc. |

---

## 3. Detailed Test Coverage

### 3.1 Governance Models (`test_governance_models.py`)

#### 3.1.1 Agent Model
**Unit Tests:**
- All 8 statuses: `INITIALIZING` → `ACTIVE` → `WORKING`/`DELIBERATING`/`REVIEWING` / `IDLE_WORKING`/`IDLE_PAUSED` → `SUSPENDED`/`TERMINATED`
- Status transition validation (invalid transitions raise `ValueError`)
- Tier-based `spawn_child()` permissions:
  - `HEAD_OF_COUNCIL` (0xxxx) → can spawn `COUNCIL_MEMBER` (1xxxx)
  - `COUNCIL_MEMBER` → cannot spawn
  - `LEAD_AGENT` (2xxxx) → can spawn `TASK_AGENT` (3xxxx–6xxxx)
  - `TASK_AGENT` → cannot spawn
  - Critics (7xxxx–9xxxx) → cannot spawn
- Agent ID generation per tier (0xxxx–9xxxx format validation)
- `pre_task_ritual()` / `post_task_ritual()` constitutional alignment flow
- `compress_ethos()` LLM path + Python fallback
- `read_and_align_constitution()` with graceful file fallback
- `get_system_prompt()` includes constitution + ethos + idle mode
- Hierarchical relationships: `parent` / `subordinates` backrefs

**Integration Tests:**
- Persist agent with linked `Ethos` (FK `ethos_id`)
- Parent/child FK constraint (ondelete='RESTRICT')
- Agentium ID uniqueness per tier
- Constitutional version tracking (`constitution_version`, `constitution_read_count`)

#### 3.1.2 Constitution Model
**Unit Tests:**
- `get_articles_dict()` normalizes string → `{title, content}` dict
- `get_prohibited_actions_list()` JSON parsing
- `get_sovereign_preferences()` JSON parsing
- Amendment chain traversal: `get_amendment_chain()`
- `archive()` sets `archived_date` and `is_active=False`
- Version numbering: `v1.0.0` format + sequential `version_number`

**Integration Tests:**
- Active constitution query (`is_active=True` + latest `effective_date`)
- `replaces_version` / `replaced_by` self-referential relationships
- `AmendmentVoting` → `Constitution` backref (`voting_sessions`)

#### 3.1.3 Ethos Model
**Unit Tests:**
- Working memory fields: `current_objective`, `active_plan`, `constitutional_references`, `task_progress_markers`, `reasoning_artifacts`, `outcome_summary`, `lessons_learned`
- JSON serialization methods: `get_*/set_*` for all fields
- `add_lesson_learned()` keeps last 20 entries
- `verify()` / `increment_version()` flow
- **LLM Compression** (`build_compression_payload()`, `apply_llm_compression()`):
  - 75/25 strategy for artifacts/lessons
  - Constitutional ref deduplication
  - Outcome summary (25% readable snapshot)
  - Word count guard (≥50 words)
- **Python Fallback** (`prune_obsolete_content()`):
  - Same 75/25 heuristic
  - `_compress_reasoning_artifacts()`, `_compress_lessons_learned()`, `_deduplicate_constitutional_references()`

**Integration Tests:**
- Ethos ↔ Agent FK (`agent_id`, `ethos_id`)
- `constitutional_references` JSON persistence
- Version increments on each update

#### 3.1.4 Voting Models
**Models:** `AmendmentVoting`, `TaskDeliberation`, `IndividualVote`, `VotingRecord`

**Unit Tests:**
- **AmendmentVoting:**
  - `cast_vote()` with eligibility check, revoke/replace logic
  - Quorum: ≥60% of eligible voters participate
  - Supermajority: ≥66% FOR votes (configurable)
  - `conclude()` returns `{result, votes_for, votes_against}`
  - Discussion thread JSON append
- **TaskDeliberation:**
  - `cast_vote()` with `min_quorum` and `required_approvals`
  - Participation rate calculation
  - `emergency_override()` by Head of Council (bypasses voting)
  - Auto-updates linked `Task` status on conclude
- **IndividualVote:**
  - `change_vote()` tracks `original_vote` and `vote_changed`
  - Dual FK: `task_deliberation_id` OR `amendment_voting_id` (check constraint)
- **VotingRecord:**
  - `generate_for_period()` aggregates votes by agent/time

**Integration Tests:**
- Vote persistence with council member FKs
- AmendmentVoting → Constitution link (`amendment_id`)
- TaskDeliberation → Task link (`task_id` + `deliberation_id` backref)
- IndividualVote backrefs to `Agent.votes_cast`

---

### 3.2 Task & Scheduling Models (`test_task_scheduling_models.py`)

#### 3.2.1 Task Model
**Unit Tests:**
- **All 15 Statuses:** `PENDING` → `DELIBERATING` → `APPROVED`/`REJECTED` → `DELEGATING` → `ASSIGNED` → `IN_PROGRESS` → `REVIEW` → `COMPLETED` / `FAILED` / `RETRYING` / `ESCALATED` / `STOPPED` / `WAITING` + IDLE states (`IDLE_PENDING`/`IDLE_RUNNING`/`IDLE_PAUSED`/`IDLE_COMPLETED`)
- **State Machine:** `TaskStateMachine.validate_transition()` rejects invalid transitions
- `set_status()` emits `TaskEvent` + triggers `CheckpointService` at phase boundaries
- **Governance Flow:**
  - `start_deliberation()` creates `TaskDeliberation`
  - `approve_by_council()` / `approve_by_head()` / `delegate_to_lead()`
  - `assign_to_task_agents()` runs fast `pre_task_ritual()`
  - `complete()` triggers `post_task_ritual()` (ethos execution)
- **Self-Healing:** `fail()` → `RETRYING` (up to `max_retries=5`) → `ESCALATED`
- **Provider Exhaustion:** `mark_failed(reason)` with structured `failure_reason` enum
- `acceptance_criteria` (JSON) + `veto_authority` (code/output/plan)
- `complexity_score` (1-10) + `delegation_metadata` for DecisionEngine traceability

**Integration Tests:**
- Full governance flow: Task → Deliberation → Council Vote → Head Approval → Lead Delegation → Task Agent Assignment → Execution → Completion
- Parent/child tasks (`parent_task_id`, `SubTask` relationship)
- Workflow linkage: `workflow_id`, `context_data`, `celery_task_id`
- Decision correlation: `decision_id` → `AuditLog.correlation_id`

#### 3.2.2 ScheduledTask Model
**Unit Tests:**
- Cron expression validation (`@daily`, `@hourly`, 5-part cron)
- `calculate_next_run()` using `croniter` (fallback if not installed)
- `mark_running(agent_id)` / `mark_completed(success)` state transitions
- `pause()` / `resume()` with next_run recalculation
- Rxxxx ID generation (format validation)
- Owner always Head 00001 (`owner_agentium_id`)
- Failure count tracking, `max_retries` → `ERROR` status

**Integration Tests:**
- `ScheduledTaskExecution` history (FK, ordering by `started_at.desc()`)
- Celery beat schedule integration (verify task appears in beat schedule)
- Executing agent relationship (ephemeral 3xxxx Task Agent)

#### 3.2.3 Checkpoint Model (`ExecutionCheckpoint`)
**Unit Tests:**
- Phase enum: `PLAN_APPROVED`, `EXECUTION_COMPLETE`, `CRITIQUE_PASSED`, `MANUAL`, `WAIT_ENTERED`
- Branching: `parent_checkpoint_id` + `branch_name`
- Serialization: `agent_states` (JSON), `artifacts` (JSON list), `task_state_snapshot` (JSON)
- Checkpoint ID format: `C{session}{HHMMSS}{hex4}`

**Integration Tests:**
- Save/restore cycle via `CheckpointService`
- Task linkage (`task_id` FK)
- Parent/child checkpoint tree traversal

#### 3.2.4 Workflow Models
**Models:** `Workflow`, `WorkflowExecution`, `WorkflowStep`, `WorkflowVersion`, `WorkflowSubTask`

**Unit Tests:**
- `WorkflowStepType`: `TASK`, `CONDITION`, `PARALLEL`, `HUMAN_APPROVAL`, `DELAY`, `WAIT_POLL`
- DAG validation: `on_success_step` / `on_failure_step` form valid graph
- `WorkflowExecution` status: `PENDING` → `RUNNING` → `PAUSED` / `COMPLETED` / `FAILED` / `COMPLETED_WITH_ERRORS`
- Version history: `WorkflowVersion` snapshots on edit
- `WorkflowSubTask`: `depends_on` (JSON array) for dependency DAG, `celery_task_id` for tracking

**Integration Tests:**
- `WorkflowExecutor` runs DAG steps in order (parallel branches concurrent)
- Celery `workflow_tasks.py` integration
- Execution `context_data` persistence across steps
- Visual DAG data structure in `template_json`

---

### 3.3 User & Audit Models (`test_user_audit_models.py`)

#### 3.3.1 User + UserModelConfig + UserPreference
**Unit Tests:**
- **User:**
  - Password: SHA-256 pre-hash + bcrypt (supports >72 byte passwords)
  - RBAC roles: `primary_sovereign`, `deputy_sovereign`, `observer`
  - `effective_role` property: `is_admin` → `primary_sovereign`, expiry check
  - Delegation chains: `delegated_by_id` → `delegations_granted`/`received`
  - `can_veto` / `is_sovereign` properties
- **UserModelConfig:**
  - 18 `ProviderType` enums (OPENAI, ANTHROPIC, GEMINI, GROQ, MISTRAL, COHERE, TOGETHER, FIREWORKS, PERPLEXITY, AI21, MOONSHOT, DEEPSEEK, QIANWEN, ZHIPU, AZURE_OPENAI, LOCAL, CUSTOM, OPENAI_COMPATIBLE)
  - `get_effective_base_url()` per provider (with defaults + explicit required list)
  - API key encryption/masking (`api_key_encrypted`, `api_key_masked`)
  - Usage tracking: `increment_usage()`, `record_spend()` (concurrency warning)
  - Cooldown logic: `record_failure()` → 3 failures → 5min cooldown + `ERROR` status
  - Monthly budget: `monthly_budget_usd` + `current_spend_usd` reset logic
- **UserPreference:** JSON storage, user-specific overrides

**Integration Tests:**
- UserCreation with hashed password + default role
- Sovereign configs (`user_id=NULL`) vs user-owned configs
- `ConnectionStatus` transitions: `TESTING` → `ACTIVE` / `ERROR`
- `last_login_at` updated on authentication

#### 3.3.2 AuditLog + ConstitutionViolation + SessionLog
**Unit Tests:**
- **AuditLog:**
  - Factory `log()` creates entry (does NOT persist - caller must `db.add()`)
  - `metadata_json` field (renamed from `metadata` to avoid SQLAlchemy conflict)
  - `correlation_id` groups related events
  - `parent_audit_id` for event chains
  - Shortcuts: `system_log()`, `security_log()`
  - Indexes: `created_at`, `actor_id+action`, `level+category`, `correlation_id`
- **ConstitutionViolation:**
  - Violation types, severity, `blocked`/`auto_terminated`/`escalated_to`
  - Sovereign review: `mark_reviewed(decision, notes)` → `reviewed_by_sovereign`
  - `escalate(head_agentium_id)` alerts Head of Council
- **SessionLog:**
  - Activity tracking: `record_activity()`, `requests_count`, `tasks_created`, etc.
  - `is_active(timeout_seconds=3600)` idle detection
  - `end_session(reason)` termination
  - Audit linkage via `session_id` (FK to `AuditLog.session_id`)

**Integration Tests (Critical):**
- **Immutability Verification:** Attempt UPDATE/DELETE on `AuditLog` and `ConstitutionViolation` → should fail (DB constraint or ORM event)
- Query patterns: by `actor_id`, `action`, `target_type+target_id`, `correlation_id`, `created_at` range
- `AuditLog` ↔ `SessionLog` bidirectional linkage

---

### 3.4 Tool & Channel Models (`test_tool_channel_models.py`)

#### 3.4.1 MCPTool + ToolVersion + ToolStagingArea
**Unit Tests:**
- **MCPTool:**
  - Tier classification: `pre_approved` | `restricted` | `forbidden`
  - Status lifecycle: `pending` → `pending_vote` → `approved`/`rejected` → `revoked`/`disabled`
  - Constitutional article reference (`constitutional_article`)
  - Approval metadata: `approved_by_council`, `approval_vote_id`, `approved_at`, `approved_by`
  - Health tracking: `health_status` (healthy/degraded/down/unknown), `consecutive_failures`
  - Usage stats: `usage_count`, `last_used_at`
  - Audit log append: `audit_log` JSON array `[{agent_id, timestamp, input_hash, result}]`
- **ToolVersion:**
  - Immutable code snapshot per version
  - `is_active` singleton constraint (only one active per tool)
  - Rollback tracking: `is_rolled_back`, `rolled_back_from_version`
  - Approval linkage: `approved_by_voting_id`
- **ToolStagingArea:**
  - Status: `pending_approval` → `approved` → `activated` / `rejected` / `deprecated` / `sunset`
  - Requires vote: `requires_vote` + `voting_id`
  - Deprecation metadata: `deprecated_by`, `deprecation_reason`, `replacement_tool_name`
  - Version linkage: `current_version`

**Integration Tests:**
- MCPTool ↔ AmendmentVoting (constitutional approval flow)
- ToolVersion → ToolStagingArea version tracking
- Code snapshot persistence + rollback simulation

#### 3.4.2 Channel Models
**Models:** `ExternalChannel`, `ExternalMessage`, `ChannelMetrics`

**Unit Tests:**
- **ExternalChannel:**
  - 12 `ChannelType` enums (WHATSAPP, SLACK, TELEGRAM, EMAIL, DISCORD, SIGNAL, GOOGLE_CHAT, TEAMS, ZALO, MATRIX, IMESSAGE, CUSTOM)
  - Status: `PENDING` → `ACTIVE` / `ERROR` / `DISCONNECTED` / `ARCHIVED`
  - `generate_webhook_url(base_url)` format
  - Config JSON: credentials, rate limits, content filters
  - Routing: `default_agent_id`, `auto_create_tasks`, `require_approval`
- **ExternalMessage:**
  - Sender metadata + media URL + raw_payload JSON
  - Processing status: `received` → `processing` → `responded`
  - Response tracking: `response_content`, `responded_at`, `responded_by_agent_id`
  - Error retry: `error_count`, `last_error`
- **ChannelMetrics:**
  - Circuit breaker: `CLOSED` / `HALF_OPEN` / `OPEN`
  - `success_rate` property (derived)
  - Consecutive failures + rate limit hits tracking
  - Unique `channel_id` index for fast metric lookup

**Integration Tests:**
- Channel ↔ Message FK (cascade: channel delete → messages deleted)
- ChannelMetrics unique channel_id (one-to-one)
- Webhook delivery flow (ExternalChannel → ExternalMessage → Task creation)

---

## 4. Fixtures & Test Infrastructure

### 4.1 Unit Test Fixtures (`backend/tests/unit/models/conftest.py`)
```python
@pytest.fixture
def db_session():
    """In-memory SQLite session for fast unit tests"""

@pytest.fixture
def sample_head_of_council(db_session):
    """Agent with agentium_id='00001', HEAD_OF_COUNCIL type"""

@pytest.fixture
def sample_council_member(db_session, sample_head_of_council):
    """Agent with agentium_id='10001', COUNCIL_MEMBER type, parent=head"""

@pytest.fixture
def sample_lead_agent(db_session, sample_head_of_council):
    """Agent with agentium_id='20001', LEAD_AGENT type"""

@pytest.fixture
def sample_task_agent(db_session, sample_lead_agent):
    """Agent with agentium_id='30001', TASK_AGENT type"""

@pytest.fixture
def sample_constitution(db_session):
    """Active Constitution with articles, prohibited_actions, sovereign_preferences"""

@pytest.fixture
def sample_ethos(db_session, sample_task_agent):
    """Ethos linked to agent with working memory populated"""

@pytest.fixture
def sample_task(db_session, sample_council_member, sample_lead_agent, sample_task_agent):
    """Task in PENDING state with full governance fields"""
```

### 4.2 Integration Test Fixtures (`backend/tests/integration/models/conftest.py`)
```python
@pytest.fixture(scope="session")
def alembic_engine():
    """PostgreSQL test DB with all migrations applied"""

@pytest.fixture
def db_session(alembic_engine):
    """Real DB session with transaction rollback after each test"""

@pytest.fixture
def celery_app():
    """Celery test app configured with eager mode for synchronous task execution"""

@pytest.fixture
def celery_worker(celery_app):
    """Celery worker for testing async task execution"""
```

---

## 5. Implementation Phases

### Phase 1: Governance Models (Week 1)
- [ ] `test_governance_models.py` - Unit tests for Agent, Constitution, Ethos, Voting
- [ ] `test_governance_integration.py` - DB persistence, relationships
- [ ] Shared governance fixtures

### Phase 2: Task & Scheduling Models (Week 2)
- [ ] `test_task_scheduling_models.py` - Unit tests for Task, ScheduledTask, Checkpoint, Workflow
- [ ] `test_task_scheduling_integration.py` - Celery integration, full governance flows
- [ ] Shared task/scheduling fixtures

### Phase 3: User & Audit Models (Week 3)
- [ ] `test_user_audit_models.py` - Unit tests for User, UserModelConfig, AuditLog, ViolationReport
- [ ] `test_user_audit_integration.py` - Immutability verification, auth flows
- [ ] Shared user/audit fixtures

### Phase 4: Tool & Channel Models (Week 4)
- [ ] `test_tool_channel_models.py` - Unit tests for MCPTool, ToolVersion, ToolStaging, Channel
- [ ] `test_tool_channel_integration.py` - Marketplace flow, webhook delivery
- [ ] Shared tool/channel fixtures

### Phase 5: CI/CD Integration (Week 5)
- [ ] Add test files to pytest collection
- [ ] Configure coverage thresholds per module
- [ ] Document test patterns in CONTRIBUTING.md

---

## 6. Success Criteria

| Criterion | Target |
|-----------|--------|
| **Code Coverage** | ≥90% for model files in `backend/models/entities/` |
| **State Machine Coverage** | All valid transitions tested + 3 invalid transitions rejected per model |
| **Relationship Coverage** | All FKs tested for: create, read, cascade, constraint violation |
| **Immutability** | UPDATE/DELETE on AuditLog/ConstitutionViolation raises exception |
| **Serialization** | All `to_dict()` methods tested for completeness |
| **Integration Pass Rate** | 100% on clean test DB |
| **Execution Time** | Unit tests <30s, Integration tests <2min |

---

## 7. Dependencies & Prerequisites

| Dependency | Purpose |
|------------|---------|
| `pytest` | Test framework |
| `pytest-asyncio` | Async test support |
| `factory-boy` | Test data factories (optional) |
| `croniter` | ScheduledTask next_run calculation |
| `faker` | Random test data generation |
| PostgreSQL test container | Integration test DB (via testcontainers or docker-compose) |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Complex state machines hard to test exhaustively | Use parametrized transition matrix; focus on valid + 3 invalid per state |
| Celery integration tests flaky | Use `task_always_eager=True` for synchronous execution in tests |
| DB immutability hard to enforce at ORM level | Add DB-level triggers + verify in integration tests |
| Large test suite slows CI | Parallel execution by domain group; unit tests in-memory SQLite |
| Cross-model fixture dependencies | Define fixture hierarchy: constitution → ethos → agent → task |

---

## 9. Appendix: Model → Test Mapping

| Model | Unit Test File | Integration Test File |
|-------|---------------|----------------------|
| Agent | test_governance_models.py | test_governance_integration.py |
| Constitution | test_governance_models.py | test_governance_integration.py |
| Ethos | test_governance_models.py | test_governance_integration.py |
| AmendmentVoting | test_governance_models.py | test_governance_integration.py |
| TaskDeliberation | test_governance_models.py | test_governance_integration.py |
| IndividualVote | test_governance_models.py | test_governance_integration.py |
| VotingRecord | test_governance_models.py | test_governance_integration.py |
| Task | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| SubTask | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| ScheduledTask | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| ExecutionCheckpoint | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| Workflow | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| WorkflowExecution | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| WorkflowStep | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| WorkflowVersion | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| WorkflowSubTask | test_task_scheduling_models.py | test_task_scheduling_integration.py |
| User | test_user_audit_models.py | test_user_audit_integration.py |
| UserModelConfig | test_user_audit_models.py | test_user_audit_integration.py |
| UserPreference | test_user_audit_models.py | test_user_audit_integration.py |
| AuditLog | test_user_audit_models.py | test_user_audit_integration.py |
| ConstitutionViolation | test_user_audit_models.py | test_user_audit_integration.py |
| SessionLog | test_user_audit_models.py | test_user_audit_integration.py |
| MCPTool | test_tool_channel_models.py | test_tool_channel_integration.py |
| ToolVersion | test_tool_channel_models.py | test_tool_channel_integration.py |
| ToolStagingArea | test_tool_channel_models.py | test_tool_channel_integration.py |
| ExternalChannel | test_tool_channel_models.py | test_tool_channel_integration.py |
| ExternalMessage | test_tool_channel_models.py | test_tool_channel_integration.py |
| ChannelMetrics | test_tool_channel_models.py | test_tool_channel_integration.py |

---

*End of Design Spec*