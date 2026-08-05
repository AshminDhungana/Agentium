# Functional Correctness Verification — Design Specification

**Ticket:** 21.1 — [P2] Functional Correctness  
**Date:** 2026-08-05  
**Status:** Design Complete — Awaiting Implementation Plan  
**Approach:** Hybrid (Extended Integration Tests + Benchmark Runner)

---

## 1. Problem Statement

Verify that agents in the Agentium system meet functional correctness criteria:

1. **End-to-end task completion** — Agent completes representative multi-step tasks from start to terminal state
2. **Tool-call parameter validity** — Every tool invocation uses parameters valid against the ToolRegistry JSON Schema
3. **Multi-step context retention** — Context persists across retry, crash, and agent handoff across all 3 layers:
   - Ethos working memory (`working_memory`, `task_progress_markers`, `active_plan`)
   - Task checkpoint data (`Task.checkpoint_data` + TaskExecutor recovery)
   - LLM conversation history (built in `agent_orchestrator.process_intent`)
4. **Output schema compliance** — Agent outputs conform to expected schemas; Critics (Code/Output/Plan) enforce as final gate
5. **Graceful fallback on uncertainty** — Agent invokes `deep_think` tool or escalates via `create_task` instead of hallucinating tool calls

---

## 2. Approach: Hybrid (Approach C)

| Layer | Purpose | Runs | Artifacts |
|-------|---------|------|-----------|
| **Extended Integration Tests** | CI gate — blocks merge on regression | Every PR | JUnit XML, pass/fail |
| **Benchmark Runner** | Metrics tracking — latency, tokens, retries, context retention | Nightly + manual | JSON + HTML reports |

**Shared Validators** — Single implementation used by both paths (DRY):
- `SchemaValidator` — Tool params + output schemas
- `ContextValidator` — 3-layer context retention
- `FallbackValidator` — deep_think/escalation detection
- `TerminalStateValidator` — Task reaches terminal state

---

## 3. Extended Integration Test Scenarios

### 3.1 New Tests in `test_agent_lifecycle.py`

| Test | Verifies |
|------|----------|
| `test_multi_step_workflow_research_summarize` | End-to-end: web_search → web_fetch → data_transform → vector_db → output |
| `test_multi_step_workflow_code_review` | Code generation → Code Critic rejection → iteration → acceptance |
| `test_context_retention_across_retry` | All 3 context layers survive TaskExecutor retry (max_retries=1) |

### 3.2 New Tests in `test_orchestration.py`

| Test | Verifies |
|------|----------|
| `test_tool_schema_enforcement_all_tools` | Parametrized: every registered tool accepts valid params |
| `test_tool_schema_rejection_invalid_params` | ToolRegistry rejects invalid params for every tool |
| `test_critic_output_schema_enforcement` | Code/Output/Plan Critics reject non-compliant outputs |
| `test_deep_think_fallback_on_uncertainty` | LLM returns tool_call with confidence < 0.5 OR malformed tool_call → orchestrator catches, invokes deep_think, escalates via create_task |

### 3.3 New Tests in `test_agentic_loop_hardening.py`

| Test | Verifies |
|------|----------|
| `test_task_terminal_state_all_failure_modes` | Task reaches FAILED/COMPLETED/ESCALATED — never stranded IN_PROGRESS |
| `test_context_survives_head_crash_recovery` | All 3 context layers intact after SelfHealingService revives Head (00001) |

### 3.4 New Tests in `test_provider_resilience.py`

| Test | Verifies |
|------|----------|
| `test_graceful_degradation_provider_exhaustion` | Provider failover preserves task integrity |
| `test_fallback_chain_preserves_context` | After each provider failover: Ethos working_memory + Task.checkpoint_data + LLM conversation history all preserved |

---

## 4. Benchmark Runner Architecture

