# Critic Agents Verification Design

**Date:** 2026-09-04  
**Status:** Proposed  
**Related TODO:** Section 6.3 — Critic Agents (Judiciary)

---

## Overview

Verify and complete the Critic Agents system (items 6.3.1–6.3.4 in TODO.md):
- **6.3.1** — Code Critic (7xxxx) reviews generated code for syntax/security
- **6.3.2** — Output Critic (8xxxx) verifies output alignment with intent
- **6.3.3** — Plan Critic (9xxxx) validates DAG soundness
- **6.3.4** — Critic feedback is incorporated before final response

Current state: Core implementation exists in `critic_agents.py`, `critics.py` (models), `critics.py` (routes). Unit tests only cover polymorphic identity. Integration tests mock the critic service. No tests exercise the actual review logic (preflight, AI review, rule-based fallback).

---

## Verification Scope

### 1. Unit Tests for Review Logic (`backend/tests/unit/test_critic_review_logic.py`)

Test each critic's review functions with controlled inputs:

| Critic Type | Functions to Test | Key Scenarios |
|-------------|-------------------|---------------|
| **Code (7xxxx)** | `_review_code`, `_ai_review`, `_preflight_check` | Dangerous patterns (`eval`, `exec`, `os.system`), empty output, oversized output, valid code passes |
| **Output (8xxxx)** | `_review_output`, `_ai_review`, `_preflight_check` | Empty output, error tracebacks, relevance to task description, valid output passes |
| **Plan (9xxxx)** | `_review_plan`, `_ai_review`, `_preflight_check` | Empty plan, duplicate steps, >100 steps, valid plan passes |
| **Shared** | `_parse_ai_verdict`, `_build_critic_system_prompt`, `_build_critic_user_prompt` | JSON parsing, malformed AI responses, prompt construction |

**Approach:** Pure unit tests with mocked `ModelService.generate()`. No external dependencies.

### 2. Integration Tests for Full Review Flow (`backend/tests/integration/test_critic_integration.py`)

Test the complete `review_task_output()` flow with the database:

| Scenario | Description |
|----------|-------------|
| Code critic rejects dangerous code | Spawn critic → submit code with `eval()` → verify REJECT with specific reason |
| Code critic passes clean code | Spawn critic → submit clean Python → verify PASS |
| Output critic rejects empty/error output | Submit empty string or traceback → verify REJECT |
| Output critic passes relevant output | Submit output matching task keywords → verify PASS |
| Plan critic rejects duplicate/overlong plan | Submit plan with duplicate steps or >100 lines → verify REJECT |
| Retry logic | REJECT → retry with same critic instance → PASS on retry |
| Escalation after max retries | 5 REJECTs → verify ESCALATE and Council escalation |
| Acceptance criteria integration | Task with criteria → verify criteria evaluated before AI review |
| Consensus protocol | First REJECT → secondary critic PASS → conditional PASS |
| Case law indexing | Hard REJECT → verify knowledge stored in `critic_case_law` collection |

**Approach:** Use `seeded_db` fixture. Mock `ModelService.generate()` for AI review tests. Use real DB for acceptance criteria, deduplication, case law.

### 3. Manual Verification Script (`scripts/verify_critics.py`)

Interactive script to test critics against real LLM (requires API keys):

```bash
python scripts/verify_critics.py --type code --model openai:gpt-4o-mini
```

Features:
- Select critic type (code/output/plan)
- Provide task description and output content
- Show critic verdict, reason, suggestions
- Test multiple iterations (retry simulation)
- Save results for regression comparison

### 4. Gap Fixes (if found during verification)

| Potential Gap | Fix Approach |
|---------------|--------------|
| Missing syntax validation (e.g., Python `ast.parse`) | Add AST parsing in `_review_code` preflight |
| Weak relevance check in output critic | Improve keyword overlap logic or add embedding similarity |
| Plan critic doesn't validate DAG structure | Add DAG cycle detection in `_review_plan` |
| AI review parsing failures | Harden `_parse_ai_verdict` with regex fallback |
| Critic model orthogonality not enforced | Verify `preferred_review_model` differs from executor model |

---

## Test Matrix

| Test Type | File | Count (est.) | Dependencies |
|-----------|------|--------------|--------------|
| Unit — Code Critic | `test_critic_review_logic.py` | 12 | None (mocked) |
| Unit — Output Critic | `test_critic_review_logic.py` | 10 | None (mocked) |
| Unit — Plan Critic | `test_critic_review_logic.py` | 10 | None (mocked) |
| Unit — Shared/Utils | `test_critic_review_logic.py` | 8 | None (mocked) |
| Integration — Full Flow | `test_critic_integration.py` | 12 | `seeded_db`, mocked LLM |
| Manual Verification | `scripts/verify_critics.py` | N/A | Real API keys |

---

## Acceptance Criteria

All items in TODO.md Section 6.3 marked `[x]` after:

1. ✅ All new unit tests pass (`pytest backend/tests/unit/test_critic_review_logic.py -v`)
2. ✅ All new integration tests pass (`pytest backend/tests/integration/test_critic_integration.py -v`)
3. ✅ Manual verification script runs without errors for all three critic types
4. ✅ Any gaps identified are fixed and verified
5. ✅ Existing tests still pass (no regressions)

---

## Implementation Order

1. **Phase 1** — Create `test_critic_review_logic.py` (unit tests)
2. **Phase 2** — Create `test_critic_integration.py` (integration tests)
3. **Phase 3** — Create `scripts/verify_critics.py` (manual verification)
4. **Phase 4** — Run all tests, fix gaps, re-run
5. **Phase 5** — Update TODO.md with `[x]` for 6.3.1–6.3.4

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AI review tests flaky due to LLM non-determinism | Use mocked `ModelService` for CI; manual script for real LLM |
| Database state pollution between integration tests | Use transaction rollback fixtures (`seeded_db`) |
| Critic ID allocation conflicts in parallel tests | Use unique task IDs per test; critics are ephemeral per-task |
| Missing acceptance criteria test coverage | Add explicit tests for `AcceptanceCriteriaService` integration |

---

## Next Steps

Upon approval:
1. Invoke `writing-plans` skill to create detailed implementation plan
2. Execute phases in order
3. Update TODO.md upon completion