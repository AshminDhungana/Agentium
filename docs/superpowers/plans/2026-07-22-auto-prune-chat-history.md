# Auto-Prune Chat History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a two-tier auto-pruning system for chat history: soft-delete messages older than 7 days of inactivity per conversation (retaining last 10), hard-delete soft-deleted messages older than 30 days. Runs daily via Celery Beat.

**Architecture:** New `ChatPruneService` encapsulates pruning logic. Celery task `prune_chat_history` reads preferences, finds stale conversations via `Conversation.last_message_at` index, prunes each. Admin API enables manual/dry-run triggers. Zero changes to AI context pipeline — existing `is_deleted` filter handles exclusion.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Celery 5.3, PostgreSQL 15, pytest, alembic

## Global Constraints

- Follow existing patterns: `UserPreferenceService` for config, `AuditLog.log()` for auditing, `SessionLocal()` for background task DB sessions
- Celery tasks in `backend/tasks/`; beat schedule in `backend/celery_beat_schedule.py`
- Admin routes under `/api/v1/admin/` with `get_current_admin_user` dependency
- Tests: unit in `backend/tests/unit/`, integration in `backend/tests/integration/` (requires `pytest.mark.integration`)
- Migrations: `backend/alembic/versions/` with `alembic revision --autogenerate`
- Type hints required; docstrings for public functions
- Commit per task; run `pytest` after each task

---

### Task 1: Add Chat Prune Preferences to UserPreferenceService

**Files:**
- Modify: `backend/services/user_preference_service.py:24-46` (DEFAULT_PREFERENCES dict)
- Test: `backend/tests/unit/test_user_preference_service.py` (add test for new keys)

**Interfaces:**
- Produces: 5 new keys in `DEFAULT_PREFERENCES` dict with defaults matching spec

- [ ] **Step 1: Write failing test**

```python
def test_chat_prune_preferences_exist():
    """New chat prune preferences should be in DEFAULT_PREFERENCES."""
    from backend.services.user_preference_service import UserPreferenceService
    prefs = UserPreferenceService.DEFAULT_PREFERENCES
    assert 'chat.prune_enabled' in prefs
    assert prefs['chat.prune_enabled'] is True
    assert 'chat.prune_retention_days' in prefs
    assert prefs['chat.prune_retention_days'] == 7
    assert 'chat.prune_hard_delete_days' in prefs
    assert prefs['chat.prune_hard_delete_days'] == 30
    assert 'chat.prune_retain_count' in prefs
    assert prefs['chat.prune_retain_count'] == 10
    assert 'chat.prune_schedule_cron' in prefs
    assert prefs['chat.prune_schedule_cron'] == "0 3 * * *"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd E:\Ongoing Projects\Agentium
pytest backend/tests/unit/test_user_preference_service.py::test_chat_prune_preferences_exist -v
```
Expected: FAIL (KeyError or missing keys)

- [ ] **Step 3: Add preferences to DEFAULT_PREFERENCES**

```python
# In backend/services/user_preference_service.py, inside DEFAULT_PREFERENCES dict (around line 46)
    'chat.prune_enabled': True,
    'chat.prune_retention_days': 7,
    'chat.prune_hard_delete_days': 30,
    'chat.prune_retain_count': 10,
    'chat.prune_schedule_cron': "0 3 * * *",
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest backend/tests/unit/test_user_preference_service.py::test_chat_prune_preferences_exist -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/user_preference_service.py backend/tests/unit/test_user_preference_service.py
git commit -m "feat: add chat prune preferences to UserPreferenceService defaults"
```

---

### Task 2: Create Alembic Migration for Preference Defaults

**Files:**
- Create: `backend/alembic/versions/XXXX_add_chat_prune_prefs.py`
- Test: None (migration tested via integration test later)

**Interfaces:**
- Produces: 5 rows in `user_preferences` table with `agentium_id` PREF0100-PREF0104, `user_id=NULL` (global defaults)

- [ ] **Step 1: Generate migration**

```bash
cd E:\Ongoing Projects\Agentium
cd backend
alembic revision --autogenerate -m "add chat prune preferences"
```

- [ ] **Step 2: Edit generated migration to insert preference rows**

