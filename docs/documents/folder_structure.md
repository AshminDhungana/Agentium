# Complete Project Directory Structure Documentation

> **Definitive Repository Map for Agentium**  
> **Target Version:** `v0.21.0-beta`  
> **Last Synchronized:** Codebase Audit Verification  

---

## High-Level Root Layout

```
Agentium/
├── .github/                          # GitHub Actions workflows & issue templates
├── backend/                          # Core Python / FastAPI backend service
├── bridges/                          # External bridge services (WhatsApp Baileys, etc.)
├── docs/                             # Architecture Decision Records (ADRs) & documentation
├── frontend/                         # React 18 + Vite + TypeScript web SPA
├── mobile/                           # Native mobile clients (Android & iOS)
├── redis/                            # Custom Redis server configuration
├── scripts/                          # Host installation, voice startup, and bootstrap scripts
├── sdk/                              # Official developer SDKs (Python & TypeScript)
├── tests/                            # Global test suites (unit, integration, API, tasks)
├── voice-bridge/                     # Neural voice bridge service (STT, TTS, VAD, Wake-word)
├── docker-compose.yml               # Production multi-container composition
├── docker-compose.test.yml          # Ephemeral test infrastructure composition
├── docker-compose.remote-executor.yml # Hardened sandboxed execution container
├── Makefile                         # Developer CLI commands
├── nginx.conf                       # Production Nginx reverse proxy
└── README.md                        # Project overview and quick start guide
```

---

## 1. Backend Service (`backend/`)

