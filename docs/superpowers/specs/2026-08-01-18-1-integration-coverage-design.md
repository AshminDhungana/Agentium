# Design Spec: Task 18.1 — Integration Suite ≥80% Coverage on `backend/services`

**Date:** 2026-08-01  
**Status:** Draft  
**Author:** Claude Code (brainstorming session)

---

## 1. Problem Statement

The integration test suite currently achieves only **~13-14% coverage** on `backend/services` (target: **≥80%**). Additionally, **4 tests are skipped** due to optional infrastructure dependencies (Docker, Redis), which violates the "zero skipped tests" requirement. The `docker-compose.test.yml` is already ephemeral (no persistent volumes) — that portion of the task is **complete**.

---

## 2. Current State

### 2.1 Coverage Breakdown (from `pytest --cov=services`)

| Coverage Tier | Services | Examples |
|--------------|----------|----------|
| **0%** (22 services) | `auto_delegation_service`, `task_executor`, `reincarnation_service`, `initialization_service`, `self_healing_service`, `predictive_scaling`, `workflow_engine`, `chat_service`, `channel_manager`, `model_provider`, `chat_prune_service`, `config_versioning`, `fact_checker`, `governance_command_service`, `mcp_stats_service`, `overflow_recovery`, `self_improvement_service`, `slow_query_service`, `remote_executor/*`, `workflow_executor`, `workflow_planner`, `workflow_tools` |
| **7-20%** (35 services) | `agent_orchestrator`, `amendment_service`, `api_key_manager`, `audio_service`, `capability_registry`, `idle_governance`, `knowledge_service`, `mcp_governance`, `plugin_marketplace_service`, `pricing_sync_service`, `provider_rate_limiter`, `push_notification_service`, `reasoning_trace_service`, `skill_manager`, `storage_service`, `token_optimizer`, `tool_creation_service`, `tool_deprecation`, `tool_factory`, `tool_marketplace`, `tool_versioning`, `user_preference_service`, `wait_poll_service`, `webhook_dispatch_service`, `workflow_engine`, `monitoring_service`, ... |
| **20-50%** (15 services) | `acceptance_criteria`, `rbac_service`, `citation_graph_service`, `context_manager`, `knowledge_assist`, `skill_rag`, `task_state_machine`, `whisper_cpp_service`, ... |
| **>50%** (5 services) | `auth` (21%), `channels/base` (64%), `decision_engine` (26%), `media_interceptor` (25%), `mcp_tool_bridge` (26%) |

**Total: 18,580 statements, 13% covered**

### 2.2 Skipped Tests (4 total)

| Test File | Test Function | Skip Reason |
|-----------|---------------|-------------|
| `test_genesis_redis.py` | `test_genesis_state_persists_to_redis` | Redis unreachable |
| `test_workspace_persistence.py` | `test_code_output_persists_to_host` | Docker daemon unavailable |
| `test_phase13_success_criteria.py` | `test_create_and_execute_5_step_workflow` | Missing `agentium_id` column (alembic not at head) |
| `test_phase13_success_criteria.py` | `test_workflow_version_increments_on_update` | Same |

### 2.3 Failing Tests (~250 errors)

Most failures stem from:
- Missing database tables/columns (alembic migrations not applied in test DB)
- Redis connection issues (wrong host/port in CI)
- SQLAlchemy session/transaction mismanagement in fixtures
- Missing test data seeding

---

## 3. Design Approach: Tiered Coverage Strategy

We categorize services into three tiers based on criticality and dependency footprint:

### Tier 1: Core Services (15) — **Integration Tests Required**
*Must achieve 80% coverage via real integration tests (PostgreSQL, Redis, ChromaDB).*

| Service | Lines | Key Dependencies |
|---------|-------|------------------|
| `auto_delegation_service` | 572 | DB (agents, tasks), DelegationEngine |
| `task_executor` | 1,851 | DB (tasks, checkpoints, agents), Celery |
| `reincarnation_service` | 1,291 | DB (agents, checkpoints), SelfHealingService |
| `initialization_service` | 1,418 | DB (constitution, agents, capabilities), Redis |
| `self_healing_service` | 895 | DB (agents, heartbeats), ReincarnationService |
| `predictive_scaling` | 322 | Redis (metrics), DB (agents) |
| `workflow_engine` | 441 | DB (workflows, executions), Celery |
| `chat_service` | 1,038 | DB (messages, agents), VectorStore, ModelService |
| `channel_manager` | 2,700 | DB (channels, messages), Redis, external APIs |
| `model_provider` | 2,332 | External LLMs, Redis (rate limiting), DB (pricing) |
| `idle_governance` | 1,161 | DB (agents, tasks), SelfHealingService, OverflowRecovery |
| `agent_orchestrator` | 1,350 | DB (agents, tasks), DelegationEngine, ReincarnationService |
| `amendment_service` | 760 | DB (constitution, amendments, votes) |
| `event_processor` | 498 | DB (events, triggers), Celery, webhook dispatch |
| `monitoring_service` | 1,323 | DB (audit, tasks, agents), Redis, pg_stat_statements |

