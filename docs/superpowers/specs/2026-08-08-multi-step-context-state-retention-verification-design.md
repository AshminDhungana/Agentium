# 21.1.3 — Multi-Step Context & State Retention Verification Design

## Overview

This document describes the design for automated integration tests that verify context retention across multi-turn task lifetimes in three core components:
- **chat_context.py** — Token-efficient chat context (sliding window, pinning, summarization, full-history recovery)
- **context_manager.py** — Context window management with thresholds, reincarnation, and wisdom transfer
- **checkpoint_service.py** — Checkpoint creation, time-travel resume, and branching

## Current State Analysis

| Component | Key Features | Existing Tests |
|-----------|-------------|----------------|
| `chat_context.py` | Sliding window (10), pinned first message, Redis summary, full-history tools | `test_chat_context_compaction.py` (integration), `test_chat_context.py` (unit) |
| `context_manager.py` | Warning (75%) / Critical (90%) thresholds, reincarnation, wisdom accumulation | None found |
| `checkpoint_service.py` | Full state capture, resume, branching, import/export | `test_checkpoint_diff.py`, `test_checkpoint_chroma.py` |

## Test Design Philosophy

1. **Integration-first** — Tests run against real Postgres + Redis stack
2. **Single-responsibility** — One test class per component, one test method per scenario
3. **Deterministic fixtures** — Seed known state, assert exact outcomes
4. **Isolation** — Each test cleans up its own data; no shared state between tests
5. **Coverage target** — 80%+ line coverage on new test code

---

## 1. Chat Context Verification (`test_chat_context_retention.py`)

### 1.1 Sliding Window + Pinning + Summary Injection

**Test Class:** `TestChatContextWindowPinning`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_short_history_no_compression` | 5 turns, window=10 | `context_compressed=False`, all 5 turns in history, no pin duplicate |
| `test_long_history_pins_first_and_windows` | 60 turns, window=10 | `context_compressed=True`, history=11 (pinned first + last 10), first message=`s0`, last message=`h29` |
| `test_first_message_not_duplicated_in_window` | 6 turns (first + 5 recent), window=10 | first message appears exactly once, `context_compressed=False` |
| `test_summary_flag_marks_compression` | Any history + summary provided | `context_compressed=True` regardless of turn count |
| `test_window_size_configurable` | window=5, 20 turns | history=6 (pinned + 5 recent) |

**Implementation Notes:**
- Use `seeded_db` fixture (Postgres)
- Use `ChatContextBuilder` directly (no HTTP layer)
- Mock Redis for `load_summary`/`save_summary` or use real Redis via `redis_client` fixture

### 1.2 Summarization + Full History Recovery

**Test Class:** `TestChatContextSummarizationRecovery`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_summarize_history_creates_structured_json` | 55 turns, trigger summarize | `summary_json` contains `key_facts`, `decisions`, `open_threads`; stored in Redis with 7-day TTL |
| `test_format_summary_for_prompt_renders_readable` | JSON summary from above | Output contains "Key facts:", "Decisions:", "Open threads:" |
| `test_get_full_history_recovers_middle_turn` | 55 turns seeded, window=10 | `get_full_history(limit=200)` returns all 55 turns; turn-27 present in recovered history |
| `test_search_chat_history_finds_query` | 55 turns with unique markers | `search_chat_history("turn-27")` returns matching turns only |
| `test_summarize_skips_short_conversations` | 5 turns | `summarize_history` returns `None` (threshold: 6 turns) |

**Implementation Notes:**
- Requires real Redis (or fakeredis) for summary persistence
- `summarize_history` opens its own DB session — test must handle session lifecycle
- Model provider mock: inject fake provider returning valid JSON summary

### 1.3 Token Estimation & Truncation

