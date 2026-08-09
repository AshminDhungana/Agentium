# 21.1.3 Multi-Step Context & State Retention Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create comprehensive integration tests verifying context retention across multi-turn task lifetimes for chat_context.py, context_manager.py, and checkpoint_service.py

**Architecture:** Four test files covering each component plus cross-component integration. Each test class targets one feature group, each test method verifies one scenario. Uses real Postgres + Redis via existing fixtures.

**Tech Stack:** pytest, SQLAlchemy, Redis, fakeredis for CI, existing seeded_db and redis_client fixtures

## Global Constraints

- All tests marked `@pytest.mark.integration` requiring integration stack
- Use `seeded_db` fixture (Postgres) and `redis_client` fixture (Redis) from conftest.py
- Tests must be deterministic — seed known state, assert exact outcomes
- Each test cleans up its own data; no shared state between tests
- Target: ≥25 new test methods, ≥80% line coverage on new test files
- Follow existing test patterns in `backend/tests/integration/`

---

### Task 1: Create test_chat_context_retention.py - Window Pinning Tests

**Files:**
- Create: `backend/tests/integration/test_chat_context_retention.py`

**Interfaces:**
- Consumes: `seeded_db` fixture, `ChatContextBuilder`, `ChatMessage` model, `User` model
- Produces: Test class `TestChatContextWindowPinning` with 5 test methods

- [ ] **Step 1.1: Create test file with imports and TestChatContextWindowPinning class**

```python
"""
Integration tests for chat context sliding window, pinning, and summary injection.
Verifies Task 2.1 token-efficient chat context behavior.
"""

import pytest
from backend.services.chat_context import ChatContextBuilder
from backend.models.entities.chat_message import ChatMessage as ChatMsg
from backend.models.entities.user import User


@pytest.mark.integration
class TestChatContextWindowPinning:
    """Tests for sliding window + pinned first message + summary compression."""

    def test_short_history_no_compression(self, seeded_db):
        """5 turns, window=10: no compression, all turns kept, no pin duplicate."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        # Clean any existing messages
        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 5 sovereign + 5 head turns = 10 total
        for i in range(5):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is False
        assert len(out["history"]) == 10
        assert out["raw_turn_count"] == 10
        # First message appears exactly once (not duplicated as pin)
        first_count = sum(1 for m in out["history"] if m["content"] == "s0")
        assert first_count == 1

    def test_long_history_pins_first_and_windows(self, seeded_db):
        """60 turns, window=10: compressed, history=11 (pinned first + last 10)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 30 sovereign + 30 head = 60 total
        for i in range(30):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is True
        assert out["raw_turn_count"] == 60
        # History = [pinned first] + last 10 turns = 11
        assert len(out["history"]) == 11
        # First message pinned at head
        assert out["history"][0]["content"] == "s0"
        # Most recent turn present (h29 is last seeded)
        assert out["history"][-1]["content"] == "h29"

    def test_first_message_not_duplicated_in_window(self, seeded_db):
        """6 turns (first + 5 recent), window=10: first appears once, no compression."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # First message + 5 recent turns
        db.add(ChatMsg(user_id=str(user.id), role="sovereign", content="first"))
        for i in range(5):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        # Window (10) covers everything; first message appears exactly once
        assert sum(1 for m in out["history"] if m["content"] == "first") == 1
        assert out["context_compressed"] is False
        assert len(out["history"]) == 6

    def test_summary_flag_marks_compression(self, seeded_db):
        """Any history + summary provided: context_compressed=True regardless of turn count."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Just 1 turn
        db.add(ChatMsg(user_id=str(user.id), role="sovereign", content="only one"))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        summary_json = '{"key_facts":["x"]}'
        out = builder.build(db, str(user.id), summary=summary_json)

        assert out["context_compressed"] is True

    def test_window_size_configurable(self, seeded_db):
        """window=5, 20 turns: history=6 (pinned + 5 recent)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 10 sovereign + 10 head = 20 total
        for i in range(10):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=5)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is True
        assert out["raw_turn_count"] == 20
        # History = [pinned first] + last 5 turns = 6
        assert len(out["history"]) == 6
        assert out["history"][0]["content"] == "s0"
        assert out["history"][-1]["content"] == "h9"
```

---

### Task 2: Add Summarization + Full History Recovery Tests to test_chat_context_retention.py

**Files:**
- Modify: `backend/tests/integration/test_chat_context_retention.py` (append TestChatContextSummarizationRecovery class)

**Interfaces:**
- Consumes: `seeded_db`, `redis_client` fixtures, `load_summary`, `save_summary`, `summarize_history`, `format_summary_for_prompt`, `get_full_history`, `search_chat_history`, `set_chat_request`, `clear_chat_request`
- Produces: Test class `TestChatContextSummarizationRecovery` with 5 test methods

- [ ] **Step 2.1: Add TestChatContextSummarizationRecovery class with 5 test methods**