```python
# In the generated file, in upgrade() function:
from alembic import op
import sqlalchemy as sa

op.execute("""
    INSERT INTO user_preferences (id, agentium_id, category, key, value_json, data_type, scope, description, is_editable_by_agents, created_at, updated_at)
    VALUES
        (gen_random_uuid(), 'PREF0100', 'chat', 'prune_enabled', 'true', 'boolean', 'global', 'Enable auto-pruning of chat history', 'Y', NOW(), NOW()),
        (gen_random_uuid(), 'PREF0101', 'chat', 'prune_retention_days', '7', 'integer', 'global', 'Days of inactivity before soft-delete', 'Y', NOW(), NOW()),
        (gen_random_uuid(), 'PREF0102', 'chat', 'prune_hard_delete_days', '30', 'integer', 'global', 'Days after soft-delete before hard-delete', 'Y', NOW(), NOW()),
        (gen_random_uuid(), 'PREF0103', 'chat', 'prune_retain_count', '10', 'integer', 'global', 'Always retain last N messages per conversation', 'Y', NOW(), NOW()),
        (gen_random_uuid(), 'PREF0104', 'chat', 'prune_schedule_cron', '"0 3 * * *"', 'string', 'global', 'Celery Beat cron schedule (UTC)', 'N', NOW(), NOW())
    ON CONFLICT (agentium_id) DO NOTHING
""")
```

- [ ] **Step 3: Run migration to verify**

```bash
cd backend
alembic upgrade head
```

- [ ] **Step 4: Verify rows inserted**