### 4.1 Directory Structure
```
backend/tests/benchmarks/functional_correctness/
├── __init__.py
├── runner.py
├── scenarios/
│   ├── research_summarize.yaml
│   ├── code_generation_review.yaml
│   ├── data_pipeline.yaml
│   └── multi_agent_handoff.yaml
├── validators/
│   ├── schema_validator.py
│   ├── context_validator.py
│   ├── fallback_validator.py
│   └── terminal_state_validator.py
└── reports/
    └── generate_report.py
```

### 4.2 Scenario YAML Format (Declarative)

```yaml
name: "Research and Summarize"
agent_type: "task_agent"
tier: "3xxxx"
steps:
  - name: "web_search"
    tool: "web_search"
    params:
      query: "latest developments in agentic AI architectures"
      max_results: 5
    expect_output_schema:
      type: "object"
      required: ["results"]
  # ... more steps ...
success_criteria:
  - all_steps_completed: true
  - tool_params_valid: true
  - output_schema_compliant: true
  - context_retained_across_steps: true
  - terminal_state_reached: true
  - max_duration_seconds: 120  # Total scenario timeout (not per-step)
```

### 4.3 Four Benchmark Scenarios

| Scenario | Steps | Purpose |
|----------|-------|---------|
| `research_summarize.yaml` | search → fetch → transform → store → output | Multi-tool chain, external APIs |
| `code_generation_review.yaml` | generate → Code Critic (reject) → iterate → accept | Critic loop, schema enforcement |
| `data_pipeline.yaml` | read → transform → validate → write → vector_db | Data processing, file I/O |
| `multi_agent_handoff.yaml` | Lead → Task → Critic → Lead | Hierarchical delegation, context handoff |

---

## 5. Shared Validators (Single Source of Truth)

### 5.1 SchemaValidator
- `validate_tool_params(tool_name, params)` — Uses ToolRegistry JSON Schema
- `validate_output(output, expected_schema)` — JSON Schema validation

### 5.2 ContextValidator
- `validate_ethos_working_memory(ethos, expected_keys)` — Ethos layer
- `validate_task_checkpoint(task, expected_data)` — Task checkpoint layer
- `validate_llm_history(messages, min_turns)` — LLM conversation layer

### 5.3 FallbackValidator
- `validate_fallback_triggered(agent_id, db)` — AuditLog check for deep_think/escalation
- `validate_no_hallucination(tool_calls, tool_registry)` — Every call valid name + params

### 5.4 TerminalStateValidator
- `validate_terminal_state(task)` — Task.status in {COMPLETED, FAILED, ESCALATED}

---

## 6. CI Integration

### 6.1 GitHub Actions Workflow (`.github/workflows/functional-correctness.yml`)

Two jobs:
1. **integration-tests** — Runs on every push/PR to main/develop (~15 min)
   - Executes new functional correctness integration tests
   - Uploads JUnit XML for CI dashboard
   - **Blocks merge on failure**

2. **benchmark-runner** — Runs nightly (02:00 UTC) + manual dispatch (~30 min)
   - Executes all 4 benchmark scenarios
   - Generates `summary.json` + `report.html`
   - Comments PR with benchmark summary table

### 6.2 Metrics & P2 Thresholds

| Metric | Source | P2 Threshold | Alert If |
|--------|--------|--------------|----------|
| Step duration (median) | `time.perf_counter()` | < 30s | > 60s p95 |
| Total tokens/scenario | LLMClient metadata | < 50k | > 100k |
| Tool call retries/step | Orchestrator counter | 0 median | > 2 |
| Fallback triggered (valid tasks) | AuditLog | 0 | > 0 |
| Context retention score | ContextValidator | 1.0 | < 1.0 |
| Schema validation pass rate | SchemaValidator | 100% | < 100% |
| Terminal state reached | TerminalStateValidator | 100% | < 100% |
| Provider fallbacks per scenario | LLMClient failover counter | 0 median | > 1 |