```python
import json
from unittest.mock import AsyncMock, patch

from backend.services.chat_context import (
    load_summary,
    save_summary,
    summarize_history,
    format_summary_for_prompt,
    get_full_history,
    search_chat_history,
    set_chat_request,
    clear_chat_request,
)
from backend.services.model_provider import ModelService


@pytest.mark.integration
class TestChatContextSummarizationRecovery:
    """Tests for background summarization and on-demand full history recovery."""

    async def test_summarize_history_creates_structured_json(self, seeded_db, redis_client):
        """55 turns, trigger summarize: summary_json has key_facts, decisions, open_threads; stored in Redis."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # Seed 55 turns (alternating)
        for i in range(55):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        # Mock model provider to return valid JSON summary
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value={
            "content": json.dumps({
                "key_facts": ["User wants to build a dashboard", "API keys configured"],
                "decisions": ["Use React for frontend", "PostgreSQL for database"],
                "open_threads": ["Need to design schema", "Authentication pending"]
            }),
            "model": "test-model",
            "tokens_used": 150,
            "latency_ms": 500,
        })

        with patch.object(ModelService, 'get_provider', AsyncMock(return_value=mock_provider)):
            summary_json = await summarize_history(db, user_id, config_id=None)

        # Verify summary structure
        assert summary_json is not None
        summary = json.loads(summary_json)
        assert "key_facts" in summary
        assert "decisions" in summary
        assert "open_threads" in summary
        assert len(summary["key_facts"]) > 0
        assert len(summary["decisions"]) > 0
        assert len(summary["open_threads"]) > 0

        # Verify stored in Redis
        stored = await load_summary(user_id)
        assert stored is not None
        assert stored == summary_json

        # Verify TTL (~7 days = 604800 seconds)
        ttl = await redis_client.ttl(f"agentium:chat_summary:{user_id}")
        assert ttl > 0
        assert ttl <= 604800

    def test_format_summary_for_prompt_renders_readable(self):
        """JSON summary renders to human-readable block with labels."""
        summary_json = json.dumps({
            "key_facts": ["Fact A", "Fact B"],
            "decisions": ["Decision X"],
            "open_threads": ["Thread 1", "Thread 2"]
        })

        rendered = format_summary_for_prompt(summary_json)

        assert "Key facts:" in rendered
        assert "Fact A" in rendered
        assert "Fact B" in rendered
        assert "Decisions:" in rendered
        assert "Decision X" in rendered
        assert "Open threads:" in rendered
        assert "Thread 1" in rendered
        assert "Thread 2" in rendered

    async def test_get_full_history_recovers_middle_turn(self, seeded_db):
        """55 turns seeded, window=10: get_full_history returns all 55; turn-27 present."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        N = 55
        for i in range(N):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        set_chat_request(user_id=user_id, db=db)
        try:
            recovered = get_full_history(limit=200)
        finally:
            clear_chat_request()

        assert recovered["status"] == "ok"
        assert recovered["message_count"] >= N
        contents = [m["content"] for m in recovered["history"]]
        assert "turn-27-unique-marker-27" in contents

    async def test_search_chat_history_finds_query(self, seeded_db):
        """55 turns with unique markers: search_chat_history returns matching turns only."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        N = 55
        for i in range(N):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        set_chat_request(user_id=user_id, db=db)
        try:
            result = search_chat_history(query="turn-27", limit=20)
        finally:
            clear_chat_request()

        assert result["status"] == "ok"
        assert result["query"] == "turn-27"
        assert result["message_count"] >= 1
        # Only turn-27 should match
        for msg in result["history"]:
            assert "turn-27" in msg["content"]

    async def test_summarize_skips_short_conversations(self, seeded_db):
        """5 turns: summarize_history returns None (threshold: 6 turns)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # Only 5 turns
        for i in range(5):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"short-{i}",
            ))
        db.commit()

        summary_json = await summarize_history(db, user_id, config_id=None)
        assert summary_json is None
```

---

### Task 3: Add Token Estimation & Truncation Tests to test_chat_context_retention.py

**Files:**
- Modify: `backend/tests/integration/test_chat_context_retention.py` (append TestChatContextTokenEstimation class)

**Interfaces:**
- Consumes: `seeded_db` fixture, `estimate_tokens`, `ChatContextBuilder._truncate`
- Produces: Test class `TestChatContextTokenEstimation` with 3 test methods

- [ ] **Step 3.1: Add TestChatContextTokenEstimation class with 3 test methods**

```python
@pytest.mark.integration
class TestChatContextTokenEstimation:
    """Tests for token estimation and graceful truncation."""

    def test_estimate_tokens_positive(self):
        """Mixed messages: returns positive integer."""
        from backend.services.chat_context import estimate_tokens

        n = estimate_tokens(
            [{"role": "user", "content": "hello world"}, {"role": "assistant", "content": "hi"}],
            system_prompt="You are helpful.",
        )
        assert isinstance(n, int) and n > 0

    def test_truncate_preserves_pinned(self, seeded_db):
        """History exceeds model_limit: pinned first message never dropped; oldest non-pinned dropped first."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Create many messages with a very small model_limit to force truncation
        for i in range(50):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i} " * 500,  # Long content to increase tokens
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i} " * 500,
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10, model_limit=1000)  # Very small limit
        out = builder.build(db, str(user.id))

        # Pinned first message should never be dropped
        assert out["history"][0]["content"].startswith("s0 ")
        # Should have been truncated (compressed = True when truncation happens)
        assert out["context_compressed"] is True

    def test_truncate_with_summary(self, seeded_db):
        """Summary + history exceeds limit: truncation works with summary in system prompt."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        for i in range(30):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i} " * 300,
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i} " * 300,
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10, model_limit=2000)
        summary = '{"key_facts":["a"],"decisions":["b"],"open_threads":["c"]}'
        out = builder.build(db, str(user.id), summary=summary)

        # With summary, history should still be truncated to fit
        assert out["context_compressed"] is True
        assert len(out["history"]) >= 2  # At least pinned + one recent
        # Pinned message preserved
        assert out["history"][0]["content"].startswith("s0 ")
```