```
backend/
├── main.py                           # FastAPI application entry point, lifespan, & router mounting
├── celery_app.py                     # Celery configuration & 34 beat periodic schedules
├── alembic.ini                       # Alembic database migration configuration
├── requirements.txt                  # Production Python dependencies
├── requirements-dev.txt              # Developer & testing dependencies
├── pytest.ini                        # Pytest test suite configuration
├── Dockerfile                        # Standard backend Dockerfile
├── Dockerfile.privileged             # Privileged Dockerfile for host workspace access
├── Dockerfile.remote-executor        # Air-gapped container image for sandbox execution
│
├── alembic/                          # Database migration scripts
│   ├── env.py                        # Alembic runtime environment
│   ├── script.py.mako                # Migration file template
│   └── versions/                     # Migration versions
│       ├── 000_combined_migration.py # Initial baseline migration
│       └── ...                       # Incremental schema migrations
│
├── api/                              # HTTP Presentation Layer
│   ├── dependencies/                 # Route dependencies
│   │   └── auth.py                   # JWT user & role dependency injection
│   ├── schemas/                      # Pydantic 2 request & response schemas
│   │   ├── examples.py               # RFC 7807 response schema builders
│   │   ├── messages.py               # Chat & routing schema models
│   │   ├── task.py                   # Task request/response contracts
│   │   └── tool_creation.py          # Dynamic tool generation contracts
│   ├── host_access.py                # Host workspace file & system access
│   ├── sovereign.py                  # Sovereign administrator endpoints
│   └── routes/                       # 47 Modular API route controllers
│       ├── ab_testing.py             # Model & prompt A/B testing
│       ├── admin.py                  # Administrative controls & health
│       ├── agents.py                 # Agent fleet queries & detail
│       ├── api_keys.py               # Provider API key management
│       ├── audio.py                  # Audio file upload & processing
│       ├── audit_routes.py           # Sovereign audit log queries
│       ├── auth.py                   # User registration, login, token refresh
│       ├── browser.py                # Playwright streaming & screenshot queries
│       ├── capability_routes.py      # Runtime capability inspection
│       ├── channels.py               # 12 communication channel configuration
│       ├── chat.py                   # Multi-agent chat endpoint
│       ├── checkpoints.py            # Agent memory checkpointing & branching
│       ├── constitution.py           # Constitution viewing & amendment proposals
│       ├── critics.py                # Independent Judiciary review records
│       ├── dashboard.py              # Primary executive metrics
│       ├── events.py                 # Event triggers & threshold rules
│       ├── federation.py             # Instance peer-to-peer federation
│       ├── files.py                  # S3/local file uploads and downloads
│       ├── genesis.py                # First-boot Genesis Protocol controller
│       ├── improvements.py           # Self-improvement learning metrics
│       ├── inbox.py                  # Unified multimodal communication inbox
│       ├── knowledge.py              # RAG knowledge base & citation graph
│       ├── lifecycle_routes.py       # Agent status transitions (ACTIVE, SUSPENDED...)
│       ├── mcp_tools.py              # Model Context Protocol tools router
│       ├── mobile.py                 # Mobile device registration & delta sync
│       ├── models.py                 # Multi-provider model configuration
│       ├── monitoring_routes.py      # Zero-Touch Operations metrics
│       ├── outbound_webhooks.py      # Outbound webhook event subscriptions
│       ├── plugins.py                # Third-party plugin marketplace
│       ├── provider_analytics.py     # Provider latency, cost, and usage stats
│       ├── rbac.py                   # Role-Based Access Control configuration
│       ├── reassign_routes.py        # Task reassignment & escalation
│       ├── remote_executor.py        # Sandboxed execution gateway
│       ├── scaling.py                # Predictive auto-scaling dashboard
│       ├── scheduled_tasks.py        # User scheduled tasks dispatch
│       ├── skills.py                 # Skills management & execution
│       ├── tasks.py                  # Core task intake & lifecycle
│       ├── tool_creation.py          # Autonomous runtime tool creation
│       ├── tools.py                  # Central tool discovery registry
│       ├── user_preferences.py       # User personal preferences
│       ├── users.py                  # User account management
│       ├── voice.py                  # Voice session tokens & commands
│       ├── voting.py                 # Legislative ballots & council voting
│       ├── wait_poll.py              # Workflow wait condition evaluator
│       ├── webhooks.py               # Inbound third-party webhooks
│       ├── websocket.py              # Real-time WebSocket connection hub
│       └── workflows.py              # DAG workflow automation engine
│
├── core/                             # Core Infrastructure & Middlewares
│   ├── auth.py                       # JWT token issuance, verification, password hashing
│   ├── chunking.py                   # Document chunking for vector ingestion
│   ├── config.py                     # Pydantic BaseSettings environment loader
│   ├── constitutional_guard.py       # Two-tier constitutional enforcement engine
│   ├── database.py                   # SQLAlchemy 2 engine, SessionLocal, healthcheck
│   ├── error_responses.py            # RFC 7807 standardized error response handlers
│   ├── exceptions.py                 # Typed HTTP domain exceptions
│   ├── llm_client.py                 # Unified multi-provider LLM abstraction
│   ├── middleware.py                 # Redis-backed RateLimitMiddleware
│   ├── observer_middleware.py        # Read-only observer role enforcement gate
│   ├── redis.py                      # Async Redis connection pool helper
│   ├── security_checks.py            # Security startup checks (MinIO creds, mounts)
│   ├── security_middleware.py        # DDoS, payload size, session, error counter
│   ├── timing_middleware.py          # Performance timing regression gate
│   ├── tool_registry.py              # Global runtime tool registry
│   ├── vector_store.py               # ChromaDB client & collection management
│   └── voice_auth.py                 # Voice bridge authentication helpers
│
├── models/                           # Domain Entities & Database Schema
│   ├── database.py                   # Database session helper & connection health
│   └── entities/                     # 40+ SQLAlchemy ORM entities
│       ├── ab_testing.py             # A/B test experiments & allocations
│       ├── agents.py                 # Agent entities, status enums, ID tiers
│       ├── audit.py                  # Tamper-evident AuditLog records
│       ├── channels.py               # 12 communication channel records
│       ├── chat_message.py           # Conversational messages
│       ├── checkpoint.py             # Agent memory checkpoints
│       ├── citation_edge.py          # Cross-document citation graph edges
│       ├── constitution.py           # Articles, rules, amendments, versions
│       ├── critics.py                # Critic reviews, verdicts, acceptance criteria
│       ├── delegation.py             # Task auto-delegation records
│       ├── event_trigger.py          # Event threshold triggers
│       ├── federation.py             # Peer instances & exchange logs
│       ├── knowledge_document.py     # Canonical knowledge records
│       ├── mcp_tool.py               # MCP server & tool registrations
│       ├── mobile.py                 # Mobile device tokens & sync states
│       ├── model_pricing.py          # Provider token pricing tables
│       ├── monitoring.py             # Telemetry & health snapshots
│       ├── plugin.py                 # Registered plugins
│       ├── reasoning_trace.py        # Detailed agent reasoning logs
│       ├── remote_execution.py       # Sandboxed execution logs & exit codes
│       ├── scheduled_task.py         # Scheduled task definitions
│       ├── skill.py                  # Registered skill definitions
│       ├── speaker_profile.py        # Voice recognition speaker profiles
│       ├── system_settings.py        # Dynamic system configuration
│       ├── task.py                   # Tasks, dependencies, status, priority
│       ├── task_events.py            # Chronological task event log
│       ├── tool_marketplace_listing.py # Published marketplace tools
│       ├── tool_staging.py           # Staging area for dynamic tools
│       ├── tool_usage_log.py         # Tool execution audit records
│       ├── tool_version.py           # Semantic tool version history
│       ├── user.py                   # Users, passwords, roles (RBAC)
│       ├── user_config.py            # User model API key configurations
│       ├── user_preference.py        # Individual user preference key-values
│       ├── voice_config.py           # Voice bridge configuration
│       ├── voting.py                 # Legislative proposals, votes, tallies
│       ├── wait_condition.py         # Workflow wait-and-poll conditions
│       ├── webhook.py                # Webhook registrations & delivery logs
│       └── workflow.py               # Workflow DAG templates, steps, executions
│
├── services/                         # Business Logic Layer (85+ modules)
│   ├── agent_orchestrator.py         # Central routing & circuit breaker engine
│   ├── api_key_manager.py            # API key resilience & rotation
│   ├── api_manager.py                # Multi-provider LLM client manager
│   ├── audio_service.py              # Audio transcription & TTS processing
│   ├── auto_delegation_service.py    # Complexity scoring (1–10) & delegation
│   ├── browser_service.py            # Playwright browser controller
│   ├── capability_registry.py        # Runtime capability permission checks
│   ├── channel_manager.py            # Multi-channel integration mesh
│   ├── citation_graph_service.py     # Citation graph BFS relevance boosting
│   ├── critic_agents.py              # Ephemeral Judiciary critic service
│   ├── db_maintenance.py             # Database cleanup & slow query tracking
│   ├── event_processor.py            # Event threshold evaluation
│   ├── federation_service.py         # Peer instance task & vote exchange
│   ├── idle_governance.py            # Persistent Council background patrols
│   ├── initialization_service.py     # Genesis Protocol & agent repair
│   ├── knowledge_service.py          # RAG pipeline & ChromaDB indexing
│   ├── mcp_tool_bridge.py            # Model Context Protocol bridge & stats
│   ├── model_allocation.py           # Tier-to-model allocation rules
│   ├── monitoring_service.py         # Zero-Touch Operations telemetry
│   ├── persistent_council.py         # Council member state manager
│   ├── push_notification_service.py  # FCM & APNs notification dispatcher
│   ├── rbac_service.py               # User role evaluation service
│   ├── reasoning_trace_service.py    # Agent reasoning trace inspector
│   ├── reincarnation_service.py      # Crash detection & agent resurrection
│   ├── self_healing_service.py       # Failover & degradation management
│   ├── skill_manager.py              # Skill registration & lifecycle
│   ├── storage_service.py            # S3 primary / local disk fallback
│   ├── token_optimizer.py            # Daily active & idle token budget caps
│   ├── tool_creation_service.py      # Dynamic tool generation & test harness
│   └── workflow_engine.py            # DAG workflow state transitions
│
└── tools/                            # 33 Built-in Tool Implementations
    ├── _workspace.py                 # Host workspace resolution & validation
    ├── browser_router.py             # Playwright vs. Nodriver routing
    ├── browser_tool.py               # Playwright headless browser tool
    ├── clarification_tool.py         # Human clarification request tool
    ├── code_analyzer_tool.py         # AST code analysis tool
    ├── code_execution_tool.py        # Local Python execution wrapper
    ├── data_transform_tool.py        # JSON/CSV data transform tool
    ├── deep_think_tool.py            # Extended reasoning scratchpad
    ├── desktop_tool.py               # OS desktop mouse & keyboard automation
    ├── embedding_tool.py             # On-demand vectorization tool
    ├── ethos_tool.py                 # Agent ethos memory tool
    ├── file_tool.py                  # Local filesystem read/write tool
    ├── git_tool.py                   # Git version control tool
    ├── governance_tool.py            # Council voting and status tool
    ├── host_os_tool.py               # Host operating system shell tool
    ├── http_api_tool.py              # Generic HTTP request tool
    ├── mcp_agent_tools.py            # MCP tool invocation wrapper
    ├── nodriver_tool.py              # Bot-detection bypass browser tool
    ├── remote_exec_tool.py           # Sandboxed code execution tool
    ├── shell_tool.py                 # Subprocess command runner
    ├── skill_creator_tool.py         # Automated skill directory generator
    ├── task_management_tool.py       # Child task spawning tool
    ├── text_editor_tool.py           # Precision file chunk editing tool
    ├── tool_creator_tool.py          # Dynamic tool creator tool
    ├── tool_search_tool.py           # Semantic tool search tool
    ├── user_preference_tool.py       # User preference access tool
    ├── vector_db_tool.py             # Direct ChromaDB vector querying
    ├── web_crawler_tool.py           # Multi-page web crawling tool
    ├── web_fetch_tool.py             # Single page markdown fetch tool
    └── web_search_tool.py            # Tavily / Brave / SerpAPI search tool
```

