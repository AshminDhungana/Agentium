# 🏛️ Agentium

> Your Personal AI Agent Nation (Secure and Reliable), which has a sovereign AI governance platform with constitutional law, democratic deliberation, and hierarchical agent orchestration

[![Status](https://img.shields.io/badge/status-active--development-brightgreen)](https://github.com/yourusername/agentium)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)

**Agentium** transforms AI task execution into a structured digital democracy. Unlike monolithic AI assistants, Agentium operates as a self-governing ecosystem where AI agents function like a parliamentary system—complete with a **Head of Council** (Executive), **Council Members** (Legislature), **Lead Agents** (Directors), **Task Agents** (Executors), and **Critic Agents** (Independent Judiciary)—all bound by a **Constitution** and managed through democratic voting.

Built for those who believe AI should be **transparent, accountable, and sovereign**, Agentium runs entirely on your infrastructure with local-first architecture.

## ![Image](./docs/dashboard.png)

## ✨ What Makes Agentium Unique?

### 🏛️ Democratic AI Governance

Tasks aren't just executed; they're deliberated. The Council votes on constitutional amendments, resource allocation, and major system changes. Every decision is logged, auditable, and reversible.

### ⚖️ Constitutional Framework

A living document stored that all agents can access. Agents literally ask _"Is this constitutional?"_ before acting. Amendments require democratic approval.

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
- **Code Critic**: `4xxxx` (40001-49999) — Code validation (syntax, security, logic)
- **Output Critic**: `5xxxx` (50001-59999) — Output validation (user intent alignment)
- **Plan Critic**: `6xxxx` (60001-69999) — Plan validation (DAG soundness)

> Critics operate **outside** the democratic chain. They have absolute veto authority but no voting rights. Rejected tasks retry within the same team (max 5 retries) before escalating to Council.

### 🔄 Self-Governing Lifecycle

Agents auto-spawn when load increases, auto-terminate when tasks complete, and can be liquidated by Council vote if they violate the Constitution or remain idle >7 days.

---

## 🏗️ Architecture

### Dual-Storage Knowledge System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AGENTIUM GOVERNANCE STACK                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 💬 Interface Layer                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Web Dashboard (React+Vite)      │  WhatsApp    Telegram                    │
│  ├─ Agent Tree Visualization     │  Discord     API                         │
│  ├─ Voting Interface              │  Slack                                   │
│  ├─ Critic Review Queue           │                                          │
│  └─ Constitution Editor           │                                          │
└───────────────────────────────────┴──────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ Control Layer                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  FastAPI Gateway    │  WebSocket Hub    │  Redis Message Bus                │
│  ├─ Agent Orchestrator                  │  Hierarchical Routing             │
│  ├─ Constitutional Guard                │  3x→2x→1x→0x Routing              │
│  ├─ Voting Service                      │  Persistent Queues                │
│  └─ Checkpoint Service                  │  Time-Travel Recovery             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
┌───────────────────────────────┐           ┌───────────────────────────────┐
│ 🏛️ Governance Layer            │           │ 💾 Storage Layer               │
├───────────────────────────────┤           ├───────────────────────────────┤
│                               │           │ PostgreSQL (Structured Truth) │
│ 👑 Head (0xxxx)               │           │ ├─ Agent Entities             │
│ ├─ Veto Power                 │           │ ├─ Voting Records             │
│ ├─ Emergency Override         │           │ ├─ Audit Logs                 │
│ ├─ Genesis Protocol           │           │ ├─ Constitution Versions      │
│ └─ Final Approval             │           │ ├─ Checkpoint States          │
│                               │           │ └─ User Config                │
│ ⚖️ Council (1xxxx)             │           │                               │
│ ├─ Propose Amendments         │           │ ChromaDB (Vector Meaning) ⭐  │
│ ├─ Vote on Tasks              │           │ ├─ Constitution (embeddings)  │
│ ├─ Knowledge Moderation       │           │ ├─ Country Values             │
│ ├─ Agent Liquidation          │           │ ├─ Task Learnings (RAG)       │
│ └─ Strategic Decisions        │           │ ├─ Best Practices             │
│                               │           │ └─ Staged Knowledge           │
│ 🎯 Lead (2xxxx)                │           └───────────────────────────────┘
│ ├─ Spawn Task Agents          │                         │
│ ├─ Delegate Work              │                         │
│ ├─ Resource Allocation        │                         │
│ └─ Aggregate Results          │                         │
│                               │                         │
│ 🤖 Task (3xxxx)                │                         │
│ ├─ Execute Commands           │                         │
│ ├─ Generate Code              │                         │
│ ├─ Submit Learnings           │                         │
│ └─ Query Knowledge            │                         │
└───────────────┬───────────────┘                         │
                │                                         │
                ▼                                         │
┌─────────────────────────────────────────────────────────┴───────────────────┐
│ 🔍 Execution Validation Layer                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐       │
│  │ 🔍 Plan Critic   │   │ 🔍 Code Critic   │   │ 🔍 Output Critic │       │
│  │    (6xxxx)       │   │    (4xxxx)       │   │    (5xxxx)       │       │
│  │                  │   │                  │   │                  │       │
│  │ Reviews:         │   │ Reviews:         │   │ Reviews:         │       │
│  │ • DAG Soundness  │   │ • Syntax         │   │ • User Intent    │       │
│  │ • Dependencies   │   │ • Security       │   │ • Acceptance     │       │
│  │ • Feasibility    │   │ • Logic Bugs     │   │   Criteria       │       │
│  │                  │   │ • API Misuse     │   │ • Completeness   │       │
│  │ Authority:       │   │                  │   │                  │       │
│  │ VETO → Retry     │   │ Authority:       │   │ Authority:       │       │
│  │ ESCALATE→Council │   │ VETO → Retry     │   │ VETO → Retry     │       │
│  │ (No Vote)        │   │ ESCALATE→Lead    │   │ ESCALATE→Lead    │       │
│  │                  │   │ (No Vote)        │   │ (No Vote)        │       │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘       │
│           │                      │                      │                 │
│           └──────────────────────┼──────────────────────┘                 │
│                                  │                                        │
│                    ┌─────────────┴──────────────┐                         │
│                    ▼                            ▼                         │
│         ┌──────────────────────┐    ┌──────────────────────┐             │
│         │  REMOTE EXECUTOR     │    │  CHECKPOINT SERVICE  │             │
│         │  (Sandboxed Env)     │    │  (State Capture)     │             │
│         │                      │    │                      │             │
│         │ • Code Execution     │    │ • Phase Boundaries   │             │
│         │ • Data Transform     │    │ • Time-Travel        │             │
│         │ • Tool Invocation    │    │ • Branch/Restore     │             │
│         │ • Returns Summary    │    │ • Audit Trail        │             │
│         │   (Never Raw Data)   │    │                      │             │
│         └──────────────────────┘    └──────────────────────┘             │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🧠 Background Processing Layer                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Celery Workers       │  Constitutional Patrol   │  Knowledge Maintenance   │
│  ├─ Task Queue        │  (Heartbeat)             │  (Deduplication)         │
│  ├─ Vote Tally        │  Compliance Checks       │  Embedding Updates       │
│  ├─ Critic Queue      │  Auto-termination        │  Orphaned Data Cleanup   │
│  └─ Agent Liquidation │  Idle Detection          │  Semantic Indexing       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

**Separation of Powers**

- **Executive** (Head): Final approval, emergency override
- **Legislative** (Council): Voting, amendments, strategic policy
- **Judicial** (Critics): Independent validation, veto authority
- **Workers** (Task/Lead): Execution without political influence

**Democratic Accountability**

- All Council votes stored in PostgreSQL with timestamp, tally, and agent signatures
- Constitution changes require 66% majority + Head ratification
- Agent liquidation requires Council vote or constitutional violation proof
- Every action traceable to a specific agent ID

**Knowledge Sovereignty**

- **PostgreSQL**: Source of truth for entities, hierarchies, votes
- **ChromaDB**: Semantic understanding (embeddings of constitution, learnings)
- **Dual Query**: Agents ask _both_ databases before major decisions
- **Vector Augmented Retrieval**: Task agents retrieve past learnings via RAG

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux)
- 8GB RAM minimum (16GB recommended)
- 10GB free disk space

### Installation

```bash
# Clone the repository
git clone https://github.com/AshminDhungana/Agentium.git
cd agentium

# Launch the stack
docker compose up -d
(First Build will take 10-20 minutes)

# Watch initialization logs
docker compose logs -f agentium-backend

# Access the dashboard
open http://localhost:3000
```

**First Login**: You'll be guided through the Genesis Protocol where you name your AI Nation.

### System Requirements

- Works the same on **Windows, macOS, and Linux**
- No local Python/Node setup required — everything runs in Docker
- Ideal for local development, experimentation, and self-hosting

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
- Lead Agents can have other Lead Agents below them if task agent count increases
- Lead agents can have many layers of Leads below them as per required

---

## 🛠️ Technology Stack

| Component            | Technology                                        | Purpose                               |
| -------------------- | ------------------------------------------------- | ------------------------------------- |
| **Frontend**         | React 18, TypeScript, Tailwind, Zustand           | Dashboard, voting UI, agent tree      |
| **API Gateway**      | FastAPI, WebSocket, Pydantic                      | REST + real-time communication        |
| **Message Bus**      | Redis, Celery                                     | Inter-agent routing, background tasks |
| **Structured Data**  | PostgreSQL, SQLAlchemy, Alembic                   | Entity state, voting records, audit   |
| **Vector Knowledge** | ChromaDB, Sentence-Transformers                   | RAG, constitution, learnings          |
| **AI Models**        | Local (Kimi, GPT4, All) + API (OpenAI, Anthropic) | Agent intelligence                    |
| **Container**        | Docker, Compose, Healthchecks                     | Cross-platform deployment             |
| **Security**         | JWT                                               | Per-agent authentication              |

---

## 🧪 Development Roadmap

### Phase 0: Foundation ✅

- [x] PostgreSQL entity models
- [x] Hierarchical ID system (0/1/2/3xxxx)
- [x] Docker compose setup

### Phase 1: Knowledge Infrastructure 🚧 **Current Focus**

- [x] ChromaDB integration World Knowledge
- [x] Knowledge Library service
- [x] Initialization Protocol (Country naming)
- [x] RAG pipeline World Knowledge

### Phase 2: Governance Core ✅

- [x] Message Bus (Redis)
- [x] Agent Orchestrator (metrics + circuit breaker)
- [x] Constitutional Guard (two-tier: PostgreSQL + ChromaDB)
- [x] Voting Service with quorum logic
- [x] Amendment Service (propose → vote → ratify)
- [x] Critic Agents with veto authority (Code/Output/Plan)

### Phase 3: Lifecycle Management

- [x] Agent Factory (spawn/liquidate)
- [x] Auto-scaling algorithms
- [x] Capability Registry
- [x] Automated termination (idle detection)
- [ ] Phase 3 - Testing

### Phase 4: Intelligence

- [x] Multi-model provider support
- [ ] Browser automation integration
- [ ] Advanced RAG with source citations
- [ ] Voice interface

### Phase 5: Ecosystem

- [ ] Plugin marketplace
- [ ] Scaling Workforce, Ministry, Law, Judiciary and more
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

Read our [Contributing Guide](./CONTRIBUTING.md)

---

## 🛡️ Security & Ethics

- **Local-First**: Your data never leaves your infrastructure by default
- **Immutable Audit**: All votes, actions, and terminations logged to PostgreSQL
- **Principle of Least Privilege**: Task agents cannot spawn other agents
- **Constitutional Bounded**: Agents cannot override the Constitution without democratic process
- **Emergency Brakes**: Head can halt entire system; Council can veto Head with 75% vote
- **Individual Ethos**: Individual agents ethos must be removed after agent deletion or reassignment
- **World Knowledge**: World knowledge must be updated and maintained regularly

---

## 💬 Support & Community

- 📧 Email: **dhungana.ashmin@gmail.com**

---

## 📄 License

Apache License 2.0 — See [LICENSE](LICENSE) file

**Built with ❤️ and purpose by Ashmin Dhungana**

> _"The price of freedom is eternal vigilance. The price of AI sovereignty is democratic architecture."_