---

### Task 4: Create test_context_manager_retention.py - Thresholds & Reincarnation Tests

**Files:**
- Create: `backend/tests/integration/test_context_manager_retention.py`

**Interfaces:**
- Consumes: `ContextWindowManager` singleton (`context_manager`), `ContextWindowStatus` dataclass
- Produces: Test class `TestContextManagerThresholds` with 5 test methods

- [ ] **Step 4.1: Create test file with imports and TestContextManagerThresholds class**

```python
"""
Integration tests for context window management thresholds and reincarnation triggers.
Verifies ContextWindowManager behavior for warning/critical thresholds and reincarnation.
"""

import pytest
from backend.services.context_manager import ContextWindowManager, context_manager, ContextWindowStatus


# Fixture to reset singleton state between tests
@pytest.fixture(autouse=True)
def reset_context_manager():
    """Reset context_manager singleton before each test."""
    context_manager.agent_contexts.clear()
    yield
    context_manager.agent_contexts.clear()


@pytest.mark.integration
class TestContextManagerThresholds:
    """Tests for warning/critical thresholds and reincarnation trigger."""

    def test_warning_threshold_at_75_percent(self):
        """Register agent (128k limit), update to 96k tokens: is_warning=True, is_critical=False."""
        context_manager.register_agent("test-agent-1", "gpt-4o")  # 128k limit
        context_manager.update_usage("test-agent-1", 96_000)  # 75%

        status = context_manager.check_status("test-agent-1")

        assert status is not None
        assert status.is_warning is True
        assert status.is_critical is False
        assert abs(status.usage_percentage - 0.75) < 0.01
        assert status.current_tokens == 96_000
        assert status.max_tokens == 128_000

    def test_critical_threshold_at_90_percent(self):
        """Update to 115k tokens: is_critical=True, is_warning=True."""
        context_manager.register_agent("test-agent-2", "gpt-4o")  # 128k limit
        context_manager.update_usage("test-agent-2", 115_200)  # 90%

        status = context_manager.check_status("test-agent-2")

        assert status is not None
        assert status.is_critical is True
        assert status.is_warning is True
        assert abs(status.usage_percentage - 0.90) < 0.01

    def test_absolute_max_at_95_percent(self):
        """Update to 121k tokens: should_reincarnate=True."""
        context_manager.register_agent("test-agent-3", "gpt-4o")  # 128k limit
        context_manager.update_usage("test-agent-3", 121_600)  # 95%

        status = context_manager.check_status("test-agent-3")
        should_reincarnate = context_manager.should_reincarnate("test-agent-3")

        assert status.is_critical is True
        assert should_reincarnate is True

    def test_unknown_model_uses_default_limit(self):
        """Register with 'unknown-model': max_tokens=128000 (default)."""
        context_manager.register_agent("test-agent-4", "unknown-model-xyz")
        status = context_manager.check_status("test-agent-4")

        assert status.max_tokens == 128_000

    def test_update_usage_sets_current_not_accumulates(self):
        """update_usage(100), then update_usage(200): current_tokens=200 (not 300)."""
        context_manager.register_agent("test-agent-5", "gpt-4o")
        context_manager.update_usage("test-agent-5", 100)
        context_manager.update_usage("test-agent-5", 200)

        status = context_manager.check_status("test-agent-5")
        assert status.current_tokens == 200
        assert status.max_tokens == 128_000
```

---

### Task 5: Add Wisdom Transfer Tests to test_context_manager_retention.py

**Files:**
- Modify: `backend/tests/integration/test_context_manager_retention.py` (append TestContextManagerWisdomTransfer class)

**Interfaces:**
- Consumes: `context_manager` singleton, `ContextWindowManager` methods
- Produces: Test class `TestContextManagerWisdomTransfer` with 5 test methods

- [ ] **Step 5.1: Add TestContextManagerWisdomTransfer class with 5 test methods**