```bash
cd backend
python -c "
from backend.models.database import SessionLocal
from backend.models.entities.user_preference import UserPreference
db = SessionLocal()
prefs = db.query(UserPreference).filter(UserPreference.key.like('chat.prune_%')).all()
for p in prefs:
    print(p.key, p.get_value())
db.close()
"
```
Expected: 5 rows with correct values

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*add_chat_prune_prefs*.py
git commit -m "db: add chat prune preference defaults via migration"
```

---

### Task 3: Create ChatPruneService with Core Pruning Logic

**Files:**
- Create: `backend/services/chat_prune_service.py`
- Test: `backend/tests/unit/test_chat_prune_service.py`

**Interfaces:**
- Consumes: `Session` (SQLAlchemy), `conversation_id`, `retention_days`, `hard_delete_days`, `retain_count`
- Produces: `PruneStats` dataclass with fields `soft_deleted`, `hard_deleted`, `retained`, `conversation_id`
- Public methods:
  - `prune_conversation(conversation_id: str, retention_days: int, hard_delete_days: int, retain_count: int) -> PruneStats`
  - `prune_all_conversations(retention_days: int, hard_delete_days: int, retain_count: int) -> AggregateStats`
  - `dry_run_prune(retention_days: int, hard_delete_days: int, retain_count: int) -> AggregateStats`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_chat_prune_service.py
import pytest
from datetime import datetime, timedelta
from backend.services.chat_prune_service import ChatPruneService, PruneStats, AggregateStats
from backend.models.entities.chat_message import ChatMessage
from backend.models.entities.conversation import Conversation
from backend.models.entities.user import User

class TestChatPruneService:
    @pytest.fixture
    def service(self, db_session):
        return ChatPruneService(db_session)

    @pytest.fixture
    def user(self, db_session):
        u = User(id="test-user-id", email="test@test.com", is_admin=True, is_active=True)
        db_session.add(u)
        db_session.commit()
        return u

    @pytest.fixture
    def conversation(self, db_session, user):
        c = Conversation(id="test-conv-id", user_id=user.id, last_message_at=datetime.utcnow() - timedelta(days=10))
        db_session.add(c)
        db_session.commit()
        return c

    def test_prune_conversation_below_retain_count(self, service, conversation, db_session):
        """Conversation with <= retain_count messages: no deletions."""
        now = datetime.utcnow()
        for i in range(5):
            msg = ChatMessage(
                conversation_id=conversation.id,
                user_id="test-user-id",
                role="sovereign" if i % 2 == 0 else "head_of_council",
                content=f"msg {i}",
                created_at=now - timedelta(days=20 - i),
            )
            db_session.add(msg)
        db_session.commit()

        stats = service.prune_conversation(conversation.id, retention_days=7, hard_delete_days=30, retain_count=10)

        assert stats.soft_deleted == 0
        assert stats.hard_deleted == 0
        assert stats.retained == 5
        # Verify all messages still have is_deleted='N'
        msgs = db_session.query(ChatMessage).filter_by(conversation_id=conversation.id).all()
        assert all(m.is_deleted == 'N' for m in msgs)

    def test_prune_conversation_soft_deletes_old_messages(self, service, conversation, db_session):
        """Messages older than retention_days (excluding last retain_count) get soft-deleted."""
        now = datetime.utcnow()
        # 20 messages spanning 30 days
        for i in range(20):
            msg = ChatMessage(
                conversation_id=conversation.id,
                user_id="test-user-id",
                role="sovereign" if i % 2 == 0 else "head_of_council",
                content=f"msg {i}",
                created_at=now - timedelta(days=30 - i * 1.5),
            )
            db_session.add(msg)
        db_session.commit()

        stats = service.prune_conversation(conversation.id, retention_days=7, hard_delete_days=30, retain_count=10)

        # Last 10 retained, first 10 older than 7 days -> soft deleted
        assert stats.retained == 10
        assert stats.soft_deleted == 10
        assert stats.hard_deleted == 0

        msgs = db_session.query(ChatMessage).filter_by(conversation_id=conversation.id).all()
        soft_deleted = [m for m in msgs if m.is_deleted == 'Y']
        assert len(soft_deleted) == 10
        # The retained 10 should be the most recent
        retained_msgs = [m for m in msgs if m.is_deleted == 'N']
        assert len(retained_msgs) == 10

    def test_prune_conversation_hard_deletes_old_soft_deleted(self, service, conversation, db_session):
        """Soft-deleted messages older than hard_delete_days get hard-deleted."""
        now = datetime.utcnow()
        # Create 15 messages: 10 recent (retained), 5 old soft-deleted
        for i in range(15):
            is_old = i < 5
            msg = ChatMessage(
                conversation_id=conversation.id,
                user_id="test-user-id",
                role="sovereign" if i % 2 == 0 else "head_of_council",
                content=f"msg {i}",
                created_at=now - timedelta(days=40 - i * 2),
                is_deleted='Y' if is_old else 'N',
            )
            db_session.add(msg)
        db_session.commit()

        stats = service.prune_conversation(conversation.id, retention_days=7, hard_delete_days=30, retain_count=10)

        # 5 old soft-deleted > 30 days -> hard deleted
        assert stats.hard_deleted == 5
        assert stats.soft_deleted == 0  # no new soft deletes (old ones already deleted)
        assert stats.retained == 10

        remaining = db_session.query(ChatMessage).filter_by(conversation_id=conversation.id).count()
        assert remaining == 10

    def test_prune_all_conversations_skips_active(self, service, user, db_session):
        """Conversations with recent activity are skipped entirely."""
        now = datetime.utcnow()
        # Active conversation (last message 2 days ago)
        active_conv = Conversation(id="active-conv", user_id=user.id, last_message_at=now - timedelta(days=2))
        for i in range(15):
            msg = ChatMessage(conversation_id=active_conv.id, user_id=user.id, role="sovereign", content=f"a{i}", created_at=now - timedelta(days=5 - i))
            db_session.add(msg)
        # Stale conversation (last message 10 days ago)
        stale_conv = Conversation(id="stale-conv", user_id=user.id, last_message_at=now - timedelta(days=10))
        for i in range(15):
            msg = ChatMessage(conversation_id=stale_conv.id, user_id=user.id, role="sovereign", content=f"s{i}", created_at=now - timedelta(days=15 - i))
            db_session.add(msg)
        db_session.add_all([active_conv, stale_conv])
        db_session.commit()

        stats = service.prune_all_conversations(retention_days=7, hard_delete_days=30, retain_count=10)

        assert stats.conversations_processed == 1  # only stale
        assert stats.total_soft_deleted == 5  # 15 - 10 retained

    def test_dry_run_prune_returns_stats_without_deleting(self, service, conversation, db_session):
        """dry_run_prune returns what would be deleted but makes no changes."""
        now = datetime.utcnow()
        for i in range(15):
            msg = ChatMessage(
                conversation_id=conversation.id,
                user_id="test-user-id",
                role="sovereign",
                content=f"msg {i}",
                created_at=now - timedelta(days=20 - i),
            )
            db_session.add(msg)
        db_session.commit()

        stats = service.dry_run_prune(retention_days=7, hard_delete_days=30, retain_count=10)

        assert stats.total_soft_deleted == 5
        # Verify no actual changes
        msgs = db_session.query(ChatMessage).filter_by(conversation_id=conversation.id).all()
        assert all(m.is_deleted == 'N' for m in msgs)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest backend/tests/unit/test_chat_prune_service.py -v
```
Expected: FAIL (module not found, classes not defined)

- [ ] **Step 3: Implement ChatPruneService**

