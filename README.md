# 🏛️ Agentium

> Your Personal AI Agent Nation — Sovereign, Constitutional, and Fully Self-Governing.

[![Status](https://img.shields.io/badge/status-public%20beta-blue)](https://github.com/AshminDhungana/Agentium)
[![Version](https://img.shields.io/badge/version-v0.21.0--beta-blue)](https://github.com/AshminDhungana/Agentium)
[![v1.0.0 ETA](https://img.shields.io/badge/v1.0.0%20expected-Dec%2031%2C%202026-orange)](https://github.com/AshminDhungana/Agentium)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)
[![Docs](https://img.shields.io/badge/docs-OpenAPI%203.1-brightgreen)](http://localhost:8000/docs)

**Agentium** transforms AI task execution into a structured digital democracy. Unlike monolithic AI assistants, Agentium operates as a self-governing ecosystem where AI agents function like a parliamentary system — complete with a **Head of Council** (Executive), **Council Members** (Legislature), **Lead Agents** (Directors), **Task Agents** (Executors), and **Critic Agents** (Independent Judiciary) — all bound by a **Constitution** and managed through democratic voting.

Built for those who believe AI should be **transparent, accountable, and sovereign**, Agentium runs entirely on your infrastructure with local-first architecture. Agentium can spawn up to **99,999 AI Agents** with proper control and management, and handle up to **9,999 concurrent tasks** provided by the user — all at once.

## ![[Agentium Demo]](./docs/assets/animation.svg)

---

## ✨ What Makes Agentium Unique?

### 🏛️ Democratic AI Governance

Tasks aren't just executed; they're deliberated. The Council votes on constitutional amendments, resource allocation, and major system changes. Every decision is logged, auditable, and reversible.

### ⚖️ Constitutional Framework

A living document stored in dual storage that all agents access before acting. Agents literally ask _"Is this constitutional?"_ before every action. Amendments require democratic approval with a 60% quorum.

### 🧠 Collective Intelligence (Knowledge Library)

- **Dual-Storage Architecture**: PostgreSQL for structured data, ChromaDB for semantic knowledge
- **Shared Memory**: Task agents share learnings; Council curates institutional knowledge
- **RAG-Powered**: World knowledge retrieved via semantic search using `BAAI/bge-base-en-v1.5` embeddings (768-dim)
- **Revision-Aware**: No knowledge is stored blindly — all entries are deduplication-checked and revision-aware

### 🔐 Brains vs. Hands (Remote Code Execution)

A sandboxed Docker executor separates reasoning from execution. Raw data **never** enters agent context. Agents reason about data shape and schema only — PII and working sets stay inside the execution layer.

### 🔌 Constitutional MCP Tool Governance

MCP servers are integrated through the Constitution, not around it. Every tool invocation is audited. Tools are tiered: Pre-Approved (Council vote to use), Restricted (Head approval per use), or Forbidden (constitutionally banned).

### 💬 Unified Multimodal Inbox

One user. One conversation. All channels. Text, image, video, audio, and files are normalized into a single canonical conversation state. Channels are transport layers only — the conversation is sovereign and channel-agnostic.

### 🏗️ Hierarchical Agent IDs

Rigorous identification system:

- **Head**: `0xxxx` (00001–09999) — The Sovereign's direct representative
- **Council**: `1xxxx` (10001–19999) — Democratic deliberation layer
- **Lead**: `2xxxx` (20001–29999) — Department coordination
- **Task**: `3xxxx` (30001–69999) — Execution workers
- **Code Critic**: `7xxxx` (70001–79999) — Code validation (syntax, security, logic)
- **Output Critic**: `8xxxx` (80001–89999) — Output validation (user intent alignment)
- **Plan Critic**: `9xxxx` (90001–99999) — Plan validation (DAG soundness)

> Critics operate **outside** the democratic chain. They have veto authority with checks and balances implimented but no voting rights. Rejected tasks retry within the same team (max 5 retries) before escalating to Council.

### 🔄 Self-Governing Lifecycle

Agents auto-spawn when load increases, auto-terminate when tasks complete, and can be liquidated by Council vote if they violate the Constitution or remain idle >7 days.

---

## 🔮 Autonomous Orchestration & Production Hardening

### 🤖 Automatic Task Delegation Engine

Every task is automatically scored (1–10), broken into a sub-task DAG, and assigned to the correct agent tier by capability. Tasks stuck beyond their escalation timeout auto-reassign or trigger a Council micro-vote. Cost-aware delegation falls back to local Ollama when budgets are tight.

### 🛡️ Self-Healing & Auto-Recovery

Exponential-backoff retries replace fixed-interval retries. A heartbeat monitor detects crashed agents within 30 seconds; the **Reincarnation Service** restores them from the latest checkpoint and resumes interrupted tasks. When all API providers are down, the system enters **Graceful Degradation** mode — CRITICAL and SOVEREIGN tasks continue on local models while normal tasks pause.

### 📈 Predictive Auto-Scaling

A time-series load predictor (weighted moving average) forecasts demand 1 h, 6 h, and 24 h ahead. Agents are pre-spawned before surges and pre-liquidated during lulls. A **Token Budget Guard** caps daily AI spend and downgrades to cheaper models at 80 % consumption.

### 🏗️ Workflow Automation Pipeline

A drag-and-drop workflow designer supports `task → condition → parallel → human_approval → task` patterns. Workflows are versioned, cron-scheduled, and auto-documented by LLM on completion. Human-approval gates pause execution via WebSocket until acted on.

### ⚡ Intelligent Event Processing

Webhook, threshold, schedule, and API-poll triggers automatically fire workflows or create tasks. HMAC-SHA256 validation, event deduplication, and a dead-letter queue ensure reliable processing. Circuit breakers pause triggers that fire too frequently.

### 📊 Zero-Touch Operations Dashboard

Real-time anomaly detection (Z-score against 7-day baselines), automated incident response for known failure patterns, SLA compliance tracking, capacity planning, and chaos-engineering injection — all visible in a single dashboard with five health rings.

### 🌐 Frontend Reliability

Global error boundaries catch per-widget failures without crashing the page. WebSocket reconnection uses exponential backoff (1 s → 2 s → 4 s → 8 s, cap 30 s). Browser tasks stream live screenshots in real time.

### 🛡️ Platform Hardening

Application-layer DDoS hardening: layered rate limits (per-IP, per-user, per-endpoint), payload size limits, and automatic IP blocklisting for suspicious patterns. Privilege-escalation audit trails capture every role change.

### 🔍 Advanced RAG

Knowledge decay scoring automatically sinks stale entries; cross-document citation graphs boost frequently cited documents. Fact-checking against the vector database improves retrieval accuracy.

### 🎤 Voice Interface

 Local **whisper.cpp** (built into the backend image) is the **primary** speech-to-text engine — no API key required. OpenAI Whisper is the keyed fallback, with browser-native Web Speech as the final net. The host-side **Voice Bridge** (`voice-bridge/`) turns this into a "Jarvis"-style assistant: instant `openWakeWord` detection, Silero VAD end-of-speech, Kokoro-82M neural TTS, talk-over barge-in with echo cancellation, a configurable persona, and speaker-aware greetings. Phone (Twilio) and Discord voice channel support.

### Local Speech-to-Text (whisper.cpp)

Agentium builds [whisper.cpp](https://github.com/ggerganov/whisper.cpp) into the
backend image and uses it as the **primary** STT engine — no API key required.
Fallback chain: `whisper.cpp → OpenAI Whisper (if a key is set) → browser-native`.
Configurable env vars: `WHISPER_MODEL` (default `base.en`), `WHISPER_CPP_BIN`,
`WHISPER_MODEL_DIR`, `WHISPER_TIMEOUT` (default 60s), `WHISPER_MAX_CONCURRENCY`
(default 1). For GPU: build with `--build-arg WHISPER_BACKEND=cuda` and run
 the backend with `--gpus all`.

### 🎙️ Voice Bridge (host-side) configuration

The `voice-bridge/` process runs on the host (outside Docker) and streams
mic audio to the backend. It degrades gracefully: missing models fall back to
safer behavior, and every new setting defaults to the previous behavior.

> **Setup & operations:** see [`docs/documents/voice-bridge-setup.md`](docs/documents/voice-bridge-setup.md)
> for install/uninstall/verify per OS, logs, and troubleshooting.

### 🔄 Git Versioning for Config

All constitution, model, plugin, and channel configuration changes are automatically snapshotted to a local Git repository with one-click restore.

---

## 🏗️ Architecture

### Full Governance Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AGENTIUM GOVERNANCE STACK                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 💻 Interface Layer                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  Web Dashboard (React+Vite)      │  WhatsApp    Telegram    Discord         │
│  ├─ Agent Tree Visualization     │  Slack       Signal      Google Chat     │
│  ├─ Voting Interface             │  Teams       Matrix      iMessage        │
│  ├─ Critic Review Dashboard      │  Zalo        API         Phone           │
│  ├─ Constitution Editor          │                                          │
│  ├─ Checkpoint Timeline          │                                          │
│  ├─ MCP Tool Registry            │                                          │
│  ├─ Scaling Dashboard            │                                          │
│  ├─ Workflow Designer            │                                          │
│  └─ Event Trigger Manager        │                                          │
└───────────────────────────────────┴──────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ Control Layer                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  FastAPI Gateway    │  WebSocket Hub    │  Redis Message Bus                │
│  ├─ Agent Orchestrator                  │  Hierarchical Routing             │
│  ├─ Constitutional Guard (2-tier)       │  3x→2x→1x→0x Routing             │
│  ├─ Context Ray Tracer                  │  Persistent Queues                │
│  ├─ Voting Service                      │  Time-Travel Recovery             │
│  ├─ Unified Inbox / Channel Manager     │                                    │
│  ├─ Checkpoint Service                  │                                    │
│  ├─ Auto-Delegation Service             │                                    │
│  ├─ Reincarnation Service               │                                    │
│  └─ Event Processor                     │                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┴───────────────────────┐
            ▼                                               ▼
┌───────────────────────────────┐           ┌───────────────────────────────┐
│ 🏛️ Governance Layer           │           │ 💾 Storage Layer               │
├───────────────────────────────┤           ├───────────────────────────────┤
│ 👑 Head (0xxxx)               │           │ PostgreSQL (Structured Truth)│
│ ├─ Veto Power                 │           │ ├─ Agent Entities              │
│ ├─ Emergency Override         │           │ ├─ Voting Records              │
│ ├─ Genesis Protocol             │           │ ├─ Audit Logs                  │
│ └─ Final Approval             │           │ ├─ Constitution Versions       │
│                               │           │ ├─ Checkpoint States           │
│ ⚖️ Council (1xxxx)             │           │ ├─ MCP Tool Registry           │
│ ├─ Propose Amendments         │           │ ├─ Workflow Versions           │
│ ├─ Vote on Tasks              │           │ ├─ Speaker Profiles            │
│ ├─ Knowledge Moderation       │           │ ├─ Task Dependencies           │
│ ├─ Agent Liquidation          │           │ ├─ Citation Edges              │
│ └─ Strategic Decisions        │           │ └─ Conversation / Message      │
│                               │           │                                │
│ 🎯 Lead (2xxxx)               │           │ ChromaDB (Vector Meaning)      │
│ ├─ Spawn Task Agents          │           │ ├─ Constitution (embeddings)   │
│ ├─ Delegate Work              │           │ ├─ Task Learnings (RAG)        │
│ ├─ Resource Allocation        │           │ ├─ Best Practices              │
│ └─ Aggregate Results          │           │ ├─ Staged Knowledge              │
│                               │           │ └─ Decay Scores                │
│ 🤖 Task (3xxxx)               │           │                                │
│ ├─ Execute Commands           │           │ Object Storage                 │
│ ├─ Generate Code              │           │ ├─ User Media (images, video)  │
│ ├─ Submit Learnings           │           │ ├─ AI-Generated Media          │
│ └─ Query Knowledge            │           │ └─ File Attachments              │
│                               │           └───────────────────────────────┘
│ Git Config Versioning         │
│ └─ Constitution / Model /     │
│    Plugin / Channel configs   │
│    (auto-snapshot + restore)  │
└───────────────┬───────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔮 Intelligence Layer (Self-Improvement)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Learning Impact Tracker  │  Anti-Pattern Scanner     │  Knowledge Consol.   │
│  ├─ 7-day success-rate   │  ├─ Recurrence count     │  ├─ Daily merge       │
│     delta tracking       │  ├─ Auto-amendment flag   │  ├─ Deduplication     │
│  └─ Federated knowledge  │  └─ Severity scoring      │  └─ Embedding refresh│
│     sharing              │                            │                     │
│                                                                               │
│  Citation Graph Engine                                                       │
│  ├─ BFS traversal to depth n                                                 │
│  ├─ Frequency boost multiplier (cap 1.3×)                                  │
│  └─ Cross-document link tracking                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🔍 Execution Validation Layer (Critics — Independent Judiciary)             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐       │
│  │ Plan Critic 9xxxx│   │ Code Critic 7xxxx│   │ Output Critic 8x │       │
│  │ DAG Soundness    │   │ Syntax/Security  │   │ User Intent      │       │
│  │ VETO → Retry     │   │ VETO → Retry     │   │ VETO → Retry     │       │
│  │ ESCALATE→Council │   │ ESCALATE→Lead    │   │ ESCALATE→Lead    │       │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘       │
│                                                                             │
│  ┌──────────────────────┐         ┌──────────────────────┐                │
│  │  REMOTE EXECUTOR     │         │  CHECKPOINT SERVICE  │                │
│  │  (Sandboxed Docker)  │         │  (State Capture)     │                │
│  │  Raw data never      │         │  Phase Boundaries    │                │
│  │  enters agent ctx    │         │  Time-Travel/Branch  │                │
│  └──────────────────────┘         └──────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🧠 Background Processing Layer                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Celery Workers       │  Constitutional Patrol   │  Knowledge Maintenance   │
│  ├─ Task Queue        │  (Heartbeat)             │  (Deduplication)         │
│  ├─ Vote Tally        │  ├─ Crash Detection      │  Embedding Updates       │
│  ├─ Critic Queue      │  ├─ Reincarnation        │  Orphaned Data Cleanup   │
│  ├─ Agent Liquidation │  ├─ Anomaly Detection    │  Semantic Indexing       │
│  ├─ Predictive Scale│  └─ Auto-Remediation     │                           │
│  ├─ Event Processing  │                           │                           │
│  └─ Workflow Cron     │                           │                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

**Separation of Powers**

- **Executive** (Head): Final approval, emergency override
- **Legislative** (Council): Voting, amendments, strategic policy
- **Judicial** (Critics): Independent validation, veto authority — outside the democratic chain
- **Workers** (Task/Lead): Execution without political influence

**Democratic Accountability**

- All Council votes stored in PostgreSQL with timestamp, tally, and agent signatures
- Constitution changes require 60% quorum + Head ratification
- Agent liquidation requires Council vote or constitutional violation proof
- Every action traceable to a specific agent ID

**Knowledge Sovereignty**

- **PostgreSQL**: Source of truth for entities, hierarchies, votes, conversations
- **ChromaDB**: Semantic understanding (embeddings of constitution, learnings)
- **Dual Query**: Agents query both databases before major decisions
- **RAG Pipeline**: Task agents retrieve past learnings and constitutional context automatically

**Cognitive Discipline (Ethos)**

- Each agent maintains a minimal working memory (Ethos) — continuously updated, never bloated
- Ethos is read before task execution, updated during, compressed after
- Higher-tier agents may view and correct subordinate Ethos
- Constitutional recalibration occurs between every task

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux)
- 8 GB RAM minimum (16 GB recommended)
- 10 GB free disk space

### Installation

```bash
# Clone the repository
git clone https://github.com/AshminDhungana/Agentium.git
cd Agentium

# Launch the stack
docker compose up -d
# First build takes (20–40) minutes
# Depends on your internet speed and your PC performance

# Watch initialization logs
docker compose logs -f

# Access the dashboard
open http://localhost:3000
```

**First Login**: You'll be guided through the **Genesis Protocol** — your AI Nation is named by democratic Council vote before any tasks are accepted.

### Accessing API Documentation

Agentium serves an auto-generated OpenAPI 3.1 specification at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

All 80+ endpoints are documented with example request/response bodies.

### System Requirements

- Works identically on **Windows, macOS, and Linux**
- No local Python/Node setup required — everything runs in Docker
- Ideal for local development, experimentation, and self-hosting

---

## 🏠 Self-Hosting Guide

👉 [Self-Hosting Documentation](./docs/documents/selfhost.md)

---

## 📖 Usage Guide

### 1. The Genesis (First Run)

Upon first login, you'll witness the **Initialization Protocol**:

1. The Head of Council greets you (The Sovereign)
2. Council proposes names for your "Nation" (the system instance)
3. Democratic vote executes — watch the real-time tally in the dashboard
4. Constitution is ratified with your chosen name and stored in both PostgreSQL and ChromaDB
5. System becomes fully operational

### 2. Daily Operations

**Submitting a Task**:

```
You (Sovereign) → Head (0xxxx): "Analyze Q3 financial reports"
    ↓
Head validates intent + constitutional compliance
    ↓
Council votes on resource allocation (if required)
    ↓
Lead Agent (2xxxx) creates execution DAG
    ↓
Plan Critic (9xxxx) validates DAG
    ↓
Task Agents (3xxxx) execute — with Code + Output Critics reviewing
    ↓
Results aggregated → Head → You (2–3 line response only)
```

**Auto-Scaling in Action**:

- Load increases → Lead detects queue depth
- Lead requests Council approval for new Task Agents
- Council votes (automated if resolved <5 seconds)
- New `3xxxx` agents spawned with knowledge from Vector DB
- When queue empties, oldest Task Agents liquidated
- Leads can nest further Leads below them for large task trees

**Multi-Channel**: Send tasks from WhatsApp, Telegram, Slack, Discord, or any connected channel. The conversation is unified — you'll see full history in the web dashboard regardless of which channel you used.

---

## 🛠️ Technology Stack

| Component            | Technology                                             | Purpose                                               |
| -------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| **Frontend**         | React 18, TypeScript, Tailwind, Zustand                | Dashboard, voting UI, agent tree, checkpoint timeline |
| **API Gateway**      | FastAPI, WebSocket, Pydantic                           | REST + real-time communication                        |
| **Message Bus**      | Redis, Celery                                          | Inter-agent routing, background tasks                 |
| **Structured Data**  | PostgreSQL, SQLAlchemy, Alembic                        | Entity state, voting records, audit, conversations    |
| **Vector Knowledge** | ChromaDB, Sentence-Transformers (BAAI/bge-base-en-v1.5, 768-dim, cosine) | RAG, constitution, learnings                        |
| **AI Models**        | OpenAI, Anthropic, Groq, Ollama, any OpenAI-compatible | Agent intelligence, multi-provider failover           |
| **Code Execution**   | Docker sandbox (Remote Executor)                       | Isolated code execution, PII containment              |
| **Tool Governance**  | MCP SDK + Constitutional Guard                         | Tiered external tool access                           |
| **Containerization** | Docker, Compose, Healthchecks                          | Cross-platform deployment                             |
| **Security**         | JWT, Role-based capabilities                           | Per-agent authentication and authorization            |
| **Browser Control**  | Playwright (headless Chromium)                         | Web scraping, screenshots, search — sandboxed         |
| **Voice**            | whisper.cpp (primary STT), OpenAI Whisper (fallback), OpenAI TTS | Local speech-to-text, text-to-speech, WebSocket streaming |

---

## 📦 SDKs

Agentium ships with two first-class SDKs, both auto-generated from the OpenAPI 3.1 spec and producing identical audit trails.

| SDK | Installation | Repository |
| --- | ------------ | ---------- |
| **Python** | `pip install agentium-sdk` | [`sdk/python`](./sdk/python) |
| **TypeScript** | `npm install @agentium/sdk` | [`sdk/typescript`](./sdk/typescript) |

Quick example (Python):
```python
from agentium_sdk import AgentiumClient

async with AgentiumClient("http://localhost:8000", api_key="sk-...") as client:
    agents = await client.list_agents()
    task = await client.create_task(title="Analyze Q3 reports")
```

Quick example (TypeScript):
```typescript
import { AgentiumClient } from '@agentium/sdk';

const client = new AgentiumClient({ baseUrl: 'http://localhost:8000', apiKey: 'sk-...' });
const agents = await client.listAgents();
const task = await client.createTask({ title: 'Analyze Q3 reports' });
```

---

## 🧪 Development Roadmap

### Development ✅ COMPLETE

### Testing, Improvement, Bug  (Ongoing)


**🎯 v1.0.0 Target Release:** December 31, 2026

---

## 🛡️ Security & Ethics

- **Local-First**: Your data never leaves your infrastructure by default
- **Immutable Audit**: All votes, actions, and terminations logged to PostgreSQL
- **Principle of Least Privilege**: Task agents cannot spawn other agents
- **Constitutional Bounded**: Agents cannot override the Constitution without democratic process
- **Emergency Brakes**: Head can halt the entire system; Council can veto Head with 75% supermajority
- **Execution Isolation**: Raw data and PII are confined to the sandboxed Remote Executor — never in agent reasoning context
- **Tool Governance**: MCP tools are constitutionally tiered; Tier 3 tools are categorically forbidden
- **Ethos Hygiene**: Individual agent Ethos must be removed after agent deletion or reassignment
- **Original Constitution**: Can never be deleted under any circumstances

---

## 🤝 Contributing

Agentium is built for the community. We welcome:

- 🏛️ **Governance Models**: New voting algorithms, constitutional frameworksFixes
- 🧠 **Knowledge Systems**: RAG improvements, embedding models
- 🔌 **Integrations**: New messaging channels, AI providers, MCP servers
- 📖 **Documentation**: Tutorials, constitutional examples
- 🐛 **Bug Reports**: Help us maintain integrity

Read our [Contributing Guide](./CONTRIBUTING.md)

---

## 💬 Support

- 📧 Email: **dhungana.ashmin@gmail.com**

---

## 📄 License

Apache License 2.0 — See [LICENSE](LICENSE) file

**Built with ❤️ and purpose by Ashmin Dhungana**

> _"The price of freedom is eternal vigilance. The price of AI sovereignty is democratic architecture."_