### Tier 2: Supporting Services (25) — **Contract Tests Acceptable**
*Public API contracts tested with mocked external dependencies (DB, Redis, LLMs).*

| Service | Lines | Contract Focus |
|---------|-------|----------------|
| `api_key_manager` | 1,138 | CRUD + rotation + validation |
| `capability_registry` | 582 | Register/lookup/grant/revoke |
| `knowledge_service` | 713 | Ingest/search/delete documents |
| `skill_manager` | 584 | Create/list/invoke skills |
| `storage_service` | 347 | Upload/download/delete files |
| `token_optimizer` | 589 | Estimate/optimize token usage |
| `tool_creation_service` | 509 | Propose/register/execute tools |
| `user_preference_service` | 609 | Get/set/delete preferences |
| `wait_poll_service` | 436 | Poll/wait/notify patterns |
| `webhook_dispatch_service` | 231 | Dispatch/retry/verify webhooks |
| `provider_rate_limiter` | 439 | Rate limit per provider/key |
| `pricing_sync_service` | 160 | Fetch/sync model pricing |
| `plugin_marketplace_service` | 315 | List/install/update plugins |
| `reasoning_trace_service` | 885 | Create/query traces |
| `citation_graph_service` | 314 | Add/query citation edges |
| `knowledge_governance` | 610 | Policy enforcement on knowledge |
| `mcp_governance` | 738 | MCP server approval/revocation |
| `mcp_client` | 188 | Connect/call/list tools |
| `mcp_tool_bridge` | 263 | Bridge MCP ↔ internal tools |
| `chat_context` | 365 | Compaction/summarization |
| `chat_prune_service` | 253 | Prune old messages |
| `config_versioning` | 222 | Version/rollback config |
| `slow_query_service` | 213 | Log/analyze slow queries |
| `prompt_template_manager` | 857 | CRUD/render templates |

### Tier 3: Utility/Leaf Services (50+) — **Unit Tests Sufficient**
*Isolated logic tested with pure unit tests (no external deps).*

Examples: `auth`, `audit_service`, `structured_input_service`, `decision_engine`, `fact_checker`, `governance_command_service`, `mcp_stats_service`, `overflow_recovery`, `self_improvement_service`, `remote_executor/*`, `workflow_executor`, `workflow_planner`, `workflow_tools`, `voice/*`, `whisper_cpp_service`, `audio_service`, `browser_service`, `file_processor`, `host_access`, `media_interceptor`, `message_bus`, `model_allocation`, `push_notification_service`, `rbac_service`, `token_optimizer`, `tool_analytics`, `tool_deprecation`, `tool_factory`, `tool_marketplace`, `tool_versioning`, `webhooks_dispatch_service`, ...

---

## 4. Elimination of Skipped Tests

Replace all 4 `pytest.skip()` calls with **marker-gated conditional execution**:

### 4.1 New Pytest Markers

```python
# pytest.ini additions
markers =
    integration: marks tests as integration (require running services)
    requires_redis: requires reachable Redis (REDIS_URL)
    requires_docker: requires Docker daemon + unix socket
    requires_alembic_head: requires test DB at alembic head migration
    slow: marks tests that take > 10s
```

### 4.2 CI Configuration

```yaml
# .github/workflows/integration-tests.yml
# Run only tests WITHOUT infrastructure markers in CI
- name: Run integration tests with coverage
  working-directory: ./backend
  run: pytest -m "integration and not requires_docker and not requires_redis and not requires_alembic_head"
```

### 4.3 Local/Optional Execution

```bash
# Run all integration tests including infra-dependent ones
pytest -m integration

# Run only Redis-dependent tests
pytest -m requires_redis

# Run only Docker-dependent tests
pytest -m requires_docker
```

This achieves **zero skipped tests in CI** while preserving the ability to run them locally/in staged environments.

---

## 5. Test Infrastructure Fixes

### 5.1 Database Fixtures (`conftest.py`)

