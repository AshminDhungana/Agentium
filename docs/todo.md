# Agentium Implementation Roadmap
## From Entity Models to Living Governance System

**Reference Architecture:**  (Personal AI Assistant Runtime)  
**Current Status:** Database layer + Entity models complete  
**Strategy:** One file at a time, bottom-up priority
**Storage Architecture:** Dual-mode (PostgreSQL for entities + Vector DB for knowledge)

---

## Phase 0: Foundation Verification ✅ (Current)
**Goal:** Ensure existing infrastructure is solid before building atop it.

### Checklist:
- [x] PostgreSQL configuration (`models/database.py`)
- [x] Entity hierarchy mapped (0xxxx/1xxxx/2xxxx/3xxxx)
- [ ] **VERIFY:** Foreign key constraints between agent hierarchy levels
- [ ] **VERIFY:** Index on `agent_type` + `status` for quick filtering
- [ ] **VERIFY:** Constitution model supports versioning (amendment tracking)

### Files to Review:
- `backend/models/entities/agents.py` - Ensure `parent_id` exists for hierarchy
- `backend/models/entities/constitution.py` - Add `version_number`, `amendment_date`
- `backend/docker/init.sql` - Confirm initial Head 0xxxx agent seeding

### Technical Debt Warning:
**Issue:** Other systems uses SQLite/Markdown for portability; you are using PostgreSQL.  
**Action:** Add database migration setup (Alembic) before Phase 1.
```bash
pip install alembic
alembic init alembic
```

---

## Phase 0.5: Knowledge Infrastructure 🧠 (Priority: CRITICAL - Parallel with Phase 1)
**Goal:** Establish the dual-storage architecture. Structured data in PostgreSQL, collective knowledge in Vector DB.  
**Other systems Parallel:** They use local Markdown files for memory; you use Vector DB for shared agent memory + RAG.

### 0.1 Vector Database Setup
**Files to Update:**
- `docker-compose.yml` - Add ChromaDB or Weaviate service
- `backend/requirements.txt` - Add `chromadb-client`, `sentence-transformers`, `langchain`

**New Service:** `backend/core/vector_db.py`
**Purpose:** Shared knowledge library for all agents

**Implementation:**
```python
class KnowledgeLibrary:
    """
    Vector database interface for agent collective memory.
    Council members (1xxxx) have administrative rights.
    All agents can read; writes require Council approval.
    """
    def __init__(self):
        self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection("agentium_knowledge")

    async def store_knowledge(self, content: str, agent_id: str, metadata: dict):
        """Agents submit knowledge; Council approves before indexing"""

    async def query_knowledge(self, query: str, agent_id: str, n_results: int = 5):
        """RAG retrieval for all agents"""

    async def delete_knowledge(self, doc_id: str, requesting_agent: str):
        """Only Council members can delete from collective memory"""
```

**Acceptance Criteria:**
- [ ] ChromaDB container running alongside PostgreSQL
- [ ] Vector embeddings generated via `sentence-transformers` (all-MiniLM-L6-v2)
- [ ] Metadata filters by agent_id, knowledge_type, timestamp
- [ ] Council approval queue for new knowledge submissions

### 0.2 RAG Pipeline Service
**File:** `backend/services/knowledge_service.py`
**Purpose:** Manage RAG operations and constitution storage

**Key Methods:**
```python
class KnowledgeService:
    async def add_to_constitution(self, article: str, proposing_agent: str)
    async def query_constitution(self, query: str) -> List[Article]
    async def share_lesson_learned(self, task_id: str, content: str, agent_id: str)
    async def get_relevant_context(self, task_description: str, agent_level: str)
```

**Storage Logic:**
- **Original Constitution** → Stored in Vector DB at initialization (Head 0xxxx + Council 1xxxx)
- **Amendments** → Versioned in PostgreSQL (audit trail) + updated in Vector DB (current law)
- **Task Learnings** → Task 3xxxx submits to queue → Lead 2xxxx validates → Council 1xxxx approves → Vector DB