### 6.3 Report Outputs
- **summary.json** — Machine-readable for historical tracking, CI gating
- **report.html** — Human-readable with charts (trends, heatmaps)
- **JUnit XML** — Integration test results for CI dashboard

---

## 7. Implementation Phasing

| Phase | Focus | Files | Est. Lines | Timeline |
|-------|-------|-------|------------|----------|
| 1 | Core fixtures & validators | 7 | ~750 | Week 1 |
| 2 | Extended integration tests | 4 | ~680 | Week 1-2 |
| 3 | Benchmark runner & scenarios | 7 | ~720 | Week 2 |
| 4 | CI integration | 2 | ~150 | Week 2-3 |
| 5 | Documentation & thresholds | 3 | ~100 | Week 3 |
| **Total** | | **23** | **~2,400** | **3 weeks** |

### Phase 1 Files (Core Infrastructure)
```
backend/tests/integration/fixtures/functional_correctness.py
backend/tests/benchmarks/functional_correctness/__init__.py
backend/tests/benchmarks/functional_correctness/validators/__init__.py
backend/tests/benchmarks/functional_correctness/validators/schema_validator.py
backend/tests/benchmarks/functional_correctness/validators/context_validator.py
backend/tests/benchmarks/functional_correctness/validators/fallback_validator.py
backend/tests/benchmarks/functional_correctness/validators/terminal_state_validator.py
```

### Phase 2 Files (Integration Tests)
```
backend/tests/integration/test_agent_lifecycle.py          (+3 tests)
backend/tests/integration/test_orchestration.py             (+4 tests)
backend/tests/integration/test_agentic_loop_hardening.py    (+2 tests)
backend/tests/integration/test_provider_resilience.py       (+2 tests)
```

### Phase 3 Files (Benchmark Runner)
```
backend/tests/benchmarks/functional_correctness/scenarios/__init__.py
backend/tests/benchmarks/functional_correctness/scenarios/research_summarize.yaml
backend/tests/benchmarks/functional_correctness/scenarios/code_generation_review.yaml
backend/tests/benchmarks/functional_correctness/scenarios/data_pipeline.yaml
backend/tests/benchmarks/functional_correctness/scenarios/multi_agent_handoff.yaml
backend/tests/benchmarks/functional_correctness/runner.py
backend/tests/benchmarks/functional_correctness/reports/generate_report.py
```

### Phase 4 Files (CI)
```
.github/workflows/functional-correctness.yml
backend/tests/benchmarks/functional_correctness/conftest.py
```

### Phase 5 Files (Docs)
```
docs/operations/functional-correctness-benchmarks.md
backend/tests/benchmarks/functional_correctness/thresholds.yaml
CHANGELOG.md (entry)
```

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Test DB contention (parallel runs) | Separate test DB schemas per job; unique docker-compose project names |
| Flaky provider calls in benchmarks | Mock LLMClient in benchmarks; real providers only in integration tests |
| Validator drift between paths | Single validator classes imported by both; unit test validators independently |
| Head agent (00001) conflicts | Fresh agents per test; Head only via session-scoped `seeded_db` fixture |

---

## 9. Success Criteria

- [ ] All 11 new integration tests pass on CI (every PR)
- [ ] Benchmark runner executes 4 scenarios nightly, produces JSON + HTML reports
- [ ] PR comments show benchmark summary table with pass/fail + metrics
- [ ] All P2 thresholds documented in `thresholds.yaml` and enforced in CI
- [ ] Zero validator drift — single validator classes used by both test paths
- [ ] Documentation enables local benchmark runs and threshold tuning

---

## 10. Out of Scope

- Modifying agent orchestration logic (this is verification only)
- Adding new tools or Critic types
- Changing constitutional guard behavior
- Load testing at 2× peak (covered by 21.5)
- Prompt injection resistance testing (covered by 21.2)

---

*Design complete. Ready for implementation plan via writing-plans skill.*