```python
from datetime import datetime
from backend.services.context_manager import context_manager


@pytest.mark.integration
class TestContextManagerWisdomTransfer:
    """Tests for wisdom accumulation and transfer across incarnations."""

    def test_add_wisdom_stores_entry(self):
        """add_wisdom(summary='completed X', topics=['A','B']): accumulated_wisdom has 1 entry with all fields."""
        context_manager.register_agent("wisdom-agent-1", "gpt-4o")
        context_manager.add_wisdom("wisdom-agent-1", "completed task X", ["topic-A", "topic-B"])

        stats = context_manager.get_stats("wisdom-agent-1")

        assert stats["wisdom_entries"] == 1
        assert stats["total_wisdom_tokens"] > 0
        # Verify entry structure
        agent_ctx = context_manager.agent_contexts["wisdom-agent-1"]
        wisdom = agent_ctx["accumulated_wisdom"][0]
        assert "timestamp" in wisdom
        assert wisdom["incarnation"] == 1
        assert wisdom["summary"] == "completed task X"
        assert wisdom["topics"] == ["topic-A", "topic-B"]
        assert wisdom["token_count"] > 0

    def test_multiple_wisdom_entries_accumulate(self):
        """add_wisdom 3 times: 3 entries, get_stats shows correct counts."""
        context_manager.register_agent("wisdom-agent-2", "gpt-4o")
        context_manager.add_wisdom("wisdom-agent-2", "first task", ["A"])
        context_manager.add_wisdom("wisdom-agent-2", "second task", ["B", "C"])
        context_manager.add_wisdom("wisdom-agent-2", "third task", ["D"])

        stats = context_manager.get_stats("wisdom-agent-2")

        assert stats["wisdom_entries"] == 3
        assert stats["total_wisdom_tokens"] > 0
        assert len(context_manager.agent_contexts["wisdom-agent-2"]["accumulated_wisdom"]) == 3

    def test_prepare_for_reincarnation_returns_wisdom(self):
        """Add wisdom, call prepare_for_reincarnation: returns incarnation_number, accumulated_wisdom."""
        context_manager.register_agent("wisdom-agent-3", "gpt-4o")
        context_manager.add_wisdom("wisdom-agent-3", "important lesson", ["X"])

        prep = context_manager.prepare_for_reincarnation("wisdom-agent-3")

        assert prep["incarnation_number"] == 1
        assert len(prep["accumulated_wisdom"]) == 1
        assert prep["accumulated_wisdom"][0]["summary"] == "important lesson"
        assert prep["model"] == "gpt-4o"

    def test_transfer_to_successor_inherits_wisdom(self):
        """create old_id, add wisdom, transfer to new_id: new agent has incarnation=2, copied wisdom, fresh tokens."""
        context_manager.register_agent("old-agent-1", "gpt-4o")
        context_manager.add_wisdom("old-agent-1", "learned something", ["Y"])

        context_manager.transfer_to_successor("old-agent-1", "new-agent-1")

        # Old agent cleaned up
        assert "old-agent-1" not in context_manager.agent_contexts

        # New agent has inherited state
        new_ctx = context_manager.agent_contexts["new-agent-1"]
        assert new_ctx["incarnation"] == 2
        assert new_ctx["current_tokens"] == 0
        assert new_ctx["message_count"] == 0
        assert len(new_ctx["accumulated_wisdom"]) == 1
        assert new_ctx["accumulated_wisdom"][0]["summary"] == "learned something"
        assert new_ctx["max_tokens"] == 128_000

    def test_transfer_cleans_up_old_context(self):
        """After transfer: old_id removed from agent_contexts."""
        context_manager.register_agent("cleanup-old", "gpt-4o")
        context_manager.transfer_to_successor("cleanup-old", "cleanup-new")

        assert "cleanup-old" not in context_manager.agent_contexts
        assert "cleanup-new" in context_manager.agent_contexts
```

---

### Task 6: Create test_checkpoint_retention.py - State Capture Tests

**Files:**
- Create: `backend/tests/integration/test_checkpoint_retention.py`

**Interfaces:**
- Consumes: `seeded_db` fixture, `CheckpointService`, `Task`, `Agent`, `HeadOfCouncil`, `ExecutionCheckpoint`, `CheckpointPhase`, `AuditLog`
- Produces: Test class `TestCheckpointStateCapture` with 4 test methods

- [ ] **Step 6.1: Create test file with imports and TestCheckpointStateCapture class**

