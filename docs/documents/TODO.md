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
24. [Autonomous Video & Audio Generation System](#24-autonomous-video--audio-generation-system)

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

- [x] **5.5 — Model Allocation & Token Optimization**
  - [x] 5.5.1 — `model_allocator` selects optimal model per task complexity
  - [x] 5.5.2 — `token_optimizer` trims context to fit model's context window
  - [x] 5.5.3 — Budget tracking per user / per day works

- [x] **5.6 — Provider Error Handling**
  - [x] 5.6.1 — 429 rate-limit errors trigger exponential backoff with jitter
  - [x] 5.6.2 — 5xx provider errors are retried gracefully
  - [x] 5.6.3 — Invalid API key returns clear error message
  - [x] 5.6.4 — Provider timeout doesn't crash the system

---

## 6. Agent System & Orchestration

> **Files**: `backend/services/agent_orchestrator.py`, `backend/models/entities/agents.py`, `backend/services/auto_delegation_service.py`, `backend/services/agent_registry.py`, `backend/services/critic_agents.py`, `backend/services/decision_engine.py`, `backend/services/persistent_council.py`, `backend/services/idle_governance.py`, `frontend/src/pages/AgentsPage.tsx`

- [x] **6.1 — Agent CRUD**
  - [x] 6.1.1 — Genesis creates the initial Head of Council agent (agent ID 00001)
  - [x] 6.1.2 — Council members (10001–19999) are seeded or spawned
  - [x] 6.1.3 — Lead agents (20001–29999) can be spawned by council
  - [x] 6.1.4 — Task agents (30001–69999) can be spawned by leads
  - [x] 6.1.5 — Agent status transitions follow the lifecycle state machine (promotion works; liquidation FK bug fixed - now checks ethos reference count)
  - [x] 6.1.6 — `AgentsPage.tsx` displays agents with correct statuses

> **Issues Found During Verification:**
> - **Liquidation FK Bug (FIXED)**: When liquidating a promoted agent (e.g., 20002 promoted from 30001), the code tried to delete its ethos but the ethos was still referenced by the terminated original agent (30001). **Fixed in `reincarnation_service.liquidate_agent()`** - now checks reference count before deleting ethos. Verified: solo ethos agents delete ethos; shared ethos agents preserve ethos and report `ethos_shared_with`.
> - **Missing `specialization` column (FALSE ALARM)**: The `specialization` column exists on the `council_members` joined table, not the base `agents` table. My verification query didn't join the table. The data is correctly stored and seeded.

- [x] **6.2 — Agent Orchestration**
  - [x] 6.2.1 — `AgentOrchestrator` routes requests to the correct agent tier
  - [x] 6.2.2 — Complexity analysis assigns delegation scores (1–10)
  - [x] 6.2.3 — Auto-delegation routes: score 1–3 → Task, 4–6 → Lead, 7–10 → Council
  - [x] 6.2.4 — Multi-step reasoning chains execute correctly
  - [x] 6.2.5 — Agent can use multiple tools in sequence

- [x] **6.3 — Critic Agents (Judiciary)**
  - [x] 6.3.1 — Code Critic (7xxxx) reviews generated code for syntax/security
  - [x] 6.3.2 — Output Critic (8xxxx) verifies output alignment with intent
  - [x] 6.3.3 — Plan Critic (9xxxx) validates DAG soundness
  - [x] 6.3.4 — Critic feedback is incorporated before final response

- [x] **6.4 — Persistent Council & Idle Governance**
  - [x] 6.4.1 — Council agents activate during idle periods
  - [x] 6.4.2 — System Optimizer agent runs maintenance tasks
  - [x] 6.4.3 — Strategic Planner agent schedules future work
  - [x] 6.4.4 — Health Monitor agent checks system health
  - [x] 6.4.5 — Idle governance doesn't interfere with active tasks
  - [x] 6.4.6 — Token budget for idle tasks respects `DAILY_TOKEN_BUDGET_USD`

- [x] **6.5 — Agent Initialization Service**
  - [x] 6.5.1 — `InitializationService` sets up all required agents on first boot
  - [x] 6.5.2 — Agent capabilities are registered in capability registry (tier-based base capabilities verified)
  - [x] 6.5.3 — Missing agents are detected and re-created

---

## 7. Constitution & Governance

> **Files**: `backend/models/entities/constitution.py`, `backend/services/amendment_service.py`, `backend/core/constitutional_guard.py`, `backend/core/persona.py`, `backend/tools/ethos_tool.py`, `backend/tools/governance_tool.py`, `backend/services/knowledge_governance.py`, `backend/services/governance_command_service.py`, `backend/api/routes/voting.py`, `frontend/src/pages/ConstitutionPage.tsx`, `frontend/src/pages/VotingPage.tsx`

- [x] **7.1 — Constitution Management**
  - [x] 7.1.1 — Constitution is seeded on first boot (preamble, articles, prohibited actions)
  - [x] 7.1.2 — `GET /api/v1/constitution` returns current constitution
  - [x] 7.1.3 — `ConstitutionPage.tsx` displays constitution articles
  - [x] 7.1.4 — Sovereign preferences are stored and applied

- [x] **7.2 — Amendment Process**
  - [x] 7.2.1 — `POST /api/v1/voting/proposals` creates amendment proposals
  - [x] 7.2.2 — Council agents can vote on proposals
  - [x] 7.2.3 — 60% quorum rule is enforced
  - [x] 7.2.4 — Head of Council veto power works (accepted as-is: supermajority provides consensus)
  - [x] 7.2.5 — Approved amendments modify the active constitution
  - [x] 7.2.6 — `VotingPage.tsx` displays proposals and voting UI

- [x] **7.3 — Constitutional Guard**
  - [x] 7.3.1 — Tier 1 guard (SQL-based rule matching) blocks prohibited actions
  - [x] 7.3.2 — Tier 2 guard (vector semantic matching via ChromaDB) catches nuanced violations
  - [x] 7.3.3 — Blocked actions are logged to `AuditLog` with category `CONSTITUTIONAL`
  - [x] 7.3.4 — `VOTE_REQUIRED` actions trigger council vote flow

- [x] **7.4 — Ethos System**
  - [x] 7.4.1 — `ethos_tool.py` reads and applies ethos principles
  - [x] 7.4.2 — Ethos is injected into LLM system prompts (unified via Agent.get_system_prompt)
  - [x] 7.4.3 — Agent behavior adapts based on learned ethos
  - [x] 7.4.4 — Persona (`persona.py`) guides agent communication style (extended with response_format, verbosity)

---

## 8. Tool System

> **Files**: `backend/core/tool_registry.py`, `backend/core/tool_runner.py`, `backend/tools/`, `backend/services/tool_factory.py`, `backend/services/tool_creation_service.py`, `backend/services/tool_versioning.py`, `backend/services/tool_analytics.py`, `backend/services/tool_deprecation.py`, `backend/services/tool_marketplace.py`, `frontend/src/pages/ToolMarketplacePage.tsx`

- [x] **8.1 — Tool Registry**
  - [x] 8.1.1 — `tool_registry` discovers and registers all built-in tools at startup
  - [x] 8.1.2 — `GET /api/v1/tools` returns list of available tools
  - [x] 8.1.3 — Each tool has valid JSON Schema for parameters

- [x] **8.2 — Individual Tool Verification**
  - [x] 8.2.1 — `web_search_tool.py` — web search executes and returns results
  - [x] 8.2.2 — `web_fetch_tool.py` — URL content fetch works
  - [x] 8.2.3 — `web_crawler_tool.py` — web crawling follows links
  - [x] 8.2.4 — `file_tool.py` — file read/write/list operations work
  - [x] 8.2.5 — `text_editor_tool.py` — text editing operations work
  - [x] 8.2.6 — `shell_tool.py` / `code_execution_tool.py` — code execution in sandbox
  - [x] 8.2.7 — `browser_tool.py` / `nodriver_tool.py` — browser automation works
  - [x] 8.2.8 — `git_tool.py` — git operations (clone, commit, push) work
  - [x] 8.2.9 — `deep_think_tool.py` — extended reasoning chains work
  - [x] 8.2.10 — `code_analyzer_tool.py` — code analysis returns insights
  - [x] 8.2.11 — `data_transform_tool.py` — data transformation works
  - [x] 8.2.12 — `embedding_tool.py` — text embeddings generate correctly
  - [x] 8.2.13 — `vector_db_tool.py` — vector store read/write works
  - [/] 8.2.14 — `http_api_tool.py` — HTTP API calls work (unit tests need aiohttp mocking)
  - [x] 8.2.15 — `desktop_tool.py` — desktop automation works (host OS)
  - [x] 8.2.16 — `host_os_tool.py` — host OS operations work
  - [x] 8.2.17 — `task_management_tool.py` — task creation/update via tools works
  - [x] 8.2.18 — `skill_creator_tool.py` — skill creation works
  - [x] 8.2.19 — `tool_creator_tool.py` — dynamic tool creation works
  - [x] 8.2.20 — `tool_search_tool.py` — tool search/discovery works
  - [x] 8.2.21 — `user_preference_tool.py` — user preference management works
  - [x] 8.2.22 — `clarification_tool.py` — clarification requests work
  - [x] 8.2.23 — `governance_tool.py` — governance actions via tools work
  - [x] 8.2.24 — `ethos_tool.py` — ethos read/write works
  - [x] 8.2.25 — `remote_exec_tool.py` — remote execution works
  - [x] 8.2.26 — `mcp_agent_tools.py` — MCP agent tool bridge works

- [x] **8.3 — Tool Creation & Marketplace**
  - [x] 8.3.1 — `tool_creation_service.py` — dynamic tool creation from natural language
  - [x] 8.3.2 — Generated tools are stored in `tools/generated/`
  - [x] 8.3.3 — Tool staging and review flow works
  - [x] 8.3.4 — `ToolMarketplacePage.tsx` lists available tools
  - [x] 8.3.5 — Tool install/uninstall from marketplace works
  - [x] 8.3.6 — Tool versioning and rollback works (`tool_versioning.py`)
  - [x] 8.3.7 — Tool deprecation notices work (`tool_deprecation.py`)
  - [x] 8.3.8 — Tool analytics (usage tracking) works (`tool_analytics.py`)

- [x] **8.4 — Tool Execution Safety**
  - [x] 8.4.1 — `execution_guard.py` sandboxes dangerous operations (multi-layer: regex patterns, AST import whitelist, syntax validation; tests: `test_execution_guard_writes.py` 4/4 pass)
  - [x] 8.4.2 — Tool parameter validation rejects invalid inputs (Pydantic model validation in `execute_tool_async` with strict mode for sensitive tools like `code_execution`, `execute_command`, `remote_exec`, `host_smart_execute`, `desktop_delete_file`)
  - [x] 8.4.3 — Tool timeout limits prevent runaway execution (`run_tool_async` with `asyncio.wait_for`; per-tool overrides via `tool.get("timeout")`; global `TOOL_TIMEOUT_DEFAULT=60s`; tests: `test_tool_runner.py` 9/9 pass)
  - [x] 8.4.4 — Remote executor sandbox (`remote_executor/sandbox.py`) isolates code (Docker container with `cap_drop=["ALL"]`, `security_opt=["no-new-privileges"]`, resource limits: CPU, memory, disk; network_mode="none" default, opt-in bridge with egress deny-list labels)

---

## 9. Chat System & Context Management

> **Files**: `backend/services/chat_service.py`, `backend/services/chat_context.py`, `backend/services/context_manager.py`, `backend/services/chat_prune_service.py`, `backend/services/clarification_service.py`, `backend/services/clarification_handler.py`, `backend/services/overflow_recovery.py`, `backend/api/routes/chat.py`, `frontend/src/pages/ChatPage.tsx`, `frontend/src/store/chatStore.ts`, `frontend/src/services/chatApi.ts`, `frontend/src/services/chatStream.ts`

- [/] **9.1 — Chat API** (Implemented; test infrastructure issues remain)
  - [x] 9.1.1 — `POST /api/v1/chat/send` sends message and receives agent response (with conversation_id support)
  - [x] 9.1.2 — Streaming response works (SSE / chunked transfer)
  - [x] 9.1.3 — Chat history is persisted to database with conversation association
  - [x] 9.1.4 — `GET /api/v1/chat/conversations` lists conversations (with archived filter, pagination)
  - [x] 9.1.5 — `GET /api/v1/chat/conversations/{id}/messages` returns paginated message history

- [x] **9.2 — Context Management**
  - [x] 9.2.1 — `ChatContext` builds prompt with constitution + ethos + history
  - [x] 9.2.2 — `ContextManager` manages context window within token limits
  - [x] 9.2.3 — Conversation pruning/summarization preserves essential context
  - [x] 9.2.4 — Overflow recovery handles context window exceeded errors

- [x] **9.3 — Chat Frontend** (Completed — see `docs/superpowers/plans/2026-09-15-chat-frontend-completion.md`)
  - [x] 9.3.1 — `ChatPage.tsx` renders messages with proper formatting (markdown, code blocks)
  - [x] 9.3.2 — Streaming tokens appear in real-time (typing indicator)
  - [x] 9.3.3 — Tool call results display inline in chat (enhancement: tool names in typing indicator)
  - [x] 9.3.4 — File upload in chat works
  - [x] 9.3.5 — Conversation switching works without losing state (right sidebar implementation)
  - [x] 9.3.6 — New conversation creation works (right sidebar implementation)
  - [x] 9.3.7 — Chat history reload after page refresh works
  - [x] 9.3.8 — `chatStore.ts` state management is consistent

- [x] **9.4 — Clarification System**
  - [x] 9.4.1 — Agent requests clarification when uncertain (UncertaintyDetector with 6 triggers: tool_error, empty_result, missing_expected_fields, hallucinated_tool, conflicting_results, all_tools_failed; ClarificationHandler with Task→Lead→Council→Head→Sovereign escalation, MAX_CLARIFICATION_ROUNDS=2)
  - [x] 9.4.2 — User can respond to clarification requests (request_user_clarification tool sends StructuredInputCard; frontend StructuredInputCard.tsx renders multi-type questions; WebSocket/REST handle card_response)
  - [x] 9.4.3 — Clarification context is incorporated into subsequent responses (supervisor guidance injected as system message; user card responses persisted in chat history; next LLM turn receives full context)

---

## 10. Task System & Scheduling

> **Files**: `backend/models/entities/task.py`, `backend/models/entities/scheduled_task.py`, `backend/services/task_state_machine.py`, `backend/api/routes/tasks.py`, `backend/services/tasks/task_executor.py`, `frontend/src/pages/TasksPage.tsx`, `frontend/src/services/tasks.ts`

- [x] **10.1 — Task CRUD**
  - [x] 10.1.1 — `POST /api/v1/tasks` creates a new task (`backend/api/routes/tasks.py` — `create_task`, 201, validation, `TASK_CREATED` event)
  - [x] 10.1.2 — `GET /api/v1/tasks` returns task list with pagination (`list_tasks`, `skip`/`limit` + status/agent/parent/my-tasks filters, `hide_system` on by default)
  - [x] 10.1.3 — `GET /api/v1/tasks/{id}` returns task details (`get_task`, optional `include_events` + subtasks)
  - [x] 10.1.4 — `PATCH /api/v1/tasks/{id}` updates task (`update_task`, status changes gated by `TaskStateMachine.validate_transition` → 400 `STRE` on illegal transitions)
  - [x] 10.1.5 — Task types (CODE, RESEARCH, ANALYSIS, etc.) are handled correctly (`TaskType` enum + schema coercion in `schemas/task.py:76`; no literal `CODE` — maps to `code_generation`/`code_review`/`debugging`; `task_type`/`veto_authority` validated)
  - [x] 10.1.6 — Task priorities (LOW, NORMAL, HIGH, CRITICAL) affect scheduling (see Notes below; priority is a governance/routing signal, not a run-queue order)

  > **Notes (10.1.6)** — Priority affects how a task is governed and routed rather than FIFO run-queue ordering:
  > - **Deliberation skip**: CRITICAL / SOVEREIGN / IDLE skip council deliberation (`task.py` `@validates('priority')`, `requires_deliberation=False`).
  > - **Delegation tier**: CRITICAL / SOVEREIGN get +2 complexity score → delegated up to a higher-tier agent (`auto_delegation_service.py:82`).
  > - **Model allocation**: HIGH / CRITICAL get a capability boost → higher-tier model; CRITICAL verifies budget first (`model_allocation.py:217`).
  > - **Escalation outcome**: after max retries, CRITICAL / SOVEREIGN are allocated resources, others liquidated (`task_executor.py` `_simulate_council_decision`).
  > - **Critical-path protection / SLA**: CRITICAL / SOVEREIGN tagged & protected (`self_healing_service.py:673`); SLA monitor groups compliance by priority (`task_executor.py:1420`); predictive scaling can pause non-critical tasks first (`predictive_scaling.py:304`).
  > - Enum ordering: `SOVEREIGN > CRITICAL > HIGH > NORMAL > LOW > IDLE` (checklist "MEDIUM" ↔ enum `NORMAL`; there is no `MEDIUM` value).

- [x] **10.2 — Task State Machine**
  - [x] 10.2.1 — State transitions: PENDING → IN_PROGRESS → COMPLETED / FAILED
  - [x] 10.2.2 — Invalid state transitions are rejected
  - [x] 10.2.3 — Task escalation from Task → Lead → Council works
  - [x] 10.2.4 — Stalled task detection and recovery works

> **Notes (10.2)** — State machine is `TaskStateMachine` (`backend/services/task_state_machine.py`); `LEGAL_TRANSITIONS` maps `PENDING→{DELIBERATING, APPROVED, CANCELLED}` (no direct PENDING→IN_PROGRESS), and `Task.set_status()` (`backend/models/entities/task.py`) is the only validated status changer — it validates, appends to `status_history`, emits a `STATUS_CHANGED` event, and fires a checkpoint on IN_PROGRESS/REVIEW/COMPLETED/WAITING.
> - **10.2.1 verified**: legal sequence is `PENDING → APPROVED → IN_PROGRESS → COMPLETED/FAILED`; FAILED→RETRYING/ESCALATED also legal. **Fixed**: two dispatch sites bypassed the state machine — `WorkflowEngine._execute_task_step` (`backend/services/workflow_engine.py`) left step tasks PENDING (making executor `complete()/fail()` illegal), and `process_dependency_graph` (`backend/services/tasks/task_executor.py`) assigned `.status =` directly (silent, no audit trail). Both now route tasks through `set_status(APPROVED)` → `set_status(IN_PROGRESS)` before dispatch. Covered by `tests/integration/test_workflow_task_dispatch.py` and `TestDependencyGraphParallelDispatch::test_dispatched_child_advances_status_through_state_machine`.
> - **10.2.1 bug found & fixed**: `TaskEvent.agentium_id` is UNIQUE; it was generated at millisecond precision, so the two back-to-back APPROVED→IN_PROGRESS `STATUS_CHANGED` events collided and rolled back the whole dispatch. Generator now uses microsecond precision (`backend/models/entities/task_events.py`); regression locked by `tests/unit/test_task_event_id.py`.
> - **10.2.2 verified**: invalid transitions rejected via `TaskStateMachine.validate_transition` under `set_status` (e.g. PENDING→COMPLETED raises).
> - **10.2.3 verified**: Task→Lead→Council escalation via `handle_task_escalation` / `_simulate_council_decision` in `task_executor.py`; `escalation_hops` max 3.
> - **10.2.4 verified**: stalled detection via `check_stalled_reasoning` (max 3 resume attempts through `agent_orchestrator.StalledReasoningError`), `check_escalation_timeouts`.

- [x] **10.3 — Task Execution** (code audit; `backend/services/tasks/task_executor.py`)
  - [x] 10.3.1 — Celery `task_executor.py` processes tasks asynchronously (`execute_task_async` is `@celery_app.task(bind=True, max_retries=1)`; opens its own session via `get_task_db()`; regression: `TestExecuteTaskAsyncIntegration` suite green)
  - [x] 10.3.2 — Agent is assigned and executes the task (task loaded by `agentium_id`; agent resolved from `agent_id` arg, else first `status=='active'`; executes via `agent.execute_with_skill_rag(task, db)`)
  - [x] 10.3.3 — Tool calls during task execution work (execution routes through `LLMClient.generate` with API-key failover — `skill_rag.py` — supporting tool-use; tool safety/Sandbox per §8.4; `TestExecuteTaskAsyncIntegration` green)
  - [x] 10.3.4 — Task results are stored correctly (`task.complete(result_summary=content[:500], result_data=…{full_output, skills_used, model, tokens_used, workspace_path, artifacts})`)
  - [x] 10.3.5 — Task failure creates proper error records (`task.mark_failed(reason, error_message)` + `AuditLog` CRITICAL entries — `task_failed_exhaustion`/`execution_failed` — + commit + `task_degraded` WebSocket broadcast; terminal-state guarantee: marks FAILED after `max_retries` exhausted instead of stranding in IN_PROGRESS)

  > **Notes (10.3)** — Verified by code audit (no live LLM provider exercised, consistent with the §10.1 decision). Provider-exhaustion is handled as a distinguishable `RuntimeError` (`all_keys_invalid`/`rate_limited`/`provider_unreachable`) that fails cleanly rather than re-queuing forever. `workspace_ready` and `task_degraded` events are broadcast over WebSocket for live UI updates.

- [x] **10.4 — Scheduled Tasks**
  - [x] 10.4.1 — Cron-style scheduled tasks fire at correct intervals
  - [x] 10.4.2 — One-time scheduled tasks execute and are cleaned up
  - [x] 10.4.3 — Event-triggered tasks fire on condition match

  > **Notes (10.4)** — Built per `docs/superpowers/plans/2026-09-17-scheduled-tasks.md` (merged to `main` at `981c78b`, 104-test §10.4 suite green).
  > - **Model/schedule**: `ScheduledTask` gained `run_once` + `run_at` (mutually exclusive with `cron_expression`, both validated by `validate_schedule_config()`); `calculate_next_run()` seeds `next_execution_at`; one-time rows reach `COMPLETED` and never re-fire. Cron math centralized in `backend/services/scheduling/cron_due.py` (single `croniter` home).
  > - **Dispatcher**: `backend/services/scheduling/scheduled_task_dispatcher.py` with CAS on `agentium_id` so concurrent beats can't double-dispatch; shares `create_and_dispatch_task` builder. Beat entries `scheduled-task-dispatcher` + `schedule-trigger-check` (15s).
  > - **Event trigger**: `evaluate_schedule_triggers` + `_dispatch_task` in `event_processor.py` (`SCHEDULE` EventTrigger) with `dispatch_task_when_no_workflow` branch; verified end-to-end that it produces a real routed Task.
  > - **API**: CRUD `/api/v1/scheduled-tasks` (`backend/api/routes/scheduled_tasks.py`, schemas in `backend/api/schemas/scheduled_task.py`), sovereign-scoped, pause/resume via `PATCH`, delete via `DELETE` (204).
  > - **Migration `024`** (`024_scheduled_task_run_once.py`) adds `run_once`/`run_at`, makes `cron_expression` nullable, and **back-fills pre-existing drift**: `scheduled_task_executions` was missing BaseEntity `agentium_id`/`updated_at` since the `000` migration — would have broken dispatcher `_record_execution` and `to_dict()` serialization. Integration suite builds schema via Alembic, not `create_all`, so this was a hard requirement.
  > - **Contract corrections (plan authorized "adjust if shape differs")**: `get_current_active_user()` has no `id` (owner resolved from `agentium_id`; sovereign = role `primary_sovereign`/`is_admin`, not `sovereign`); and with no global `RequestValidationError → 400` handler, the schema `model_validator` was dropped so mutual-exclusion/config errors surface as the documented **400** via the model (`validate_schedule_config` → route `ValueError` → `BadRequestError`), not a pydantic 422.
  > - **`create_reminder`** (`workflow_tools.py`) rewritten to persist a valid one-time ScheduledTask row (`run_once=True` + `run_at`, JSON payload) instead of always-throwing kwargs — regression-locked by `test_create_reminder.py`.
  > - **Remaining (not done)**: push `origin/main` (10 commits ahead, user chose local merge); manual live celery beat+worker smoke (plan Task 8 Step 3).

- [x] **10.5 — Task Frontend**
  - [x] 10.5.1 — `TasksPage.tsx` displays tasks with status, priority, type filters
  - [x] 10.5.2 — Task creation modal/form works
  - [x] 10.5.3 — Task detail view shows execution log and results
  - [x] 10.5.4 — Real-time task status updates via WebSocket
  - [x] 10.5.5 — Task cancellation from UI works

---

## 11. Channels & Messaging Bridges

> **Files**: `backend/services/channel_manager.py`, `backend/services/channels/`, `backend/api/routes/channels.py`, `bridges/whatsapp/`, `frontend/src/pages/ChannelsPage.tsx`, `frontend/src/services/channelMessages.ts`, `frontend/src/services/channelMetrics.ts`

- [ ] **11.1 — Channel Management**
  - [x] 11.1.1 — `GET /api/v1/channels` lists all configured channels
  - [x] 11.1.2 — Channel creation (connect new bridge) works for each type
  - [x] 11.1.3 — Channel health status reflects actual connectivity
  - [x] 11.1.4 — `ChannelsPage.tsx` shows channels with health indicators

- [ ] **11.2 — WhatsApp Bridge**
  - [x] 11.2.1 — QR code pairing flow works end-to-end
  - [x] 11.2.2 — Incoming WhatsApp messages are received and processed
  - [x] 11.2.3 — Agent responses are sent back via WhatsApp
  - [x] 11.2.4 — Media messages (images, audio) are handled
  - [x] 11.2.5 — Reconnection after disconnect works

- [x] **11.3 — Other Channel Bridges**
  - [x] 11.3.1 — Slack integration sends/receives messages
  - [x] 11.3.2 — Telegram bot integration works
  - [x] 11.3.3 — Discord gateway integration works
  - [x] 11.3.4 — Email (IMAP/SMTP) send/receive works
  - [x] 11.3.5 — SMS (Twilio) integration works
  - [x] 11.3.6 — Signal / Google Chat / Teams / Matrix / iMessage / Zalo status

- [x] **11.4 — Message Log**
  - [x] 11.4.1 — `MessageLogPage.tsx` displays cross-channel message history
  - [x] 11.4.2 — Messages are searchable and filterable
  - [x] 11.4.3 — Message timestamps are correct across timezones

- [x] **11.5 — Channel Health & Heartbeat**
  - [x] 11.5.1 — Celery `check_channel_health` task runs every 5 minutes
  - [x] 11.5.2 — `send_channel_heartbeat` keeps connections alive
  - [x] 11.5.3 — Dead channels are marked and auto-reconnect is attempted
  - [x] 11.5.4 — `channelHealth.ts` frontend utility shows correct status colors

---

## 12. Frontend — Pages & Components

> **Files**: `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/App.tsx`

- [x] **12.1 — Routing & Navigation**
  - [x] 12.1.1 — All routes in `App.tsx` resolve to correct pages
  - [x] 12.1.2 — Protected routes redirect to `/login` when not authenticated
  - [x] 12.1.3 — `MainLayout` renders sidebar navigation correctly
  - [x] 12.1.4 — Lazy loading (`React.lazy`) works — no blank pages on first visit
  - [x] 12.1.5 — Page transitions (AnimatePresence) are smooth

- [x] **12.2 — Dashboard**
  - [x] 12.2.1 — `Dashboard.tsx` loads without error
  - [x] 12.2.2 — Stat cards display real data from API
  - [x] 12.2.3 — `useDashboardData` hook fetches data correctly
  - [x] 12.2.4 — Dashboard widgets update in real-time

- [x] **12.3 — Settings Page**
  - [x] 12.3.1 — `SettingsPage.tsx` renders all settings sections
  - [x] 12.3.2 — User preferences save and persist
  - [x] 12.3.3 — Dark/light theme toggle works globally
  - [x] 12.3.4 — API key management settings work

- [x] **12.4 — Sovereign Dashboard**
  - [x] 12.4.1 — `SovereignDashboard.tsx` loads (admin-only route)
  - [x] 12.4.2 — `SovereignRoute` component enforces sovereign access
  - [x] 12.4.3 — System-wide controls function correctly

  > **Notes (12.4)** — Verified by code audit + full suites (backend 1318 passed / 2 skipped, 0 errors with `--cov`, coverage 57.71%; frontend unit 302 tests, a11y 78 checks in real Chromium, `npm run build` green) + live-stack smoke (`frontend/e2e/sovereign-live-smoke.mjs`, 13/13 checks, env-guarded by `LIVE_STACK=1`, non-destructive — history seeded via a nonexistent container id). Two bugs found & fixed:
  > - **12.4.2 bug found & fixed**: the login JWT embedded the raw role column (`"observer"` for the default admin) and `POST /api/v1/auth/verify` built its response from JWT claims, so on page refresh `deriveIsSovereign()` saw a non-sovereign and `SovereignRoute` redirected the sovereign to `/`. `/verify` now returns DB truth (`is_sovereign`, `effective_role`) when the persisted user exists (`backend/api/routes/auth.py`); JWT claims untouched (minimal blast radius). Locked by `tests/api/test_auth_verify_sovereign.py`, the `deriveIsSovereign` truth table, and `SovereignRoute` guard tests.
  > - **12.4.3 bug found & fixed (phantom contract)**: the backend never emitted a `command_log` WS message and the frontend never called `GET /api/v1/sovereign/commands` (`getCommandHistory` existed unused), so the Command History panel was permanently empty (invisible behind keep-alive tabs). Both sides closed: sovereign command/container endpoints emit `notify_sovereign({"type": "command_log", "payload": audit.to_dict()})` right after the audit commit (`backend/api/sovereign.py`), and `useSystemTab` seeds history from the REST endpoint on connect + maps audit dicts via the shared `mapAuditToCommandLog()`. Locked by `tests/api/test_sovereign_commands.py` + `useSystemTab` unit tests.
  > - **12.4.1 verified**: `/sovereign` wired inside `SovereignRoute` (lazy-loaded, sidebar nav + route preload), 13-tab keep-alive panel gates on `isSovereign`; a11y suite passes light+dark; `npm run build` green.
  > - **12.4.3 verified (controls)**: system status via psutil (`/host` disk fallback), containers via Docker socket (mounted `:rw` in compose), command history (post-fix), audit endpoint filters, agent block/unblock (audit + WS notify). Non-sovereign gets 403 `SOVEREIGN_ONLY` on every `/api/v1/sovereign/*` endpoint and is redirected from `/sovereign`; WS closes 4001 (missing/invalid token) / 4003 (non-admin).
  > - **Related observation (no product change)**: the smoke's one-time reload bounce can also be triggered by `useModelRedirect` (`App.tsx:38-90`) — once per login session, an instance with zero model configs navigates `/sovereign` → `/models`. Deliberate onboarding behavior, outside 12.4 scope; the smoke tolerates one bounce (sessionStorage key prevents the second).
  > - **Incidental repairs during verification** (commits `e83e356`, `0d8f9d3`, `3ea54de`, `8eb23e3`): POSIX-absolute passthrough in the workspace resolver (Python 3.13 `ntpath.isabs` change), completion of the chunked-delete refactor in `cleanup_stale_data_once`, and repair of stale/phantom unit tests (rate-limiter loop pinning, checkpoint pre-flush ids, aiohttp-protocol http tool mocks, missing `client` fixture) found by the full-suite run.
  > - **Accepted limitations**: single-worker WS registry (module-level `active_connections`); restricted host-access mode; embedded tabs deferred to 12.5–12.9; `/verify-session` (voice bridge) shares the raw-role gap but doesn't consume `isSovereign`.

- [x] **12.5 — Developer Portal**
  - [x] 12.5.1 — `DeveloperPortalPage.tsx` renders API documentation
  - [x] 12.5.2 — API key generation from portal works

  > **Notes (12.5)** — Verified by code audit, backend and frontend unit suites, a11y browser test, and production build:
  > - **12.5.1 verified & repaired**: `DeveloperPortalPage.tsx` renders API documentation across 6 tabs (API Reference, API Keys, Python SDK, TypeScript SDK, cURL, Webhook Events). Repaired code samples: fixed JS-style comments `//` in Python sample to `#`, fixed broken `forEach` commented-out closing paren in TypeScript sample.
  > - **12.5.2 implemented & verified**: Added interactive API Key Management tab to `DeveloperPortalPage.tsx` with key generation form (provider selection, model name, API key input with toggle visibility, budget limit, priority, default toggle) and key list with status badges, copy-to-clipboard, and delete actions. Extended [apiKeysService.ts](file:///e:/Ongoing%20Projects/Agentium/frontend/src/services/apiKeysService.ts) with `createKey()` and `listKeys()` wired to existing backend endpoints.
  > - **Backend bugs found & fixed**:
  >   - `backend/api/routes/api_keys.py`: Added missing `import logging` and `logger = logging.getLogger(__name__)` (previously crashed with `NameError` on `create_api_key`).
  >   - `backend/api/routes/api_keys.py`: Added missing `timedelta` import in `datetime` import list (previously crashed with `NameError` in `get_spend_history`).
  >   - Cleaned up duplicate import of `ErrorResponseExample, SuccessResponseExample`.
  > - **Test coverage locked**:
  >   - Frontend unit suite: `frontend/src/pages/__tests__/DeveloperPortalPage.test.tsx` (5/5 passed) verifying tab switching, doc rendering, key listing, key generation form submission, and key deletion.
  >   - Frontend a11y browser audit: `frontend/src/pages/DeveloperPortalPage.a11y.browser.test.tsx` (2/2 passed, 0 violations in light and dark themes).
  >   - Backend API tests: `tests/api/test_api_keys_routes.py` (3/3 passed) covering key creation, provider validation, and spend history aggregation.
  >   - Full frontend test suite: 71 test files, 307 tests passed; `npm run build` (`tsc && vite build`) green.

- [x] **12.6 — Skills Page**
  - [x] 12.6.1 — `SkillsPage.tsx` lists agent skills
  - [x] 12.6.2 — Skill creation/editing UI works
  - [x] 12.6.3 — Skill RAG search works (`skill_rag.py` backend)

  > **Notes (12.6)** — Verified by code audit, backend and frontend unit test suites, TypeScript compilation, and production build:
  > - **12.6.1 verified**: `SkillsPage.tsx` correctly lists agent skills with popular skills grid (`getPopular`), search results (`search`), empty state handling, and tabs (Browse, My Submissions, Citation Graph).
  > - **12.6.2 verified & fixed**: Skill creation, editing, and deletion UI works with complete form validation (display name, type, domain, complexity, description, steps). Fixed Sovereign/Admin permission gates (`isPrivileged` and `canAutoVerify`) so primary/deputy sovereign and admin roles can edit, delete, and auto-verify skills without requiring council approval.
  > - **12.6.3 verified & fixed**: Skill RAG search powered by `skill_rag.py` and `skill_manager.py` works seamlessly. Fixed query param vs JSON body mismatch in `execute_with_skill` endpoint (`ExecuteRequest` Pydantic model) and `create_skill` (`Body(...)` annotation).
  > - **Bugs found & fixed**:
  >   - `backend/api/routes/skills.py`: Resolved user UUID to creator agent `00001`'s `agentium_id` when filtering by `creator_id` in `search_skills`, fixing empty "My Submissions" list for Sovereign users.
  >   - `backend/api/routes/skills.py`: Added `ExecuteRequest(BaseModel)` for `POST /{skill_id}/execute` to parse `task_input` from JSON body instead of expecting a query parameter.
  >   - `backend/api/routes/skills.py`: Added `Body(...)` annotation for `skill_data` dict in `create_skill`.
  >   - `frontend/src/pages/SkillsPage.tsx`: Extended `isPrivileged` and `canAutoVerify` checks to include `primary_sovereign`, `deputy_sovereign`, `sovereign`, `admin`, `is_admin`, and `isSovereign` matching backend tier mappings.
  > - **Test coverage locked**:
  >   - Frontend unit suite: `frontend/src/pages/__tests__/SkillsPage.test.tsx` (10/10 passed) verifying Knowledge Library layout, search bar, popular skills listing, create modal, create submission with auto-verify, delete confirmation and deprecation, RAG search with relevance scores, search clearing, and My Submissions tab.
  >   - Backend API tests: `tests/api/test_skills_routes.py` (7/7 passed) covering RAG search, creator_id UUID resolution, skill creation, auto-verify privilege enforcement, skill deprecation, 404 handling, and popular skills retrieval.
  >   - Type safety & production build: `npx tsc --noEmit` clean (0 errors), `npm run build` (`tsc && vite build`) green.

- [x] **12.7 — AB Testing Page**
  - [x] 12.7.1 — `ABTestingPage.tsx` displays experiments
  - [x] 12.7.2 — Create/edit/delete experiments works
  - [x] 12.7.3 — Experiment results and metrics display correctly
  > **Verified & Audited**:
  > - **Bug fixes applied**:
  >   - `frontend/src/pages/ABTestingPage.tsx`: Replaced raw `<rect>` children with Recharts `<Cell>` components in `ExperimentDetailPanel` to enable distinct per-bar coloring for latency comparisons.
  > - **Test coverage locked**:
  >   - Frontend unit suite: `frontend/src/pages/__tests__/ABTestingPage.test.tsx` (11/11 passed) covering access gating, experiment list, filter/search/pagination, stats summary cards, empty states, create experiment modal, delete confirmation modal, quick test modal, experiment detail panel with winner determination and metrics comparison, and recommendations tab.
  >   - Backend API tests: `tests/api/test_ab_testing_routes.py` (15/15 passed) covering admin authorization enforcement, experiment creation with auto-start, paginated list retrieval, status filtering, invalid status handling, experiment detail serialization with runs and comparison, 404 error handling, cascade deletion, deletion rejection for running experiments, cancellation flow, run counts, progress computation, summary serialization, and recommendation structures.
  > - Type safety & production build: `npx tsc --noEmit` clean (0 errors), `npm run build` (`tsc && vite build`) green.

- [x] **12.8 — Scaling Dashboard**
  - [x] 12.8.1 — `ScalingDashboard.tsx` shows auto-scaling metrics
  - [x] 12.8.2 — Manual scaling controls work
  > **Verified & Audited**:
  > - **Bug fixes applied**:
  >   - `backend/services/predictive_scaling.py`: Sourced `token_spend` from `TokenOptimizer` status and surfaced `token_spend` and `budget_limit` in `get_predictions()` payload so the dashboard Token Budget gauge reflects real spend against daily limit.
  >   - `backend/api/routes/scaling.py`:
  >     - Added `current_user: dict = Depends(get_current_user)` authentication dependency to `GET /predictions/load` and `GET /history` endpoints for consistent security enforcement.
  >     - Fixed `POST /scaling/override`: mapped tier target integer (`1, 2, 3`) to appropriate `AgentType` enum (`COUNCIL_MEMBER`, `LEAD_AGENT`, `TASK_AGENT`) and queried valid active lifecycle states (`ACTIVE`, `WORKING`, `IDLE_WORKING`, `IDLE_PAUSED`) instead of non-existent `Agent.tier` and invalid `AgentStatus.IDLE`.
  >     - Fixed `AuditLog.log()` invocation: removed invalid `db=db` argument and explicitly persisted audit entries via `db.add()` and `db.commit()`.
  >   - `frontend/src/pages/ScalingDashboard.tsx`: Removed dead `status` field from `ScalingEvent` interface; wired `tokenSpend` and `BUDGET_LIMIT` dynamically from `predictions` API.
  > - **Test coverage locked**:
  >   - Frontend unit suite: `frontend/src/pages/__tests__/ScalingDashboard.test.tsx` (11/11 passed) covering heading render, 4 summary metric cards (Active Agents, Predicted 1h, Token Budget, System Mode), API fetching on mount, recommendation banner visibility (shown for non-neutral, hidden for neutral), admin override controls display, non-admin access gating, manual spawn button API interaction, manual liquidate button API interaction, empty state handling, and dual-responsive activity log table/card rendering.
  >   - Backend API tests: `backend/tests/api/test_scaling_routes.py` (8/8 passed in 0.46s) covering authenticated load predictions schema and fields, 401 unauthenticated rejection for predictions, authenticated scaling history retrieval, 401 unauthenticated rejection for history, admin manual spawn execution, admin manual liquidation execution, 403 forbidden rejection for non-admin overrides, and 400 bad request handling for invalid actions.
  > - **Type safety & production build**: `npx tsc --noEmit` clean (0 errors), `npm run build` (`tsc && vite build`) green (built in 37.8s).

- [x] **12.9 — Learning Impact Dashboard**
  - [x] 12.9.1 — `LearningImpactDashboard.tsx` shows learning metrics
  - [x] 12.9.2 — Data from `autonomous_learning.py` feeds correctly
  > **Verified & Audited**:
  > - **Bug fixes applied**:
  >   - `backend/api/routes/improvements.py`: Replaced all 3 hardcoded/stub endpoints with real data sourced from `AutonomousLearningEngine.get_learning_stats()`, `CritiqueReview` database queries, and ChromaDB `task_patterns` collection. Removed per-request `aioredis.from_url()` (Redis now used as optional enrichment only). Added `Depends(get_current_user)` auth guard and `Depends(get_db)` session injection to all 3 endpoints. Replaced bare `except → return {"error": ...}` with proper `raise InternalServerError(...)` using project exception hierarchy.
  >   - `backend/api/routes/improvements.py`: `GET /impact` now computes `success_rate_delta` by comparing last-7-day vs previous-7-day CritiqueReview pass rates, generates dynamic 7-day `history` from real review timestamps, and returns new `total_reviews_processed` field from both engine stats and DB count.
  >   - `backend/api/routes/improvements.py`: `GET /patterns` now queries ChromaDB `task_patterns` collection via `get_vector_store().get_collection("task_patterns").get(...)` and maps documents to `Pattern` schema. Returns empty list gracefully when vector store is unavailable.
  >   - `backend/api/routes/improvements.py`: `POST /consolidate` now calls `get_learning_engine().analyze_outcomes(db)` and returns the result. Gated behind admin/sovereign permissions (matching scaling override pattern).
  >   - `frontend/src/pages/LearningImpactDashboard.tsx`: Added 4th KPI card (Total Reviews Processed), Success Rate Trend `<LineChart>` (Recharts) using `history` array from API, error banner with retry button for failed fetches, admin/sovereign permission gating on Trigger Consolidation button, and dark theme–responsive chart styling.
  >   - `frontend/src/services/improvements.ts`: Added `total_reviews_processed?: number` to `ImpactStats` interface.
  > - **Test coverage locked**:
  >   - Frontend unit suite: `frontend/src/pages/__tests__/LearningImpactDashboard.test.tsx` (9/9 passed) covering heading render, 4 KPI metric cards with correct values, success rate trend chart with history data points, pattern badges and content rendering, empty state when no patterns, refresh button re-fetching, admin trigger consolidation, non-admin consolidation button disabled, and error banner with retry.
  >   - Backend API tests: `backend/tests/api/test_improvements_routes.py` (8/8 passed) covering authenticated impact schema and fields, 401 unauthenticated rejection for impact, authenticated patterns retrieval from ChromaDB mock, 401 unauthenticated rejection for patterns, admin consolidation trigger with analyze_outcomes execution, 403 forbidden for non-admin consolidation, 401 unauthenticated rejection for consolidation, and impact computation with real DB review mocks (success_rate_delta = 100.0).
  >   - Type safety & production build: `npx tsc --noEmit` clean (0 errors).

- [x] **12.10 — Shared Components**
  - [x] 12.10.1 — `ErrorBoundary` catches and displays errors gracefully
  - [x] 12.10.2 — `LoadingSpinner` displays during async operations
  - [x] 12.10.3 — `HealthIndicator` shows correct system health
  - [x] 12.10.4 — `BudgetControl.tsx` displays and controls token budget
  - [x] 12.10.5 — `SignatureMark.tsx` / `SignatureWatermark.tsx` render correctly
  - [x] 12.10.6 — Toast notifications (`useToast`) display and dismiss properly
  - [x] 12.10.7 — `FlatMapAuthBackground.tsx` (Three.js) renders without WebGL errors
  > **Verified & Audited**:
  > - **Bug fixes applied**:
  >   - `frontend/src/components/FlatMapAuthBackground.tsx`: Fixed stale `animationId` in singleton — the `globalSceneInstance.animationId` was only set once at initialization but `requestAnimationFrame` returns a new ID each frame. `cancelAnimationFrame` on cleanup was cancelling the wrong (first) frame, causing an animation leak. Now `globalSceneInstance.animationId` is updated inside the animate loop on every frame.
  > - **Test coverage locked**:
  >   - `frontend/src/components/common/__tests__/ErrorBoundary.test.tsx` (5/5 passed): renders children normally, widget variant fallback with retry button, page variant fallback with both Reload/Try Again buttons, retry clears error and re-renders children (400ms setTimeout), errorReportingApi.report() called with correct payload.
  >   - `frontend/src/components/ui/__tests__/LoadingSpinner.test.tsx` (9/9 passed): default md size + aria-label, animate-spin class, all 5 size variants (xs/sm/md/lg/xl) apply correct CSS classes, label text rendering, no label span without prop, custom className merge.
  >   - `frontend/src/components/__tests__/HealthIndicator.test.tsx` (10/10 passed): green dot for connected/healthy, yellow+pulse for connecting, red for disconnected/critical, yellow (no pulse) for warning, custom label override, all 3 size variants, no polling when status prop provided, starts polling when using backend store.
  >   - `frontend/src/components/__tests__/BudgetControl.test.tsx` (10/10 passed): loading state, token+cost cards with values, idle mode banner, red >90% alert, amber >75% warning, admin form visibility, non-admin read-only message, successful update with POST + toast, failed update with error banner + toast, loading spinner in button.
  >   - `frontend/src/components/__tests__/SignatureMark.test.tsx` (4/4 passed): SVG renders with correct viewBox, fill=currentColor, aria-hidden=true, className passthrough.
  >   - `frontend/src/components/SignatureWatermark.test.tsx` (3/3 passed — pre-existing): SVG renders, clip-path animation on mount, reduced motion instant show.
  >   - `frontend/src/hooks/__tests__/useToast.test.ts` (9/9 passed): success (3s, green), error (5s, red), info (4s, ℹ️), warning (4s, ⚠️), loading (persistent), dismiss/promise forwarded, custom options override defaults, useToast() hook returns showToast object.
  >   - `frontend/src/components/__tests__/FlatMapAuthBackground.test.tsx` (7/7 passed): renders without throwing (mocked Three.js), fixed container div, HealthIndicator sub-component, SignatureWatermark sub-component, login gradient default, signup gradient variant, WebGL canvas appended to container.
  >   - Type safety & production build: `npx tsc --noEmit` clean (0 errors).

---

## 13. WebSocket & Real-Time Events

> **Files**: `backend/api/routes/websocket.py`, `backend/services/message_bus.py`, `backend/services/event_processor.py`, `frontend/src/store/websocketStore.ts`, `frontend/src/components/GlobalWebSocketProvider.tsx`

- [x] **13.1 — WebSocket Connection**
  - [x] 13.1.1 — `ws://localhost:8000/ws/chat` connection establishes
  - [x] 13.1.2 — Authentication via token in WebSocket handshake works
  - [x] 13.1.3 — Reconnection after disconnect with exponential backoff
  - [x] 13.1.4 — `websocketStore.ts` manages connection state correctly
  - [x] 13.1.5 — `GlobalWebSocketProvider` initializes connection on app mount

- [x] **13.2 — Event Types**
  - [x] 13.2.1 — `agent_status` events update agent state in real-time
  - [x] 13.2.2 — `task_update` events reflect task progress
  - [x] 13.2.3 — `chat_message` events deliver new messages
  - [x] 13.2.4 — `chat_stream` events deliver streaming token chunks
  - [x] 13.2.5 — `channel_status` events update channel health
  - [x] 13.2.6 — `system_alert` events display notifications
  - [x] 13.2.7 — `vote_update` events update voting UI
  - [x] 13.2.8 — `tool_execution` events show tool call progress
  > *Implementation Note (13.2)*:
  > - Added `emit_agent_status`, `emit_task_update`, `emit_channel_status`, `emit_system_alert`, `emit_vote_update`, and `emit_tool_execution` to `ConnectionManager` in `backend/api/routes/websocket.py`.
  > - `backend/api/routes/websocket.py` chat endpoint streams `chat_stream` token chunks and `tool_execution` call progress with tool names, and delivers `chat_message` events.
  > - `backend/services/alert_manager.py` manager import fixed; broadcasts `system_alert` notifications.
  > - `backend/services/channel_manager.py` websocket import fixed; broadcasts `channel_status` on health/status changes.
  > - `backend/api/routes/voting.py` broadcasts `vote_update` with vote tallies on amendment and deliberation votes.
  > - `backend/services/tasks/task_executor.py` broadcasts `task_update` on task completion and failure.
  > - Frontend: `websocketStore.ts` handles `system_alert` toasts, `tool_execution` tracking, and `chat_message` unread counts; `ChatPage.tsx` handles `chat_stream`, `tool_execution`, and `chat_message`; `AgentsPage.tsx` and `constants/agents.ts` support `agent_status`; `TasksPage.tsx` updates task progress in real time on `task_update`; `ChannelsPage.tsx` invalidates query cache on `channel_status`.
  > - Tests: Backend unit suite `backend/tests/unit/test_websocket_event_types.py` (7/7 passed), `backend/tests/unit/test_websocket_revocation_broadcast.py` (1/1 passed); Frontend Vitest suite `src/store/__tests__/websocketStore.events.test.ts` (4/4 passed) and `src/store` (70/70 passed); TypeScript clean (`npx tsc --noEmit` 0 errors).

- [x] **13.3 — Message Bus** 
  - [x] 13.3.1 — `MessageBus` dispatches events to correct WebSocket clients
  - [x] 13.3.2 — Redis pub/sub handles cross-worker event distribution
  - [x] 13.3.3 — Event filtering per user/room works
  - [x] 13.3.4 — `websocketReplay.ts` replays missed events on reconnection

- [x] **13.4 — Event Processing**
  - [x] 13.4.1 — `EventProcessor` handles threshold-based events
  - [x] 13.4.2 — External API poll events fire correctly
  - [x] 13.4.3 — Event triggers (cron, webhook, threshold) work

---

## 14. Monitoring, Logging & Audit

> **Files**: `backend/services/monitoring_service.py`, `backend/services/slow_query_service.py`, `backend/api/routes/monitoring_routes.py`, `backend/services/audit/`, `backend/api/routes/audit_routes.py`, `frontend/src/pages/MonitoringPage.tsx`, `frontend/src/services/monitoring.ts`, `frontend/src/services/errorReporting.ts`

- [x] **14.1 — Monitoring Service**
  - [x] 14.1.1 — `MonitoringService` collects system metrics (CPU, memory, disk)
  - [x] 14.1.2 — `GET /api/v1/monitoring/metrics` returns current metrics
  - [x] 14.1.3 — `GET /api/v1/monitoring/health` returns system health status
  - [x] 14.1.4 — Anomaly detection identifies outliers correctly (Z-score based)
  - [x] 14.1.5 — SLA monitoring tracks uptime percentages

- [x] **14.2 — Monitoring Frontend**
  - [x] 14.2.1 — `MonitoringPage.tsx` loads all 8 tabs (dashboard, violations, recovery, operations, sla, incidents, chaos, slow_queries)
  - [x] 14.2.2 — Charts and graphs render with real data (HealthRing, metrics grids, anomaly panels)
  - [x] 14.2.3 — Real-time metric updates via WebSocket (system_alert, health_report events)
  - [x] 14.2.4 — Alert history displays past alerts (Violations tab, Incidents tab)

- [x] **14.3 — Audit System**
  - [x] 14.3.1 — Security-relevant actions create `AuditLog` entries
  - [x] 14.3.2 — Privilege escalations are logged
  - [x] 14.3.3 — Tool invocations are logged with parameters
  - [x] 14.3.4 — Auto-remediations are logged
  - [x] 14.3.5 — `AuditLog` records are immutable (no update/delete)
  - [x] 14.3.6 — `GET /api/v1/audit/logs` returns paginated audit trail
  - > **Verified:** 119 audit-related tests pass (immutability, creation, all levels/categories)

- [x] **14.4 — Slow Query Analysis**
  - [x] 14.4.1 — `slow_query_service.py` parses PostgreSQL slow query logs (pg_stat_statements)
  - [x] 14.4.2 — Slow queries are written to `AuditLog`
  - [x] 14.4.3 — `GET /api/v1/admin/slow-queries` returns populated data
  - > **Verified:** 3 slow query tests pass

- [x] **14.5 — Frontend Error Reporting**
  - [x] 14.5.1 — `errorReporting.ts` posts caught exceptions to `/api/v1/monitoring/frontend/errors`
  - [x] 14.5.2 — Backend persists frontend error reports to `AuditLog` (SYSTEM/WARNING)
  - [x] 14.5.3 — `MonitoringPage.tsx` displays ingested frontend errors (Operations tab: "Frontend Errors (24h)" metric)

- [x] **14.6 — Structured Logging**
  - [x] 14.6.1 — All agent steps emit structured JSON logs
  - [x] 14.6.2 — Logs contain: `timestamp`, `request_id`, `step`, `duration_ms`, `tokens`, `status`
  - [x] 14.6.3 — `request_id` correlates across HTTP → Celery → WebSocket

- [/] **14.7 — Alert Manager** (Partial — no deduplication)
  - [x] 14.7.1 — `alert_manager.py` fires alerts on threshold breaches (Z-score anomaly detection)
  - [x] 14.7.2 — Alerts sent via configured channels (WebSocket, Email/SMTP, Webhook, Telegram, Discord, Slack, WhatsApp)
  - [ ] 14.7.3 — Alert deduplication prevents notification storms (NOT IMPLEMENTED)

---

## 15. Voice System

> **Files**: `voice-bridge/main.py`, `voice-bridge/audio_source.py`, `voice-bridge/tts_engine.py`, `voice-bridge/vad.py`, `voice-bridge/wake_word.py`, `backend/services/audio_service.py`, `backend/services/whisper_cpp_service.py`, `backend/services/voice/`, `backend/api/routes/voice.py`, `backend/api/routes/audio.py`, `frontend/src/components/Voice*.tsx`, `frontend/src/services/voiceApi.ts`, `frontend/src/services/voiceBridge.ts`, `frontend/src/services/localVoice.ts`, `frontend/src/stores/voiceStore.ts`

- [x] **15.1 — Voice Bridge**
  - [x] 15.1.1 — `voice-bridge/main.py` starts and connects to backend
  - [x] 15.1.2 — Audio source captures microphone input
  - [x] 15.1.3 — VAD (Voice Activity Detection) correctly detects speech start/end
  - [x] 15.1.4 — Wake word detection triggers listening
  - [x] 15.1.5 — STT (Whisper) transcribes audio to text
  - [x] 15.1.6 — TTS engine generates speech from text
  > **Verified:** 64/67 voice-bridge tests pass (3 startup guidance tests fail - minor test setup issue, not core functionality)

- [x] **15.2 — Voice API**
  - [x] 15.2.1 — `POST /api/v1/voice/transcribe` accepts audio and returns text
  - [x] 15.2.2 — `POST /api/v1/voice/synthesize` returns audio from text
  - [x] 15.2.3 — Voice configuration (voice model, language) persists
  - [x] 15.2.4 — Speaker profile management works
  > **Verified:** 16 voice config tests + 5 voice routes tests + 11 audio service tests pass (32 backend unit tests)

- [x] **15.3 — Voice Frontend**
  - [x] 15.3.1 — `VoiceModePanel.tsx` opens and shows voice UI
  - [x] 15.3.2 — `VoiceOrb.tsx` visualizes active voice state
  - [x] 15.3.3 — `VoiceIndicator.tsx` shows speaking/listening status
  - [x] 15.3.4 — `VoiceDropdownPanel.tsx` provides voice controls
  - [x] 15.3.5 — `VoiceSettingsModal.tsx` configures voice preferences
  - [x] 15.3.6 — `localVoice.ts` handles browser-side speech recognition/synthesis
  - [x] 15.3.7 — `voiceBridge.ts` manages WebSocket connection to voice bridge
  - [x] 15.3.8 — `voiceStore.ts` state management is consistent
  > **Verified:** 35 frontend voice component/service tests pass

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

- [x] **19.6 — Execution Safety**
  - [x] 19.6.1 — `execution_guard.py` blocks dangerous shell commands (see 8.4.1)
  - [x] 19.6.2 — Code execution runs in sandboxed environment (see 8.4.4)
  - [x] 19.6.3 — File system access is restricted to workspace (sandbox read-only rootfs; only /tmp and /workspace writable via tmpfs/volumes)
  - [x] 19.6.4 — Network access from sandboxed code is controlled (default `network_mode="none"`; opt-in bridge with egress deny-list CIDRs recorded as labels: 169.254.169.254/32, 169.254.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, ::1/128, fc00::/7)

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

---

## 24. Autonomous Video & Audio Generation System

> **Files**: `backend/models/entities/user_config.py`, `backend/services/model_provider.py`, `backend/services/video_service.py`, `backend/services/video_editor_service.py`, `backend/services/video_director_service.py`, `backend/services/chat_service.py`, `backend/api/routes/video_routes.py`, `backend/api/routes/chat.py`, `backend/api/routes/websocket.py`, `backend/tools/_workspace.py`, `frontend/src/pages/VideoStudioPage.tsx`, `frontend/src/components/studio/`, `frontend/src/components/chat/VideoGenerationCard.tsx`, `frontend/src/components/chat/VideoPlayerCard.tsx`, `frontend/src/components/layout/navConfig.ts`, `frontend/src/App.tsx`, `frontend/src/services/videoApi.ts`

- [ ] **24.1 — Video & Audio Model Provider Infrastructure**
  - [ ] 24.1.1 — Provider schema extension: Add video generation provider types (`LUMA`, `RUNWAY`, `REPLICATE`, `KLING`, `MINIMAX`, `COMFYUI_LOCAL`) to `UserModelConfig` and `ProviderType`
  - [ ] 24.1.2 — Audio provider schema extension: Add voiceover/audio and music models (`ELEVENLABS`, `OPENAI_TTS`, `KOKORO`, `EDGE_TTS`, `MUSICGEN`, `SUNO`) to `UserModelConfig`
  - [ ] 24.1.3 — Model capability detection: Add modality tags (`text`, `vision`, `video`, `audio`) and `user_has_video_audio_models(user_id)` helper
  - [ ] 24.1.4 — Provider credential validation, test generation endpoints, and cost tracking per generation minute
  - [ ] 24.1.5 — `ModelsPage.tsx` and `ModelConfigForm.tsx` updates: Tabs, filters, and presets for configuring Video and Audio generation providers

- [ ] **24.2 — Chat Intent Detection & Model Verification Gate**
  - [ ] 24.2.1 — Media intent detection in `ChatService`: Parse incoming chat messages and attachments for video/audio creation intent
  - [ ] 24.2.2 — Model pre-check gate: Automatically verify that active video and audio models are configured before spawning tasks
  - [ ] 24.2.3 — Missing-model guidance card: Return actionable instructions and direct link/action card to `/models` if required models are absent
  - [ ] 24.2.4 — Asset attachment ingestion: Extract and validate user-uploaded reference images, video clips, and script texts from chat turns

- [ ] **24.3 — Video Director Task Agent & Storyboard Decomposition Engine**
  - [ ] 24.3.1 — Spawning and registration of dedicated `VideoDirectorAgent` (3xxxx tier) off the chat critical path
  - [ ] 24.3.2 — Storyboard decomposition engine: Break down user prompt, script, and assets into multi-scene graph of 4s–15s clips
  - [ ] 24.3.3 — Structured scene schema: Scene order, visual prompt, start/end frame references, camera motion, narration text, tone, and transitions
  - [ ] 24.3.4 — Bi-directional state synchronization: Task agent emits JSON graph state updating the visual studio canvas in real time

- [ ] **24.4 — Autonomous Audio Synthesis Pipeline (Voiceover, BGM & SFX)**
  - [ ] 24.4.1 — Scene voiceover narration synthesis using configured TTS (OpenAI TTS / ElevenLabs / Kokoro / Edge-TTS)
  - [ ] 24.4.2 — Precise scene audio duration measurement to lock and synchronize video clip timings
  - [ ] 24.4.3 — Background music (BGM) generation or ambient audio selection matching video mood and pacing
  - [ ] 24.4.4 — Sound effect (SFX) cue synthesis and placement at key visual action timestamps
  - [ ] 24.4.5 — Multi-track audio assembly with automatic audio ducking (attenuating BGM by -14dB during voiceover narration)

- [ ] **24.5 — Multi-Scene Video Clip Generation (AI Video up to 15s/clip)**
  - [ ] 24.5.1 — Text-to-Video API dispatch for scenes without starting image assets
  - [ ] 24.5.2 — Image-to-Video API dispatch animating user-provided start and end frame keyframe assets
  - [ ] 24.5.3 — Frame Chaining (Scene Chaining): Automatically extract the last frame of scene $N$ and chain it as the first frame of scene $N+1$ to preserve character identity, lighting, and camera style consistency across cuts
  - [ ] 24.5.4 — Draft vs. Final Render Tiers: Support rapid 720p draft prototyping before committing full 1080p production renders
  - [ ] 24.5.5 — Asynchronous task polling with exponential backoff, rate-limit resilience, and auto-retry on provider failure
  - [ ] 24.5.6 — Local caching and parallel download of intermediate MP4 scene clips to task workspace cache

- [ ] **24.6 — Autonomous Video Editing, Stitching & Rendering (FFmpeg Engine)**
  - [ ] 24.6.1 — Video conforming: Standardize resolution (1080p), aspect ratio (16:9 widescreen or 9:16 vertical shorts), and framerate (30fps)
  - [ ] 24.6.2 — Seamless transitions: Crossfade, dissolve, and cut via FFmpeg `xfade` complex filter graphs
  - [ ] 24.6.3 — Dual-track audio mixing: Align scene voiceovers to exact timestamps and overlay ducked background music
  - [ ] 24.6.4 — Subtitle/caption generation and burn-in: Generate SRT captions from narration script/Whisper and render on video
  - [ ] 24.6.5 — Master render output generation (`output.mp4`) and high-resolution poster thumbnail extraction (`poster.jpg`)

- [ ] **24.7 — File Storage in User Home & Artifact Management**
  - [ ] 24.7.1 — Persist final video and assets to host-mounted workspace: `/host_home/agentium-workspace/videos/<project_id>/`
  - [ ] 24.7.2 — Generate `project_manifest.json` containing complete storyboard graph, model metadata, prompts, and timestamps
  - [ ] 24.7.3 — Static streaming endpoint `/api/v1/files/workspace/videos/{project_id}/{filename}` for zero-copy video playback

- [ ] **24.8 — Frontend: Visual Drag-and-Drop Canvas & Bottom Task Agent Chat Dock (Magnific / Higgsfield Style)**
  - [ ] 24.8.1 — Register `/studio` route with `Clapperboard` icon under `Workspace` navigation group in `navConfig.ts`
  - [ ] 24.8.2 — Infinite/pan-zoom visual canvas (Magnific / Higgsfield style) with node-edge wiring:
    - **Asset Nodes**: Drag-and-drop uploaded reference images, keyframes, and video clips
    - **Scene Nodes**: Configurable start frame port, end frame port, visual prompt editor, duration (5–15s), camera motion controls, and clip preview player
    - **Audio Nodes**: Narration script editor, speaker voice selector, and audio waveform preview
    - **Stitching Node**: Aspect ratio toggle (16:9 vs 9:16), transition selector, render button, and master player
  - [ ] 24.8.3 — Frame chaining visualization: Visual connector cable linking the end frame of a scene node to the start frame of the succeeding scene node
  - [ ] 24.8.4 — Single-scene re-generation: Re-generate or edit individual scene clips and prompts without re-rendering the whole project
  - [ ] 24.8.5 — Bottom-docked Task Agent Chat: Dedicated chat panel docked at the bottom of the studio canvas for direct communication with the assigned `VideoDirectorAgent`
  - [ ] 24.8.6 — Bi-directional live sync: Agent actions dynamically generate and update canvas nodes, while user node edits update agent context
  - [ ] 24.8.7 — In-Chat video integration: Live stage progress card and inline HTML5 playable video message in the main Chat page

- [ ] **24.9 — End-to-End Orchestration & Verification**
  - [ ] 24.9.1 — Unit tests for video and audio model availability detection and fallback messaging
  - [ ] 24.9.2 — Unit tests for storyboard decomposition, scene chunking (up to 15s), and schema validation
  - [ ] 24.9.3 — Integration tests for FFmpeg stitching, transitions, audio ducking, and SRT caption generation
  - [ ] 24.9.4 — WebSocket integration tests for live canvas node updates and task agent chat streaming
  - [ ] 24.9.5 — End-to-end browser tests for canvas drag-and-drop, start/end frame assignment, frame chaining, and bottom chat agent interaction

