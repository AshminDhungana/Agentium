# Auto-Prune Chat History — Design Specification

**Date**: 2026-07-22  
**Priority**: P2  
**Status**: Design Review  
**Author**: AI Assistant (brainstorming skill)  
**Related**: Task 10.5, Chat Context Compaction (Task 2.1)

---

## 1. Problem Statement

Agentium's chat history grows unbounded over time. The current system uses a **sliding window + background summarization** approach (Task 2.1) that limits what goes to the AI model, but the underlying PostgreSQL `chat_messages` table accumulates all messages indefinitely. This causes:

- **Storage bloat**: Unbounded row growth in `chat_messages`
- **Query degradation**: `ChatContextBuilder._load_raw()` scans more rows over time (even with index, full scan of `is_deleted='N'` grows)
- **Token waste**: While the sliding window limits context, old messages still consume DB space
- **No data lifecycle policy**: No automatic cleanup aligned with the 7-day context window used by summarization

**Goal**: Implement a two-tier auto-pruning system that:
1. **Soft-deletes** (marks `is_deleted='Y'`) messages older than 7 days of inactivity per conversation, **but always retains the last 10 messages** per conversation
2. **Hard-deletes** (permanently removes) soft-deleted messages older than 30 days
3. Runs daily via Celery Beat
4. Reuses existing `is_deleted` column — AI context already excludes soft-deleted messages via `ChatContextBuilder._load_raw()` filter

---

## 2. Background & Research

### 2.1 Current Architecture (Agentium)

| Component | Behavior |
|-----------|----------|
| `ChatMessage` model | `is_deleted` column (String(1), default 'N'), `conversation_id`, `created_at` |
| `ChatContextBuilder._load_raw()` | Filters `ChatMsg.is_deleted == 'N'` — **soft-deleted auto-excluded from AI context** |
| `ChatContextBuilder` window | Default 10 turns, pins first user message |
| `summarize_history()` | Background task, Redis summary with 7-day TTL |
| `get_full_history` tool | Can retrieve soft-deleted messages if explicitly called |
| Celery Beat | Runs periodic tasks (e.g., `constitutional_patrol`, `knowledge_maintenance`) |

### 2.2 Industry Best Practices (Research)

| System | Approach | Key Insight |
|--------|----------|-------------|
| **OpenAI Responses API** | Server-side compaction at `compact_threshold` (token-based) + standalone `/responses/compact` endpoint | Compaction is **token-aware**, not time-based; preserves reasoning items |
| **PostgreSQL Autovacuum** | Threshold-based: `vacuum_threshold = base + scale_factor * reltuples` | **Adaptive frequency** based on table activity, not fixed schedule |
| **MongoDB TTL Indexes** | Automatic expiry based on timestamp field | **Native DB-level expiration**, no app logic needed |
| **Redis Keyspace Notifications** | Expired key events | Event-driven cleanup possible |
| **Discord/Slack** | Per-channel retention policies (30d–∞), user-configurable | **Per-conversation** granularity, user control |

### 2.3 Key Design Principles from Research

1. **Two-tier deletion** (soft → hard) enables recovery and aligns with existing `is_deleted` column
2. **Per-conversation granularity** matches Agentium's `conversation_id` model and user mental model
3. **Retain-last-N** (10 messages) preserves immediate context even in dormant conversations — critical for "resume where left off"
4. **Configurable via user preferences** follows Agentium's existing `UserPreferenceService` pattern
5. **Celery Beat + idempotent task** matches existing background job architecture
6. **Token-aware compaction** (OpenAI) is complementary — our time-based pruning reduces DB size; sliding window handles token budget

---

## 3. Design

### 3.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Celery Beat (03:00 UTC daily)               │
│                         │                                       │
│                         ▼                                       │
│              ┌────────────────────┐                             │
│              │ prune_chat_history │                             │
│              │     Celery Task    │                             │
│              └────────┬───────────┘                             │
│                       │                                         │
│         ┌─────────────┼─────────────┐                           │
│         ▼             ▼             ▼                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                  │
│  │ Load prefs │ │ Find stale │ │ For each   │                  │
│  │ (retention,│ │ conversations│ │ conversation:│               │
│  │  retain_N, │ │ (last_msg >  │ │  1. Load   │                  │
│  │  hard_del) │ │  retention)  │ │  messages  │                  │
│  └────────────┘ └────────────┘ │  2. Split  │                  │
│                                │     recent │                  │
│                                │     vs old │                  │
│                                │  3. Soft-del│                 │
│                                │     old    │                  │
│                                │  4. Hard-del│                 │
│                                │     >30d   │                  │
│                                └────────────┘                  │
│                       │                                         │
│                       ▼                                         │
│              ┌────────────────┐                                 │
│              │ Audit Log +    │                                 │
│              │ Stats Emit     │                                 │
│              └────────────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 User Preferences (New Keys)

