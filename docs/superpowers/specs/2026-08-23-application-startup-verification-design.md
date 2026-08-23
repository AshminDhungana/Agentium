# Application Startup (Lifespan) Verification Design

## Purpose
This document outlines the verification approach for the Application Startup (Lifespan) section (4.1) of the Agentium TODO.md verification backlog. The goal is to verify that all 9 sub-items under section 4.1 are functioning correctly.

## Scope
Verification of the following items from TODO.md section 4.1:
- 4.1.1: `lifespan()` in `main.py` completes all init steps without error
- 4.1.2: Security startup checks run (`run_security_startup_checks`)
- 4.1.3: Workspace config validation runs
- 4.1.4: Constitution seed executes on first boot
- 4.1.5: Persistent Council status check runs
- 4.1.6: API Manager, Model Allocator, Token Optimizer initialize
- 4.1.7: MCP Tool Bridge initializes (`init_bridge`)
- 4.1.8: Pricing sync runs in background
- 4.1.9: Idle Governance engine starts

## Architecture Overview
The Application Startup verification leverages the existing lifespan function in `backend/main.py` which orchestrates all initialization steps during application startup. Each verification item corresponds to a specific step or check within the lifespan function.

### Key Components
1. **Lifespan Function** (`backend/main.py:lifespan`) - Main orchestrator
2. **Security Startup Checks** (`backend/core/security_checks.py`) - MinIO credential validation
3. **Workspace Config Validation** (`backend/tools/_workspace.py`) - Host workspace verification
4. **Constitution Seeding** (`backend/services/initialization_service.py`) - Fallback constitution creation
5. **Persistent Council Status Check** (`backend/services/persistent_council.py`) - HeadOfCouncil verification
6. **API Manager Initialization** (`backend/services/api_manager.py`) - Universal provider support
7. **Model Allocator Initialization** (`backend/services/model_allocation.py`) - Optimal model selection
8. **Token Optimizer Initialization** (`backend/services/token_optimizer.py`) - Cost optimization
9. **MCP Tool Bridge Initialization** (`backend/services/mcp_tool_bridge.py`) - MCP tool integration
10. **Pricing Sync Service** (`backend/services/pricing_sync_service.py`) - Background price updates
11. **Idle Governance Engine** (`backend/services/idle_governance.py`) - Background task processing

## Data Flow
1. Application startup triggers the `lifespan` async context manager in `main.py`
2. Each initialization step runs sequentially within the lifespan function:
   - Security startup checks (MinIO credentials)
   - Workspace persistence config validation
   - Database initialization and admin bootstrap
   - Constitution seeding (fallback)
   - Persistent Council status check
   - API Manager initialization
   - Model Allocator initialization
   - Token Optimizer initialization
   - API Key Manager initialization
   - Idle Governance Engine startup
   - Capability Registry loading
   - MCP Tool Bridge initialization
   - Knowledge Base bootstrap
   - Optional folder-skill seeding
   - VOICE_JWT_SECRET auto-generation
   - Browser service initialization (if enabled)

3. Background processes started during lifespan:
   - Pricing sync runs asynchronously
   - Idle Governance Engine starts background monitors
   - Database Maintenance Service starts maintenance monitors

## Error Handling
Each verification item includes specific error handling:
- **Security Startup Checks**: Logs warning for default MinIO credentials, raises RuntimeError if `MINIO_BLOCK_DEFAULT_CREDS=true`
- **Workspace Config Validation**: Logs warning if misconfigured, degrades to container-local storage
- **Database Initialization**: Raises exception on failure, aborting startup
- **Constitution Seeding**: Logs warning on failure, continues startup (non-fatal)
- **Persistent Council Status Check**: Logs warning on failure, continues startup (non-fatal)
- **API Manager Initialization**: Logs error on failure, continues startup
- **Model Allocator Initialization**: Logs error on failure, continues startup
- **Token Optimizer Initialization**: Logs error on failure, continues startup
- **MCP Tool Bridge Initialization**: Logs warning on failure, continues startup (manual sync available)
- **Knowledge Base Bootstrap**: Logs error on failure, continues startup
- **Idle Governance Engine**: Logs error on failure, continues startup without full background loops

## Testing Approach
Verification will be performed through:

1. **Startup Log Analysis**: Check application logs for success/failure messages for each initialization step
2. **Integration Tests**: Existing integration tests cover specific components:
   - `test_genesis_country_name_flow.py` - Constitution seeding and genesis
   - Various API endpoint tests that depend on initialized services
3. **Manual Verification Steps**:
   - Start application with `docker compose up` or `uvicorn backend.main:app`
   - Monitor logs for each verification item's success indicators
   - Verify background processes are running (pricing sync, idle governance)
   - Check API endpoints that require initialized services (models, tools, etc.)
   - Validate MCP tool availability through `/api/v1/mcp/status` endpoint
   - Confirm Idle Governance status through `/api/v1/governance/idle/status`

## Success Criteria
For each of the 9 verification items, the following must be true:
- **4.1.1**: No errors in lifespan function execution; all init steps complete
- **4.1.2**: Security startup checks execute and log appropriate messages (warning for default creds, error if blocked)
- **4.1.3**: Workspace config validation runs and logs configuration status
- **4.1.4**: Constitution seed executes on first boot and creates fallback constitution
- **4.1.5**: Persistent Council status check runs and logs HeadOfCouncil presence/absence
- **4.1.6**: API Manager, Model Allocator, and Token Optimizer initialize without errors
- **4.1.7**: MCP Tool Bridge initializes and loads approved tools
- **4.1.8**: Pricing sync service starts background task for price updates
- **4.1.9**: Idle Governance engine starts and begins background monitoring

## Implementation Notes
The verification approach leverages existing application startup mechanisms rather than creating new verification code. By examining application logs and checking service status endpoints, we can confirm each initialization step completed successfully.

All verification items are designed to be non-fatal where appropriate, allowing the application to start even if certain components fail (with degraded functionality), except for critical items like database initialization which will abort startup on failure.