---

## 2. Frontend Application (`frontend/`)

```
frontend/
├── package.json                      # Node dependencies (React 18, Lucide, Tailwind, Vite)
├── vite.config.ts                    # Vite build configuration & proxy settings
├── tsconfig.json                     # TypeScript compiler configuration
├── Dockerfile                        # Nginx production build Dockerfile
│
└── src/
    ├── App.tsx                       # React Router root & authentication gate
    ├── main.tsx                      # DOM mount entry point
    ├── index.css                     # Design tokens, variables, & utility classes
    │
    ├── components/                   # Reusable UI components
    │   ├── layout/                   # Layout wrappers
    │   │   ├── Header.tsx            # Global top header & user menu
    │   │   ├── Sidebar.tsx           # Collapsible side navigation
    │   │   └── MainLayout.tsx        # Base page layout structure
    │   ├── ui/                       # Accessible UI primitive components
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── dialog.tsx
    │   │   ├── input.tsx
    │   │   └── select.tsx
    │   ├── AgentTree.tsx             # Interactive 99,999 agent hierarchy visualizer
    │   ├── BrowserTaskViewer.tsx     # Live Playwright viewport screenshot stream
    │   ├── ChatWindow.tsx            # Multi-agent conversation interface
    │   ├── TaskCard.tsx              # Task metadata & status component
    │   └── VoteCard.tsx              # Legislative Council ballot card
    │
    ├── pages/                        # 27 Route-Level Page Views
    │   ├── ABTestingPage.tsx         # Prompt and model A/B testing
    │   ├── AgentsPage.tsx            # Agent fleet inspection & state controls
    │   ├── ChannelsPage.tsx          # 12 communication channel configuration
    │   ├── ChatPage.tsx              # Primary multi-agent conversational interface
    │   ├── ConstitutionPage.tsx      # Constitution articles & amendment proposals
    │   ├── Dashboard.tsx             # Executive summary & system throughput
    │   ├── DeveloperPortalPage.tsx   # Developer API keys & documentation
    │   ├── FederationPage.tsx        # Cross-instance peer federation
    │   ├── LearningImpactDashboard.tsx # Learning effectiveness & RAG metrics
    │   ├── LoginPage.tsx             # Authentication portal
    │   ├── MessageLogPage.tsx        # Communication message audit trail
    │   ├── MobilePage.tsx            # Mobile client pairing & sync telemetry
    │   ├── ModelsPage.tsx            # LLM provider settings & API keys
    │   ├── MonitoringPage.tsx        # Zero-Touch Operations telemetry & logs
    │   ├── RBACManagement.tsx        # User roles and permissions editor
    │   ├── ScalingDashboard.tsx      # Predictive auto-scaling monitor
    │   ├── SettingsPage.tsx          # System settings & credentials
    │   ├── SignupPage.tsx            # Account registration
    │   ├── SkillsPage.tsx            # Skills catalog & execution playbook viewer
    │   ├── SovereignDashboard.tsx    # Sovereign command & emergency override view
    │   ├── TasksPage.tsx             # Task intake, queue, and detail inspect
    │   ├── ToolMarketplacePage.tsx   # Tool catalog and dynamic factory
    │   ├── Usermanagement.tsx        # User directory & status administration
    │   ├── VotingPage.tsx            # Legislative voting floor
    │   ├── WebhookManagementPage.tsx # Outbound webhook event configuration
    │   ├── WorkflowDesignerPage.tsx  # Visual DAG workflow builder
    │   └── WorkflowsPage.tsx         # Active workflow execution monitoring
    │
    ├── store/                        # Zustand Global State Management
    │   ├── authStore.ts              # JWT token & user profile state
    │   ├── backendStore.ts           # System status & metrics state
    │   └── websocketStore.ts         # Real-time WebSocket subscriptions
    │
    └── services/                     # Axios HTTP Client
        └── api.ts                    # Typed API client functions
```