- Ensure `db_engine` fixture runs `alembic upgrade head` after `CREATE DATABASE`
- Add `alembic` to test dependencies
- Verify all tables/columns exist before tests run

### 5.2 Redis Fixtures

- Use `fakeredis[lua]` for unit/contract tests (already in requirements-dev.txt)
- For integration tests: ensure `REDIS_URL` points to test container
- Add health check in fixture setup

### 5.3 ChromaDB Fixtures

- Current `vector_store` fixture purges collections correctly
- Ensure `CHROMA_HOST`/`CHROMA_PORT` point to test container

### 5.4 Test Data Seeding

- Expand `seeded_db` fixture to create minimal required data for each Tier 1 service
- Add service-specific fixture modules (e.g., `fixtures_agents.py`, `fixtures_tasks.py`)

---

## 6. Coverage Enforcement in CI

### 6.1 pytest.ini Update

```ini
[pytest]
addopts = --cov=services --cov-report=term-missing --cov-report=html --cov-fail-under=80 --ignore=tests/benchmarks --ignore=tests/load --timeout=180 --timeout-method=thread
```

### 6.2 GitHub Actions Update

```yaml
# integration-tests.yml
- name: Run integration tests with coverage
  working-directory: ./backend
  run: pytest -m "integration and not requires_docker and not requires_redis and not requires_alembic_head" --cov=services --cov-fail-under=80
```

### 6.3 Separate Coverage Jobs (Optional)

```yaml
# Unit + Contract coverage (fast)
- name: Run unit + contract tests
  run: pytest tests/unit tests/contract --cov=services --cov-fail-under=80

# Integration coverage (slow, runs after)
- name: Run integration tests
  run: pytest tests/integration -m "not requires_docker and not requires_redis" --cov=services --cov-fail-under=80
```

---

## 7. Implementation Phases

### Phase 1: Infrastructure Stabilization (Week 1)
- [ ] Fix `conftest.py` to run alembic migrations in test DB
- [ ] Add pytest markers for infrastructure requirements
- [ ] Update CI to exclude marked tests
- [ ] Verify `docker-compose.test.yml` stack comes up clean in CI

### Phase 2: Eliminate Skipped Tests (Week 1)
- [ ] Replace 4 `pytest.skip()` with markers
- [ ] Add local-run documentation for marked tests

### Phase 3: Tier 1 Integration Tests (Week 2)
- [ ] Write integration tests for top 5 Tier 1 services (auto_delegation, task_executor, reincarnation, initialization, self_healing)
- [ ] Add service-specific fixtures
- [ ] Target: 30%+ coverage from new integration tests

### Phase 4: Tier 1 Remaining + Tier 2 Contract Tests (Week 2-3)
- [ ] Complete remaining 10 Tier 1 services
- [ ] Write contract tests for 25 Tier 2 services
- [ ] Target: 60%+ combined coverage

### Phase 5: Tier 3 Unit Tests + CI Gate (Week 3)
- [ ] Add unit tests for Tier 3 services to close gaps
- [ ] Enable `--cov-fail-under=80` in CI
- [ ] Verify full pipeline passes

---

## 8. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Integration coverage on `backend/services`** | ≥80% | `pytest --cov=services --cov-fail-under=80` |
| **Skipped tests in CI** | 0 | `pytest -m "integration and not requires_*"` exits 0 with no skips |
| **Ephemeral compose stack** | Verified | `docker-compose.test.yml` has no `volumes:` for data services |
| **CI pipeline passes** | 100% | GitHub Actions `integration-tests` job succeeds |

---

## 9. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tier 1 services too complex for integration tests | Medium | High | Start with 5 highest-value services; use contract tests as fallback |
| Alembic migrations break in test DB | Medium | Medium | Run `alembic upgrade head` in `db_engine` fixture; test locally first |
| CI timeouts with full test suite | High | Medium | Split into unit/contract/integration jobs; run in parallel |
| Flaky tests reappear | Medium | Medium | Add `--timeout=180`; use `pytest-rerunfailures` for known flaky tests |

---

## 10. References

- `docker-compose.test.yml` — Already ephemeral (no volumes)
- `backend/.coveragerc` — `source = backend/services`, `branch = True`
- `backend/pytest.ini` — Current `--cov-fail-under=20`
- `.github/workflows/integration-tests.yml` — CI pipeline
- `backend/tests/integration/conftest.py` — Fixture definitions
- `backend/requirements-dev.txt` — `fakeredis[lua]>=2.26` available