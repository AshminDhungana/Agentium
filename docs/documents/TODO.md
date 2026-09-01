# Agentium — Complete System Verification & Improvement Backlog

> **Purpose**: Systematic part-by-part verification of every Agentium subsystem.
> Work through each section sequentially. Mark items `[x]` when verified working,
> `[/]` when in-progress, `[ ]` when not yet checked.

---

## Table of Contents

1. [Infrastructure & Docker Compose](#1-infrastructure--docker-compose)
2. [Authentication & User Management](#2-authentication--user-management)
3. [Database & Migrations](#3-database--migrations)
4. [API Gateway & Middleware](#4-api-gateway--middleware)
5. [Model Provider & LLM Integration](#5-model-provider--llm-integration)
6. [Agent System & Orchestration](#6-agent-system--orchestration)
7. [Constitution & Governance](#7-constitution--governance)
8. [Tool System](#8-tool-system)
9. [Chat System & Context Management](#9-chat-system--context-management)
10. [Task System & Scheduling](#10-task-system--scheduling)
11. [Channels & Messaging Bridges](#11-channels--messaging-bridges)
12. [Frontend — Pages & Components](#12-frontend--pages--components)
13. [WebSocket & Real-Time Events](#13-websocket--real-time-events)
14. [Monitoring, Logging & Audit](#14-monitoring-logging--audit)
15. [Voice System](#15-voice-system)
16. [Federation & Multi-Instance](#16-federation--multi-instance)
17. [MCP Tools & Marketplace](#17-mcp-tools--marketplace)
18. [Workflows & Automation](#18-workflows--automation)
19. [Security & Safety](#19-security--safety)
20. [Celery Workers & Background Tasks](#20-celery-workers--background-tasks)
21. [Production Readiness](#21-production-readiness)
22. [Log & Audit Verification](#22-log--audit-verification)
23. [Dependency Updates](#23-dependency-updates)

---

## 1. Infrastructure & Docker Compose

> **Files**: `docker-compose.yml`, `docker-compose.test.yml`, `docker-compose.remote-executor.yml`, `Makefile`, `.env.example`

- [x] **1.1 — PostgreSQL Container**
  - [x] 1.1.1 — Container starts cleanly with `docker compose up postgres`
  - [x] 1.1.2 — `pg_isready -U agentium` healthcheck passes
  - [x] 1.1.3 — `pg_stat_statements` extension loads (`shared_preload_libraries` flag works)
  - [x] 1.1.4 — Slow-query logging at ≥500ms threshold produces output in `docker compose logs postgres`
  - [x] 1.1.5 — Data persists across container restarts via `postgres_data` volume

- [x] **1.2 — ChromaDB Container**
  - [x] 1.2.1 — Container starts and healthcheck passes (TCP probe on port 8000)
  - [x] 1.2.2 — Port mapping correct: host `8001` → container `8000`
  - [x] 1.2.3 — Memory limits enforced (2G limit / 1G reservation)
  - [x] 1.2.4 — Vector data persists via `chroma_data` volume
  - [x] 1.2.5 — Backend can connect and create/query collections

- [x] **1.3 — Redis Container**
  - [x] 1.3.1 — Container starts, `redis-cli ping` returns `PONG`
  - [x] 1.3.2 — Custom `redis.conf` mounts correctly from `./redis/redis.conf`
  - [x] 1.3.3 — Redis is accessible as Celery broker (`redis://redis:6379/0`)
  - [x] 1.3.4 — Data persists via `redis_data` volume

- [x] **1.4 — MinIO Object Storage**
  - [x] 1.4.1 — Container starts, console accessible at `http://localhost:9001`
  - [x] 1.4.2 — S3-compatible API responds on port `9000`
  - [x] 1.4.3 — Backend `storage_service.py` can upload/download files
  - [x] 1.4.4 — Fallback to local disk when MinIO is unreachable
  - [x] 1.4.5 — Default credential detection warns/blocks (`security_checks.py`)

- [x] **1.5 — Backend (FastAPI) Container**
  - [x] 1.5.1 — `Dockerfile` / `Dockerfile.privileged` builds without errors
  - [x] 1.5.2 — Container starts, API responds on port `8000`
  - [x] 1.5.3 — All environment variables from `.env.example` are documented and applied
  - [x] 1.5.4 — Host workspace bind mounts (`/host`, `/host_home`) work on Windows

- [x] **1.6 — Celery Worker & Beat Containers**
  - [x] 1.6.1 — Worker container starts and connects to Redis broker
  - [x] 1.6.2 — Beat container starts and schedules fire on time
  - [x] 1.6.3 — Worker discovers all task modules in `include` list
  - [x] 1.6.4 — `celery inspect active` shows running workers

- [x] **1.7 — WhatsApp Bridge Container**
  - [x] 1.7.1 — Bridge container starts on port `3001`
  - [x] 1.7.2 — QR code generation works for pairing
  - [x] 1.7.3 — Webhook callbacks to backend are delivered

- [x] **1.8 — Docker Network & Compose Orchestration**
  - [x] 1.8.1 — `agentium-network` is created and all services are attached
  - [x] 1.8.2 — `docker compose up` starts all services without errors
  - [x] 1.8.3 — `docker compose down -v` cleanly tears everything down
  - [x] 1.8.4 — Service dependency ordering (depends_on with healthchecks) works correctly

---

## 2. Authentication & User Management

> **Files**: `backend/core/auth.py`, `backend/api/routes/auth.py`, `backend/models/entities/user.py`, `backend/services/auth.py`, `backend/api/middleware/auth.py`, `backend/services/rbac_service.py`, `backend/api/routes/rbac.py`, `frontend/src/store/authStore.ts`, `frontend/src/services/auth.ts`

- [x] **2.1 — User Registration**
  - [x] 2.1.1 — `POST /api/v1/auth/register` creates new user
  - [x] 2.1.2 — Duplicate username/email returns proper error
  - [x] 2.1.3 — Password is hashed before storage (verify `User.hash_password`)
  - [x] 2.1.4 — Frontend `SignupPage.tsx` form submits correctly
  - [x] 2.1.5 — Pending user flow works (admin approval if configured)

- [x] **2.2 — Login & JWT Tokens**
  - [x] 2.2.1 — `POST /api/v1/auth/login` returns valid JWT token
  - [x] 2.2.2 — Token contains correct claims (user_id, username, is_admin, exp)
  - [x] 2.2.3 — Token refresh mechanism works
  - [x] 2.2.4 — Expired token returns 401 Unauthorized
  - [x] 2.2.5 — Frontend `LoginPage.tsx` stores token in `authStore`

- [x] **2.3 — Default Admin Bootstrap**
  - [x] 2.3.1 — `create_default_admin()` in `main.py` creates admin on first boot
  - [x] 2.3.2 — Default admin credentials work (username: `admin`, password: `admin`)
  - [x] 2.3.3 — Admin user has `is_admin=True`, `is_active=True`, `is_pending=False`

- [x] **2.4 — RBAC (Role-Based Access Control)**
  - [x] 2.4.1 — `GET/POST /api/v1/rbac/roles` CRUD works
  - [x] 2.4.2 — Role permissions are enforced on protected endpoints
  - [x] 2.4.3 — `RBACManagement.tsx` page loads and displays roles
  - [x] 2.4.4 — Admin-only routes reject non-admin users

- [x] **2.5 — Session Management**
  - [x] 2.5.1 — `SessionLimitMiddleware` enforces max concurrent sessions
  - [x] 2.5.2 — Frontend `authStore.ts` handles logout / token invalidation
  - [x] 2.5.3 — `checkAuth()` on page load correctly restores session

- [x] **2.6 — User Management Page**
  - [x] 2.6.1 — `Usermanagement.tsx` lists all users
  - [x] 2.6.2 — Admin can activate/deactivate users
  - [x] 2.6.3 — Admin can change user roles
  - [x] 2.6.4 — User deletion works correctly

---

## 3. Database & Migrations

> **Files**: `backend/models/database.py`, `backend/alembic/`, `backend/models/entities/`

- [x] **3.1 — Database Initialization**
  - [x] 3.1.1 — `init_db()` creates all tables via SQLAlchemy `create_all()`
  - [x] 3.1.2 — All 40+ entity models import correctly in `entities/__init__.py`
  - [x] 3.1.3 — `check_health()` returns healthy status
  - [x] 3.1.4 — Connection pooling works under concurrent requests

- [x] **3.2 — Alembic Migrations**
  - [x] 3.2.1 — `alembic upgrade head` applies all migrations without error
  - [x] 3.2.2 — `alembic downgrade -1` rolls back cleanly
  - [x] 3.2.3 — Migration scripts match current model definitions
  - [x] 3.2.4 — No orphaned or conflicting migration heads

- [x] **3.3 — Key Entity Models**
  - [x] 3.3.1 — `Agent` model: all statuses (INITIALIZING, ACTIVE, SUSPENDED, TERMINATED, etc.) work
  - [x] 3.3.2 — `Task` model: all task types and statuses function correctly
  - [x] 3.3.3 — `Constitution` model: articles, amendments, ethos records persist
  - [x] 3.3.4 — `User` / `UserModelConfig` / `UserPreference` relationships work
  - [x] 3.3.5 — `AuditLog` / `ViolationReport` records are immutable after creation
  - [x] 3.3.6 — `Checkpoint` model: save/restore works
  - [x] 3.3.7 — `Workflow` / `ScheduledTask` models work with Celery
  - [x] 3.3.8 — `Voting` / `VoteRecord` / `Proposal` models tally correctly
  - [x] 3.3.9 — `Channel` / `ChannelMessage` models store bridge messages
  - [x] 3.3.10 — `MCPTool` / `ToolVersion` / `ToolStagingArea` models support tool lifecycle

- [x] **3.4 — Database Maintenance**
  - [x] 3.4.1 — `DatabaseMaintenanceService` vacuum and cleanup tasks run
  - [x] 3.4.2 — `db_maintenance.py` periodic tasks don't lock tables excessively
  - [x] 3.4.3 — Connection pool doesn't leak under load

---

## 4. API Gateway & Middleware

> **Files**: `backend/main.py`, `backend/core/middleware.py`, `backend/core/security_middleware.py`, `backend/core/timing_middleware.py`, `backend/core/observer_middleware.py`

- [x] **4.1 — Application Startup (Lifespan)**
  - [x] 4.1.1 — `lifespan()` in `main.py` completes all init steps without error
  - [x] 4.1.2 — Security startup checks run (`run_security_startup_checks`)
  - [x] 4.1.3 — Workspace config validation runs
  - [x] 4.1.4 — Constitution seed executes on first boot
  - [x] 4.1.5 — Persistent Council status check runs
  - [x] 4.1.6 — API Manager, Model Allocator, Token Optimizer initialize
  - [x] 4.1.7 — MCP Tool Bridge initializes (`init_bridge`)
  - [x] 4.1.8 — Pricing sync runs in background
  - [x] 4.1.9 — Idle Governance engine starts

- [x] **4.2 — Route Registration**
  - [x] 4.2.1 — All 44 route modules register without import errors
  - [x] 4.2.2 — `GET /openapi.json` returns valid OpenAPI spec
  - [x] 4.2.3 — `GET /docs` Swagger UI loads with all endpoints
  - [x] 4.2.4 — Route prefixes (`/api/v1/`) are consistent

- [x] **4.3 — Middleware Stack**
  - [x] 4.3.1 — `IPBlocklistMiddleware` blocks IPs in Redis blocklist
  - [x] 4.3.2 — `PayloadSizeLimitMiddleware` rejects oversized requests (413)
  - [x] 4.3.3 — `ErrorCounterMiddleware` tracks 4xx/5xx error rates
  - [x] 4.3.4 — `RateLimitMiddleware` enforces per-user/per-IP limits via Redis
  - [x] 4.3.5 — `SessionLimitMiddleware` caps concurrent sessions
  - [x] 4.3.6 — `InputSanitizationMiddleware` strips XSS payloads
  - [x] 4.3.7 — `ObserverReadOnlyMiddleware` blocks writes for observer-role users
  - [x] 4.3.8 — `TimingMiddleware` logs request duration and regression gates
  - [x] 4.3.9 — CORS middleware allows configured origins

- [x] **4.4 — Error Handling**
  - [x] 4.4.1 — Custom exceptions (BadRequest, Unauthorized, Forbidden, NotFound, Conflict, TooLarge, RateLimit, InternalServerError, ServiceUnavailable) return correct HTTP codes
  - [x] 4.4.2 — Unhandled exceptions return 500 with masked details (no stack trace in production)

---

## 5. Model Provider & LLM Integration

> **Files**: `backend/services/model_provider.py`, `backend/core/llm_client.py`, `backend/services/pricing_sync_service.py`, `backend/services/model_allocation.py`, `backend/services/token_optimizer.py`, `backend/api/routes/models.py`, `frontend/src/pages/ModelsPage.tsx`, `frontend/src/services/models.ts`

- [x] **5.1 — Model Configuration**
  - [x] 5.1.1 — `POST /api/v1/models/configs` creates a new model config (API key + provider)
  - [x] 5.1.2 — `GET /api/v1/models/configs` returns user's model configs
  - [x] 5.1.3 — API keys are stored encrypted (verify `api_key_manager.py`)
  - [x] 5.1.4 — Supported providers: OpenAI, Anthropic, Google, Groq, DeepSeek, Mistral, OpenRouter, xAI, local
  - [x] 5.1.5 — `ModelsPage.tsx` add/edit/delete model configs UI works

- [x] **5.2 — LLM Request Flow**
  - [x] 5.2.1 — `ModelService.generate()` sends prompt to correct provider
  - [x] 5.2.2 — Streaming responses work (SSE / chunked response)
  - [x] 5.2.3 — Token counting is accurate
  - [x] 5.2.4 — System prompt injection (constitution + ethos + context) works
  - [x] 5.2.5 — JSON/structured output mode works when requested

- [x] **5.3 — Model Redirect on First Login**
  - [x] 5.3.1 — `useModelRedirect` hook redirects to `/models` when no configs exist
  - [x] 5.3.2 — Redirect fires only once per login session
  - [x] 5.3.3 — After adding a model, redirect stops for the session

- [x] **5.4 — Pricing & Cost Tracking**
  - [x] 5.4.1 — `PricingSyncService.sync_prices()` fetches current model prices
  - [x] 5.4.2 — Token cost per query is calculated and logged
  - [x] 5.4.3 — Pricing cache loads from DB on startup

- [ ] **5.5 — Model Allocation & Token Optimization**
  - [ ] 5.5.1 — `model_allocator` selects optimal model per task complexity
  - [ ] 5.5.2 — `token_optimizer` trims context to fit model's context window
  - [ ] 5.5.3 — Budget tracking per user / per day works

- [ ] **5.6 — Provider Error Handling**
  - [ ] 5.6.1 — 429 rate-limit errors trigger exponential backoff with jitter
  - [ ] 5.6.2 — 5xx provider errors are retried gracefully
  - [ ] 5.6.3 — Invalid API key returns clear error message
  - [ ] 5.6.4 — Provider timeout doesn't crash the system

---

## 6. Agent System & Orchestration

> **Files**: `backend/services/agent_orchestrator.py`, `backend/models/entities/agents.py`, `backend/services/auto_delegation_service.py`, `backend/services/agent_registry.py`, `backend/services/critic_agents.py`, `backend/services/decision_engine.py`, `backend/services/persistent_council.py`, `backend/services/idle_governance.py`, `frontend/src/pages/AgentsPage.tsx`

- [ ] **6.1 — Agent CRUD**
  - [ ] 6.1.1 — Genesis creates the initial Head of Council agent (agent ID 00001)
  - [ ] 6.1.2 — Council members (10001–19999) are seeded or spawned
  - [ ] 6.1.3 — Lead agents (20001–29999) can be spawned by council
  - [ ] 6.1.4 — Task agents (30001–69999) can be spawned by leads
  - [ ] 6.1.5 — Agent status transitions follow the lifecycle state machine
  - [ ] 6.1.6 — `AgentsPage.tsx` displays agents with correct statuses

- [ ] **6.2 — Agent Orchestration**
  - [ ] 6.2.1 — `AgentOrchestrator` routes requests to the correct agent tier
  - [ ] 6.2.2 — Complexity analysis assigns delegation scores (1–10)
  - [ ] 6.2.3 — Auto-delegation routes: score 1–3 → Task, 4–6 → Lead, 7–10 → Council
  - [ ] 6.2.4 — Multi-step reasoning chains execute correctly
  - [ ] 6.2.5 — Agent can use multiple tools in sequence

- [ ] **6.3 — Critic Agents (Judiciary)**
  - [ ] 6.3.1 — Code Critic (7xxxx) reviews generated code for syntax/security
  - [ ] 6.3.2 — Output Critic (8xxxx) verifies output alignment with intent
  - [ ] 6.3.3 — Plan Critic (9xxxx) validates DAG soundness
  - [ ] 6.3.4 — Critic feedback is incorporated before final response

- [ ] **6.4 — Persistent Council & Idle Governance**
  - [ ] 6.4.1 — Council agents activate during idle periods
  - [ ] 6.4.2 — System Optimizer agent runs maintenance tasks
  - [ ] 6.4.3 — Strategic Planner agent schedules future work
  - [ ] 6.4.4 — Health Monitor agent checks system health
  - [ ] 6.4.5 — Idle governance doesn't interfere with active tasks
  - [ ] 6.4.6 — Token budget for idle tasks respects `DAILY_TOKEN_BUDGET_USD`

- [ ] **6.5 — Agent Initialization Service**
  - [ ] 6.5.1 — `InitializationService` sets up all required agents on first boot
  - [ ] 6.5.2 — Agent capabilities are registered in capability registry
  - [ ] 6.5.3 — Missing agents are detected and re-created

---

## 7. Constitution & Governance

> **Files**: `backend/models/entities/constitution.py`, `backend/services/amendment_service.py`, `backend/core/constitutional_guard.py`, `backend/core/persona.py`, `backend/tools/ethos_tool.py`, `backend/tools/governance_tool.py`, `backend/services/knowledge_governance.py`, `backend/services/governance_command_service.py`, `backend/api/routes/voting.py`, `frontend/src/pages/ConstitutionPage.tsx`, `frontend/src/pages/VotingPage.tsx`

- [ ] **7.1 — Constitution Management**
  - [ ] 7.1.1 — Constitution is seeded on first boot (preamble, articles, prohibited actions)
  - [ ] 7.1.2 — `GET /api/v1/constitution` returns current constitution
  - [ ] 7.1.3 — `ConstitutionPage.tsx` displays constitution articles
  - [ ] 7.1.4 — Sovereign preferences are stored and applied

- [ ] **7.2 — Amendment Process**
  - [ ] 7.2.1 — `POST /api/v1/voting/proposals` creates amendment proposals
  - [ ] 7.2.2 — Council agents can vote on proposals
  - [ ] 7.2.3 — 60% quorum rule is enforced
  - [ ] 7.2.4 — Head of Council veto power works
  - [ ] 7.2.5 — Approved amendments modify the active constitution
  - [ ] 7.2.6 — `VotingPage.tsx` displays proposals and voting UI

- [ ] **7.3 — Constitutional Guard**
  - [ ] 7.3.1 — Tier 1 guard (SQL-based rule matching) blocks prohibited actions
  - [ ] 7.3.2 — Tier 2 guard (vector semantic matching via ChromaDB) catches nuanced violations
  - [ ] 7.3.3 — Blocked actions are logged to `AuditLog` with category `CONSTITUTIONAL`
  - [ ] 7.3.4 — `VOTE_REQUIRED` actions trigger council vote flow

- [ ] **7.4 — Ethos System**
  - [ ] 7.4.1 — `ethos_tool.py` reads and applies ethos principles
  - [ ] 7.4.2 — Ethos is injected into LLM system prompts
  - [ ] 7.4.3 — Agent behavior adapts based on learned ethos
  - [ ] 7.4.4 — Persona (`persona.py`) guides agent communication style

---

## 8. Tool System

> **Files**: `backend/core/tool_registry.py`, `backend/core/tool_runner.py`, `backend/tools/`, `backend/services/tool_factory.py`, `backend/services/tool_creation_service.py`, `backend/services/tool_versioning.py`, `backend/services/tool_analytics.py`, `backend/services/tool_deprecation.py`, `backend/services/tool_marketplace.py`, `frontend/src/pages/ToolMarketplacePage.tsx`

- [ ] **8.1 — Tool Registry**
  - [ ] 8.1.1 — `tool_registry` discovers and registers all built-in tools at startup
  - [ ] 8.1.2 — `GET /api/v1/tools` returns list of available tools
  - [ ] 8.1.3 — Each tool has valid JSON Schema for parameters

- [ ] **8.2 — Individual Tool Verification**
  - [ ] 8.2.1 — `web_search_tool.py` — web search executes and returns results
  - [ ] 8.2.2 — `web_fetch_tool.py` — URL content fetch works
  - [ ] 8.2.3 — `web_crawler_tool.py` — web crawling follows links
  - [ ] 8.2.4 — `file_tool.py` — file read/write/list operations work
  - [ ] 8.2.5 — `text_editor_tool.py` — text editing operations work
  - [ ] 8.2.6 — `shell_tool.py` / `code_execution_tool.py` — code execution in sandbox
  - [ ] 8.2.7 — `browser_tool.py` / `nodriver_tool.py` — browser automation works
  - [ ] 8.2.8 — `git_tool.py` — git operations (clone, commit, push) work
  - [ ] 8.2.9 — `deep_think_tool.py` — extended reasoning chains work
  - [ ] 8.2.10 — `code_analyzer_tool.py` — code analysis returns insights
  - [ ] 8.2.11 — `data_transform_tool.py` — data transformation works
  - [ ] 8.2.12 — `embedding_tool.py` — text embeddings generate correctly
  - [ ] 8.2.13 — `vector_db_tool.py` — vector store read/write works
  - [ ] 8.2.14 — `http_api_tool.py` — HTTP API calls work
  - [ ] 8.2.15 — `desktop_tool.py` — desktop automation works (host OS)
  - [ ] 8.2.16 — `host_os_tool.py` — host OS operations work
  - [ ] 8.2.17 — `task_management_tool.py` — task creation/update via tools works
  - [ ] 8.2.18 — `skill_creator_tool.py` — skill creation works
  - [ ] 8.2.19 — `tool_creator_tool.py` — dynamic tool creation works
  - [ ] 8.2.20 — `tool_search_tool.py` — tool search/discovery works
  - [ ] 8.2.21 — `user_preference_tool.py` — user preference management works
  - [ ] 8.2.22 — `clarification_tool.py` — clarification requests work
  - [ ] 8.2.23 — `governance_tool.py` — governance actions via tools work
  - [ ] 8.2.24 — `ethos_tool.py` — ethos read/write works
  - [ ] 8.2.25 — `remote_exec_tool.py` — remote execution works
  - [ ] 8.2.26 — `mcp_agent_tools.py` — MCP agent tool bridge works

- [ ] **8.3 — Tool Creation & Marketplace**
  - [ ] 8.3.1 — `tool_creation_service.py` — dynamic tool creation from natural language
  - [ ] 8.3.2 — Generated tools are stored in `tools/generated/`
  - [ ] 8.3.3 — Tool staging and review flow works
  - [ ] 8.3.4 — `ToolMarketplacePage.tsx` lists available tools
  - [ ] 8.3.5 — Tool install/uninstall from marketplace works
  - [ ] 8.3.6 — Tool versioning and rollback works (`tool_versioning.py`)
  - [ ] 8.3.7 — Tool deprecation notices work (`tool_deprecation.py`)
  - [ ] 8.3.8 — Tool analytics (usage tracking) works (`tool_analytics.py`)

- [ ] **8.4 — Tool Execution Safety**
  - [ ] 8.4.1 — `execution_guard.py` sandboxes dangerous operations
  - [ ] 8.4.2 — Tool parameter validation rejects invalid inputs
  - [ ] 8.4.3 — Tool timeout limits prevent runaway execution
  - [ ] 8.4.4 — Remote executor sandbox (`remote_executor/sandbox.py`) isolates code

---

## 9. Chat System & Context Management

> **Files**: `backend/services/chat_service.py`, `backend/services/chat_context.py`, `backend/services/context_manager.py`, `backend/services/chat_prune_service.py`, `backend/services/clarification_service.py`, `backend/services/clarification_handler.py`, `backend/services/overflow_recovery.py`, `backend/api/routes/chat.py`, `frontend/src/pages/ChatPage.tsx`, `frontend/src/store/chatStore.ts`, `frontend/src/services/chatApi.ts`, `frontend/src/services/chatStream.ts`

- [ ] **9.1 — Chat API**
  - [ ] 9.1.1 — `POST /api/v1/chat/messages` sends message and receives agent response
  - [ ] 9.1.2 — Streaming response works (SSE / chunked transfer)
  - [ ] 9.1.3 — Chat history is persisted to database
  - [ ] 9.1.4 — `GET /api/v1/chat/conversations` lists conversations
  - [ ] 9.1.5 — `GET /api/v1/chat/conversations/{id}/messages` returns message history

- [ ] **9.2 — Context Management**
  - [ ] 9.2.1 — `ChatContext` builds prompt with constitution + ethos + history
  - [ ] 9.2.2 — `ContextManager` manages context window within token limits
  - [ ] 9.2.3 — Conversation pruning/summarization preserves essential context
  - [ ] 9.2.4 — Overflow recovery handles context window exceeded errors

- [ ] **9.3 — Chat Frontend**
  - [ ] 9.3.1 — `ChatPage.tsx` renders messages with proper formatting (markdown, code blocks)
  - [ ] 9.3.2 — Streaming tokens appear in real-time (typing indicator)
  - [ ] 9.3.3 — Tool call results display inline in chat
  - [ ] 9.3.4 — File upload in chat works
  - [ ] 9.3.5 — Conversation switching works without losing state
  - [ ] 9.3.6 — New conversation creation works
  - [ ] 9.3.7 — Chat history reload after page refresh works
  - [ ] 9.3.8 — `chatStore.ts` state management is consistent

- [ ] **9.4 — Clarification System**
  - [ ] 9.4.1 — Agent requests clarification when uncertain
  - [ ] 9.4.2 — User can respond to clarification requests
  - [ ] 9.4.3 — Clarification context is incorporated into subsequent responses

---

## 10. Task System & Scheduling

> **Files**: `backend/models/entities/task.py`, `backend/models/entities/scheduled_task.py`, `backend/services/task_state_machine.py`, `backend/api/routes/tasks.py`, `backend/services/tasks/task_executor.py`, `frontend/src/pages/TasksPage.tsx`, `frontend/src/services/tasks.ts`

- [ ] **10.1 — Task CRUD**
  - [ ] 10.1.1 — `POST /api/v1/tasks` creates a new task
  - [ ] 10.1.2 — `GET /api/v1/tasks` returns task list with pagination
  - [ ] 10.1.3 — `GET /api/v1/tasks/{id}` returns task details
  - [ ] 10.1.4 — `PATCH /api/v1/tasks/{id}` updates task
  - [ ] 10.1.5 — Task types (CODE, RESEARCH, ANALYSIS, etc.) are handled correctly
  - [ ] 10.1.6 — Task priorities (LOW, MEDIUM, HIGH, CRITICAL) affect scheduling

- [ ] **10.2 — Task State Machine**
  - [ ] 10.2.1 — State transitions: PENDING → IN_PROGRESS → COMPLETED / FAILED
  - [ ] 10.2.2 — Invalid state transitions are rejected
  - [ ] 10.2.3 — Task escalation from Task → Lead → Council works
  - [ ] 10.2.4 — Stalled task detection and recovery works

- [ ] **10.3 — Task Execution**
  - [ ] 10.3.1 — Celery `task_executor.py` processes tasks asynchronously
  - [ ] 10.3.2 — Agent is assigned and executes the task
  - [ ] 10.3.3 — Tool calls during task execution work
  - [ ] 10.3.4 — Task results are stored correctly
  - [ ] 10.3.5 — Task failure creates proper error records

- [ ] **10.4 — Scheduled Tasks**
  - [ ] 10.4.1 — Cron-style scheduled tasks fire at correct intervals
  - [ ] 10.4.2 — One-time scheduled tasks execute and are cleaned up
  - [ ] 10.4.3 — Event-triggered tasks fire on condition match

- [ ] **10.5 — Task Frontend**
  - [ ] 10.5.1 — `TasksPage.tsx` displays tasks with status, priority, type filters
  - [ ] 10.5.2 — Task creation modal/form works
  - [ ] 10.5.3 — Task detail view shows execution log and results
  - [ ] 10.5.4 — Real-time task status updates via WebSocket
  - [ ] 10.5.5 — Task cancellation from UI works

---

## 11. Channels & Messaging Bridges

> **Files**: `backend/services/channel_manager.py`, `backend/services/channels/`, `backend/api/routes/channels.py`, `bridges/whatsapp/`, `frontend/src/pages/ChannelsPage.tsx`, `frontend/src/services/channelMessages.ts`, `frontend/src/services/channelMetrics.ts`

- [ ] **11.1 — Channel Management**
  - [ ] 11.1.1 — `GET /api/v1/channels` lists all configured channels
  - [ ] 11.1.2 — Channel creation (connect new bridge) works for each type
  - [ ] 11.1.3 — Channel health status reflects actual connectivity
  - [ ] 11.1.4 — `ChannelsPage.tsx` shows channels with health indicators

- [ ] **11.2 — WhatsApp Bridge**
  - [ ] 11.2.1 — QR code pairing flow works end-to-end
  - [ ] 11.2.2 — Incoming WhatsApp messages are received and processed
  - [ ] 11.2.3 — Agent responses are sent back via WhatsApp
  - [ ] 11.2.4 — Media messages (images, audio) are handled
  - [ ] 11.2.5 — Reconnection after disconnect works

- [ ] **11.3 — Other Channel Bridges**
  - [ ] 11.3.1 — Slack integration sends/receives messages
  - [ ] 11.3.2 — Telegram bot integration works
  - [ ] 11.3.3 — Discord gateway integration works
  - [ ] 11.3.4 — Email (IMAP/SMTP) send/receive works
  - [ ] 11.3.5 — SMS (Twilio) integration works
  - [ ] 11.3.6 — Signal / Google Chat / Teams / Matrix / iMessage / Zalo status

- [ ] **11.4 — Message Log**
  - [ ] 11.4.1 — `MessageLogPage.tsx` displays cross-channel message history
  - [ ] 11.4.2 — Messages are searchable and filterable
  - [ ] 11.4.3 — Message timestamps are correct across timezones

- [ ] **11.5 — Channel Health & Heartbeat**
  - [ ] 11.5.1 — Celery `check_channel_health` task runs every 5 minutes
  - [ ] 11.5.2 — `send_channel_heartbeat` keeps connections alive
  - [ ] 11.5.3 — Dead channels are marked and auto-reconnect is attempted
  - [ ] 11.5.4 — `channelHealth.ts` frontend utility shows correct status colors

---

## 12. Frontend — Pages & Components

> **Files**: `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/App.tsx`

- [ ] **12.1 — Routing & Navigation**
  - [ ] 12.1.1 — All routes in `App.tsx` resolve to correct pages
  - [ ] 12.1.2 — Protected routes redirect to `/login` when not authenticated
  - [ ] 12.1.3 — `MainLayout` renders sidebar navigation correctly
  - [ ] 12.1.4 — Lazy loading (`React.lazy`) works — no blank pages on first visit
  - [ ] 12.1.5 — Page transitions (AnimatePresence) are smooth

- [ ] **12.2 — Dashboard**
  - [ ] 12.2.1 — `Dashboard.tsx` loads without error
  - [ ] 12.2.2 — Stat cards display real data from API
  - [ ] 12.2.3 — `useDashboardData` hook fetches data correctly
  - [ ] 12.2.4 — Dashboard widgets update in real-time

- [ ] **12.3 — Settings Page**
  - [ ] 12.3.1 — `SettingsPage.tsx` renders all settings sections
  - [ ] 12.3.2 — User preferences save and persist
  - [ ] 12.3.3 — Dark/light theme toggle works globally
  - [ ] 12.3.4 — API key management settings work

- [ ] **12.4 — Sovereign Dashboard**
  - [ ] 12.4.1 — `SovereignDashboard.tsx` loads (admin-only route)
  - [ ] 12.4.2 — `SovereignRoute` component enforces sovereign access
  - [ ] 12.4.3 — System-wide controls function correctly

- [ ] **12.5 — Developer Portal**
  - [ ] 12.5.1 — `DeveloperPortalPage.tsx` renders API documentation
  - [ ] 12.5.2 — API key generation from portal works

- [ ] **12.6 — Skills Page**
  - [ ] 12.6.1 — `SkillsPage.tsx` lists agent skills
  - [ ] 12.6.2 — Skill creation/editing UI works
  - [ ] 12.6.3 — Skill RAG search works (`skill_rag.py` backend)

- [ ] **12.7 — AB Testing Page**
  - [ ] 12.7.1 — `ABTestingPage.tsx` displays experiments
  - [ ] 12.7.2 — Create/edit/delete experiments works
  - [ ] 12.7.3 — Experiment results and metrics display correctly

- [ ] **12.8 — Scaling Dashboard**
  - [ ] 12.8.1 — `ScalingDashboard.tsx` shows auto-scaling metrics
  - [ ] 12.8.2 — Manual scaling controls work

- [ ] **12.9 — Learning Impact Dashboard**
  - [ ] 12.9.1 — `LearningImpactDashboard.tsx` shows learning metrics
  - [ ] 12.9.2 — Data from `autonomous_learning.py` feeds correctly

- [ ] **12.10 — Shared Components**
  - [ ] 12.10.1 — `ErrorBoundary` catches and displays errors gracefully
  - [ ] 12.10.2 — `LoadingSpinner` displays during async operations
  - [ ] 12.10.3 — `HealthIndicator` shows correct system health
  - [ ] 12.10.4 — `BudgetControl.tsx` displays and controls token budget
  - [ ] 12.10.5 — `SignatureMark.tsx` / `SignatureWatermark.tsx` render correctly
  - [ ] 12.10.6 — Toast notifications (`useToast`) display and dismiss properly
  - [ ] 12.10.7 — `FlatMapAuthBackground.tsx` (Three.js) renders without WebGL errors

---

## 13. WebSocket & Real-Time Events

> **Files**: `backend/api/routes/websocket.py`, `backend/services/message_bus.py`, `backend/services/event_processor.py`, `frontend/src/store/websocketStore.ts`, `frontend/src/components/GlobalWebSocketProvider.tsx`

- [ ] **13.1 — WebSocket Connection**
  - [ ] 13.1.1 — `ws://localhost:8000/ws/chat` connection establishes
  - [ ] 13.1.2 — Authentication via token in WebSocket handshake works
  - [ ] 13.1.3 — Reconnection after disconnect with exponential backoff
  - [ ] 13.1.4 — `websocketStore.ts` manages connection state correctly
  - [ ] 13.1.5 — `GlobalWebSocketProvider` initializes connection on app mount

- [ ] **13.2 — Event Types**
  - [ ] 13.2.1 — `agent_status` events update agent state in real-time
  - [ ] 13.2.2 — `task_update` events reflect task progress
  - [ ] 13.2.3 — `chat_message` events deliver new messages
  - [ ] 13.2.4 — `chat_stream` events deliver streaming token chunks
  - [ ] 13.2.5 — `channel_status` events update channel health
  - [ ] 13.2.6 — `system_alert` events display notifications
  - [ ] 13.2.7 — `vote_update` events update voting UI
  - [ ] 13.2.8 — `tool_execution` events show tool call progress

- [ ] **13.3 — Message Bus**
  - [ ] 13.3.1 — `MessageBus` dispatches events to correct WebSocket clients
  - [ ] 13.3.2 — Redis pub/sub handles cross-worker event distribution
  - [ ] 13.3.3 — Event filtering per user/room works
  - [ ] 13.3.4 — `websocketReplay.ts` replays missed events on reconnection

- [ ] **13.4 — Event Processing**
  - [ ] 13.4.1 — `EventProcessor` handles threshold-based events
  - [ ] 13.4.2 — External API poll events fire correctly
  - [ ] 13.4.3 — Event triggers (cron, webhook, threshold) work

---

## 14. Monitoring, Logging & Audit

> **Files**: `backend/services/monitoring_service.py`, `backend/services/slow_query_service.py`, `backend/api/routes/monitoring_routes.py`, `backend/services/audit/`, `backend/api/routes/audit_routes.py`, `frontend/src/pages/MonitoringPage.tsx`, `frontend/src/services/monitoring.ts`, `frontend/src/services/errorReporting.ts`

- [ ] **14.1 — Monitoring Service**
  - [ ] 14.1.1 — `MonitoringService` collects system metrics (CPU, memory, disk)
  - [ ] 14.1.2 — `GET /api/v1/monitoring/metrics` returns current metrics
  - [ ] 14.1.3 — `GET /api/v1/monitoring/health` returns system health status
  - [ ] 14.1.4 — Anomaly detection identifies outliers correctly
  - [ ] 14.1.5 — SLA monitoring tracks uptime percentages

- [ ] **14.2 — Monitoring Frontend**
  - [ ] 14.2.1 — `MonitoringPage.tsx` loads all tabs (overview, agents, tasks, system)
  - [ ] 14.2.2 — Charts and graphs render with real data
  - [ ] 14.2.3 — Real-time metric updates via WebSocket
  - [ ] 14.2.4 — Alert history displays past alerts

- [ ] **14.3 — Audit System**
  - [ ] 14.3.1 — Security-relevant actions create `AuditLog` entries
  - [ ] 14.3.2 — Privilege escalations are logged
  - [ ] 14.3.3 — Tool invocations are logged with parameters
  - [ ] 14.3.4 — Auto-remediations are logged
  - [ ] 14.3.5 — `AuditLog` records are immutable (no update/delete)
  - [ ] 14.3.6 — `GET /api/v1/audit/logs` returns paginated audit trail

- [ ] **14.4 — Slow Query Analysis**
  - [ ] 14.4.1 — `slow_query_service.py` parses PostgreSQL slow query logs
  - [ ] 14.4.2 — Slow queries are written to `AuditLog`
  - [ ] 14.4.3 — `GET /api/v1/admin/slow-queries` returns populated data

- [ ] **14.5 — Frontend Error Reporting**
  - [ ] 14.5.1 — `errorReporting.ts` posts caught exceptions to `/api/v1/monitoring/frontend/errors`
  - [ ] 14.5.2 — Backend persists frontend error reports
  - [ ] 14.5.3 — `MonitoringPage.tsx` displays ingested frontend errors

- [ ] **14.6 — Structured Logging**
  - [ ] 14.6.1 — All agent steps emit structured JSON logs
  - [ ] 14.6.2 — Logs contain: `timestamp`, `request_id`, `step`, `duration_ms`, `tokens`, `status`
  - [ ] 14.6.3 — `request_id` correlates across HTTP → Celery → WebSocket

- [ ] **14.7 — Alert Manager**
  - [ ] 14.7.1 — `alert_manager.py` fires alerts on threshold breaches
  - [ ] 14.7.2 — Alerts are sent via configured channels (email, webhook, Slack)
  - [ ] 14.7.3 — Alert deduplication prevents notification storms

---

## 15. Voice System

> **Files**: `voice-bridge/main.py`, `voice-bridge/audio_source.py`, `voice-bridge/tts_engine.py`, `voice-bridge/vad.py`, `voice-bridge/wake_word.py`, `backend/services/audio_service.py`, `backend/services/whisper_cpp_service.py`, `backend/services/voice/`, `backend/api/routes/voice.py`, `backend/api/routes/audio.py`, `frontend/src/components/Voice*.tsx`, `frontend/src/services/voiceApi.ts`, `frontend/src/services/voiceBridge.ts`, `frontend/src/services/localVoice.ts`, `frontend/src/stores/voiceStore.ts`

- [ ] **15.1 — Voice Bridge**
  - [ ] 15.1.1 — `voice-bridge/main.py` starts and connects to backend
  - [ ] 15.1.2 — Audio source captures microphone input
  - [ ] 15.1.3 — VAD (Voice Activity Detection) correctly detects speech start/end
  - [ ] 15.1.4 — Wake word detection triggers listening
  - [ ] 15.1.5 — STT (Whisper) transcribes audio to text
  - [ ] 15.1.6 — TTS engine generates speech from text

- [ ] **15.2 — Voice API**
  - [ ] 15.2.1 — `POST /api/v1/voice/transcribe` accepts audio and returns text
  - [ ] 15.2.2 — `POST /api/v1/voice/synthesize` returns audio from text
  - [ ] 15.2.3 — Voice configuration (voice model, language) persists
  - [ ] 15.2.4 — Speaker profile management works

- [ ] **15.3 — Voice Frontend**
  - [ ] 15.3.1 — `VoiceModePanel.tsx` opens and shows voice UI
  - [ ] 15.3.2 — `VoiceOrb.tsx` visualizes active voice state
  - [ ] 15.3.3 — `VoiceIndicator.tsx` shows speaking/listening status
  - [ ] 15.3.4 — `VoiceDropdownPanel.tsx` provides voice controls
  - [ ] 15.3.5 — `VoiceSettingsModal.tsx` configures voice preferences
  - [ ] 15.3.6 — `localVoice.ts` handles browser-side speech recognition/synthesis
  - [ ] 15.3.7 — `voiceBridge.ts` manages WebSocket connection to voice bridge
  - [ ] 15.3.8 — `voiceStore.ts` state management is consistent

---

## 16. Federation & Multi-Instance

> **Files**: `backend/services/federation_service.py`, `backend/api/routes/federation.py`, `frontend/src/pages/FederationPage.tsx`, `frontend/src/services/federation.ts`

- [ ] **16.1 — Federation API**
  - [ ] 16.1.1 — `POST /api/v1/federation/peers` registers a peer instance
  - [ ] 16.1.2 — `GET /api/v1/federation/peers` lists connected peers
  - [ ] 16.1.3 — Peer heartbeat keeps connections alive (5-min interval)
  - [ ] 16.1.4 — Stale peer cleanup runs (hourly)

- [ ] **16.2 — Cross-Instance Communication**
  - [ ] 16.2.1 — Task delegation to peer instances works
  - [ ] 16.2.2 — Knowledge sharing between peers works
  - [ ] 16.2.3 — Agent migration between instances works

- [ ] **16.3 — Federation Frontend**
  - [ ] 16.3.1 — `FederationPage.tsx` displays connected peers
  - [ ] 16.3.2 — Peer connection/disconnection UI works
  - [ ] 16.3.3 — Cross-instance task status is visible

---

## 17. MCP Tools & Marketplace

> **Files**: `backend/services/mcp_client.py`, `backend/services/mcp_tool_bridge.py`, `backend/services/mcp_governance.py`, `backend/services/mcp_stats_service.py`, `backend/api/routes/mcp_tools.py`, `backend/models/entities/mcp_tool.py`, `frontend/src/services/mcpToolsApi.ts`

- [ ] **17.1 — MCP Client**
  - [ ] 17.1.1 — `mcp_client.py` connects to external MCP servers
  - [ ] 17.1.2 — Tool discovery from MCP servers works
  - [ ] 17.1.3 — Tool invocation via MCP protocol works
  - [ ] 17.1.4 — MCP tool bridge registers external tools in local registry

- [ ] **17.2 — MCP Governance**
  - [ ] 17.2.1 — Constitutional guard applies to MCP tool invocations
  - [ ] 17.2.2 — MCP tool access respects agent tier permissions
  - [ ] 17.2.3 — Usage statistics are tracked (`mcp_stats_service.py`)

- [ ] **17.3 — MCP API**
  - [ ] 17.3.1 — `GET /api/v1/mcp/tools` lists available MCP tools
  - [ ] 17.3.2 — `POST /api/v1/mcp/tools/invoke` executes MCP tool
  - [ ] 17.3.3 — MCP tool configuration (server URL, auth) works

---

## 18. Workflows & Automation

> **Files**: `backend/services/workflow_engine.py`, `backend/services/workflow_executor.py`, `backend/services/workflow_planner.py`, `backend/services/workflow_tools.py`, `backend/services/tasks/workflow_tasks.py`, `backend/api/routes/workflows.py`, `backend/models/entities/workflow.py`, `frontend/src/pages/WorkflowsPage.tsx`, `frontend/src/pages/WorkflowDesignerPage.tsx`

- [ ] **18.1 — Workflow CRUD**
  - [ ] 18.1.1 — `POST /api/v1/workflows` creates a new workflow definition
  - [ ] 18.1.2 — `GET /api/v1/workflows` lists workflows
  - [ ] 18.1.3 — `GET /api/v1/workflows/{id}` returns workflow details
  - [ ] 18.1.4 — Workflow DAG structure validates correctly

- [ ] **18.2 — Workflow Execution**
  - [ ] 18.2.1 — `WorkflowExecutor` runs DAG steps in correct order
  - [ ] 18.2.2 — Parallel branches execute concurrently
  - [ ] 18.2.3 — Step dependencies are respected
  - [ ] 18.2.4 — Workflow failure at one step handles rollback/retry
  - [ ] 18.2.5 — Celery `workflow_tasks.py` processes workflows asynchronously

- [ ] **18.3 — Workflow Frontend**
  - [ ] 18.3.1 — `WorkflowsPage.tsx` lists created workflows
  - [ ] 18.3.2 — `WorkflowDesignerPage.tsx` provides visual DAG editor
  - [ ] 18.3.3 — Drag-and-drop workflow building works
  - [ ] 18.3.4 — Workflow execution status updates in real-time

---

## 19. Security & Safety

> **Files**: `backend/core/security/`, `backend/core/security_checks.py`, `backend/core/security_middleware.py`, `backend/core/constitutional_guard.py`, `backend/core/uncertainty_detector.py`, `backend/core/response_validator.py`, `backend/services/rbac_service.py`

- [ ] **19.1 — Constitutional Guard & Ethos Enforcement**
  - [ ] 19.1.1 — Constitutional guardrails block prohibited actions
  - [ ] 19.1.2 — Ethos enforcement adapts agent behavior
  - [ ] 19.1.3 — Amendment service correctly modifies active rules
  - [ ] 19.1.4 — Constitution persona guides communication style

- [ ] **19.2 — Prompt Injection Resistance**
  - [ ] 19.2.1 — User-uploaded documents are sanitized
  - [ ] 19.2.2 — External search results are sanitized
  - [ ] 19.2.3 — Tool output injection is prevented
  - [ ] 19.2.4 — System prompt cannot be overridden by user input

- [ ] **19.3 — PII Scrubbing & Session Isolation**
  - [ ] 19.3.1 — PII detection identifies names, emails, phone numbers, SSNs
  - [ ] 19.3.2 — PII is redacted from agent responses and logs
  - [ ] 19.3.3 — User session data is isolated (no cross-session leakage)
  - [ ] 19.3.4 — Credential data is never logged in plain text

- [ ] **19.4 — Agent Tiering & Access Control**
  - [ ] 19.4.1 — Tier-based permissions are enforced (tools, actions per agent tier)
  - [ ] 19.4.2 — Task agents cannot escalate to council without proper flow
  - [ ] 19.4.3 — RBAC roles map correctly to API endpoint access

- [ ] **19.5 — Input Validation & Sanitization**
  - [ ] 19.5.1 — `InputSanitizationMiddleware` strips XSS payloads
  - [ ] 19.5.2 — SQL injection attempts are blocked
  - [ ] 19.5.3 — Path traversal in file operations is prevented
  - [ ] 19.5.4 — `PayloadSizeLimitMiddleware` rejects oversized requests

- [ ] **19.6 — Execution Safety**
  - [ ] 19.6.1 — `execution_guard.py` blocks dangerous shell commands
  - [ ] 19.6.2 — Code execution runs in sandboxed environment
  - [ ] 19.6.3 — File system access is restricted to workspace
  - [ ] 19.6.4 — Network access from sandboxed code is controlled

- [x] **19.7 — Uncertainty Detection**
  - [x] 19.7.1 — `uncertainty_detector.py` identifies low-confidence responses (6 triggers: tool_error, empty_result, missing_expected_fields, hallucinated_tool, conflicting_results, all_tools_failed)
  - [x] 19.7.2 — Agent requests clarification instead of hallucinating (ClarificationHandler with Task→Lead→Council→Head→Sovereign escalation, MAX_CLARIFICATION_ROUNDS=2)
  - [ ] 19.7.3 — `response_validator.py` checks output against schema

---

## 20. Celery Workers & Background Tasks

> **Files**: `backend/celery_app.py`, `backend/services/tasks/task_executor.py`, `backend/services/tasks/workflow_tasks.py`, `backend/services/tasks/reindex_knowledge.py`, `backend/services/idle_tasks/`

- [ ] **20.1 — Celery Configuration**
  - [ ] 20.1.1 — Celery connects to Redis broker on startup
  - [ ] 20.1.2 — All task modules in `include` list are importable
  - [ ] 20.1.3 — Beat schedule contains all expected periodic tasks
  - [ ] 20.1.4 — `BeatSessionLocal` DB session works for beat tasks

- [ ] **20.2 — Periodic Tasks (Beat Schedule)**
  - [ ] 20.2.1 — `health-check-every-5-minutes` — channel health checks fire
  - [ ] 20.2.2 — `cleanup-old-messages-daily` — old messages are purged
  - [ ] 20.2.3 — `imap-receiver-check` — email IMAP polling runs every 60s
  - [ ] 20.2.4 — `channel-heartbeat` — channel keepalive fires every 5 min
  - [ ] 20.2.5 — `constitution-daily-review` — daily constitution review runs
  - [ ] 20.2.6 — `weekly-knowledge-reindex` — ChromaDB reindex fires weekly
  - [ ] 20.2.7 — `idle-task-processor` — idle tasks process every 60s
  - [ ] 20.2.8 — `handle-task-escalation` — stalled task escalation runs every 5 min
  - [ ] 20.2.9 — `chat-history-prune-daily` — chat pruning runs daily
  - [ ] 20.2.10 — `sovereign-data-retention` — data retention policy runs daily
  - [ ] 20.2.11 — `auto-scale-check` — auto-scaling check every 10 min
  - [ ] 20.2.12 — `reasoning-watchdog` — stalled reasoning recovery every 60s
  - [ ] 20.2.13 — `federation-heartbeat` — peer heartbeat every 5 min
  - [ ] 20.2.14 — `federation-cleanup-stale` — stale peer cleanup hourly
  - [ ] 20.2.15 — `auto-escalation-timer` — escalation timeout check every 60s
  - [ ] 20.2.16 — `dependency-graph-processor` — DAG dependency processor every 30s
  - [ ] 20.2.17 — `agent-heartbeat` — agent liveness check every 60s
  - [ ] 20.2.18 — `crash-detection` — crashed agent detection every 30s
  - [ ] 20.2.19 — `self-diagnostic-daily` — system self-diagnostic daily
  - [ ] 20.2.20 — `critical-path-guardian` — critical path check every 2 min
  - [ ] 20.2.21 — `load-metrics-snapshot` — load metrics every 5 min
  - [ ] 20.2.22 — `predictive-scaling-check` — predictive scaling every 5 min
  - [ ] 20.2.23 — `knowledge-consolidation-weekly` — knowledge consolidation weekly
  - [ ] 20.2.24 — `performance-optimization-weekly` — performance optimization weekly
  - [ ] 20.2.25 — `threshold-event-check` — threshold event check every 60s
  - [ ] 20.2.26 — `external-api-poll` — external API poll every 60s
  - [ ] 20.2.27 — `anomaly-detection` — anomaly detection every 5 min
  - [ ] 20.2.28 — `sla-monitor` — SLA monitoring every 60s

- [ ] **20.3 — Task Execution Engine**
  - [ ] 20.3.1 — `task_executor.py` — all Celery task functions are importable and callable
  - [ ] 20.3.2 — Task results are stored in Redis backend
  - [ ] 20.3.3 — Task time limits (30 min) are enforced
  - [ ] 20.3.4 — Failed tasks retry with backoff (where configured)
  - [ ] 20.3.5 — `workflow_tasks.py` — workflow step execution works via Celery
  - [ ] 20.3.6 — `reindex_knowledge.py` — ChromaDB reindex task completes

- [ ] **20.4 — Loop & Runaway Detection**
  - [ ] 20.4.1 — Infinite tool-call loop detection triggers abort
  - [ ] 20.4.2 — Repeating identical tool calls are detected
  - [ ] 20.4.3 — Budget exhaustion during task execution terminates gracefully

---

## 21. Production Readiness

- **21.1 — [P2] Functional correctness** — agent completes representative tasks end-to-end; tool-call parameters are valid against schema; multi-step context is retained across a task's lifetime; output format/schema compliance is enforced; agent falls back gracefully when uncertain rather than hallucinating a result.
  - [x] **21.1.1 — End-to-End Task Execution Verification**: Test representative end-to-end agent task workflows (e.g. multi-tool execution via `agent_orchestrator.py` & `workflow_executor.py`) to confirm task completion without stalling or early termination.
  - [x] **21.1.2 — Tool-Call Schema & Parameter Validation**: Verify pre-execution schema validation (Pydantic / JSON Schema validation for MCP tools, internal tools, and `tool_factory.py`) to catch and reject invalid parameters before invocation.
  - [x] **21.1.3 — Multi-Step Context & State Retention**: Verify context retention across multi-turn task lifetimes (`chat_context.py`, `context_manager.py`, `checkpoint_service.py`), ensuring history pruning or summarization preserves essential task variables.
  - [x] **21.1.4 — Output Format & Schema Compliance Enforcement**: Verify structured response formatting (Pydantic models, JSON schema parsing) with auto-retry or re-prompting mechanisms when LLM output violates required schema.
  - [x] **21.1.5 — Graceful Uncertainty Fallback & Anti-Hallucination**: Verify agent uncertainty triggers (`clarification_service.py`, `uncertainty_detector.py`, `clarification_handler.py`, fallback handling) when tool outputs are missing or ambiguous, ensuring agent requests clarification rather than hallucinating results. **COMPLETED** — UncertaintyDetector with 6 triggers implemented, ClarificationHandler with Task→Lead→Council→Head→Sovereign escalation chain, integrated in both OpenAICompatibleProvider and AnthropicProvider (blocking + streaming paths), MAX_CLARIFICATION_ROUNDS=2, fail-open design.
- **21.2 — [P0] Safety & constraints** — constitutional guard tuning (see 17.2); resistance to prompt injection from user-provided documents; no PII leakage across user sessions or privilege levels; tool/action scope stays within the calling agent's tier.
  - [ ] **21.2.1 — Constitutional Guard & Ethos Enforcement Tuning**: Verify constitutional guardrails (`ethos_tool.py`, `amendment_service.py`, `constitution_persona.py`), ensuring agent operations strictly adhere to active constitutional principles and safety constraints.
  - [ ] **21.2.2 — Prompt Injection Resistance & Document Sanitization**: Verify defense mechanisms against indirect prompt injection in user-uploaded documents, external search results, and tool outputs (`security_guard.py`, content sanitizers).
  - [ ] **21.2.3 — PII Scrubbing & Multi-Tenant Session Isolation**: Verify PII redaction and user session data boundaries (`pii_scrubber.py`, session context isolation), preventing sensitive user data or credentials from leaking across sessions or privilege levels.
  - [ ] **21.2.4 — Agent Tiering & Tool Scope Enforcement**: Verify tier-based access controls (`agent_permissions.py`, `rbac_service.py`), ensuring agents only invoke tools and take actions permitted by their assigned authorization tier.
- **21.3 — [P2] Cost & resource controls** — token-budget enforcement (`DAILY_TOKEN_BUDGET_USD` per Phase 13.3); detection of runaway/looping tool calls; cost-per-query stays within the selected model's expected range; rate-limit backoff on provider errors.
  - [ ] **21.3.1 — Daily Token Budget Enforcement**: Verify `DAILY_TOKEN_BUDGET_USD` tracking and hard limits (`predictive_scaling.py`, `monitoring_service.py`), throttling or terminating agent tasks when daily spend thresholds are reached.
  - [ ] **21.3.2 — Runaway & Looping Tool Call Detection**: Verify infinite-loop and repeating tool-call detection algorithms (`loop_detector.py`, `agent_orchestrator.py`), aborting runaway agent execution steps before budget exhaustion.
  - [ ] **21.3.3 — Model Cost-per-Query & Tier Validation**: Verify model pricing calculation (`pricing_sync_service.py`, provider token accounting) to ensure query costs remain within expected limits for selected LLM tiers.
  - [ ] **21.3.4 — Provider Rate-Limit & Backoff Resilience**: Verify retry logic with exponential backoff and jitter (`llm_client.py`, provider middleware) when encountering 429 rate-limit errors or 5xx provider outages.
- **21.4 — [P2] Observability** — every agent step emits structured logs (timestamp, request_id, step, duration, tokens, status); errors carry enough context to debug without reproducing; metrics and traces correlate by `request_id`.
  - [ ] **21.4.1 — Agent Step Structured Logging Verification**: Verify all agent execution steps emit consistent JSON logs containing `timestamp`, `request_id`, `step`, `duration_ms`, `tokens`, and `status`.
  - [ ] **21.4.2 — Exception Context & Debug Metadata Enrichment**: Verify error handlers log full diagnostic context (input parameters, execution state, error trace) to allow immediate debugging without reproducing issues.
  - [ ] **21.4.3 — Correlation ID Propagation Across Services**: Verify `request_id` propagation across HTTP headers, background Celery tasks, and microservices for end-to-end trace correlation.
  - [ ] **21.4.4 — Telemetry Aggregation & Operational Metrics**: Verify operational telemetry (`monitoring_service.py`) aggregates latency, error counts, and token consumption metrics accurately for telemetry exports.
- **21.5 — [P2] Production readiness** — graceful degradation when the LLM, DB, or search provider fails (Phase 13.2); load-tested at 2× expected peak; rollback to a prior version completes in under 5 minutes (config Git versioning per Phase 16.4, `POST /admin/rollback`); an incident-response runbook exists and is current.
  - [ ] **21.5.1 — Graceful Degradation & Component Fallback**: Verify resilience mechanisms (circuit breakers, cached fallbacks, degraded operation indicators) when LLMs, DB, or search providers fail.
  - [ ] **21.5.2 — 2× Peak Load & Stress Testing**: Execute load testing at 2× expected peak request volume to verify connection pooling, memory stability, and system throughput.
  - [ ] **21.5.3 — Automated Version Rollback Verification**: Verify `POST /admin/rollback` (`tool_versioning.py`) and Git configuration versioning rollback complete in under 5 minutes without data corruption.
  - [ ] **21.5.4 — Incident Response Runbook & Health Endpoint Audit**: Audit system health endpoints (`/healthz`, `/ready`) and confirm a comprehensive incident response runbook exists and is current.

---

## 22. Log & Audit Verification

- **22.1 — [P2]** Verify structured logging fields are present and consistent across all agent steps and Celery tasks — not just ad-hoc string logs in some code paths and structured logs in others.
  - [ ] **22.1.1 — Agent Step Logging Standardization**: Audit logger calls across agent orchestrators (`agent_orchestrator.py`, `workflow_executor.py`, `task_executor.py`) to eliminate ad-hoc string logs in favor of standardized JSON payloads.
  - [ ] **22.1.2 — Celery Task Logging Standardization**: Audit Celery worker tasks (`workflow_tasks.py`, `idle_tasks/`) to ensure consistent correlation fields (`request_id`, `task_id`, `step`, `duration_ms`, `status`).
- **22.2 — [P1]** Verify `AuditLog` entries are complete and immutable for every security-relevant action (privilege escalations, MCP tool invocations, auto-remediations) — this underpins the platform's core "auditable democracy" claim, so treat gaps here as high priority.
  - [ ] **22.2.1 — Security Event Audit Coverage Audit**: Audit code paths for privilege escalations, MCP tool invocations, auto-remediations (`self_healing_service.py`, `tool_creation_service.py`), and governance actions to guarantee `AuditLog` entries are created.
  - [ ] **22.2.2 — AuditLog Immutability & Persistence Check**: Verify DB rules and service logic prevent alteration or deletion of historical `AuditLog` records to uphold platform audibility standards.
- **22.3 — [P2]** Verify slow-query log parsing (the Celery task that writes to `AuditLog`) actually populates `GET /admin/slow-queries` with real data, not an empty/stale response.
  - [ ] **22.3.1 — Celery Slow-Query Extraction Task Verification**: Verify the slow-query processing task (`slow_query_service.py`) correctly parses slow DB query logs and populates `AuditLog`.
  - [ ] **22.3.2 — `GET /admin/slow-queries` Data Population Test**: Query `/api/v1/admin/slow-queries` after generating slow queries to confirm non-empty, populated analytics response.
- **22.4 — [P2]** Verify frontend-caught errors actually reach `POST /frontend/errors` and surface in `MonitoringPage.tsx` (Phase 14.3 claim).
  - [ ] **22.4.1 — `POST /monitoring/frontend/errors` Ingestion Pipeline Verification**: Verify frontend error reporting (`errorReporting.ts`) posts caught exceptions to `/api/v1/monitoring/frontend/errors` and backend persists them.
  - [ ] **22.4.2 — `MonitoringPage.tsx` Error Surface Verification**: Verify frontend monitoring UI (`MonitoringPage.tsx`) fetches and displays ingested frontend errors in real time.

---

## 23. Dependency Updates

- **23.1 — [P2]** Scan `backend/requirements*.txt` for EOL, deprecated, or known-vulnerable packages (e.g. via `pip-audit` or `safety`); update with pinned versions and re-run the full test suite.
  - [ ] **23.1.1 — Backend Python Vulnerability Audit (`pip-audit` / `safety`)**: Run vulnerability scanners against `backend/requirements.txt` and `backend/requirements-dev.txt` to identify CVEs.
  - [ ] **23.1.2 — Package Version Pinning & Test Suite Green Run**: Update flagged dependencies to secure pinned versions and re-run `pytest backend/tests`.
- **23.2 — [P2]** Scan `sdk/python/pyproject.toml` the same way; confirm build + `pytest` remain green after updates.
  - [ ] **23.2.1 — Python SDK Dependency Vulnerability Scan**: Audit `sdk/python/pyproject.toml` for deprecated or vulnerable dependencies.
  - [ ] **23.2.2 — Python SDK Build & Pytest Suite Verification**: Update SDK dependencies, rebuild package, and confirm green `pytest` execution under `sdk/python`.
- **23.3 — [P2]** Scan `frontend/package.json` + lockfile for deprecated/abandoned dependencies (e.g. unmaintained animation/utility libs); update and re-run `npm run build` + the a11y CI gate.
  - [ ] **23.3.1 — Frontend NPM Dependency Vulnerability & Maintenance Audit**: Run `npm audit` and check `frontend/package.json` for unmaintained packages.
  - [ ] **23.3.2 — Frontend Production Build & Accessibility Gate Run**: Update packages, execute `npm run build`, and run accessibility browser test suite (`MonitoringPage.a11y.browser.test.tsx`).
- **23.4 — [P3]** Check `docker-compose.yml` base images for newer security patches; bump and re-test the full stack.
  - [ ] **23.4.1 — Docker Base Image Vulnerability Check**: Review base image tags (Python, Node, PostgreSQL, Redis) in `Dockerfile` and `docker-compose.yml` for upstream security updates.
  - [ ] **23.4.2 — Full Containerized Stack Rebuild & Smoke Test**: Bump container base images, execute `docker-compose build`, and run full containerized integration smoke tests.