**Test Class:** `TestChatContextTokenEstimation`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_estimate_tokens_positive` | Mixed messages | Returns positive integer |
| `test_truncate_preserves_pinned` | History exceeds model_limit | Pinned first message never dropped; oldest non-pinned dropped first |
| `test_truncate_with_summary` | Summary + history exceeds limit | Truncation works with summary in system prompt |

---

## 2. Context Manager Verification (`test_context_manager_retention.py`)

### 2.1 Warning / Critical Thresholds + Reincarnation Trigger

**Test Class:** `TestContextManagerThresholds`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_warning_threshold_at_75_percent` | Register agent (128k limit), update to 96k tokens | `is_warning=True`, `is_critical=False`, `usage_percentage ≈ 0.75` |
| `test_critical_threshold_at_90_percent` | Update to 115k tokens | `is_critical=True`, `is_warning=True` |
| `test_absolute_max_at_95_percent` | Update to 121k tokens | `should_reincarnate=True` |
| `test_unknown_model_uses_default_limit` | Register with "unknown-model" | `max_tokens=128000` (default) |
| `test_update_usage_sets_current_not_accumulates` | update_usage(100), then update_usage(200) | `current_tokens=200` (not 300) |

**Implementation Notes:**
- `ContextWindowManager` is a singleton — reset `agent_contexts` between tests
- Use `model_name` param to control limits

### 2.2 Wisdom Accumulation + Transfer Across Incarnations

**Test Class:** `TestContextManagerWisdomTransfer`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_add_wisdom_stores_entry` | add_wisdom(summary="completed X", topics=["A","B"]) | `accumulated_wisdom` has 1 entry with timestamp, incarnation, summary, topics, token_count |
| `test_multiple_wisdom_entries_accumulate` | add_wisdom 3 times | 3 entries, `get_stats` shows correct counts |
| `test_prepare_for_reincarnation_returns_wisdom` | Add wisdom, call prepare_for_reincarnation | Returns `incarnation_number`, `accumulated_wisdom` |
| `test_transfer_to_successor_inherits_wisdom` | create old_id, add wisdom, transfer to new_id | New agent has `incarnation=2`, copied `accumulated_wisdom`, fresh `current_tokens=0`, `message_count=0` |
| ` test_transfer_cleans_up_old_context` | After transfer | `old_id` removed from `agent_contexts` |

**Implementation Notes:**
- Tests are pure unit tests (no DB/Redis needed)
- Use `context_manager` singleton, reset between tests

---

## 3. Checkpoint Service Verification (`test_checkpoint_retention.py`)

### 3.1 Full State Capture

**Test Class:** `TestCheckpointStateCapture`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_create_checkpoint_captures_task_snapshot` | Task with status, result_data, assigned agents | `task_state_snapshot` contains all fields; `phase` correct |
| `test_create_checkpoint_captures_agent_states` | Task with 2 assigned agents + supervisor | `agent_states` has 3 entries, each with status, current_task_id, agent_type, ethos_summary, capabilities |
| `test_create_checkpoint_captures_subtasks` | Task with 2 active subtasks | `subtask_snapshots` list with id, status, description, assigned agents, result_data for each |
| `test_create_checkpoint_audit_log_created` | After create | `AuditLog` entry with action="checkpoint_created" |

**Implementation Notes:**
- Use `seeded_db` fixture
- Create real `Task`, `Agent`, `HeadOfCouncil` entities

### 3.2 Time-Travel Resume