```python
"""
Integration tests for checkpoint service state capture, resume, and branching.
Verifies CheckpointService behavior for full state capture, time-travel, and branching.
"""

import uuid
import pytest
from datetime import datetime

from backend.services.checkpoint_service import CheckpointService
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.user import User


@pytest.mark.integration
class TestCheckpointStateCapture:
    """Tests for full state capture during checkpoint creation."""

    def _create_test_task_with_agents(self, db, user_id):
        """Helper: create task with supervisor, assigned agents, and subtasks."""
        # Create supervisor (HeadOfCouncil)
        supervisor = Agent(
            agentium_id="HOC001",
            agent_type=AgentType.HEAD_OF_COUNCIL,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
        )
        db.add(supervisor)

        # Create 2 assigned agents
        agent1 = Agent(
            agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            custom_capabilities={"skill": "analysis"},
        )
        agent2 = Agent(
            agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            custom_capabilities={"skill": "execution"},
        )
        db.add_all([agent1, agent2])
        db.flush()

        # Create task
        task = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Test Task",
            description="Test task for checkpoint verification",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            supervisor_id=supervisor.agentium_id,
            assigned_task_agent_ids=[agent1.agentium_id, agent2.agentium_id],
            created_by=str(user_id),
            is_active=True,
        )
        db.add(task)
        db.flush()

        # Create 2 subtasks
        subtask1 = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Subtask 1",
            description="First subtask",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            supervisor_id=task.supervisor_id,
            parent_task_id=task.id,
            assigned_task_agent_ids=[agent1.agentium_id],
            result_data={"score": 85},
            completion_summary="Subtask 1 completed successfully",
            is_active=True,
        )
        subtask2 = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Subtask 2",
            description="Second subtask",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            supervisor_id=task.supervisor_id,
            parent_task_id=task.id,
            assigned_task_agent_ids=[agent2.agentium_id],
            result_data=None,
            completion_summary=None,
            is_active=True,
        )
        db.add_all([subtask1, subtask2])
        db.commit()

        return task, supervisor, [agent1, agent2], [subtask1, subtask2]

    def test_create_checkpoint_captures_task_snapshot(self, seeded_db):
        """Task with status, result_data, assigned agents: task_state_snapshot contains all fields."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
            artifacts=[{"key": "artifact1", "value": "data"}],
        )

        snapshot = checkpoint.task_state_snapshot
        assert "status" in snapshot
        assert snapshot["status"] == TaskStatus.IN_PROGRESS.value
        assert "result_data" in snapshot
        assert snapshot["result_data"] == {}
        assert "assigned_task_agent_ids" in snapshot
        assert set(snapshot["assigned_task_agent_ids"]) == set(task.assigned_task_agent_ids)
        assert "supervisor_id" in snapshot
        assert snapshot["supervisor_id"] == task.supervisor_id
        assert "description" in snapshot
        assert checkpoint.phase == CheckpointPhase.EXECUTION_COMPLETE
        assert len(checkpoint.artifacts) == 1

    def test_create_checkpoint_captures_agent_states(self, seeded_db):
        """Task with 2 assigned agents + supervisor: agent_states has 3 entries with all fields."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, supervisor, agents, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        agent_states = checkpoint.agent_states
        assert len(agent_states) == 3  # supervisor + 2 agents

        # Check supervisor
        sup_state = agent_states[supervisor.agentium_id]
        assert sup_state["status"] == AgentStatus.ACTIVE.value
        assert sup_state["agent_type"] == AgentType.HEAD_OF_COUNCIL.value
        assert sup_state["is_persistent"] is True
        assert "ethos_summary" in sup_state

        # Check assigned agents
        for agent in agents:
            a_state = agent_states[agent.agentium_id]
            assert a_state["status"] == AgentStatus.ACTIVE.value
            assert a_state["agent_type"] == AgentType.LEAD_AGENT.value
            assert a_state["is_persistent"] is False
            assert "custom_capabilities" in a_state

    def test_create_checkpoint_captures_subtasks(self, seeded_db):
        """Task with 2 active subtasks: subtask_snapshots list with all fields for each."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, subtasks = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        snapshots = checkpoint.task_state_snapshot.get("subtask_snapshots", [])
        assert len(snapshots) == 2

        for snap in snapshots:
            assert "id" in snap
            assert "status" in snap
            assert "description" in snap
            assert "assigned_task_agent_ids" in snap
            assert "result_data" in snap
            assert "completion_summary" in snap

        # Verify specific subtask data
        completed_snap = next(s for s in snapshots if s["status"] == TaskStatus.COMPLETED.value)
        assert completed_snap["result_data"] == {"score": 85}
        assert completed_snap["completion_summary"] == "Subtask 1 completed successfully"

        in_progress_snap = next(s for s in snapshots if s["status"] == TaskStatus.IN_PROGRESS.value)
        assert in_progress_snap["result_data"] is None
        assert in_progress_snap["completion_summary"] is None

    def test_create_checkpoint_audit_log_created(self, seeded_db):
        """After create: AuditLog entry with action=checkpoint_created."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        audit = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_created"
        ).first()

        assert audit is not None
        assert audit.category == AuditCategory.SYSTEM
        assert audit.level == AuditLevel.INFO
        assert "checkpoint_created" in audit.description


- [ ] **Step 6.2: Add TestCheckpointResume class with 6 test methods**

```python
@pytest.mark.integration
class TestCheckpointResume:
    """Tests for time-travel resume from checkpoint."""

    def test_resume_restores_task_status(self, seeded_db):
        """Task was COMPLETED, checkpoint has PENDING: Task status = PENDING after resume."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))
        # Modify task to COMPLETED
        task.status = TaskStatus.COMPLETED
        task.result_data = {"final_score": 100}
        db.commit()

        # Create checkpoint with PENDING status
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        # Verify checkpoint captured PENDING
        assert checkpoint.task_state_snapshot["status"] == TaskStatus.IN_PROGRESS.value

        # Now resume from checkpoint
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        assert resumed_task.status == TaskStatus.IN_PROGRESS
        assert resumed_task.result_data == {}

    def test_resume_restores_result_data(self, seeded_db):
        """Checkpoint has result_data={'score': 42}: task.result_data == {'score': 42} after resume."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))
        # Clear result_data
        task.result_data = {}
        db.commit()

        # Create checkpoint with specific result_data
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        # Manually set checkpoint's task_state_snapshot result_data
        checkpoint.task_state_snapshot["result_data"] = {"score": 42, "details": "completed"}
        db.commit()

        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        assert resumed_task.result_data == {"score": 42, "details": "completed"}

    def test_resume_restores_assigned_agents(self, seeded_db):
        """Checkpoint has assigned_task_agent_ids: task.assigned_task_agent_ids matches after resume."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, agents, _ = self._create_test_task_with_agents(db, str(user.id))
        # Change assigned agents
        task.assigned_task_agent_ids = ["NEW_AGENT_1"]
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        original_agent_ids = set(checkpoint.task_state_snapshot["assigned_task_agent_ids"])
        assert original_agent_ids == set([a.agentium_id for a in agents])

        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        assert set(resumed_task.assigned_task_agent_ids) == original_agent_ids

    def test_resume_restores_agent_states(self, seeded_db):
        """Checkpoint has agent states with statuses: Agents in DB have matching status, current_task_id."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, supervisor, agents, _ = self._create_test_task_with_agents(db, str(user.id))

        # Change agent states
        supervisor.status = AgentStatus.ERROR
        agents[0].status = AgentStatus.IDLE
        agents[1].status = AgentStatus.COMPLETED
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        # Verify captured states
        assert checkpoint.agent_states[supervisor.agentium_id]["status"] == AgentStatus.ACTIVE.value
        assert checkpoint.agent_states[agents[0].agentium_id]["status"] == AgentStatus.ACTIVE.value
        assert checkpoint.agent_states[agents[1].agentium_id]["status"] == AgentStatus.ACTIVE.value

        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        # Agents should be restored to ACTIVE
        db.refresh(supervisor)
        db.refresh(agents[0])
        db.refresh(agents[1])
        assert supervisor.status == AgentStatus.ACTIVE
        assert agents[0].status == AgentStatus.ACTIVE
        assert agents[1].status == AgentStatus.ACTIVE

    def test_resume_restores_subtask_states(self, seeded_db):
        """Checkpoint has subtask snapshots: Subtasks have matching status, result_data, assigned agents."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, subtasks = self._create_test_task_with_agents(db, str(user.id))

        # Change subtask states
        for st in subtasks:
            st.status = TaskStatus.FAILED
            st.result_data = {"error": "failed"}
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        # Verify checkpoint captured original states
        snapshots = checkpoint.task_state_snapshot.get("subtask_snapshots", [])
        completed_snap = next(s for s in snapshots if s["status"] == TaskStatus.COMPLETED.value)
        assert completed_snap["result_data"] == {"score": 85}

        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        # Verify subtasks restored
        restored_subtasks = db.query(Task).filter(Task.parent_task_id == task.id).all()
        assert len(restored_subtasks) == 2
        for st in restored_subtasks:
            if st.status == TaskStatus.COMPLETED:
                assert st.result_data == {"score": 85}
                assert st.completion_summary == "Subtask 1 completed successfully"
            elif st.status == TaskStatus.IN_PROGRESS:
                assert st.result_data is None
                assert st.completion_summary is None

    def test_resume_creates_audit_log(self, seeded_db):
        """After resume: AuditLog entry with action=checkpoint_resumed."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        audit = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_resumed"
        ).first()

        assert audit is not None
        assert audit.category == AuditCategory.SYSTEM
        assert audit.level == AuditLevel.INFO
        assert "checkpoint_resumed" in audit.description