Added to `UserPreferenceService.DEFAULT_PREFERENCES`:

| Key | Default | Type | Description |
|-----|---------|------|-------------|
| `chat.prune_enabled` | `true` | boolean | Master toggle |
| `chat.prune_retention_days` | `7` | integer | Days of inactivity before soft-delete |
| `chat.prune_hard_delete_days` | `30` | integer | Days after soft-delete before hard-delete |
| `chat.prune_retain_count` | `10` | integer | Always keep last N messages per conversation |
| `chat.prune_schedule_cron` | `"0 3 * * *"` | string | Celery Beat cron (UTC) |

> **Note**: Preferences are **global defaults** (user_id=NULL). Per-user overrides supported via `UserPreferenceService` scope mechanism.

### 3.3 Core Algorithm: `ChatPruneService.prune_conversation()`

```python
def prune_conversation(
    self,
    conversation_id: str,
    retention_days: int = 7,
    hard_delete_days: int = 30,
    retain_count: int = 10,
) -> PruneStats:
    """
    Prune a single conversation.
    
    Returns: PruneStats(soft_deleted, hard_deleted, retained, conversation_id)
    """
    now = datetime.utcnow()
    soft_cutoff = now - timedelta(days=retention_days)
    hard_cutoff = now - timedelta(days=hard_delete_days)
    
    # Load ALL messages for this conversation (oldest first)
    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    if len(messages) <= retain_count:
        return PruneStats(0, 0, len(messages), conversation_id)
    
    # Split: recent (last N) vs old (everything before)
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
            db.delete(msg)  # Hard delete
            hard_deleted += 1
    
    db.commit()
    return PruneStats(soft_deleted, hard_deleted, len(recent), conversation_id)
```

**Invariants**:
- Last `retain_count` messages **never** soft-deleted (regardless of age)
- Soft-deleted messages excluded from AI context automatically (existing `_load_raw` filter)
- `get_full_history` tool can still retrieve soft-deleted if explicitly requested
- Hard delete is permanent — no recovery

### 3.4 Conversation Selection

Only process conversations where:
```sql
last_message_at < (now - retention_days)
```
Uses `Conversation.last_message_at` index (`idx_conv_last_message`).

**Why not scan all conversations?**  
- Conversations with recent activity don't need pruning
- Index lookup is O(log N) vs full table scan
- Aligns with "inactivity" trigger semantics

### 3.5 Celery Task

**File**: `backend/tasks/chat_tasks.py`

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def prune_chat_history(self) -> PruneResult:
    """
    Daily chat history pruning task.
    
    Reads preferences, finds stale conversations, prunes each.
    Idempotent: safe to re-run.
    """
    db = SessionLocal()
    try:
        prefs = UserPreferenceService(db).get_preferences_dict(category='chat')
        
        if not prefs.get('chat.prune_enabled', True):
            return PruneResult(skipped=True, reason="disabled")
        
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
        AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.GOVERNANCE,
            actor_type="system",
            actor_id="CHAT_PRUNE_TASK",
            action="chat_history_pruned",
            after_state=stats.to_dict(),
        )
        
        return PruneResult(
            conversations_processed=stats.conversations_processed,
            total_soft_deleted=stats.total_soft_deleted,
            total_hard_deleted=stats.total_hard_deleted,
            total_retained=stats.total_retained,
        )
    except Exception as exc:
        logger.exception("Chat prune task failed")
        raise self.retry(exc=exc)
    finally:
        db.close()
```

### 3.6 Celery Beat Schedule

**File**: `backend/celery_beat_schedule.py`

```python
from celery.schedules import crontab