```python
# backend/services/chat_prune_service.py
"""
Chat history pruning service.
Implements two-tier deletion: soft-delete after retention period, hard-delete after hard_delete period.
Always retains the last `retain_count` messages per conversation regardless of age.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from backend.models.entities.chat_message import ChatMessage
from backend.models.entities.conversation import Conversation


@dataclass
class PruneStats:
    """Statistics for a single conversation prune operation."""
    soft_deleted: int
    hard_deleted: int
    retained: int
    conversation_id: str


@dataclass
class AggregateStats:
    """Aggregated statistics across multiple conversations."""
    conversations_processed: int
    total_soft_deleted: int
    total_hard_deleted: int
    total_retained: int

    def to_dict(self) -> dict:
        return {
            "conversations_processed": self.conversations_processed,
            "total_soft_deleted": self.total_soft_deleted,
            "total_hard_deleted": self.total_hard_deleted,
            "total_retained": self.total_retained,
        }


class ChatPruneService:
    """Service for pruning chat history based on inactivity and age."""

    def __init__(self, db: Session):
        self.db = db

    def prune_conversation(
        self,
        conversation_id: str,
        retention_days: int = 7,
        hard_delete_days: int = 30,
        retain_count: int = 10,
    ) -> PruneStats:
        """
        Prune a single conversation.

        Args:
            conversation_id: The conversation to prune.
            retention_days: Days of inactivity before soft-delete.
            hard_delete_days: Days after soft-delete before hard-delete.
            retain_count: Always keep last N messages (never soft-deleted).

        Returns:
            PruneStats with counts of soft/hard deleted and retained messages.
        """
        now = datetime.utcnow()
        soft_cutoff = now - timedelta(days=retention_days)
        hard_cutoff = now - timedelta(days=hard_delete_days)

        # Load all messages for this conversation, oldest first
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        if len(messages) <= retain_count:
            return PruneStats(0, 0, len(messages), conversation_id)

        # Split: recent (last retain_count) vs old (everything before)
        recent = messages[-retain_count:]
        old = messages[:-retain_count]

        soft_deleted = 0
        hard_deleted = 0

        for msg in old:
            # Soft delete: older than retention_days AND not already deleted
            if msg.created_at < soft_cutoff and msg.is_deleted == 'N':
                msg.is_deleted = 'Y'
                soft_deleted += 1

            # Hard delete: already soft-deleted AND older than hard_delete_days
            if msg.is_deleted == 'Y' and msg.created_at < hard_cutoff:
                self.db.delete(msg)
                hard_deleted += 1

        self.db.commit()
        return PruneStats(soft_deleted, hard_deleted, len(recent), conversation_id)

    def _get_stale_conversations(self, retention_days: int) -> List[Conversation]:
        """Get conversations with last_message_at older than retention_days."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        return (
            self.db.query(Conversation)
            .filter(Conversation.last_message_at < cutoff)
            .filter(Conversation.is_deleted == 'N')
            .filter(Conversation.is_archived == 'N')
            .all()
        )

    def prune_all_conversations(
        self,
        retention_days: int = 7,
        hard_delete_days: int = 30,
        retain_count: int = 10,
    ) -> AggregateStats:
        """
        Prune all stale conversations.

        Returns aggregated statistics.
        """
        stale_conversations = self._get_stale_conversations(retention_days)

        total_soft = 0
        total_hard = 0
        total_retained = 0
        processed = 0

        for conv in stale_conversations:
            stats = self.prune_conversation(
                conv.id,
                retention_days=retention_days,
                hard_delete_days=hard_delete_days,
                retain_count=retain_count,
            )
            total_soft += stats.soft_deleted
            total_hard += stats.hard_deleted
            total_retained += stats.retained
            processed += 1

        return AggregateStats(processed, total_soft, total_hard, total_retained)

    def dry_run_prune(
        self,
        retention_days: int = 7,
        hard_delete_days: int = 30,
        retain_count: int = 10,
    ) -> AggregateStats:
        """
        Simulate pruning without making changes.

        Returns what would be deleted.
        """
        stale_conversations = self._get_stale_conversations(retention_days)

        total_soft = 0
        total_hard = 0
        total_retained = 0
        processed = 0

        now = datetime.utcnow()
        soft_cutoff = now - timedelta(days=retention_days)
        hard_cutoff = now - timedelta(days=hard_delete_days)

        for conv in stale_conversations:
            messages = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == conv.id)
                .order_by(ChatMessage.created_at.asc())
                .all()
            )

            if len(messages) <= retain_count:
                total_retained += len(messages)
                processed += 1
                continue

            old = messages[:-retain_count]
            total_retained += retain_count

            for msg in old:
                if msg.created_at < soft_cutoff and msg.is_deleted == 'N':
                    total_soft += 1
                if msg.is_deleted == 'Y' and msg.created_at < hard_cutoff:
                    total_hard += 1

            processed += 1

        return AggregateStats(processed, total_soft, total_hard, total_retained)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/unit/test_chat_prune_service.py -v
```
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_prune_service.py backend/tests/unit/test_chat_prune_service.py
git commit -m "feat: add ChatPruneService with core pruning logic and unit tests"
```

---

### Task 4: Create Celery Task for Daily Pruning

**Files:**
- Create: `backend/tasks/chat_tasks.py`
- Modify: `backend/celery_beat_schedule.py` (add schedule entry)
- Test: `backend/tests/integration/test_chat_prune_task.py`

**Interfaces:**
- Consumes: `ChatPruneService`, preferences via `UserPreferenceService`
- Produces: `AggregateStats` returned; logs structured JSON; writes audit log
- Celery task name: `backend.tasks.chat_tasks.prune_chat_history`
- Beat schedule key: `prune-chat-history-daily`

- [ ] **Step 1: Write failing integration test**

```python
# backend/tests/integration/test_chat_prune_task.py
import pytest
from datetime import datetime, timedelta
from backend.tasks.chat_tasks import prune_chat_history
from backend.models.entities.chat_message import ChatMessage
from backend.models.entities.conversation import Conversation
from backend.models.entities.user import User
from backend.models.entities.user_preference import UserPreference
from backend.services.user_preference_service import UserPreferenceService