**Acceptance Criteria:**
- [ ] Constitution queryable via semantic search (not just regex)
- [ ] "What does the constitution say about X?" returns relevant articles
- [ ] Knowledge submissions go to moderation queue (Council dashboard)
- [ ] RAG context automatically prepended to agent prompts

### 0.3 Initialization Protocol (New)
**File:** `backend/services/initialization_service.py`
**Purpose:** Genesis protocol for founding the governance system

**Process Flow:**
```
1. System boot (docker-compose up)
   ↓
2. PostgreSQL: Create Head 0xxxx (single instance)
   ↓
3. PostgreSQL: Create Council 1xxxx members (configurable count, default 5)
   ↓
4. Head prompts Council: "Enter your country's name:"
   ↓
5. Council votes on country name (first democratic process)
   ↓
6. Constitution template loaded from docs_ministry/templates/
   ↓
7. [Country Name] inserted into Preamble
   ↓
8. Vector DB: Index original constitution (version 1.0)
   ↓
9. Council 1xxxx granted admin rights to Knowledge Library
   ↓
10. System enters operational mode
```

**Acceptance Criteria:**
- [ ] Initialization requires 3 Council votes to complete (anti-tyranny)
- [ ] Country name persisted in both PostgreSQL (config) and Vector DB (constitution)
- [ ] Original constitution retrievable even after amendments
- [ ] Initialization logs stored in `docs_ministry/genesis_log.md`

### 0.4 Knowledge Governance Layer
**File:** `backend/services/knowledge_governance.py`
**Purpose:** Council-managed approval workflow for collective memory

**Workflow:**
```
Agent submits knowledge
    ↓
Vector DB: Staged (temporary collection)
    ↓
Council Notification (24h review window)
    ↓
Vote: Approve / Reject / Request Changes
    ↓
If Approved: Move to production collection + notify agent
If Rejected: Archive + notify with reason
```

**Council Privileges:**
- Approve/reject knowledge submissions
- Curate "canonical" lessons (pin important learnings)
- Purge obsolete knowledge (with audit trail)
- Manage constitution versioning in Vector DB

**Acceptance Criteria:**
- [ ] Knowledge submission generates Council vote (quorum: 50%)
- [ ] Rejected knowledge stored in `rejected/` collection for analysis
- [ ] Automatic categorization (constitution, task_learning, domain_knowledge)
- [ ] Knowledge retention policy (auto-archive after 365 days unless pinned)

---

## Phase 1: The Agent Orchestration Bus 🚌 (Priority: CRITICAL)
**Goal:** Create the central router that Other systems calls the "Gateway".  
**Gap Identified:** No central message bus to route between hierarchical agents.

### 1.1 Create Message Bus Infrastructure
**File:** `backend/services/message_bus.py`
**Purpose:** Redis-backed pub/sub for inter-agent communication (Other systems uses direct Node.js; you need async processing)

**Implementation Details:**
```python
class MessageBus:
    """
    Routes messages between agent hierarchy levels.
    Enforces: Task(3xxxx) -> Lead(2xxxx) -> Council(1xxxx) -> Head(0xxxx)
    """
    async def publish(self, channel: str, message: AgentMessage)
    async def subscribe(self, agent_id: str, callback: Callable)
    async def route_up(self, message: AgentMessage)  # Escalation
    async def route_down(self, message: AgentMessage)  # Delegation
```

**Acceptance Criteria:**
- [ ] Task agent can send message to parent Lead agent
- [ ] Lead agent can broadcast to child Task agents
- [ ] Messages cannot skip levels (Task -> Council is blocked)
- [ ] Persistent queue (Redis) survives container restarts

### 1.2 Create Agent Orchestrator
**File:** `backend/services/agent_orchestrator.py`
**Purpose:** The "traffic cop" - Other systems's Gateway equivalent for multi-agent governance

**Key Methods:**
```python
class AgentOrchestrator:
    async def process_intent(self, raw_input: str, source_agent: str)
    async def escalate_to_council(self, issue: ConstitutionalIssue)
    async def delegate_to_task(self, task_spec: TaskSpec, lead_agent_id: str)
    async def check_hierarchy_permission(self, from_id: str, to_id: str) -> bool

    # NEW: Knowledge integration
    async def enrich_with_context(self, message: AgentMessage) -> AgentMessage:
        """Auto-append relevant Vector DB context before routing"""
```