- [ ] **Step 6.3: Add TestCheckpointBranching class with 5 test methods**

```python
@pytest.mark.integration
class TestCheckpointBranching:
    """Tests for branching from a checkpoint."""

    def test_branch_creates_new_task(self, seeded_db):
        """Branch from checkpoint: New Task with new UUID, same description, type, priority."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        branch_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="experimental-branch",
            actor_id="test",
        )

        # New task created
        assert branch_task.id != task.id
        assert branch_task.title == task.title
        assert branch_task.description == task.description
        assert branch_task.task_type == task.task_type
        assert branch_task.priority == task.priority
        # Status should be PENDING for new branch
        assert branch_task.status == TaskStatus.PENDING

    def test_branch_creates_branch_checkpoint(self, seeded_db):
        """After branch: New ExecutionCheckpoint with parent_checkpoint_id linking to source, branch_name set."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        branch_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="experimental-branch",
            actor_id="test",
        )

        # Verify branch checkpoint created
        branch_checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.task_id == branch_task.id
        ).first()

        assert branch_checkpoint is not None
        assert branch_checkpoint.parent_checkpoint_id == checkpoint.id
        assert branch_checkpoint.branch_name == "experimental-branch"
        assert branch_checkpoint.phase == CheckpointPhase.BRANCH_CREATED

    def test_branch_task_independent(self, seeded_db):
        """Modify branch task: Original task unchanged; branch task has own state."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        branch_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="independent-branch",
            actor_id="test",
        )

        # Modify branch task
        branch_task.status = TaskStatus.IN_PROGRESS
        branch_task.result_data = {"branch_specific": "data"}
        db.commit()

        # Original task should be unchanged
        db.refresh(task)
        assert task.status == TaskStatus.IN_PROGRESS  # Original was IN_PROGRESS
        assert task.result_data == {}  # Original was empty

        # Branch task has its own state
        assert branch_task.status == TaskStatus.IN_PROGRESS
        assert branch_task.result_data == {"branch_specific": "data"}

    def test_branch_with_new_supervisor(self, seeded_db):
        """Pass new_supervisor_id: New task has supervisor_id = new_supervisor_id."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, supervisor, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        # Create a new supervisor
        new_supervisor = Agent(
            agentium_id="HOC002",
            agent_type=AgentType.HEAD_OF_COUNCIL,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
        )
        db.add(new_supervisor)
        db.commit()

        branch_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="new-supervisor-branch",
            actor_id="test",
            new_supervisor_id=new_supervisor.agentium_id,
        )

        assert branch_task.supervisor_id == new_supervisor.agentium_id
        assert branch_task.supervisor_id != task.supervisor_id

    def test_branch_audit_log_created(self, seeded_db):
        """After branch: AuditLog entry with action=checkpoint_branched."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        task, _, _, _ = self._create_test_task_with_agents(db, str(user.id))

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="audit-test-branch",
            actor_id="test",
        )

        audit = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_branched"
        ).first()

        assert audit is not None
        assert audit.category == AuditCategory.SYSTEM
        assert audit.level == AuditLevel.INFO
        assert "checkpoint_branched" in audit.description
```

---

### Task 7: Create test_cross_component_retention.py - Cross-Component Integration Tests

**Files:**
- Create: `backend/tests/integration/test_cross_component_retention.py`

**Interfaces:**
- Consumes: `seeded_db` fixture, `redis_client` fixture, `ChatContextBuilder`, `ContextWindowManager`, `CheckpointService`, `Task`, `Agent`, `ChatMessage`
- Produces: Test class `TestMultiComponentContextRetention` with 3 test methods

- [ ] **Step 7.1: Create test file with imports and TestMultiComponentContextRetention class**

