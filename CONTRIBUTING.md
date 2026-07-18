# Contributing to Agentium

> _"The price of freedom is eternal vigilance. The price of AI sovereignty is democratic architecture."_

Thank you for your interest in contributing to **Agentium** — a sovereign AI governance platform. This document outlines the principles, processes, and technical guidelines for participating in our ecosystem.

## 🏛️ Our Governance Philosophy

Just as Agentium implements democratic AI governance, we govern our community contributions through transparent, meritocratic processes:

- **Transparency**: All architectural decisions are documented and open for review
- **Meritocracy**: Contributions are evaluated on technical merit and alignment with constitutional principles
- **Inclusivity**: We welcome contributors from all backgrounds and expertise levels
- **Sovereignty**: Local-first development; your contributions should respect user autonomy

## 📋 Table of Contents

- [Code of Conduct](#️-code-of-conduct)
- [Getting Started](#-getting-started)
- [Development Environment](#-development-environment)
- [Architecture Guidelines](#️-architecture-guidelines)
- [Contribution Workflow](#-contribution-workflow)
- [Coding Standards](#-coding-standards)
- [Commit Message Convention](#-commit-message-convention)
- [Pull Request Process](#-pull-request-process)
- [Community](#-community)

## ⚖️ Code of Conduct

### Our Constitutional Principles

1. **Respect the Hierarchy**: Value contributions from all tiers — from Task-level documentation fixes to Head-level architectural changes
2. **Democratic Deliberation**: Disagree constructively. Major changes require consensus, not just approval
3. **Transparency**: Document your reasoning. If an agent must explain its actions, so must we
4. **Sovereignty First**: Prioritize user privacy, local execution, and data ownership in all contributions

### Unacceptable Behavior

- Harassment, discrimination, or intimidation of any kind
- Introducing surveillance or data extraction mechanisms
- Circumventing the constitutional framework for "efficiency"
- Non-consensual data collection or telemetry

## 🚀 Getting Started

### Prerequisites

- **Docker Engine** 20.10+
- **Docker Compose** 2.0+
- **Git** 2.30+
- **Node.js** 18+ (for frontend development)
- **Python** 3.11+ (for backend development)

### Repository Structure

```
agentium/
├── backend/          # FastAPI + SQLAlchemy + ChromaDB
│   ├── api/          # Routes & middleware
│   ├── models/       # Database entities
│   ├── services/     # Business logic
│   └── docs_ministry/# Constitutional templates
├── frontend/         # React + TypeScript + Vite
│   ├── src/components/
│   ├── src/pages/
│   └── src/store/    # Zustand state management
├── docker/           # Initialization scripts
└── docs/             # Documentation & specs
```

## 🛠️ Development Environment

### Quick Start

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/Agentium.git
cd Agentium

# 2. Create your branch (see naming conventions below)
git checkout -b feature/your-feature-name

# 3. Launch the governance stack
docker-compose up --build

# 4. Access services
# Dashboard: http://localhost:3000
# API Docs:  http://localhost:8000/docs
# DB Admin:  localhost:5432 (PostgreSQL)
```

### Environment Configuration

```bash
# Copy example environment
cp backend/.env.example backend/.env

# Required variables
DATABASE_URL=postgresql://agentium:secret@localhost:5432/agentium
CHROMA_HOST=localhost
CHROMA_PORT=8001
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-here

```

### Development Mode (Hot Reload)

```bash
# Backend only
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend only
cd frontend
npm install
npm run dev
```

## 🏗️ Architecture Guidelines

### Hierarchical Agent System (0/1/2/3xxxx)

When contributing features, respect the agent hierarchy:

| Tier        | ID Range | Scope                                   | Contribution Type    |
| ----------- | -------- | --------------------------------------- | -------------------- |
| **Head**    | 0xxxx    | Constitutional changes, veto logic      | Architectural RFCs   |
| **Council** | 1xxxx    | Voting systems, knowledge moderation    | Feature development  |
| **Lead**    | 2xxxx    | Resource allocation, task orchestration | API enhancements     |
| **Task**    | 3xxxx    | Execution, data processing              | Bug fixes, utilities |

### Dual-Storage Principle

All knowledge contributions must respect the dual-storage architecture:

- **PostgreSQL**: Structured truth (state, history, audit)
- **ChromaDB**: Semantic meaning (embeddings, RAG context)

Example:

```python
# Good: Dual-write pattern
async def submit_knowledge(content: str, agent_id: str):
    # 1. Structured record
    record = await KnowledgeRecord.create(
        content=content,
        agent_id=agent_id,
        status="pending"
    )
    # 2. Vector embedding (after council approval)
    await vector_store.add_document(
        document=content,
        metadata={"agent_id": agent_id, "record_id": record.id}
    )
```

### Constitutional Compliance

New features must integrate with the Constitutional Guard:

1. **Declaration**: Document how your feature respects the Constitution
2. **Validation**: Add checks in `constitutional_guard.py` if applicable
3. **Audit**: Ensure all actions are logged to `audit.py`

## 📝 Contribution Workflow

### 1. Issue Creation

Before coding, create an issue describing:

- **For Features**: Use template `feature_request.md`
  - Which agent tier does this affect?
  - Does this require constitutional amendment?
  - What democratic process is needed?

- **For Bugs**: Use template `bug_report.md`
  - Expected vs. actual behavior
  - Steps to reproduce
  - Agent ID format if relevant (e.g., "affects Lead agents 2xxxx")

### 2. Branch Naming Convention

```
feature/1xxxx-knowledge-moderation-queue
bugfix/3xxxx-task-lifecycle-cleanup
docs/constitutional-amendment-process
refactor/hierarchical-id-generation
security/vote-tally-verification
```

Prefix indicates:

- `feature/`: New capabilities
- `bugfix/`: Error corrections
- `docs/`: Documentation only
- `refactor/`: Non-functional changes
- `security/`: Security patches

### 3. Development Process

We follow **Democratic Development**:

1. **Proposal**: Open a Draft PR early for architectural feedback
2. **Deliberation**: Address reviewer concerns through discussion
3. **Voting**: Two approvals required for merge (constitutional requirement)
4. **Ratification**: Final review by maintainer (Head tier)

## 💻 Coding Standards

### Python (Backend)

**Style**: Follow PEP 8 with modifications:

```python
# Use type hints rigorously
async def spawn_agent(
    parent_id: str,
    agent_type: AgentTier,
    constitution_version: int
) -> AgentEntity:
    pass

# Docstrings must explain "why" not just "what"
def calculate_quorum(council_size: int, vote_type: VoteType) -> int:
    """
    Calculate required votes for democratic legitimacy.

    Constitutional amendments require 60% for stability,
    operational votes require 50% for agility.
    """
    pass

# Hierarchical IDs are sacred
HEAD_PATTERN = r"^0\d{4}$"
COUNCIL_PATTERN = r"^1\d{4}$"
LEAD_PATTERN = r"^2\d{4}$"
TASK_PATTERN = r"^3\d{4}$"
```

**Testing**:

```bash
# Run the constitutional test suite
pytest tests/ -v --cov=backend

# Test specific tier logic
pytest tests/test_council_voting.py -v
```

### TypeScript/React (Frontend)

**Component Structure**:

```typescript
// AgentsPage.tsx example
interface AgentsPageProps {
  // Props here
}

export const AgentsPage: React.FC<AgentsPageProps> = () => {
  // Use Zustand stores, not prop drilling
  const { agents, spawnAgent } = useAgentStore();

  // Respect hierarchy in UI
  const headAgents = agents.filter(a => a.tier === 'head');
  const councilAgents = agents.filter(a => a.tier === 'council');

  return (
    <div className="agentium-container">
      {/* Implementation */}
    </div>
  );
};
```

**State Management**:

- Use `zustand` for global state
- Keep WebSocket connections in dedicated hooks (`useWebSocket`)
- Never bypass the API layer to directly interact with storage

### Database Migrations

Database migrations are managed by **Alembic**. All migration scripts are located in `backend/alembic/versions/`.

#### Apply migrations

When starting the application for the first time, or after pulling new code that includes schema changes:

```bash
cd backend
alembic upgrade head
```

#### Create a new migration

After modifying SQLAlchemy models in `backend/models/entities/`:

```bash
cd backend
alembic revision --autogenerate -m "Description of changes"
```

> ⚠️ **Always review the generated script before committing.** Ensure it handles both PostgreSQL and ChromaDB consistency.

#### Downgrade migrations

To revert the last migration:

```bash
cd backend
alembic downgrade -1
```

To revert to a specific revision:

```bash
cd backend
alembic downgrade <revision_id>
```

To revert all migrations and start from scratch:

```bash
cd backend
alembic downgrade base
```

## 🧪 Test Execution

Tests are organized by scope and run inside Docker containers. No local Python or Node.js installation is required.

### Backend Tests

#### Run all backend tests

```bash
docker compose exec backend pytest
```

#### Run tests with coverage

```bash
docker compose exec backend pytest --cov=services --cov-report=term-missing --cov-fail-under=80
```

#### Run a specific test

```bash
docker compose exec backend pytest backend/tests/test_governance.py -v
```

#### Run integration tests

Integration tests exercise the full stack (PostgreSQL, Redis, ChromaDB, and API). They are located in `backend/tests/integration/`.

```bash
docker compose exec backend pytest backend/tests/integration/ -v
```

### Frontend Tests

#### Run frontend tests

```bash
cd frontend
npm test
```

### Linting and Type Checking

```bash
# Backend linting
docker compose exec backend flake8 backend/

# Frontend linting
cd frontend
npm run lint

# TypeScript type checking
cd frontend
npm run type-check
```

## 🎯 Commit Message Convention

We use **Conventional Commits** with a democratic twist:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:

- `feat`: New feature (requires Council approval)
- `fix`: Bug fix (Task tier)
- `docs`: Documentation (all tiers)
- `style`: Formatting (no logic change)
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

**Scopes**:

- `constitution`: Constitutional changes
- `council`: Voting/governance logic
- `agent`: Agent lifecycle
- `knowledge`: Vector DB/RAG
- `ui`: Frontend components
- `api`: REST endpoints

**Examples**:

```
feat(council): implement quadratic voting for amendments

Adds quadratic voting mechanism to prevent whale dominance
in constitutional amendments. Requires 60% quorum.

Refs: #123
```

```
fix(agent): prevent liquidation of active task agents

Resolves race condition where agents processing tasks
were liquidated due to idle timeout.

Closes: #456
```

## 🔄 Pull Request Process

### Opening a PR

1. **Fill the template** completely:
   - What constitutional principle does this support?
   - Which agent tier is primarily affected?
   - Testing performed?
   - Breaking changes?

2. **Link issues**: Use `Closes #123` or `Refs #456`

3. **Screenshots**: For UI changes, show the democratic interface in action

### Review Process

Our review mimics the Council deliberation:

1. **Automated Checks**: CI must pass (linting, tests, security scan)
2. **Peer Review**: At least one review from same-tier contributor
3. **Council Review**: For `feat/` and `refactor/`, two approvals required
4. **Head Approval**: Final merge by maintainer

### Review Criteria

Reviewers evaluate:

- [ ] **Constitutional Compliance**: Does this respect the Constitution?
- [ ] **Hierarchy Integrity**: Proper use of 0/1/2/3xxxx patterns?
- [ ] **Dual Storage**: Both SQL and Vector DB considered?
- [ ] **Audit Trail**: Are actions properly logged?
- [ ] **Security**: No unauthorized agent spawning or privilege escalation?
- [ ] **Documentation**: Updated docs and docstrings?
- [ ] **Tests**: Coverage for new logic?

## 🌐 Community

### Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Architecture RFCs, philosophical debates
- **Discord**: Real-time collaboration (respect the hierarchy!)
- **Email**: security@agentium.dev (for vulnerabilities only)

### Recognition

Contributors are recognized in our `CONTRIBUTORS.md` and categorized by tier:

- **Head Contributors**: Architectural vision, constitutional amendments
- **Council Contributors**: Feature development, governance logic
- **Lead Contributors**: Integrations, tooling
- **Task Contributors**: Bug fixes, documentation, testing

### Becoming a Maintainer

Long-term contributors may be nominated to the Council (maintainer team):

1. Consistent quality contributions over 3+ months
2. Deep understanding of constitutional principles
3. Community endorsement (democratic vote)
4. Commitment to the sovereignty mission

## 🔒 Security

### Reporting Vulnerabilities

**DO NOT** open public issues for security problems.

Email: security@agentium.dev

Include:

- Description of vulnerability
- Steps to reproduce
- Potential impact on agent sovereignty
- Suggested fix (if any)

Response within 48 hours guaranteed.

### Security Principles

Contributions must never:

- Allow Task agents (3xxxx) to spawn other agents
- Bypass the Constitutional Guard
- Expose private keys or model provider credentials
- Enable remote code execution without Council oversight

## 📚 Resources

### Documentation

- [TODO LIST](docs/todo.md)

### Learning Path

**New to Democratic AI?**

1. Read `constitution_sample.md`
2. Study the voting logic in `backend/models/entities/voting.py`
3. Review closed PRs tagged `good first issue`

**Backend Focus**:

1. Understand the dual-storage architecture
2. Learn the hierarchical ID system
3. Study the Constitutional Guard implementation

**Frontend Focus**:

1. Review the Agent Tree visualization
2. Understand the voting interface flow
3. Study Zustand store organization

## ⚡ Quick Commands

```bash
# Full test suite
make test

# Lint code
make lint

# Type check
make type-check

# Reset environment
make reset

# Seed with test data
make seed
```

---

## ⚙️ Environment Variables

All backend configuration is managed through environment variables in `backend/.env`. A fully documented example is provided in [`backend/.env.example`](backend/.env.example).

### Setup

1. Copy the example file:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Generate fresh secrets:
   ```bash
   cd backend
   python ./scripts/gen_secrets.py
   ```

3. Fill in any external API keys as needed.

### Reference Table

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_ORIGINS` | Comma-separated list of allowed frontend origins | `http://localhost:3000,http://localhost:5173` |
| `SECRET_KEY` | Secret key for JWT signing (generate new for production) | *(required)* |
| `ENCRYPTION_KEY` | Encryption key for sensitive data (generate new for production) | *(required)* |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://agentium:agentium@postgres:5432/agentium` |
| `DATABASE_POOL_SIZE` | SQLAlchemy pool size (checked-out connections kept open) | `20` |
| `DATABASE_MAX_OVERFLOW` | Extra connections allowed beyond `DATABASE_POOL_SIZE` | `10` |
| `DATABASE_POOL_TIMEOUT` | Seconds to wait for a free connection before erroring | `30` |
| `DATABASE_POOL_RECYCLE` | Seconds before an idle connection is recycled | `1800` |
| `CHROMA_HOST` | ChromaDB hostname | `chromadb` |
| `CHROMA_PORT` | ChromaDB port | `8000` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | Celery message broker (Redis) | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend (Redis) | `redis://redis:6379/0` |
| `MINIO_ROOT_USER` | MinIO root username (**required** — generate via `make setup`; never `minioadmin`) | *none (generated)* |
| `MINIO_ROOT_PASSWORD` | MinIO root password (**required** — generate via `make setup`; rotate on first deploy) | *none (generated)* |
| `S3_ENDPOINT` | S3-compatible object storage endpoint | `http://minio:9000` |
| `S3_BUCKET_NAME` | Default S3 bucket name | `agentium-media` |
| `AWS_ACCESS_KEY_ID` | AWS access key (mirrors `MINIO_ROOT_USER`) | `${MINIO_ROOT_USER}` |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (mirrors `MINIO_ROOT_PASSWORD`) | `${MINIO_ROOT_PASSWORD}` |
| `VOICE_JWT_SECRET` | Secret for Voice WebSocket JWT tokens | *(required)* |
| `VOICE_TOKEN_DURATION_MINUTES` | Voice bridge session token duration | `30` |
| `FEDERATION_ENABLED` | Enable federation between Agentium instances | `false` |
| `FEDERATION_INSTANCE_NAME` | Human-readable name for this instance | `Agentium-Primary` |
| `FEDERATION_INSTANCE_URL` | Public URL of this instance | *(required if federation enabled)* |
| `FEDERATION_SHARED_SECRET` | Shared secret for instance-to-instance auth | *(required if federation enabled)* |
| `TAVILY_API_KEY` | Tavily search API key (free tier Tanzil) | *(optional — falls back to DuckDuckGo)* |
| `BRAVE_SEARCH_API_KEY` | Brave Search API key (2k req/month free) | *(optional — falls back to DuckDuckGo)* |
| `SERPAPI_KEY` | SerpApi search API key | *(optional — falls back to DuckDuckGo)* |
| `STOCK_API_KEY` | Financial data API key | *(optional — uses yfinance)* |
| `DEFAULT_BROKER_EMAIL` | Default broker contact email | `broker@yourdomain.com` |
| `TESTING` | Set to `True` to disable external AI providers during tests | `False` |

---

## 🏛️ Final Note

Agentium is more than software — it's an experiment in digital democracy. Every contribution shapes how AI systems will govern themselves and serve humanity.

**Contribute with sovereignty. Code with purpose. Govern with wisdom.**

---

_This Constitution (CONTRIBUTING.md) may be amended through Pull Request with 60% Council approval and Head ratification._

**License**: Apache 2.0 (see LICENSE)

**Built with ❤️ and purpose by the Agentium Community**