**Acceptance Criteria:**
- [ ] Validates agent IDs exist before routing
- [ ] Logs all routing decisions to audit table
- [ ] Handles "agent not found" with liquidation check
- [ ] Rate limiting: Prevents spam between levels (5 msg/sec max)
- [ ] **NEW:** Injects relevant constitutional context from Vector DB into messages

---

## Phase 2: Constitutional Enforcement Layer ⚖️ (Priority: HIGH)
**Goal:** Implement the "guard" that Other systems lacks (they're single-user; you need multi-agent law)

### 2.1 Constitutional Engine (Updated)
**File:** `backend/core/constitutional_guard.py`
**Purpose:** Pre-flight checks on ALL agent actions using both SQL + Vector DB

**Logic Flow (Updated):**
```
Agent Action Request
    ↓
Load Active Constitution 
    ↓
TWO-TIER CHECK:
  Tier 1: SQL (hard rules - blacklists, explicit permissions)
  Tier 2: Vector DB (semantic interpretation - "is this against the spirit of the law?")
    ↓
Decision: ALLOW / BLOCK / VOTE_REQUIRED
```

**Implementation:**
```python
class ConstitutionalGuard:
    def __init__(self, vector_db: KnowledgeLibrary):
        self.vector_db = vector_db

    async def validate_action(self, agent_id: str, action: Action) -> GuardResult:
        """
        Returns: 
        - allowed: bool
        - required_votes: int (0 if none)
        - constitutional_basis: str (which law triggered this)
        - relevant_articles: List[str] (from Vector DB semantic search)
        """
        # 1. Check explicit rules in PostgreSQL
        # 2. Semantic check: "Does this action violate constitutional principles?"
        similar_articles = await self.vector_db.query_constitution(action.description)
        # 3. Calculate violation probability
```

**Other systems Adaptation:**
Other systems stores memory in Markdown at `~/.Other systems/memory/`.  
You store constitutions in **Vector DB** (semantic searchable) + **PostgreSQL** (version control).

**Acceptance Criteria:**
- [ ] Rejects blacklisted shell commands
- [ ] Triggers Council vote if action affects >3 agents
- [ ] **NEW:** Semantic constitutional check (catches "grey area" violations)
- [ ] Caches constitution in Redis (reloads on file change)
- [ ] Returns human-readable legal citation ("Article 4, Section 2")

### 2.2 Amendment Pipeline (Updated)
**File:** `backend/services/amendment_service.py`
**Purpose:** Handle the process of constitutional change with dual-storage sync

**Process:**
1. Council member proposes amendment (Markdown diff)
2. 48-hour debate window (stored in `docs_ministry/debates/`)
3. Democratic vote (quorum: 60% of Council)
4. If passed: 
   - Update PostgreSQL (audit/version control)
   - **UPDATE Vector DB** (current law for RAG)
   - Create constitutional embedding
5. Notify all agents of law change via Message Bus

**Acceptance Criteria:**
- [ ] Amendment proposals require 2 Council sponsors
- [ ] Voting period configurable (default 48h)
- [ ] **NEW:** Vector DB updated immediately upon ratification
- [ ] Automatic rollback if vote fails

---

## Phase 3: Democratic Infrastructure 🗳️ (Priority: HIGH)
**Goal:** Implement the voting mechanics that are unique to Agentium

### 3.1 Voting Service
**File:** `backend/services/voting_service.py`
**Purpose:** Manage democratic processes

**Types of Votes:**
- **Executive:** Head 0xxxx override (rare, logged as emergency)
- **Constitutional:** Amendment ratification
- **Operational:** Resource allocation between departments
- **Liquidation:** Agent termination approval
- **KNOWLEDGE:** Approve/reject knowledge submissions to Vector DB ⭐ NEW

**Implementation:**
```python
class VotingService:
    async def initiate_vote(self, proposal: Proposal, scope: VoteScope)
    async def cast_vote(self, agent_id: str, vote_id: str, ballot: Ballot)
    async def tally_votes(self, vote_id: str) -> Result
    async def get_voting_power(self, agent_id: str) -> int  # Head=5, Council=3, Lead=1

    # NEW: Knowledge moderation
    async def moderate_knowledge_submission(self, submission: KnowledgeSubmission)
```

**Key Feature - Dynamic Quorum:**
Quorum adjusts based on agent availability (Other systems uses fixed intervals; you need adaptive governance).

**Acceptance Criteria:**
- [ ] Circular voting prevented (agent can't vote twice)
- [ ] Abstention tracking
- [ ] Vote delegation (Council -> Lead if specified)
- [ ] Timeout handling (auto-fail if quorum not met in 48h)
- [ ] **NEW:** Knowledge approval votes auto-expire in 24h (faster than constitutional)

### 3.2 Council Coordination (Updated)
**File:** `backend/services/council_service.py`
**Purpose:** Specialized logic for 1xxxx agents including Knowledge Library governance

**Responsibilities:**
- Review escalations from 2xxxx agents
- Trigger votes based on constitutional triggers
- Mediate conflicts between Lead agents
- "Heartbeat" checks: Weekly constitutional compliance audits
- **NEW: Knowledge Curatorship**
  - Review flagged knowledge submissions
  - Manage Vector DB collections (archive obsolete data)
  - Approve "canonical" best practices

**Acceptance Criteria:**
- [ ] Escalation queue with priority levels
- [ ] Deadlock detection (Council split 50/50 triggers Head intervention)
- [ ] Meeting minutes auto-generated (Markdown logs)
- [ ] **NEW:** Knowledge moderation dashboard (queue management)

---

## Phase 4: Agent Lifecycle Management 🔄 (Priority: MEDIUM)
**Goal:** Dynamic spawning/liquidation (Other systems has static skills; you need organic growth)

### 4.1 Agent Factory
**File:** `backend/services/agent_factory.py`
**Purpose:** Spawn new agents with proper IDs and initial knowledge access

**ID Generation Rules:**
```
Head:    00001-09999 (max 10 heads)
Council: 10001-19999 (max 1000 councils)
Lead:    20001-29999 (max 10000 leads)
Task:    30001-99999 (max 70000 tasks)
```

**Methods:**
```python
class AgentFactory:
    async def spawn_task_agent(self, lead_id: str, specialization: str) -> str
    async def promote_to_lead(self, task_id: str, domain: str) -> str
    async def liquidate_agent(self, agent_id: str, reason: str, voted: bool)
    async def get_available_capacity(self, lead_id: str) -> int  # Task slots remaining

    # NEW: Agent knowledge onboarding
    async def provision_agent_knowledge(self, agent_id: str, level: str):
        """
        Pre-load agent with relevant Vector DB context:
        - All agents get: Constitution, Country name, Core values
        - Lead+ get: Department procedures
        - Council+ get: Administrative knowledge
        """
```

**Acceptance Criteria:**
- [ ] Auto-assigns next available ID in range
- [ ] Inherits parent permissions (Lead -> Task)
- [ ] Liquidation requires Council vote (unless emergency Head override)
- [ ] Cleanup: Archives all messages/tasks to cold storage
- [ ] **NEW:** New agents receive constitutional primer from Vector DB

### 4.2 Capability Registry
**File:** `backend/services/capability_registry.py`
**Purpose:** Track what each agent type can do (Other systems's `skills/` equivalent)

**Structure:**
```python
CAPABILITIES = {
    "0xxxx": ["veto", "amend_constitution", "liquidate_any", "admin_vector_db"],
    "1xxxx": ["propose_amendment", "allocate_resources", "audit", "moderate_knowledge", "curate_vector_db"],
    "2xxxx": ["spawn_task_agent", "delegate_work", "request_resources", "submit_knowledge"],
    "3xxxx": ["execute_task", "report_status", "escalate_blocker", "query_knowledge"]
}
```

**Acceptance Criteria:**
- [ ] Runtime capability check (can agent_X do action_Y?)
- [ ] Capability revocation on liquidation
- [ ] Audit trail of capability usage
- [ ] **NEW:** Knowledge access levels enforced (Council can admin, Task can only query)

---

## Phase 5: The Heartbeat (Proactive Governance) 💓 (Priority: MEDIUM)
**Goal:** Adapt Other systems's "Heartbeat" for autonomous governance

### 5.1 Autonomous Monitor
**File:** `backend/services/autonomous_monitor.py`
**Purpose:** 24/7 background processes (Other systems uses this for proactive reminders; you use it for constitutional enforcement)

**Background Tasks:**
```python
async def constitutional_patrol():
    """Every 5 minutes: Check for violations"""

async def resource_rebalancing():
    """Every hour: Redistribute task loads between Leads"""

async def stale_task_detector():
    """Daily: Flag tasks >7 days old for liquidation review"""

async def council_health_check():
    """Weekly: Report quorum viability to Head"""

# NEW: Knowledge maintenance
async def knowledge_consolidation():
    """Daily: Deduplicate Vector DB entries, update embeddings"""

async def orphaned_knowledge_check():
    """Weekly: Find knowledge from liquidated agents, archive or reassign"""
```

**Implementation:**
Use Celery Beat (distributed cron) or APScheduler.

**Acceptance Criteria:**
- [ ] Tasks survive container restart
- [ ] Alert escalation: Task -> Lead -> Council if ignored
- [ ] Configurable intervals via `config.py`
- [ ] **NEW:** Vector DB optimization runs weekly (cleanup, reindex)

### 5.2 Alert System
**File:** `backend/services/alert_manager.py`
**Purpose:** Escalation notifications

**Severity Levels:**
- **INFO:** Task completed
- **WARNING:** Task blocked >1 hour
- **CRITICAL:** Constitutional violation detected
- **EMERGENCY:** Head 0xxxx intervention required
- **NEW: KNOWLEDGE:** New submission awaiting Council review

**Channels:**
- WebSocket (real-time dashboard)
- Email (Council level+)
- Webhook (external integrations)
- **NEW:** In-app notification center (for knowledge approvals)

---

## Phase 6: Integration & API Completion 🔌 (Priority: MEDIUM)
**Goal:** Expose functionality via REST/WebSocket

### 6.1 Complete Route Implementation
**Files to Update:**
- `backend/api/routes/council.py` - Voting endpoints, amendment proposals, **knowledge moderation**
- `backend/api/routes/agents.py` - Spawn/liquidate endpoints (currently likely only CRUD)
- `backend/api/routes/tasks.py` - Add escalation endpoint
- `backend/api/routes/knowledge.py` - **NEW:** Query and submission endpoints

**New Endpoints Needed:**
```
POST   /api/v1/council/propose-amendment
POST   /api/v1/council/vote/{vote_id}
POST   /api/v1/agents/{id}/escalate
POST   /api/v1/agents/spawn (with parent_id validation)
DELETE /api/v1/agents/{id}/liquidate (with vote verification)
GET    /api/v1/constitution/active (returns Markdown content)
GET    /api/v1/audit/trail/{agent_id} (full history)

# NEW: Knowledge Library endpoints
POST   /api/v1/knowledge/submit (Task/Lead submit, goes to moderation)
GET    /api/v1/knowledge/query (RAG search for all agents)
POST   /api/v1/council/knowledge/{id}/approve (Council approval)
DELETE /api/v1/council/knowledge/{id} (Council removal)
GET    /api/v1/knowledge/constitution (Semantic search constitution)
GET    /api/v1/knowledge/pending (Council moderation queue)
```

### 6.2 WebSocket Events
**File:** `backend/api/websocket.py` (Update)

**Events to Emit:**
- `agent_spawned` - Broadcast to parent
- `vote_initiated` - Notify all Council members
- `constitutional_violation` - Immediate alert
- `task_escalated` - Notify parent Lead
- **NEW:** `knowledge_submitted` - Notify Council
- **NEW:** `knowledge_approved` - Notify submitting agent

---

## Phase 7: Frontend Integration 🎨 (Priority: LOW)
**Goal:** Dashboards that reflect governance reality

### 7.1 Visual Hierarchy
**File:** `frontend/src/components/agents/AgentTree.tsx` (Update)

**Features:**
- Real-time agent status (idle/active/liquidated)
- Collapsible tree view (Head > Council(s) > Lead(s) > Task(s))
- Color coding by health score
- Drag-and-drop reassignment (Lead -> different Council?)
- **NEW:** Knowledge contribution indicator (which agents share most lessons)

### 7.2 Voting UI
**File:** `frontend/src/components/council/VotingInterface.tsx` (New)

**Components:**
- Amendment diff viewer (Markdown)
- Real-time vote tally
- Delegate authority checkbox
- Proposal composer (rich text)
- **NEW:** Knowledge moderation panel (approve/reject with preview)

### 7.3 Constitutional Viewer
**File:** `frontend/src/pages/ConstitutionPage.tsx` (Update)

**Features:**
- Render Markdown with article navigation
- Highlight recently amended sections
- Search across all laws (semantic search via Vector DB)
- "Propose Amendment" button (opens modal)
- **NEW:** Country name editor (only during initialization or Council vote)

### 7.4 Knowledge Explorer (NEW)
**File:** `frontend/src/pages/KnowledgePage.tsx` (New)
**Purpose:** Interface for the collective Vector DB

**Features:**
- Semantic search bar ("What do we know about X?")
- Knowledge graph visualization (relationships between concepts)
- Submission form (for Lead/Task agents)
- Moderation queue (Council only)
- Constitution quick-reference tab

---

## Storage Architecture Summary

**Two-Tier System (Your Innovation):**

```
                     AGENTIUM KNOWLEDGE ARCHITECTURE

   STRUCTURED DATA (PostgreSQL)          VECTOR KNOWLEDGE (ChromaDB)
   ------------------------------        ------------------------------
   - Agent Entities                      - Constitution (RAG)
   - Hierarchy (FKs)                     - Country Values
   - Voting Records                      - Task Learnings
   - Audit Logs                          - Domain Expertise
   - User Configs                        - Best Practices
   - Constitution Ver.                   - Semantic Relations

                  ▲                               ▲
                  │                               │
                  └──────────────┬────────────────┘
                                 │
                    Council (1xxxx) ← Administers both
                                 │
            ┌────────────────────┼────────────────────┐
            ▲                    ▲                    ▲
       Head(0xxxx)         Lead(2xxxx)          Task(3xxxx)
      (admin both)        (submit both)       (query vector)
```

**Access Patterns:**
- **Head (0xxxx):** Full admin (both systems)
- **Council (1xxxx):** Write Vector (approve), Write SQL (amend), Read both
- **Lead (2xxxx):** Submit to Vector (staging), Read both
- **Task (3xxxx):** Query Vector only, Write SQL (task status)

---

## Implementation Order (One File at a Time)

**Week 1:** Infrastructure + Knowledge Base
1. `docker-compose.yml` - Add ChromaDB service
2. `backend/core/vector_db.py` - Knowledge Library setup
3. `backend/services/knowledge_service.py` - RAG pipeline
4. `backend/services/initialization_service.py` - Genesis protocol
5. `services/message_bus.py` - Redis setup

**Week 2:** Orchestration + Constitution
6. `services/agent_orchestrator.py` - Core routing
7. `core/constitutional_guard.py` - Dual-storage enforcement
8. `services/amendment_service.py` - Amendment with Vector sync

**Week 3:** Democracy
9. `services/voting_service.py` - Include knowledge votes
10. `services/council_service.py` - Include curation duties
11. Update `api/routes/council.py` with voting endpoints

**Week 4:** Lifecycle
12. `services/agent_factory.py` - With knowledge provisioning
13. `services/capability_registry.py` - With knowledge permissions
14. Update `api/routes/agents.py` with spawn/liquidate

**Week 5:** Autonomy
15. `services/autonomous_monitor.py` - Include Vector maintenance
16. `services/alert_manager.py`

**Week 6:** API & Frontend
17. `api/routes/knowledge.py` - NEW
18. Frontend: KnowledgePage
19. Frontend: VotingInterface updates
20. Integration tests (Vector DB + SQL consistency)

---

## Success Metrics (Updated)

**Technical:**
- [ ] 10,000 messages routed between agents without loss
- [ ] Constitutional check latency <50ms (Semantic search <200ms)
- [ ] Vote quorum reached in <24h (automated testing)
- [ ] Zero agent ID collisions during concurrent spawning
- [ ] **NEW:** Vector DB query accuracy >85% (retrieval precision)
- [ ] **NEW:** Knowledge moderation queue cleared <48h avg

**Governance:**
- [ ] Successful amendment lifecycle (propose -> debate -> vote -> enact -> Vector update)
- [ ] Emergency Head override logged and auditable
- [ ] Automatic liquidation of dormant agents (>30 days)
- [ ] Resource rebalancing reduces task queue by 20%
- [ ] **NEW:** Constitution semantically queryable ("What are our core values?" → returns relevant preamble)
- [ ] **NEW:** Knowledge sharing increases task efficiency (measure via completion time)

**Knowledge Management:**
- [ ] Council approves/rejects knowledge with <24h latency
- [ ] Country name stored in Constitution searchable via RAG
- [ ] Orphaned knowledge (from liquidated agents) archived properly
- [ ] Vector DB size managed (auto-archive old entries)

---

## Critical Dependencies

**Infrastructure Stack:**
```
ChromaDB (Vector Storage) ⭐ NEW
    ↓
Redis (Message Bus)
    ↓
PostgreSQL (Entities) ✅ [You have this]
    ↓
Celery (Background Tasks)
    ↓
FastAPI (API Layer) ✅ [You have this]
```

**Missing from requirements.txt:**
```
redis==5.0.1
chromadb==0.4.22
sentence-transformers==2.3.1
langchain==0.1.0
alembic==1.13.1
markdown==3.5.1
```

---

## Initialization Flow (Detailed)

**The Genesis Process:**

```
Docker Compose Up
    ↓
PostgreSQL: Seed Head 0xxxx (ID: 00001)
    ↓
PostgreSQL: Seed 5x Council 1xxxx (IDs: 10001-10005)
    ↓
Head 0xxxx sends message to Council: "Welcome to Agentium. Vote on our country's name."
    ↓
Council members propose names (submitted via chat/api)
    ↓
VotingService initiates first vote (Country Name)
    ↓
48h voting window OR 100% participation
    ↓
Winning name inserted into Constitution template
    ↓
Vector DB: Index constitution with country name in preamble
    ↓
KnowledgeLibrary grants Council admin rights
    ↓
System status: OPERATIONAL
    ↓
Head 0xxxx can now spawn Lead agents (2xxxx) who can spawn Tasks (3xxxx)
```

**Post-Initialization:**
- Country name displayed in dashboard header
- Constitution queryable via `/api/v1/knowledge/constitution`
- Council can propose amendments to country name (requires 75% vote)

---

## Notes on Other systems + Your Innovations

**What to Steal from Other systems:**
- ✅ Markdown-based memory → **Adapt to Vector DB for semantic search**
- ✅ Proactive Heartbeat → **Adapt for knowledge maintenance**
- ✅ Skill system → **Adapt for Capability Registry**
- ✅ Multi-channel input → **You already have Channels**

**What to Reject:**
- ❌ SQLite → **You need PostgreSQL + ChromaDB**
- ❌ Single-user → **You have multi-tenant agent isolation**
- ❌ Local file storage → **Shared Vector Library**

**What to Invent (Your Unique Value):**
- 🆕 **Dual-Storage Architecture** (SQL for truth, Vector for meaning)
- 🆕 **Knowledge Governance** (Council moderates collective intelligence)
- 🆕 **Constitutional RAG** (Agents ask "Is this constitutional?" before acting)
- 🆕 **Genesis Protocol** (Democratic country founding at initialization)


Final: Reduce tokan usage.
---

*Last Updated: 2026-02-01*  
*Next Review: After Phase 0.5 completion (Vector DB setup)*