beat_schedule = {
    # ... existing schedules ...
    'prune-chat-history-daily': {
        'task': 'backend.tasks.chat_tasks.prune_chat_history',
        'schedule': crontab(hour=3, minute=0),  # 03:00 UTC daily
        'options': {'queue': 'maintenance'},
    },
}
```

> Schedule is **configurable via preference** `chat.prune_schedule_cron` — Beat schedule can be updated dynamically via `celery beat` restart or `app.conf.beat_schedule` update.

### 3.7 Admin API (Manual Trigger)

**File**: `backend/api/routes/admin_chat.py`

```python
@router.post("/admin/chat/prune", summary="Manually trigger chat history pruning")
async def prune_chat_history(
    dry_run: bool = Query(False, description="Return stats without deleting"),
    retention_days: int = Query(None, description="Override retention days"),
    hard_delete_days: int = Query(None, description="Override hard delete days"),
    retain_count: int = Query(None, description="Override retain count"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    service = ChatPruneService(db)
    if dry_run:
        stats = service.dry_run_prune(
            retention_days=retention_days,
            hard_delete_days=hard_delete_days,
            retain_count=retain_count,
        )
        return {"dry_run": True, **stats.to_dict()}
    
    stats = service.prune_all_conversations(
        retention_days=retention_days,
        hard_delete_days=hard_delete_days,
        retain_count=retain_count,
    )
    return stats.to_dict()
```

---

## 4. Data Model

### 4.1 Existing Schema (No Changes Needed)

```sql
-- chat_messages (already exists)
CREATE TABLE chat_messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    user_id         UUID REFERENCES users(id),
    role            VARCHAR(50) NOT NULL,
    content         TEXT NOT NULL,
    is_deleted      CHAR(1) DEFAULT 'N',  -- 'N' or 'Y'
    created_at      TIMESTAMP DEFAULT NOW(),
    -- indexes: idx_chat_user_created, idx_chat_conversation, idx_chat_role
);

-- conversations (already exists)
CREATE TABLE conversations (
    id              UUID PRIMARY KEY,
    user_id         UUID REFERENCES users(id),
    last_message_at TIMESTAMP DEFAULT NOW(),
    is_archived     CHAR(1) DEFAULT 'N',
    -- index: idx_conv_last_message (last_message_at)
);
```

### 4.2 New Preferences (Inserted via Migration)

```sql
INSERT INTO user_preferences (agentium_id, category, key, value_json, data_type, scope, description, is_editable_by_agents)
VALUES
    ('PREF0100', 'chat', 'prune_enabled', 'true', 'boolean', 'global', 'Enable auto-pruning of chat history', 'Y'),
    ('PREF0101', 'chat', 'prune_retention_days', '7', 'integer', 'global', 'Days of inactivity before soft-delete', 'Y'),
    ('PREF0102', 'chat', 'prune_hard_delete_days', '30', 'integer', 'global', 'Days after soft-delete before hard-delete', 'Y'),
    ('PREF0103', 'chat', 'prune_retain_count', '10', 'integer', 'global', 'Always retain last N messages per conversation', 'Y'),
    ('PREF0104', 'chat', 'prune_schedule_cron', '"0 3 * * *"', 'string', 'global', 'Celery Beat cron schedule (UTC)', 'N')
ON CONFLICT (agentium_id) DO NOTHING;
```

---

## 5. Integration Points

| Component | Integration | Notes |
|-----------|-------------|-------|
| `ChatContextBuilder._load_raw()` | **Zero changes** | Already filters `is_deleted == 'N'` |
| `get_full_history` tool | **Zero changes** | Can access soft-deleted if explicitly requested (no filter) |
| `summarize_history()` | **Zero changes** | Runs independently; summarizes full history including soft-deleted |
| `UserPreferenceService` | **Add 5 defaults** | Existing CRUD/agent-access works unchanged |
| Celery Beat | **Add schedule entry** | Uses existing `celery_beat_schedule.py` |
| Audit Log | **Log each run** | Existing `AuditLog.log()` pattern |
| Admin API | **New endpoint** | Follows existing admin route pattern |

---

## 6. Observability & Metrics

### 6.1 Structured Logs (per task run)

```json
{
  "task": "prune_chat_history",
  "timestamp": "2026-07-22T03:00:15Z",
  "conversations_processed": 142,
  "total_soft_deleted": 8934,
  "total_hard_deleted": 1205,
  "total_retained": 1420,
  "duration_ms": 2341,
  "preferences": {
    "retention_days": 7,
    "hard_delete_days": 30,
    "retain_count": 10
  }
}
```

### 6.2 Prometheus Metrics (if enabled)

| Metric | Type | Labels |
|--------|------|--------|
| `chat_prune_conversations_total` | Counter | `status` (processed/skipped/error) |
| `chat_prune_messages_soft_deleted_total` | Counter | — |
| `chat_prune_messages_hard_deleted_total` | Counter | — |
| `chat_prune_duration_seconds` | Histogram | — |

### 6.3 Audit Log Entry

```python
AuditLog.log(
    level=AuditLevel.INFO,
    category=AuditCategory.GOVERNANCE,
    actor_type="system",
    actor_id="CHAT_PRUNE_TASK",
    action="chat_history_pruned",
    description=f"Pruned {stats.conversations_processed} conversations",
    after_state=stats.to_dict(),
)
```

---

## 7. Testing Strategy

### 7.1 Unit Tests (`backend/tests/unit/test_chat_prune_service.py`)

| Test | Scenario |
|------|----------|
| `test_prune_conversation_below_retain_count` | 5 messages, retain=10 → no deletion |
| `test_prune_conversation_soft_delete_only` | 20 messages, 15 old → 5 retained, 10 soft-deleted |
| `test_prune_conversation_hard_delete` | Soft-deleted >30d → hard deleted |
| `test_prune_conversation_mixed` | Some soft-deleted, some not, some >30d |
| `test_prune_respects_preferences` | Override retention/hard_delete/retain via params |

### 7.2 Integration Tests (`backend/tests/integration/test_chat_prune_task.py`)

| Test | Scenario |
|------|----------|
| `test_daily_task_runs` | Celery task executes, updates DB, logs audit |
| `test_dry_run_admin_api` | Admin endpoint returns stats without deletion |
| `test_preference_override` | Admin API params override user preferences |
| `test_idempotency` | Running task twice produces same result |

### 7.3 Fixtures

```python
@pytest.fixture
def conversation_with_messages(db_session):
    """Create conversation with 25 messages spanning 40 days."""
    conv = Conversation(user_id=user.id)
    db_session.add(conv)
    db_session.flush()
    
    base = datetime.utcnow() - timedelta(days=40)
    for i in range(25):
        msg = ChatMessage(
            conversation_id=conv.id,
            user_id=user.id,
            role="sovereign" if i % 2 == 0 else "head_of_council",
            content=f"Message {i}",
            created_at=base + timedelta(days=i * 1.5),
        )
        db_session.add(msg)
    db_session.commit()
    return conv
```

---

## 8. Rollout Plan

| Phase | Action | Risk |
|-------|--------|------|
| 1 | Add preferences via Alembic migration | Low — additive only |
| 2 | Deploy `ChatPruneService` + task (disabled by default) | Low — `prune_enabled=false` default |
| 3 | Enable via admin panel → Settings → Chat → "Auto-prune history" | Medium — monitor first run |
| 4 | Verify metrics/logs for 1 week | Low |
| 5 | (Optional) Add Prometheus metrics + Grafana dashboard | Low |

**Rollback**: Flip `chat.prune_enabled` to `false` — no data loss (soft-deleted messages recoverable).

---

## 9. Open Questions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| Per-conversation vs per-user? | **Per conversation** | Matches `conversation_id` model; user mental model; granular control |
| Soft delete vs hard delete? | **Two-tier: soft (7d) → hard (30d)** | Recovery window; aligns with existing `is_deleted` column; PostgreSQL vacuum handles space reclamation |
| Retain count: configurable? | **Yes, default 10** | Matches sliding window; user-controllable via preferences |
| Trigger: time-based or token-based? | **Time-based (inactivity)** | Simpler; predictable; complements token-based sliding window |
| Celery Beat vs pg_cron? | **Celery Beat** | Consistent with existing architecture; Python logic; observable via Flower |

---

## 10. Appendix: Related Artifacts

| Artifact | Path |
|----------|------|
| ChatContextBuilder | `backend/services/chat_context.py` |
| ChatMessage model | `backend/models/entities/chat_message.py` |
| UserPreferenceService | `backend/services/user_preference_service.py` |
| Celery Beat schedule | `backend/celery_beat_schedule.py` |
| Chat prune task (new) | `backend/tasks/chat_tasks.py` |
| Chat prune service (new) | `backend/services/chat_prune_service.py` |
| Admin route (new) | `backend/api/routes/admin_chat.py` |
| Alembic migration (new) | `backend/alembic/versions/XXX_add_chat_prune_prefs.py` |
| Unit tests (new) | `backend/tests/unit/test_chat_prune_service.py` |
| Integration tests (new) | `backend/tests/integration/test_chat_prune_task.py` |

---

## 11. Spec Self-Review

| Check | Status | Notes |
|-------|--------|-------|
| No TBD/TODO placeholders | ✅ | All values specified |
| No internal contradictions | ✅ | Soft-delete aligns with existing `is_deleted` filter |
| Scope focused (single feature) | ✅ | Only chat history pruning |
| All requirements traceable to user answers | ✅ | Per-conversation, retain-10, soft-7d/hard-30d, Celery Beat |
| Ambiguities resolved | ✅ | Edge cases in algorithm (invariant: last N never soft-deleted) |
| Implementation-ready detail | ✅ | Code sketches, SQL, test cases provided |

---

**Next Step**: User review → if approved, invoke `writing-plans` skill for implementation plan.