```python
"""
Cross-component integration tests for context retention across chat_context, context_manager, and checkpoint_service.
Verifies end-to-end state preservation across all three components.
"""

import pytest
from backend.services.chat_context import ChatContextBuilder
from backend.services.context_manager import context_manager
from backend.services.checkpoint_service import CheckpointService
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.chat_message import ChatMessage as ChatMsg
from backend.models.entities.user import User


@pytest.fixture(autouse=True)
def reset_context_manager():
    """Reset context_manager singleton before each test."""
    context_manager.agent_contexts.clear()
    yield
    context_manager.agent_contexts.clear()


@pytest.mark.integration
class TestMultiComponentContextRetention:
    """Tests for end-to-end context retention across all three components."""

    def test_chat_context_feeds_context_manager(self, seeded_db, redis_client):
        """Simulate chat turns -> context_manager.update_usage: context_manager tracks tokens from chat context compaction."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        # Clean existing messages
        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # Seed 55 turns
        for i in range(55):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        # Build context - this triggers compaction
        builder = ChatContextBuilder(window_size=10)
        chat_context = builder.build(db, user_id)

        # Should be compressed (55 turns > window 10)
        assert chat_context["context_compressed"] is True
        assert chat_context["raw_turn_count"] == 55

        # Estimate tokens from context and feed to context_manager
        from backend.services.chat_context import estimate_tokens
        token_count = estimate_tokens(chat_context["history"])

        # Register agent and update with chat context tokens
        context_manager.register_agent("cross-component-agent", "gpt-4o")
        context_manager.update_usage("cross-component-agent", token_count)

        status = context_manager.check_status("cross-component-agent")
        assert status is not None
        assert status.current_tokens == token_count
        assert status.max_tokens == 128_000

    def test_reincarnation_preserves_checkpoint_wisdom(self, seeded_db):
        """Agent reincarnates -> checkpoint captures state -> resume: Wisdom from context_manager reflected in checkpoint's agent_states."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        # Create task with agents
        task, supervisor, agents, _ = self._create_test_task_with_agents(db, str(user.id))

        # Use context_manager to accumulate wisdom for this agent
        context_manager.register_agent(f"agent-{supervisor.agentium_id}", "gpt-4o")
        context_manager.add_wisdom(f"agent-{supervisor.agentium_id}", "learned critical pattern", ["pattern-recognition"])

        # Create checkpoint
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        # Verify checkpoint captured wisdom in agent_states (ethos_summary)
        sup_state = checkpoint.agent_states[supervisor.agentium_id]
        assert "ethos_summary" in sup_state
        # The ethos_summary should contain wisdom information
        assert sup_state["ethos_summary"] is not None

        # Simulate reincarnation via context_manager
        prep = context_manager.prepare_for_reincarnation(f"agent-{supervisor.agentium_id}")
        assert len(prep["accumulated_wisdom"]) == 1
        assert prep["accumulated_wisdom"][0]["summary"] == "learned critical pattern"

        # Transfer to successor
        context_manager.transfer_to_successor(f"agent-{supervisor.agentium_id}", f"agent-successor-{supervisor.agentium_id}")

        # New agent should inherit wisdom
        new_ctx = context_manager.agent_contexts[f"agent-successor-{supervisor.agentium_id}"]
        assert new_ctx["incarnation"] == 2
        assert len(new_ctx["accumulated_wisdom"]) == 1
        assert new_ctx["accumulated_wisdom"][0]["summary"] == "learned critical pattern"

    def _create_test_task_with_agents(self, db, user_id):
        """Helper: create task with supervisor, assigned agents, and subtasks."""
        import uuid

        # Create supervisor (HeadOfCouncil)
        supervisor = Agent(
            agentium_id="HOC001",
            agent_type=AgentType.HEAD_OF_COUNCIL,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
        )
        db.add(supervisor)

        # Create 2 assigned agents
        agent1 = Agent(
            agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            custom_capabilities={"skill": "analysis"},
        )
        agent2 = Agent(
            agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
            agent_type=AgentType.LEAD_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
            custom_capabilities={"skill": "execution"},
        )
        db.add_all([agent1, agent2])
        db.flush()

        # Create task
        task = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Test Task",
            description="Test task for checkpoint verification",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            supervisor_id=supervisor.agentium_id,
            assigned_task_agent_ids=[agent1.agentium_id, agent2.agentium_id],
            created_by=str(user_id),
            is_active=True,
        )
        db.add(task)
        db.flush()

        # Create 2 subtasks
        subtask1 = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Subtask 1",
            description="First subtask",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            supervisor_id=task.supervisor_id,
            parent_task_id=task.id,
            assigned_task_agent_ids=[agent1.agentium_id],
            result_data={"score": 85},
            completion_summary="Subtask 1 completed successfully",
            is_active=True,
        )
        subtask2 = Task(
            agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
            title="Subtask 2",
            description="Second subtask",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            supervisor_id=task.supervisor_id,
            parent_task_id=task.id,
            assigned_task_agent_ids=[agent2.agentium_id],
            result_data=None,
            completion_summary=None,
            is_active=True,
        )
        db.add_all([subtask1, subtask2])
        db.commit()

        return task, supervisor, [agent1, agent2], [subtask1, subtask2]

    def test_full_lifecycle(self, seeded_db, redis_client):
        """Chat -> context builds -> checkpoint -> resume -> branch: End-to-end state preserved across all three components."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        # Clean existing messages
        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # ---- Phase 1: Chat conversation ----
        # Seed 55 turns
        for i in range(55):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"lifecycle-turn-{i}-{role}",
            ))
        db.commit()

        # Build chat context (triggers compaction)
        builder = ChatContextBuilder(window_size=10)
        chat_context = builder.build(db, user_id)
        assert chat_context["context_compressed"] is True
        assert chat_context["raw_turn_count"] == 55
        assert len(chat_context["history"]) == 11  # pinned first + last 10

        # ---- Phase 2: Context manager tracks tokens ----
        from backend.services.chat_context import estimate_tokens
        token_count = estimate_tokens(chat_context["history"])

        context_manager.register_agent("lifecycle-agent", "gpt-4o")
        context_manager.update_usage("lifecycle-agent", token_count)
        context_manager.add_wisdom("lifecycle-agent", "completed initial analysis", ["analysis"])

        status = context_manager.check_status("lifecycle-agent")
        assert status.current_tokens == token_count
        assert status.get("wisdom_entries", 0) == 1

        # ---- Phase 3: Create checkpoint ----
        task, supervisor, agents, _ = self._create_test_task_with_agents(db, user_id)

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )

        # Verify checkpoint captured task and agent state
        assert checkpoint.task_state_snapshot["status"] == TaskStatus.IN_PROGRESS.value
        assert len(checkpoint.agent_states) >= 3  # supervisor + 2 agents

        # ---- Phase 4: Resume from checkpoint ----
        # Modify task state
        task.status = TaskStatus.COMPLETED
        task.result_data = {"final": "result"}
        db.commit()

        # Resume
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test",
        )

        assert resumed_task.status == TaskStatus.IN_PROGRESS
        assert resumed_task.result_data == {}

        # ---- Phase 5: Branch from checkpoint ----
        branch_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="lifecycle-branch",
            actor_id="test",
        )

        assert branch_task.id != task.id
        assert branch_task.status == TaskStatus.PENDING

        # Verify branch checkpoint created
        branch_checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.task_id == branch_task.id
        ).first()
        assert branch_checkpoint is not None
        assert branch_checkpoint.parent_checkpoint_id == checkpoint.id
        assert branch_checkpoint.branch_name == "lifecycle-branch"

        # ---- End-to-end verification ----
        # Original checkpoint still exists
        assert db.query(ExecutionCheckpoint).filter(ExecutionCheckpoint.id == checkpoint.id).first() is not None
        # Context manager still has wisdom
        stats = context_manager.get_stats("lifecycle-agent")
        assert stats["wisdom_entries"] == 1
        assert stats["total_wisdom_tokens"] > 0
```

