# Project Structure Documentation

This document provides a comprehensive overview of the Agentium project directory structure.

```
Agentium/
├── .github/                          # GitHub configuration
│   └── workflows/
│       └── docker-image.yml          # CI/CD Docker image workflow
├── bridges/                          # External service integrations
│   └── whatsapp/                    # WhatsApp bridge integration
│       ├── Dockerfile                # WhatsApp bridge container
│       ├── package.json              # Node.js dependencies
│       └── package-lock.json
├── backend/                          # Python FastAPI backend
│   ├── alembic/                      # Database migrations
│   │   ├── env.py                   # Alembic environment config
│   │   └── versions/                # Migration scripts
│   │       ├── 001_schema.py        # Initial schema
│   │       ├── 002_migration.py     # General migration
│   │       └── 003_consolidated.py  # Consolidated migration (Phases 3-11)
│   ├── api/                          # API layer
│   │   ├── dependencies/
│   │   │   └── auth.py              # Auth dependencies
│   │   ├── middleware/
│   │   │   └── auth.py               # Auth middleware
│   │   ├── routes/                  # API endpoints
│   │   │   ├── ab_testing.py        # A/B testing
│   │   │   ├── admin.py             # Admin endpoints
│   │   │   ├── api_keys.py          # API key management
│   │   │   ├── audio.py             # Audio processing
│   │   │   ├── auth.py              # Authentication
│   │   │   ├── browser.py           # Browser automation
│   │   │   ├── capability_routes.py # Capabilities API
│   │   │   ├── channels.py          # Channel management
│   │   │   ├── chat.py              # Chat endpoints
│   │   │   ├── checkpoints.py       # Checkpoint management
│   │   │   ├── critics.py           # Critic agents
│   │   │   ├── dashboard.py         # Dashboard data
│   │   │   ├── events.py            # Event processing
│   │   │   ├── federation.py        # Federation management
│   │   │   ├── files.py             # File operations
│   │   │   ├── inbox.py             # Unified inbox
│   │   │   ├── improvements.py      # Self-improvement engine
│   │   │   ├── lifecycle_routes.py  # Lifecycle management
│   │   │   ├── mcp_tools.py         # MCP tools
│   │   │   ├── mobile.py            # Mobile integration
│   │   │   ├── models.py            # Model management
│   │   │   ├── monitoring_routes.py # Monitoring endpoints
│   │   │   ├── outbound_webhooks.py # Outbound webhooks
│   │   │   ├── plugins.py           # Plugin marketplace
│   │   │   ├── provider_analytics.py # Provider analytics
│   │   │   ├── rbac.py              # Role-based access control
│   │   │   ├── remote_executor.py   # Remote execution
│   │   │   ├── scaling.py           # Predictive auto-scaling
│   │   │   ├── skills.py            # Skills management
│   │   │   ├── tasks.py             # Task management
│   │   │   ├── tool_creation.py     # Tool creation
│   │   │   ├── tools.py             # Tool registry
│   │   │   ├── user_preferences.py  # User preferences
│   │   │   ├── voice.py             # Voice features
│   │   │   ├── voting.py            # Voting/constitution
│   │   │   ├── webhooks.py          # Webhook handlers
│   │   │   ├── websocket.py         # WebSocket endpoints
│   │   │   └── workflows.py         # Workflow automation
│   │   ├── schemas/                 # Pydantic schemas
│   │   │   ├── checkpoint.py
│   │   │   ├── mcp_schemas.py
│   │   │   ├── remote_executor.py
│   │   │   ├── task.py
│   │   │   ├── tool_creation.py
│   │   │   └── user_preference.py
│   │   ├── host_access.py           # Host access API
│   │   └── sovereign.py             # Sovereign governance API
│   ├── core/                        # Core functionality
│   │   ├── auth.py                  # Authentication logic
│   │   ├── config.py                # Configuration
│   │   ├── constitutional_guard.py  # Constitutional governance
│   │   ├── observer_middleware.py   # Observer middleware
│   │   ├── security/                # Security module
│   │   │   ├── __init__.py
│   │   │   └── execution_guard.py   # Execution safety
│   │   ├── security_middleware.py   # Security middleware
│   │   ├── tool_registry.py         # Tool registry
│   │   ├── vector_store.py          # Vector embeddings
│   │   └── voice_auth.py            # Voice authentication
│   ├── models/                      # Database models
│   │   ├── database.py              # Database setup
│   │   ├── entities/                # SQLAlchemy entities
│   │   │   ├── __init__.py
│   │   │   ├── ab_testing.py        # A/B testing
│   │   │   ├── agents.py            # Agent definitions
│   │   │   ├── audit.py             # Audit logs
│   │   │   ├── base.py              # Base entity
│   │   │   ├── channels.py          # Channel configs
│   │   │   ├── chat_message.py      # Chat messages
│   │   │   ├── checkpoint.py        # Execution checkpoints
│   │   │   ├── constitution.py      # Constitution rules
│   │   │   ├── critics.py           # Critic agents
│   │   │   ├── delegation.py        # Delegation management
│   │   │   ├── federation.py        # Federation data
│   │   │   ├── mcp_tool.py          # MCP tools
│   │   │   ├── mobile.py            # Mobile device records
│   │   │   ├── model_provider.py    # LLM providers
│   │   │   ├── monitoring.py        # Monitoring data
│   │   │   ├── plugin.py            # Plugin definitions
│   │   │   ├── remote_execution.py  # Remote execution
│   │   │   ├── reasoning_trace.py   # Reasoning traces
│   │   │   ├── scheduled_task.py    # Scheduled tasks
│   │   │   ├── skill.py             # Skill definitions
│   │   │   ├── system_settings.py   # System config
│   │   │   ├── task.py              # Task definitions
│   │   │   ├── task_events.py       # Task events
│   │   │   ├── tool_marketplace_listing.py # Marketplace
│   │   │   ├── tool_staging.py      # Tool staging
│   │   │   ├── tool_usage_log.py    # Usage logs
│   │   │   ├── tool_version.py      # Tool versioning
│   │   │   ├── user.py              # User entities
│   │   │   ├── user_config.py       # User config
│   │   │   ├── user_preference.py   # User preferences
│   │   │   ├── voting.py            # Voting records
│   │   │   ├── webhook.py           # Webhook entities
│   │   │   └── workflow.py          # Workflow definitions
│   │   └── schemas/                 # Request/response schemas
│   │       ├── messages.py
│   │       ├── task.py
│   │       └── tool_creation.py
│   ├── scripts/                     # Backend utility scripts
│   │   ├── __init__.py
│   │   ├── create_initial_admin.py  # Admin setup
│   │   ├── init_db.py               # Database init
│   │   ├── init_vector_db.py        # Vector DB init
│   │   └── verify_channels.py       # Channel verification
│   ├── services/                    # Business logic services
│   │   ├── ab_testing_service.py    # A/B testing service
│   │   ├── acceptance_criteria.py   # Task validation
│   │   ├── agent_orchestrator.py   # Agent management
│   │   ├── alert_manager.py        # Alert management
│   │   ├── amendment_service.py    # Constitution amendments
│   │   ├── api_key_manager.py      # API key handling
│   │   ├── api_manager.py          # API management
│   │   ├── audio_service.py        # Audio processing
│   │   ├── audit/                   # Audit processing
│   │   │   ├── __init__.py
│   │   │   └── audit_processor.py   # Audit processor
│   │   ├── auth.py                  # Auth service
│   │   ├── auto_delegation_service.py # Automatic task delegation
│   │   ├── autonomous_learning.py  # Autonomous learning
│   │   ├── browser_service.py      # Browser automation
│   │   ├── capability_registry.py  # Agent capabilities
│   │   ├── channel_manager.py      # Channel orchestration
│   │   ├── channels/                # Channel integrations
│   │   │   ├── base.py              # Base channel
│   │   │   ├── slack.py             # Slack integration
│   │   │   └── whatsapp_unified.py  # WhatsApp integration
│   │   ├── chat_service.py         # Chat handling
│   │   ├── checkpoint_service.py   # Checkpoint management
│   │   ├── clarification_service.py # Clarification requests
│   │   ├── context_manager.py      # Context handling
│   │   ├── critic_agents.py        # Critic agent logic
│   │   ├── db_maintenance.py       # Database maintenance
│   │   ├── fact_checker.py         # Fact checking
│   │   ├── federation_service.py   # Federation management
│   │   ├── event_processor.py      # Event processing
│   │   ├── file_processor.py       # PDF/image extraction
│   │   ├── host_access.py          # Host access service
│   │   ├── idle_governance.py      # Idle management
│   │   ├── idle_tasks/              # Background idle tasks
│   │   │   └── preference_optimizer.py # Preference optimization
│   │   ├── initialization_service.py # System init
│   │   ├── knowledge_governance.py # Knowledge policies
│   │   ├── knowledge_service.py    # Knowledge base
│   │   ├── mcp_client.py           # MCP client
│   │   ├── mcp_governance.py       # MCP governance
│   │   ├── mcp_tool_bridge.py      # MCP tool bridge
│   │   ├── message_bus.py          # Message bus
│   │   ├── model_allocation.py     # Model allocation
│   │   ├── model_provider.py       # LLM provider mgmt
│   │   ├── monitoring/              # Monitoring services
│   │   │   ├── __init__.py
│   │   │   └── health_checks.py
│   │   ├── monitoring_service.py    # System monitoring
│   │   ├── persistent_council.py    # Persistent council
│   │   ├── plugin_marketplace_service.py # Plugin marketplace
│   │   ├── predictive_scaling.py   # Predictive auto-scaling
│   │   ├── prompt_template_manager.py # Prompt templates
│   │   ├── push_notification_service.py # Push notifications
│   │   ├── rbac_service.py         # RBAC management
│   │   ├── reasoning_trace_service.py # Reasoning trace
│   │   ├── reincarnation_service.py # Agent reincarnation
│   │   ├── remote_executor/         # Remote execution
│   │   │   ├── __init__.py
│   │   │   ├── executor.py
│   │   │   ├── sandbox.py
│   │   │   └── service.py
│   │   ├── self_healing_service.py  # Self-healing system
│   │   ├── self_improvement_service.py # Continuous self-improvement
│   │   ├── skill_manager.py        # Skill management
│   │   ├── skill_rag.py            # Skill RAG
│   │   ├── storage_service.py      # Storage service
│   │   ├── task_state_machine.py    # Task state logic
│   │   ├── tasks/                   # Task execution
│   │   │   ├── __init__.py
│   │   │   ├── task_executor.py
│   │   │   └── workflow_tasks.py
│   │   ├── token_optimizer.py       # Token optimization
│   │   ├── tool_analytics.py        # Tool analytics
│   │   ├── tool_creation_service.py # Tool creation
│   │   ├── tool_deprecation.py      # Tool deprecation
│   │   ├── tool_factory.py          # Tool factory
│   │   ├── tool_marketplace.py      # Tool marketplace
│   │   ├── tool_versioning.py       # Tool versioning
│   │   ├── user_preference_service.py # User preferences
│   │   ├── webhook_dispatch_service.py # Webhook dispatch
│   │   ├── workflow_engine.py       # Workflow engine
│   │   ├── workflow_executor.py     # Workflow execution
│   │   ├── workflow_planner.py      # Workflow planning
│   │   └── workflow_tools.py        # Workflow tools
│   ├── tools/                       # Built-in tools
│   │   ├── browser_router.py        # Browser routing
│   │   ├── browser_tool.py         # Browser automation
│   │   ├── code_analyzer_tool.py   # Code analysis
│   │   ├── data_transform_tool.py  # Data transformation
│   │   ├── deep_think_tool.py       # Deep thinking
│   │   ├── desktop_tool.py          # Desktop automation
│   │   ├── embedding_tool.py        # Embeddings
│   │   ├── file_tool.py            # File operations
│   │   ├── git_tool.py             # Git operations
│   │   ├── host_os_tool.py         # Host OS operations
│   │   ├── http_api_tool.py        # HTTP API calls
│   │   ├── nodriver_tool.py        # Browser automation
│   │   ├── shell_tool.py           # Shell commands
│   │   ├── text_editor_tool.py     # Text editing
│   │   ├── user_preference_tool.py # User preferences
│   │   └── web_search_tool.py      # Web search
│   ├── tests/                       # Backend tests
│   │   ├── services/
│   │   │   └── test_capability_registry.py
│   │   ├── unit/
│   │   │   └── services/
│   │   ├── test_federation_e2e.py   # Federation E2E tests
│   │   ├── test_outbound_webhooks.py # Outbound webhooks tests
│   │   ├── test_plugin_marketplace.py # Plugin marketplace tests
│   │   ├── test_push_notifications.py # Push notifications tests
│   │   ├── test_rbac_delegation.py  # RBAC delegation tests
│   │   ├── test_remote_executor.py  # Remote executor tests
│   │   └── test_voting.py           # Voting tests
│   ├── alembic.ini                  # Alembic config
│   ├── celery_app.py                # Celery async tasks
│   ├── chroma_data/                 # ChromaDB data (auto-generated)
│   ├── Dockerfile                   # Backend container
│   ├── Dockerfile.privileged        # Privileged container
│   ├── Dockerfile.remote-executor   # Remote executor container
│   ├── main.py                      # FastAPI app entry
│   └── requirements.txt             # Python dependencies

├── frontend/                        # React TypeScript frontend
│   ├── public/                      # Static assets
│   ├── src/
│   │   ├── assets/                  # Static assets
│   │   ├── components/              # React components
│   │   │   ├── agents/              # Agent components
│   │   │   │   ├── AgentCard.tsx
│   │   │   │   ├── AgentListView.tsx
│   │   │   │   ├── AgentTree.tsx
│   │   │   │   ├── BulkLiquidateModal.tsx
│   │   │   │   ├── CriticStatsPanel.tsx
│   │   │   │   ├── LifecycleDashboard.tsx
│   │   │   │   ├── PromoteAgentModal.tsx
│   │   │   │   ├── SpawnAgentModal.tsx
│   │   │   │   └── TerminateAgentModal.tsx
│   │   │   ├── BrowserTaskPanel.tsx # Browser task panel
│   │   │   ├── BudgetControl.tsx
│   │   │   ├── channels/            # Channel UI
│   │   │   │   ├── ChannelMetricsCard.tsx
│   │   │   │   ├── CircuitBreakerBadge.tsx
│   │   │   │   └── MessageLogViewer.tsx
│   │   │   ├── checkpoints/         # Checkpoint UI
│   │   │   │   ├── BranchDiffView.tsx
│   │   │   │   ├── CheckpointDiffModal.tsx
│   │   │   │   ├── CheckpointImportModal.tsx
│   │   │   │   └── CheckpointTimeline.tsx
│   │   │   ├── common/              # Shared components
│   │   │   │   ├── ErrorBoundary.tsx
│   │   │   │   └── ProtectedRoute.tsx
│   │   │   ├── ConnectionStatus.tsx
│   │   │   ├── council/             # Governance UI
│   │   │   │   └── VotingInterface.tsx
│   │   │   ├── dashboard/           # Dashboard components
│   │   │   │   ├── AgentsList.tsx
│   │   │   │   ├── ChannelHealthWidget.tsx
│   │   │   │   ├── DashboardHeader.tsx
│   │   │   │   ├── FinancialBurnDashboard.tsx
│   │   │   │   ├── ProviderAnalytics.tsx
│   │   │   │   ├── QuickActions.tsx
│   │   │   │   ├── RecentTasks.tsx
│   │   │   │   ├── StatsGrid.tsx
│   │   │   │   └── SystemHealth.tsx
│   │   │   ├── federation/          # Federation UI
│   │   │   │   ├── AddPeerModal.tsx
│   │   │   │   ├── DelegateTaskModal.tsx
│   │   │   │   └── PeerTable.tsx
│   │   │   ├── FlatMapAuthBackground.tsx
│   │   │   ├── GlobalWebSocketProvider.tsx
│   │   │   ├── HealthIndicator.tsx
│   │   │   ├── layout/              # Layout components
│   │   │   │   └── MainLayout.tsx
│   │   │   ├── mcp/                 # MCP tools UI
│   │   │   │   └── MCPToolRegistry.tsx
│   │   │   ├── models/              # Model config UI
│   │   │   │   ├── ModelCard.tsx
│   │   │   │   ├── ModelCardSkeleton.tsx
│   │   │   │   └── ModelConfigForm.tsx
│   │   │   ├── monitoring/          # Monitoring UI
│   │   │   │   ├── APIKeyHealth.tsx
│   │   │   │   ├── HealthScore.tsx
│   │   │   │   └── ViolationCard.tsx
│   │   │   ├── sovereign/           # Sovereign governance UI
│   │   │   │   └── SystemTab.tsx
│   │   │   ├── SovereignRoute.tsx
│   │   │   ├── tasks/               # Task UI
│   │   │   │   ├── AutoDelegationPanel.tsx
│   │   │   │   ├── CreateTaskModal.tsx
│   │   │   │   └── TaskCard.tsx
│   │   │   ├── UnifiedInbox.tsx
│   │   │   ├── ui/                  # Shared UI components
│   │   │   │   ├── button.tsx
│   │   │   │   ├── card.tsx
│   │   │   │   ├── DashboardSkeleton.tsx
│   │   │   │   ├── ErrorState.tsx
│   │   │   │   ├── StatCard.tsx
│   │   │   │   ├── Toggle.tsx
│   │   │   │   └── WidgetErrorFallback.tsx
│   │   │   ├── VoiceIndicator.tsx
│   │   │   └── workflows/           # Workflow UI
│   │   │       ├── WorkflowAutomationPanel.tsx
│   │   │       └── WorkflowBuilder.tsx
│   │   ├── constants/               # Constants and config
│   │   │   └── providerMeta.tsx
│   │   ├── context/                 # React context providers
│   │   │   └── DragDropContext.tsx
│   │   ├── hooks/                   # Custom React hooks
│   │   │   ├── useVoiceBridge.ts
│   │   │   └── useWebSocket.ts
│   │   ├── pages/                   # Page components
│   │   │   ├── ABTestingPage.tsx
│   │   │   ├── AgentsPage.tsx
│   │   │   ├── ChannelsPage.tsx
│   │   │   ├── ChatPage.tsx
│   │   │   ├── ConstitutionPage.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── DeveloperPortalPage.tsx
│   │   │   ├── FederationPage.tsx
│   │   │   ├── LearningImpactDashboard.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   ├── MessageLogPage.tsx
│   │   │   ├── MobilePage.tsx
│   │   │   ├── ModelsPage.tsx
│   │   │   ├── MonitoringPage.tsx
│   │   │   ├── RBACManagement.tsx
│   │   │   ├── ScalingDashboard.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   ├── SignupPage.tsx
│   │   │   ├── SkillsPage.tsx
│   │   │   ├── SovereignDashboard.tsx
│   │   │   ├── TasksPage.tsx
│   │   │   ├── ToolMarketplacePage.tsx
│   │   │   ├── Usermanagement.tsx
│   │   │   ├── VotingPage.tsx
│   │   │   └── WebhookManagementPage.tsx
│   │   ├── services/                # API service layers
│   │   │   ├── abTesting.ts
│   │   │   ├── admin.ts
│   │   │   ├── agents.ts
│   │   │   ├── api.ts
│   │   │   ├── apiKeysService.ts
│   │   │   ├── auth.ts
│   │   │   ├── browserApi.ts
│   │   │   ├── chatApi.ts
│   │   │   ├── channelMessages.ts
│   │   │   ├── channelMetrics.ts
│   │   │   ├── checkpoints.ts
│   │   │   ├── constitution.ts
│   │   │   ├── federation.ts
│   │   │   ├── fileApi.ts
│   │   │   ├── hostAccessApi.ts
│   │   │   ├── inboxApi.ts
│   │   │   ├── localVoice.ts
│   │   │   ├── mcpToolsApi.ts
│   │   │   ├── models.ts
│   │   │   ├── monitoring.ts
│   │   │   ├── plugins.ts
│   │   │   ├── preferences.ts
│   │   │   ├── providerAnalyticsApi.ts
│   │   │   ├── rbac.ts
│   │   │   ├── remoteExecutorApi.ts
│   │   │   ├── skills.ts
│   │   │   ├── tasks.ts
│   │   │   ├── voiceApi.ts
│   │   │   ├── voiceBridge.ts
│   │   │   ├── voting.ts
│   │   │   └── webhooksService.ts
│   │   ├── store/                   # State management (Zustand)
│   │   │   ├── authStore.ts
│   │   │   ├── backendStore.ts
│   │   │   ├── chatStore.ts
│   │   │   └── websocketStore.ts
│   │   ├── types/                   # TypeScript types
│   │   │   ├── hostAccess.ts
│   │   │   └── index.ts
│   │   ├── utils/                   # Utility functions
│   │   ├── App.tsx                  # Root component
│   │   ├── App.css                  # App styles
│   │   ├── index.css                # Global styles
│   │   └── main.tsx                 # Entry point
│   ├── Dockerfile
│   ├── eslint.config.js
│   ├── index.html
│   ├── nginx.conf
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts

├── mobile/                          # Mobile applications
│   ├── android/                     # Android app
│   │   └── README.md
│   └── ios/                         # iOS app
│       └── README.md

├── sdk/                             # Agentium SDKs
│   ├── python/                      # Python SDK
│   │   ├── agentium_sdk/            # Python SDK package
│   │   ├── pyproject.toml           # Python SDK config
│   │   ├── README.md
│   │   └── tests/                   # Python SDK tests
│   └── typescript/                  # TypeScript SDK
│       ├── src/                     # TypeScript SDK source
│       │   ├── client.ts
│       │   ├── errors.ts
│       │   ├── index.ts
│       │   └── types.ts
│       ├── package.json             # TypeScript SDK config
│       ├── tsconfig.json
│       ├── jest.config.js
│       ├── scripts/                 # Build scripts
│       ├── tests/                   # TypeScript SDK tests
│       └── README.md

├── docs/                            # Documentation
│   ├── architecture/                # Architecture documentation
│   │   └── scalability_strategy.md  # Scalability strategy
│   ├── assets/                      # Documentation assets
│   ├── constitution/
│   │   └── core.md                  # Constitution core
│   ├── documents/
│   │   ├── agentium_guide.md        # Agentium user guide
│   │   ├── architectural_breakdown.md # Architecture details
│   │   ├── folder_structure.md      # This file
│   │   ├── selfhost.md              # Self-hosting guide
│   │   └── todo.md                  # TODO list
│   ├── workflow/                    # Workflow documentation
│   │   ├── channel_verification.md
│   │   ├── dev_workflow.md
│   │   ├── multimodel_chat.md
│   │   ├── system_workflow.md
│   │   ├── task_execution.md
│   │   └── unified_inbox.md
│   └── phase10_plan.md              # Phase 10 planning

├── scripts/                          # Build and utility scripts
├── test/                             # Test files
├── voice-bridge/                     # Voice bridge functionality
├── .gitignore
├── .github/
│   └── workflows/
│       └── docker-image.yml
├── CONTRIBUTING.md                   # Contributing guidelines
├── LICENSE
├── Makefile                          # Build automation
├── README.md
├── docker-compose.yml                # Main compose file
├── docker-compose.remote-executor.yml
└── package.json                      # Root package (metadata)
```

## Architecture Overview

### Backend (Python/FastAPI)

- **api/**: REST API endpoints organized by feature
- **core/**: Core application logic (auth, config, security, vector store)
- **models/**: Database layer with SQLAlchemy entities
- **services/**: Business logic microservices
- **tools/**: Built-in agent tools
- **tests/**: Unit and integration tests

### Frontend (React/TypeScript)

- **components/**: Reusable UI components
- **pages/**: Route-level page components
- **services/**: API communication layer
- **store/**: State management (Zustand)
- **hooks/**: Custom React hooks
- **constants/**: Application constants
- **context/**: React context providers
- **utils/**: Utility functions

### Mobile

- **android/**: Android application
- **ios/**: iOS application

### SDKs

- **python/**: Python SDK for Agentium
- **typescript/**: TypeScript/JavaScript SDK for Agentium

### Infrastructure

- **bridges/**: External service integrations (WhatsApp)
- **docker-compose.yml**: Container orchestration
- **voice-bridge/**: Voice interaction bridge