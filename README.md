# 🏛️ Agentium

> A sovereign AI governance platform with constitutional law, democratic deliberation, and hierarchical agent orchestration

[![Status](https://img.shields.io/badge/status-active--development-brightgreen)](https://github.com/yourusername/agentium)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)

**Agentium** transforms AI task execution into a structured digital democracy. Unlike monolithic AI assistants, Agentium operates as a self-governing ecosystem where AI agents function like a parliamentary system—complete with a **Head of Council** (Executive), **Council Members** (Legislature), **Lead Agents** (Directors), and **Task Agents** (Executors)—all bound by a **Constitution** and managed through democratic voting.

Built for those who believe AI should be **transparent, accountable, and sovereign**, Agentium runs entirely on your infrastructure with local-first architecture.

---

## ✨ What Makes Agentium Unique?

### 🏛️ Democratic AI Governance
Tasks aren't just executed; they're deliberated. The Council votes on constitutional amendments, resource allocation, and major system changes. Every decision is logged, auditable, and reversible.

### ⚖️ Constitutional Framework
A living document stored that all agents can access. Agents literally ask *"Is this constitutional?"* before acting. Amendments require democratic approval.

### 🧠 Collective Intelligence (Knowledge Library)
- **Dual-Storage Architecture**: PostgreSQL for structured data, ChromaDB for semantic knowledge
- **Shared Memory**: Task agents share learnings; Council curates institutional knowledge
- **RAG-Powered**: World Knowledge retrieved via semantic search, not just regex

### 🏗️ Hierarchical Agent IDs
Rigorous identification system:
- **Head**: `0xxxx` (00001-00999) — The Sovereign's direct representative
- **Council**: `1xxxx` (10001-19999) — Democratic deliberation layer  
- **Lead**: `2xxxx` (20001-29999) — Department coordination
- **Task**: `3xxxx` (30001-99999) — Execution workers

### 🔄 Self-Governing Lifecycle
Agents auto-spawn when load increases, auto-terminate when tasks complete, and can be liquidated by Council vote if they violate the Constitution or remain idle >7 days.

---

## 🏗️ Architecture

### Dual-Storage Knowledge System

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENTIUM GOVERNANCE STACK                        │
└─────────────────────────────────────────────────────────────────────────┘

💬 Interface Layer
┌─────────────────────────────────────────────────────────────────────────┐
│  Web Dashboard (React + Vite)  │  WhatsApp  │  Telegram  │  Discord    │
│  ├─ Agent Tree Visualization   │  iMessage  │  Slack     │  API        │
│  ├─ Voting Interface           │            │            │             │
│  └─ Constitution Editor        │            │            │             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
⚡ Control Layer
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI Gateway  │  WebSocket Hub  │  Message Bus (Redis)              │
│  ├─ Agent Orchestrator              │  Hierarchical Routing             │
│  ├─ Constitutional Guard (AI + RAG) │  3xxxx→2xxxx→1xxxx→0xxxx          │
│  └─ Voting Service                  │  Persistent Queues                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
🏛️ Governance Layer                    💾 Storage Layer
┌─────────────────────────┐        ┌──────────────────────────────────────┐
│ 👑 Head (0xxxx)         │        │  PostgreSQL (Structured Truth)       │
│ ├─ Veto Power           │        │  ├─ Agent Entities (hierarchy FKs)   │
│ ├─ Emergency Override   │        │  ├─ Voting Records (tally, timestamp)│
│ └─ Genesis Protocol     │        │  ├─ Audit Logs (immutable trail)     │
│                         │        │  ├─ Constitution Versions (text)     │
│ ⚖️ Council (1xxxx)      │        │  └─ User Config                      │
│ ├─ Propose Amendments   │        │                                      │
│ ├─ Vote on Tasks        │        │  ChromaDB (Vector Meaning) ⭐        │
│ ├─ Knowledge Moderation │        │  ├─ Constitution (embeddings)        │
│ └─ Agent Liquidation    │        │  ├─ Country Values                  │
│                         │        │  ├─ Task Learnings (RAG)             │
│ 🎯 Lead (2xxxx)         │        │  ├─ Best Practices                   │
│ ├─ Spawn Task Agents    │        │  └─ Staged Knowledge                │
│ ├─ Validate Work        │        └──────────────────────────────────────┘
│ └─ Resource Allocation  │                         ▲
│                         │                         │
│ 🤖 Task (3xxxx)         │                         │
│ ├─ Execute Commands     │                         │
│ ├─ Submit Learnings     │                         │
│ └─ Query Knowledge      │                         │
└─────────────────────────┘                         │
                                                    │
🧠 Processing Layer                                 │
┌───────────────────────────────────────────────────┴──────────────────┐
│  Celery Workers  │  Constitutional Patrol  │  Knowledge Maintenance  │
│  ├─ Task Queue    │  (Heartbeat)            │  (Deduplication)        │
│  ├─ Vote Tally    │  Compliance Checks      │  Embedding Updates       │
│  └─ Lifecycle     │  Auto-termination       │  Orphaned Data Cleanup   │
└────────────────────────────────────────────────────────────────────────┘
```

### The Genesis Protocol (Initialization)

When Agentium boots for the first time:

```bash
1. Docker Compose initializes PostgreSQL + ChromaDB + Redis
2. Head of Council (0xxxx) is instantiated
3. 5 Council Members (1xxxx) are spawned
4. Head prompts Council: "What shall we name our Nation?"
5. Council votes (first democratic process)
6. Constitution template loaded with Country Name in preamble
7. Vector DB indexes the Constitution (semantic + full-text)
8. Knowledge Library grants Council admin rights
9. Status: OPERATIONAL — Ready to serve The Sovereign (You)
```

---

## 🗳️ Governance Mechanics

### 1. Constitutional Law (The Supreme Authority)

**Storage**: Dual-mode  
- **PostgreSQL**: Version control, amendment history, audit trail  
- **ChromaDB**: Semantic embeddings for RAG queries

**Access Control**:
- **Read**: All agents (via `query_constitution()`)
- **Amend**: Council proposal + 60% vote + Head ratification
- **Enforce**: Constitutional Guard checks every action against both SQL rules AND semantic interpretation

**Key Features**:
- Agents can ask: *"Does this violate Article 3 regarding data privacy?"*
- Semantic search catches "grey area" violations, not just explicit bans
- Daily review required by all governance tier agents (Head + Council)

### 2. Individual Agent Ethos

Every agent has a personalized Ethos document:
- Created by parent agent upon spawning using template
- Defines should/should-not rules for that agent's role
- Task agents: reviewed by Lead Agents
- Lead agents: reviewed by Head of Council
- Agents may query parent for clarification

### 3. Democratic Voting System

**Voting Powers**:
- Head (0xxxx): 5 votes + veto power
- Council (1xxxx): 3 votes each
- Lead (2xxxx): 1 vote (on operational matters only)

**When Voting Triggers**:
- Constitutional amendments
- Agent liquidation (termination)
- Knowledge Library submissions ( Task/Lead → Council approval)
- Resource allocation disputes
- Access permission changes across system scope boundaries

**Quorum Rules**:
- Constitutional: 60% of Council
- Operational: 50% of relevant tier
- Emergency: Head override (logged as constitutional violation if abused)

### 4. Agent Lifecycle & Termination

**Termination Conditions**:
- ✅ Task completed and confirmed by higher authority (Lead Agent)
- ❌ Constitutional violation (Council vote required)
- ⏰ Inactive >7 days (auto-liquidation)
- ⏰ Lifetime exceeded 30 days (max lifespan)
- 🛑 Head emergency override (rare, audited)

**Cleanup Process**:
1. Archive all messages/tasks to cold storage (PostgreSQL)
2. Transfer orphaned knowledge to Council curation queue
3. Revoke all capabilities
4. Mark as `liquidated` in registry (never reuse IDs)

---

## 🚀 Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended for local LLMs)
- 10GB free disk space

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentium.git
cd agentium

# Configure environment (optional)
cp .env.example .env
# Edit .env to add your API keys (OpenAI, Anthropic, etc.)

# Launch the governance system
docker-compose up --build

# Access the dashboard
open http://localhost:3000

# Default credentials
Username: admin
Password: admin
```

**Services Started**:
- `http://localhost:3000` — React Dashboard
- `http://localhost:8000` — FastAPI + WebSocket
- `localhost:6379` — Redis (Message Bus)
- `localhost:5432` — PostgreSQL (Entities)
- `localhost:8001` — ChromaDB (Vector Knowledge)

---

## 📖 Usage Guide

### 1. The Genesis (First Run)

Upon first login, you'll witness the **Initialization Protocol**:
1. The Head of Council greets you (The Sovereign)
2. Council is asked to propose names for your "Nation" (the system instance)
3. Vote executes (watch real-time tally in dashboard)
4. Constitution is ratified with your chosen name
5. System becomes operational

### 2. Daily Operations

**Submitting a Task**:
```
You (Sovereign) → Head (0xxxx): "Analyze Q3 financial reports"
    ↓
Head delegates to Council for resource check
    ↓
Council votes on resource allocation
    ↓
Lead Agent (2xxxx) spawns Task Agents (3xxxx)
    ↓
Execution with constitutional checks at each step
    ↓
Results aggregated back to Head → You
```

**Auto-Scaling in Action**:
- Load increases → Lead detects queue depth
- Lead requests Council approval for new Task Agents
- Council votes (automated if <5 seconds)
- New 3xxxx agents spawned, provisioned with knowledge from Vector DB
- When queue empties, oldest Task Agents liquidated
- Lead Agents can have other Lead Agents below them if task agent count increases.
- Lead agents can have many layers of Leads below them as per required.

### 3. Knowledge Management

**For Task Agents (3xxxx)**:
```python
# After completing task, submit learning
await knowledge_service.share_lesson_learned(
    task_id="task_30452",
    content="Q3 analysis shows vendor X delays correlate with Y metric",
    agent_id="30042"
)
# Goes to Council moderation queue
```

**For Council (1xxxx)**:
- Review pending knowledge submissions in dashboard
- Vote: Approve (add) / Reject (archived) / Request Changes
- Curate "canonical" best practices (pinned, never auto-archived)

**Querying Collective Intelligence**:
```python
# Any agent can query
context = await knowledge_service.query_constitution(
    "What are our data privacy obligations when handling financial records?"
)
# Returns relevant articles from Constitution via semantic similarity
```

---

## ⚙️ Configuration

### Model Configuration (`config/models.yaml`)

```yaml
head_of_council:
  model: gpt-4-turbo
  provider: openai
  temperature: 0.2  # Low for consistency

council_members:
  model: kimi-2.5
  provider: local
  count: 5  # Auto-scale up to 15

lead_agents:
  model: claude-3-sonnet
  provider: anthropic
  max_agents: 20

task_agents:
  model: gpt-3.5-turbo
  provider: openai
  max_agents: 100
  spawn_threshold: 10  # New agent per 10 queued tasks
```

### Storage Configuration (`config/storage.yaml`)

```yaml
postgresql:
  url: postgresql://agentium:secret@db:5432/agentium
  pool_size: 20

chromadb:
  host: chromadb
  port: 8001Multi-user RBAC
  collection_name: "agentium_knowledge"
  embedding_model: "all-MiniLM-L6-v2"

redis:
  host: redis
  port: 6379
  channels:
    - "agent_bus"
    - "council_chamber"
    - "emergency_alerts"Multi-user RBAC
```

### Constitutional Templates (`docs_ministry/templates/`)

- `constitution_sample.md` — Base legal framework
- `agent_ethos_sample.md` — Role-specific ethics templates
- `genesis_log.md` — Auto-generated initialization record

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Frontend** | React 18, TypeScript, Tailwind, Zustand | Dashboard, voting UI, agent tree |
| **API Gateway** | FastAPI, WebSocket, Pydantic | REST + real-time communication |
| **Message Bus** | Redis, Celery | Inter-agent routing, background tasks |
| **Structured Data** | PostgreSQL 15, SQLAlchemy, Alembic | Entity state, voting records, audit |
| **Vector Knowledge** | ChromaDB, Sentence-Transformers | RAG, constitution, ethos, learnings |
| **AI Models** | Local (Kimi, GPT4All) + API (OpenAI, Anthropic) | Agent intelligence |
| **Container** | Docker, Compose, Healthchecks | Cross-platform deployment |
| **Security** | JWT, OAuth2, AES-256 | Per-agent authentication |

---

## 📋 API Endpoints

### Governance
```
POST   /api/v1/council/propose-amendment
POST   /api/v1/council/vote/{vote_id}
GET    /api/v1/council/pending-votes
POST   /api/v1/council/knowledge/{id}/approve
```

### Agents
```
POST   /api/v1/agents/spawn              # With parent validation
POST   /api/v1/agents/{id}/escalate      # To parent tier
DELETE /api/v1/agents/{id}/liquidate     # Vote verification required
GET    /api/v1/agents/tree               # Hierarchy visualization
```

### Knowledge Library ⭐
```
POST   /api/v1/knowledge/submit          # Task/Lead submit
GET    /api/v1/knowledge/query           # RAG search
GET    /api/v1/knowledge/constitution    # Semantic search
GET    /api/v1/knowledge/pending         # Council moderation queue
DELETE /api/v1/knowledge/{id}            # Council only
```

### Constitution
```
GET    /api/v1/constitution/active       # Current markdown
GET    /api/v1/constitution/history      # Version history
POST   /api/v1/constitution/query        # Natural language query
```

---

## 🧪 Development Roadmap

### Phase 0: Foundation ✅ 
- [x] PostgreSQL entity models
- [x] Hierarchical ID system (0/1/2/3xxxx)
- [x] Docker compose setup

### Phase 1: Knowledge Infrastructure 🚧 **Current Focus**
- [ ] ChromaDB integration World Knowledge
- [ ] Knowledge Library service
- [ ] Initialization Protocol (Country naming)
- [ ] RAG pipeline World Knowledge

### Phase 2: Governance Core
- [ ] Message Bus (Redis)
- [ ] Agent Orchestrator
- [ ] Constitutional Guard 
- [ ] Voting Service with quorum logic

### Phase 3: Lifecycle Management
- [ ] Agent Factory (spawn/liquidate)
- [ ] Auto-scaling algorithms
- [ ] Capability Registry
- [ ] Automated termination (idle detection)

### Phase 4: Intelligence
- [ ] Multi-model provider support
- [] Browser automation integration
- [ ] Advanced RAG with source citations
- [ ] Voice interface 

### Phase 5: Ecosystem
- [ ] Plugin marketplace
- [ ] Scaling Workforce, Ministry, Law, Judiciary and more.
- [ ] Multi-user RBAC (multiple Sovereigns)
- [ ] Federation (inter-Agentium communication)
- [ ] Mobile apps

---

## 🤝 Contributing

Agentium is built for the community. We welcome:

- 🏛️ **Governance Models**: New voting algorithms, constitutional frameworks
- 🧠 **Knowledge Systems**: RAG improvements, embedding models
- 🔌 **Integrations**: New messaging channels, AI providers
- 📖 **Documentation**: Tutorials, constitutional examples
- 🐛 **Bug Reports**: Help us maintain integrity

Read our [Contributing Guide](CONTRIBUTING.md) and [Constitution Template](docs_ministry/templates/constitution_sample.md).

---

## 🛡️ Security & Ethics

- **Local-First**: Your data never leaves your infrastructure by default
- **Immutable Audit**: All votes, actions, and terminations logged to PostgreSQL
- **Principle of Least Privilege**: Task agents cannot spawn other agents
- **Constitutional Bounded**: Agents cannot override the Constitution without democratic process
- **Emergency Brakes**: Head can halt entire system; Council can veto Head with 75% vote
- **Individual Ethos**: Individual agents ethos must be removed after agent deletion or reassignment.
- **World Knowledge**: World knowledge must be updated and maintained regularly.

---

## 💬 Support & Community

- 📧 Email: **dhungana.ashmin@gmail.com**

---

## 📄 License

Apache License 2.0 — See [LICENSE](LICENSE) file

**Built with ❤️ and purpose by Ashmin Dhungana**

> *"The price of freedom is eternal vigilance. The price of AI sovereignty is democratic architecture."*