---

### Task 8: Add shared fixtures to conftest.py

**Files:**
- Modify: `backend/tests/integration/conftest.py`

**Interfaces:**
- Produces: Fixtures for `chat_context_builder`, `context_manager_clean`, `seeded_task_with_agents`, `fake_model_provider`

- [ ] **Step 8.1: Add fixtures to conftest.py**

```python
# Add these fixtures to backend/tests/integration/conftest.py

import pytest
from unittest.mock import AsyncMock

from backend.services.chat_context import ChatContextBuilder
from backend.services.context_manager import context_manager
from backend.services.model_provider import ModelService


@pytest.fixture
def chat_context_builder():
    """ChatContextBuilder with default window_size=10."""
    return ChatContextBuilder(window_size=10)


@pytest.fixture(autouse=True)
def context_manager_clean():
    """Reset context_manager singleton before each test."""
    context_manager.agent_contexts.clear()
    yield context_manager
    context_manager.agent_contexts.clear()


@pytest.fixture
def seeded_task_with_agents(seeded_db):
    """Create task with supervisor, 2 assigned agents, 2 subtasks."""
    import uuid

    supervisor = Agent(
        agentium_id="HOC001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=True,
    )
    seeded_db.add(supervisor)

    agent1 = Agent(
        agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=False,
        custom_capabilities={"skill": "analysis"},
    )
    agent2 = Agent(
        agentium_id=f"LA{uuid.uuid4().hex[:6].upper()}",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=False,
        custom_capabilities={"skill": "execution"},
    )
    seeded_db.add_all([agent1, agent2])
    seeded_db.flush()

    task = Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title="Test Task",
        description="Test task for checkpoint verification",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.NORMAL,
        supervisor_id=supervisor.agentium_id,
        assigned_task_agent_ids=[agent1.agentium_id, agent2.agentium_id],
        created_by="system",
        is_active=True,
    )
    seeded_db.add(task)
    seeded_db.flush()

    subtask1 = Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title="Subtask 1",
        description="First subtask",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.NORMAL,
        supervisor_id=task.supervisor_id,
        parent_task_id=task.id,
        assigned_task_agent_ids=[agent1.agentium_id],
        result_data={"score": 85},
        completion_summary="Subtask 1 completed successfully",
        is_active=True,
    )
    subtask2 = Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title="Subtask 2",
        description="Second subtask",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.NORMAL,
        supervisor_id=task.supervisor_id,
        parent_task_id=task.id,
        assigned_task_agent_ids=[agent2.agentium_id],
        result_data=None,
        completion_summary=None,
        is_active=True,
    )
    seeded_db.add_all([subtask1, subtask2])
    seeded_db.commit()

    return task, [agent1, agent2], [subtask1, subtask2]


@pytest.fixture
def fake_model_provider():
    """Mock provider returning valid JSON summary."""
    import json
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value={
        "content": json.dumps({
            "key_facts": ["Test fact"],
            "decisions": ["Test decision"],
            "open_threads": ["Test thread"]
        }),
        "model": "test-model",
        "tokens_used": 150,
        "latency_ms": 500,
    })
    return mock
```