---

## 3. Mobile Clients (`mobile/`)

```
mobile/
├── android/                          # Native Android Client (Kotlin)
│   ├── README.md                     # Android architecture & build guide
│   └── app/                          # Planned Gradle project structure
│       └── src/main/java/com/agentium/
│           ├── AgentiumApp.kt        # Hilt DI Application class
│           ├── MainActivity.kt       # Single-activity Compose host
│           ├── data/                 # Retrofit API & Room database
│           ├── service/              # FCM push & WorkManager sync
│           └── ui/                   # Jetpack Compose screens
│
└── ios/                              # Native iOS Client (Swift)
    ├── README.md                     # iOS architecture & build guide
    └── Agentium/                     # Planned Xcode project structure
        ├── App/                      # SwiftUI entry & navigation stack
        ├── Views/                    # Composable SwiftUI views
        ├── Services/                 # URLSession REST & APNs manager
        └── Persistence/              # Core Data offline store
```

---

## 4. Software Development Kits (`sdk/`)

```
sdk/
├── python/                           # Official Python SDK
│   ├── pyproject.toml                # Poetry / Flit build configuration
│   ├── README.md                     # Usage instructions & code samples
│   └── agentium_sdk/                 # Client library package
│       ├── __init__.py               # Top-level SDK exports
│       ├── client.py                 # AgentiumClient HTTP/WS wrapper
│       ├── models.py                 # Pydantic entity representations
│       └── exceptions.py             # SDK domain exceptions
│
└── typescript/                       # Official TypeScript SDK
    ├── package.json                  # NPM configuration (`@agentium/sdk`)
    ├── tsconfig.json                 # TypeScript build settings
    ├── README.md                     # Usage instructions & code samples
    └── src/                          # TypeScript source
        ├── index.ts                  # Public package exports
        ├── client.ts                 # AgentiumClient class
        ├── types.ts                  # Interface definitions
        ├── errors.ts                 # Typed error classes
        └── generated-types.ts        # Auto-generated OpenAPI schema types
```