**Test Class:** `TestCheckpointResume`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_resume_restores_task_status` | Task was COMPLETED, checkpoint has PENDING | Task status = PENDING after resume |
| `test_resume_restores_result_data` | Checkpoint has `result_data={"score": 42}` | `task.result_data == {"score": 42}` |
| `test_resume_restores_assigned_agents` | Checkpoint has assigned_task_agent_ids | `task.assigned_task_agent_ids` matches |
| `test_resume_restores_agent_states` | Checkpoint has agent states with statuses | Agents in DB have matching status, current_task_id |
| `test_resume_restores_subtask_states` | Checkpoint has subtask snapshots | Subtasks have matching status, result_data, assigned agents |
| `test_resume_creates_audit_log` | After resume | `AuditLog` entry with action="checkpoint_resumed" |

**Implementation Notes:**
- Create checkpoint first, modify task state, then resume
- Verify all relational state is restored

### 3.3 Branching

**Test Class:** `TestCheckpointBranching`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_branch_creates_new_task` | Branch from checkpoint | New `Task` with new UUID, same description, type, priority |
| `test_branch_creates_branch_checkpoint` | After branch | New `ExecutionCheckpoint` with `parent_checkpoint_id` linking to source, `branch_name` set |
| `test_branch_task_independent` | Modify branch task | Original task unchanged; branch task has own state |
| `test_branch_with_new_supervisor` | Pass `new_supervisor_id` | New task has `supervisor_id = new_supervisor_id` |
| `test_branch_audit_log_created` | After branch | `AuditLog` entry with action="checkpoint_branched" |

---

## 4. Cross-Component Integration Test

**Test Class:** `TestMultiComponentContextRetention`

| Test Method | Scenario | Assertions |
|-------------|----------|------------|
| `test_chat_context_feeds_context_manager` | Simulate chat turns → context_manager.update_usage | `context_manager` tracks tokens from chat context compaction |
| `test_reincarnation_preserves_checkpoint_wisdom` | Agent reincarnates → checkpoint captures state → resume | Wisdom from `context_manager` reflected in checkpoint's `agent_states` |
| `test_full_lifecycle` | Chat → context builds → checkpoint → resume → branch | End-to-end state preserved across all three components |

---

## 5. Test Infrastructure Requirements

### Fixtures Needed

```python
# conftest.py additions
@pytest.fixture
def chat_context_builder():
    return ChatContextBuilder(window_size=10)

@pytest.fixture
def context_manager_clean():
    """Reset singleton before each test."""
    context_manager.agent_contexts.clear()
    yield context_manager
    context_manager.agent_contexts.clear()

@pytest.fixture
def seeded_task_with_agents(seeded_db):
    """Create task with supervisor, 2 assigned agents, 2 subtasks."""
    # ... implementation
    return task, agents, subtasks

@pytest.fixture
def fake_model_provider():
    """Mock provider returning valid JSON summary."""
    # ... implementation
```

### Running the Tests

```bash
# All context retention tests
make test-integration TEST=test_chat_context_retention
make test-integration TEST=test_context_manager_retention
make test-integration TEST=test_checkpoint_retention

# Specific class
pytest backend/tests/integration/test_chat_context_retention.py::TestChatContextWindowPinning -v
```

---

## 6. Success Criteria

| Metric | Target |
|--------|--------|
| Total new test methods | ≥25 |
| Line coverage (new test files) | ≥80% |
| Integration test pass rate | 100% on clean DB |
| Test execution time | <60s total |

---

## 7. File Structure

```
backend/tests/integration/
├── test_chat_context_retention.py      # ~12 test methods
├── test_context_manager_retention.py   # ~8 test methods
├── test_checkpoint_retention.py        # ~10 test methods
└── conftest.py                         # shared fixtures (if needed)
```

---

## 8. Dependencies

- Existing: `seeded_db`, `redis_client` fixtures (already in conftest)
- New fixtures: `chat_context_builder`, `context_manager_clean`, `seeded_task_with_agents`, `fake_model_provider`
- Mock: Model provider for summarization (can reuse existing test patterns)

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `context_manager` singleton state leaks between tests | `context_manager_clean` fixture resets `agent_contexts` dict |
| `summarize_history` opens own DB session | Use `seeded_db` bind; test cleans up own session |
| Redis not available in CI | Use `fakeredis` or mock `get_redis_client` |
| Flaky checkpoint tests due to UUID collisions | Use fixed UUIDs in test fixtures for reproducibility |

---

## 10. Approval

> **Design approved by:** ____________________ **Date:** __________
>
> **Implementation plan to follow:** `writing-plans` skill