@pytest.mark.integration
def test_prune_chat_history_task_runs(db_session):
    """Celery task executes and prunes stale conversations."""
    # Setup: create preferences
    prefs = UserPreferenceService(db_session)
    prefs.set_preference('chat.prune_enabled', True, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retention_days', 7, user_id=None, category='chat')
    prefs.set_preference('chat.prune_hard_delete_days', 30, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retain_count', 10, user_id=None, category='chat')

    # Setup: admin user
    admin = User(id="admin-id", email="admin@test.com", is_admin=True, is_active=True)
    db_session.add(admin)

    # Stale conversation (last_message_at 10 days ago)
    stale_conv = Conversation(id="stale-conv", user_id=admin.id, last_message_at=datetime.utcnow() - timedelta(days=10))
    for i in range(15):
        msg = ChatMessage(
            conversation_id=stale_conv.id,
            user_id=admin.id,
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"stale msg {i}",
            created_at=datetime.utcnow() - timedelta(days=15 - i),
        )
        db_session.add(msg)

    # Active conversation (last_message_at 2 days ago) - should be skipped
    active_conv = Conversation(id="active-conv", user_id=admin.id, last_message_at=datetime.utcnow() - timedelta(days=2))
    for i in range(15):
        msg = ChatMessage(
            conversation_id=active_conv.id,
            user_id=admin.id,
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"active msg {i}",
            created_at=datetime.utcnow() - timedelta(days=5 - i),
        )
        db_session.add(msg)

    db_session.add_all([stale_conv, active_conv])
    db_session.commit()

    # Execute task (synchronously via apply())
    result = prune_chat_history.apply().get()

    assert result["conversations_processed"] == 1
    assert result["total_soft_deleted"] == 5
    assert result["total_hard_deleted"] == 0
    assert result["total_retained"] == 25  # 10 stale + 15 active

    # Verify stale conversation messages soft-deleted
    stale_msgs = db_session.query(ChatMessage).filter_by(conversation_id="stale-conv").all()
    soft_deleted = [m for m in stale_msgs if m.is_deleted == 'Y']
    assert len(soft_deleted) == 5

    # Verify active conversation untouched
    active_msgs = db_session.query(ChatMessage).filter_by(conversation_id="active-conv").all()
    assert all(m.is_deleted == 'N' for m in active_msgs)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/integration/test_chat_prune_task.py::test_prune_chat_history_task_runs -v
```
Expected: FAIL (module not found, task not defined)

- [ ] **Step 3: Create Celery task**

```python
# backend/tasks/chat_tasks.py
"""
Celery tasks for chat maintenance.
"""

from celery import shared_task
from backend.services.chat_prune_service import ChatPruneService
from backend.services.user_preference_service import UserPreferenceService
from backend.models.database import SessionLocal
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def prune_chat_history(self):
    """
    Daily chat history pruning task.

    Reads preferences, finds stale conversations, prunes each.
    Idempotent: safe to re-run.
    """
    db = SessionLocal()
    try:
        pref_service = UserPreferenceService(db)
        prefs = pref_service.get_preferences_dict(category='chat')

        # Check if enabled
        if not prefs.get('chat.prune_enabled', True):
            logger.info("Chat pruning disabled via preference")
            return {"skipped": True, "reason": "disabled"}

        retention = int(prefs.get('chat.prune_retention_days', 7))
        hard_delete = int(prefs.get('chat.prune_hard_delete_days', 30))
        retain = int(prefs.get('chat.prune_retain_count', 10))

        service = ChatPruneService(db)
        stats = service.prune_all_conversations(
            retention_days=retention,
            hard_delete_days=hard_delete,
            retain_count=retain,
        )

        # Audit log
        audit = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="system",
            actor_id="CHAT_PRUNE_TASK",
            action="chat_history_pruned",
            description=f"Pruned {stats.conversations_processed} conversations",
            after_state=stats.to_dict(),
        )
        db.add(audit)
        db.commit()

        # Structured log
        logger.info(
            "Chat prune completed",
            extra={
                "task": "prune_chat_history",
                "conversations_processed": stats.conversations_processed,
                "total_soft_deleted": stats.total_soft_deleted,
                "total_hard_deleted": stats.total_hard_deleted,
                "total_retained": stats.total_retained,
                "preferences": {
                    "retention_days": retention,
                    "hard_delete_days": hard_delete,
                    "retain_count": retain,
                },
            },
        )

        return stats.to_dict()

    except Exception as exc:
        logger.exception("Chat prune task failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
```

- [ ] **Step 4: Add beat schedule**

```python
# backend/celery_beat_schedule.py
# Add to existing beat_schedule dict:

from celery.schedules import crontab

beat_schedule = {
    # ... existing entries ...
    'prune-chat-history-daily': {
        'task': 'backend.tasks.chat_tasks.prune_chat_history',
        'schedule': crontab(hour=3, minute=0),  # 03:00 UTC daily
        'options': {'queue': 'maintenance'},
    },
}
```

- [ ] **Step 5: Run integration test**

```bash
# Ensure Celery worker and beat are running, or test synchronously:
cd E:\Ongoing Projects\Agentium
pytest backend/tests/integration/test_chat_prune_task.py::test_prune_chat_history_task_runs -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/chat_tasks.py backend/celery_beat_schedule.py backend/tests/integration/test_chat_prune_task.py
git commit -m "feat: add chat prune Celery task and beat schedule"
```

---

### Task 5: Create Admin API Route for Manual/Dry-Run Pruning

**Files:**
- Create: `backend/api/routes/admin_chat.py`
- Modify: `backend/api/routes/__init__.py` (register router)
- Test: `backend/tests/integration/test_admin_chat_prune.py`

**Interfaces:**
- Route: `POST /api/v1/admin/chat/prune`
- Query params: `dry_run` (bool), `retention_days` (int, optional), `hard_delete_days` (int, optional), `retain_count` (int, optional)
- Auth: `get_current_admin_user` dependency
- Returns: `AggregateStats.to_dict()` with `dry_run` flag if applicable

- [ ] **Step 1: Write failing integration test**

```python
# backend/tests/integration/test_admin_chat_prune.py
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient
from backend.models.entities.chat_message import ChatMessage
from backend.models.entities.conversation import Conversation
from backend.models.entities.user import User
from backend.models.entities.user_preference import UserPreference
from backend.services.user_preference_service import UserPreferenceService

@pytest.mark.integration
async def test_admin_prune_chat_dry_run(client: AsyncClient, admin_token: str, db_session):
    """Admin dry-run returns stats without deleting."""
    prefs = UserPreferenceService(db_session)
    prefs.set_preference('chat.prune_enabled', True, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retention_days', 7, user_id=None, category='chat')
    prefs.set_preference('chat.prune_hard_delete_days', 30, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retain_count', 10, user_id=None, category='chat')

    admin = User(id="admin-id", email="admin@test.com", is_admin=True, is_active=True)
    stale_conv = Conversation(id="stale-conv", user_id=admin.id, last_message_at=datetime.utcnow() - timedelta(days=10))
    for i in range(15):
        msg = ChatMessage(conversation_id=stale_conv.id, user_id=admin.id, role="sovereign", content=f"msg {i}", created_at=datetime.utcnow() - timedelta(days=15 - i))
        db_session.add(msg)
    db_session.add_all([admin, stale_conv])
    db_session.commit()

    response = await client.post(
        "/api/v1/admin/chat/prune?dry_run=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["conversations_processed"] == 1
    assert data["total_soft_deleted"] == 5

    # Verify no actual changes
    msgs = db_session.query(ChatMessage).filter_by(conversation_id="stale-conv").all()
    assert all(m.is_deleted == 'N' for m in msgs)


@pytest.mark.integration
async def test_admin_prune_chat_executes(client: AsyncClient, admin_token: str, db_session):
    """Admin prune executes and deletes messages."""
    prefs = UserPreferenceService(db_session)
    prefs.set_preference('chat.prune_enabled', True, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retention_days', 7, user_id=None, category='chat')
    prefs.set_preference('chat.prune_hard_delete_days', 30, user_id=None, category='chat')
    prefs.set_preference('chat.prune_retain_count', 10, user_id=None, category='chat')

    admin = User(id="admin-id", email="admin@test.com", is_admin=True, is_active=True)
    stale_conv = Conversation(id="stale-conv", user_id=admin.id, last_message_at=datetime.utcnow() - timedelta(days=10))
    for i in range(15):
        msg = ChatMessage(conversation_id=stale_conv.id, user_id=admin.id, role="sovereign", content=f"msg {i}", created_at=datetime.utcnow() - timedelta(days=15 - i))
        db_session.add(msg)
    db_session.add_all([admin, stale_conv])
    db_session.commit()

    response = await client.post(
        "/api/v1/admin/chat/prune",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["total_soft_deleted"] == 5

    # Verify actual changes
    msgs = db_session.query(ChatMessage).filter_by(conversation_id="stale-conv").all()
    soft_deleted = [m for m in msgs if m.is_deleted == 'Y']
    assert len(soft_deleted) == 5


@pytest.mark.integration
async def test_admin_prune_chat_override_params(client: AsyncClient, admin_token: str, db_session):
    """Admin can override retention/hard_delete/retain via query params."""
    admin = User(id="admin-id", email="admin@test.com", is_admin=True, is_active=True)
    stale_conv = Conversation(id="stale-conv", user_id=admin.id, last_message_at=datetime.utcnow() - timedelta(days=10))
    for i in range(20):
        msg = ChatMessage(conversation_id=stale_conv.id, user_id=admin.id, role="sovereign", content=f"msg {i}", created_at=datetime.utcnow() - timedelta(days=25 - i))
        db_session.add(msg)
    db_session.add_all([admin, stale_conv])
    db_session.commit()

    # Override retain_count=5 (default 10)
    response = await client.post(
        "/api/v1/admin/chat/prune?retain_count=5",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_soft_deleted"] == 15  # 20 - 5 retained
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest backend/tests/integration/test_admin_chat_prune.py -v
```
Expected: FAIL (route not found)

- [ ] **Step 3: Create admin route**

```python
# backend/api/routes/admin_chat.py
"""
Admin routes for chat management.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from backend.api.dependencies import get_current_admin_user, get_db
from backend.models.entities.user import User
from sqlalchemy.orm import Session
from backend.services.chat_prune_service import ChatPruneService

router = APIRouter(prefix="/admin/chat", tags=["admin-chat"])


@router.post("/prune", summary="Manually trigger chat history pruning")
async def prune_chat_history(
    dry_run: bool = Query(False, description="Return stats without deleting"),
    retention_days: Optional[int] = Query(None, description="Override retention days"),
    hard_delete_days: Optional[int] = Query(None, description="Override hard delete days"),
    retain_count: Optional[int] = Query(None, description="Override retain count"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Trigger chat history pruning manually.

    - **dry_run**: If true, returns what would be pruned without making changes.
    - **retention_days**: Override default retention days (from preferences).
    - **hard_delete_days**: Override default hard delete days.
    - **retain_count**: Override default messages to retain per conversation.
    """
    service = ChatPruneService(db)

    # Use preferences as defaults
    from backend.services.user_preference_service import UserPreferenceService
    pref_service = UserPreferenceService(db)
    prefs = pref_service.get_preferences_dict(category='chat')

    retention = retention_days if retention_days is not None else int(prefs.get('chat.prune_retention_days', 7))
    hard_delete = hard_delete_days if hard_delete_days is not None else int(prefs.get('chat.prune_hard_delete_days', 30))
    retain = retain_count if retain_count is not None else int(prefs.get('chat.prune_retain_count', 10))

    if dry_run:
        stats = service.dry_run_prune(
            retention_days=retention,
            hard_delete_days=hard_delete,
            retain_count=retain,
        )
        result = stats.to_dict()
        result["dry_run"] = True
        return result

    stats = service.prune_all_conversations(
        retention_days=retention,
        hard_delete_days=hard_delete,
        retain_count=retain,
    )
    return stats.to_dict()
```

- [ ] **Step 4: Register router**

```python
# backend/api/routes/__init__.py
# Add to existing imports:
from backend.api.routes.admin_chat import router as admin_chat_router

# Add to router inclusion:
app.include_router(admin_chat_router, prefix="/api/v1")
```

- [ ] **Step 5: Run integration test**

```bash
pytest backend/tests/integration/test_admin_chat_prune.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/admin_chat.py backend/api/routes/__init__.py backend/tests/integration/test_admin_chat_prune.py
git commit -m "feat: add admin API for manual chat history pruning"
```

---

### Task 6: Verify AI Context Exclusion Works (Integration Test)

**Files:**
- Test: `backend/tests/integration/test_chat_prune_ai_context.py`

**Interfaces:**
- Verifies: `ChatContextBuilder._load_raw()` excludes `is_deleted='Y'` messages
- Verifies: `get_full_history` tool CAN access soft-deleted messages

- [ ] **Step 1: Write test**

```python
# backend/tests/integration/test_chat_prune_ai_context.py
import pytest
from datetime import datetime, timedelta
from backend.services.chat_context import ChatContextBuilder, set_chat_request, clear_chat_request, get_full_history
from backend.models.entities.chat_message import ChatMessage
from backend.models.entities.conversation import Conversation
from backend.models.entities.user import User

@pytest.mark.integration
def test_soft_deleted_messages_excluded_from_ai_context(db_session):
    """ChatContextBuilder should not include soft-deleted messages in AI context."""
    user = User(id="test-user", email="test@test.com", is_admin=True, is_active=True)
    conv = Conversation(id="test-conv", user_id=user.id, last_message_at=datetime.utcnow())
    db_session.add_all([user, conv])

    # 5 normal messages, 5 soft-deleted older messages
    for i in range(5):
        msg = ChatMessage(
            conversation_id=conv.id,
            user_id=user.id,
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"normal msg {i}",
            created_at=datetime.utcnow() - timedelta(days=5 - i),
        )
        db_session.add(msg)
    for i in range(5):
        msg = ChatMessage(
            conversation_id=conv.id,
            user_id=user.id,
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"DELETED msg {i}",
            created_at=datetime.utcnow() - timedelta(days=15 - i),
            is_deleted='Y',
        )
        db_session.add(msg)
    db_session.commit()

    builder = ChatContextBuilder(window_size=10)
    result = builder.build(db_session, user.id)

    # Only 5 normal messages should appear (soft-deleted excluded by _load_raw filter)
    assert len(result["history"]) == 5
    contents = [m["content"] for m in result["history"]]
    assert all("DELETED" not in c for c in contents)
    assert all("normal msg" in c for c in contents)


@pytest.mark.integration
def test_get_full_history_can_access_soft_deleted(db_session):
    """get_full_history tool should be able to retrieve soft-deleted messages."""
    user = User(id="test-user", email="test@test.com", is_admin=True, is_active=True)
    conv = Conversation(id="test-conv", user_id=user.id, last_message_at=datetime.utcnow())
    db_session.add_all([user, conv])

    msg = ChatMessage(
        conversation_id=conv.id,
        user_id=user.id,
        role="sovereign",
        content="this was soft deleted",
        created_at=datetime.utcnow() - timedelta(days=10),
        is_deleted='Y',
    )
    db_session.add(msg)
    db_session.commit()

    set_chat_request(user_id=str(user.id), db=db_session)
    try:
        result = get_full_history(limit=50)
    finally:
        clear_chat_request()

    assert result["status"] == "ok"
    assert result["message_count"] == 1
    assert result["history"][0]["content"] == "this was soft deleted"
```

- [ ] **Step 2: Run test to verify it passes (should already work)**

```bash
pytest backend/tests/integration/test_chat_prune_ai_context.py -v
```
Expected: PASS (no code changes needed — existing `_load_raw` filter handles this)

- [ ] **Step 3: Commit test only**

```bash
git add backend/tests/integration/test_chat_prune_ai_context.py
git commit -m "test: verify AI context excludes soft-deleted messages"
```

---

### Task 7: Run Full Test Suite and Verify

**Files:** None (verification only)

- [ ] **Step 1: Run all new unit tests**

```bash
cd E:\Ongoing Projects\Agentium
pytest backend/tests/unit/test_chat_prune_service.py backend/tests/unit/test_user_preference_service.py -v
```
Expected: All PASS

- [ ] **Step 2: Run all new integration tests**

```bash
pytest backend/tests/integration/test_chat_prune_task.py backend/tests/integration/test_admin_chat_prune.py backend/tests/integration/test_chat_prune_ai_context.py -v
```
Expected: All PASS

- [ ] **Step 3: Run full test suite (no regressions)**

```bash
pytest backend/tests/ -x --tb=short
```
Expected: No new failures

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: any test fixes from full suite run"
```

---

## Spec Coverage Checklist

| Spec Requirement | Task |
|------------------|------|
| Per-conversation pruning | Task 3 (ChatPruneService.prune_conversation) |
| Retain last 10 messages | Task 3 (retain_count logic + tests) |
| Soft delete at 7 days inactivity | Task 3 (retention_days=7 + tests) |
| Hard delete at 30 days soft-deleted | Task 3 (hard_delete_days=30 + tests) |
| Celery Beat daily 03:00 UTC | Task 4 (beat_schedule entry) |
| Preferences configurable | Task 1 + Task 2 (UserPreferenceService + migration) |
| Admin API manual/dry-run | Task 5 |
| AI context auto-excludes soft-deleted | Task 6 (verified zero changes needed) |
| Audit logging | Task 4 (AuditLog.log in task) |
| Structured logging | Task 4 (logger.info with extra) |

---

## Execution Handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-07-22-auto-prune-chat-history.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - REQUIRED SUB-SKILL: Use superpowers:executing-plans

**Which approach?**