---

## 5. Voice Bridge (`voice-bridge/`)

```
voice-bridge/
├── main.py                           # Voice daemon entry point & WebSocket bridge
├── wake_word.py                      # OpenWakeWord ("Hey Agentium") engine
├── vad.py                            # Silero Voice Activity Detection
├── audio_source.py                   # PyAudio microphone stream capture
├── tts_engine.py                     # Piper / OpenAI text-to-speech engine
├── run_voice_ui.py                   # Desktop voice UI helper
├── install.sh                        # Linux & macOS installer
├── requirements.txt                  # Voice service Python dependencies
└── README.md                         # Voice bridge documentation
```

---

## 6. External Bridges (`bridges/`)

```
bridges/
└── whatsapp/                         # Baileys WhatsApp Bridge
    ├── Dockerfile                    # Container configuration
    ├── package.json                  # Node.js dependencies (@whiskeysockets/baileys)
    └── src/
        └── index.ts                  # WebSocket bridge server & QR authenticator
```

---

## 7. Documentation & Decision Records (`docs/`)

```
docs/
├── ALEMBIC_MIGRATIONS.md             # Database migration procedures
├── chat-context-benchmark.md         # Context optimization benchmarks
├── knowledge_write_schema.md         # Schema for canonical knowledge promotions
│
├── adr/                              # Architecture Decision Records
│   ├── 001-dual-storage.md           # Decision: Dual PostgreSQL & ChromaDB
│   ├── 002-constitutional-guard-two-tier.md # Decision: SQL + Vector Guard
│   ├── 003-celery-over-asyncio.md    # Decision: Celery fleet over asyncio tasks
│   ├── 004-agent-id-numbering.md     # Decision: Immutable 5-digit tier ID scheme
│   ├── 005-rag-decay-scoring.md      # Decision: Exponential decay on learnings
│   ├── 009-error-response-standardization.md # Decision: RFC 7807 error format
│   └── 021-embedding-model-migration.md # Decision: Migration to bge-base-en-v1.5
│
└── documents/                        # In-Depth Reference Documents
    ├── TODO.md                       # Comprehensive implementation roadmap
    ├── agentium_guide.md             # The Operator & Citizen Guide
    ├── architectural_breakdown.md    # Deep Subsystem Technical Specification
    ├── folder_structure.md           # Complete Repository Directory Structure
    ├── selfhost.md                   # Self-hosting & production setup guide
    ├── tool_and_skill_creation.md    # Guide to extending tools and skills
    └── voice-bridge-setup.md         # Voice bridge setup & configuration
```

---

## 8. Test Suites (`tests/`)

```
tests/
├── conftest.py                       # Global test fixtures & database savepoints
├── api/                              # Route integration tests
├── integration/                      # Full-stack governance & lifecycle E2E tests
├── services/                         # Business logic unit tests
├── tasks/                            # Celery task execution tests
└── unit/                             # Core primitive unit tests
```

---

*Agentium Directory Structure Documentation · Version `v0.21.0-beta`*
