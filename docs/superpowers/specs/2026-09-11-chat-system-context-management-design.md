# Chat System & Context Management — Design Specification

**Date**: 2026-09-11  
**Status**: Approved for Implementation  
**Scope**: Complete Section 9 of TODO.md verification backlog

---

## 1. Overview

The chat system enables real-time communication between the Sovereign (user) and the Head of Council (agent 00001). This design unifies the REST and WebSocket paths, adds multi-conversation support, enforces context window limits on both paths, and wires the clarification card loop.

**Current State**: All backend services and frontend components exist but have duplication (REST vs WebSocket) and missing conversation UI.

**Goal**: Single source of truth for chat logic, conversation-aware UX, and bounded context windows.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CHAT SYSTEM                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   REST API      │    │   WebSocket     │                    │
│  │  POST /chat/send│    │   /ws/chat      │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                              │
│           └──────────┬───────────┘                              │
│                      ▼                                          │
│           ┌─────────────────────┐                               │
│           │ ChatService.process_│                               │
│           │     _turn()         │  ← Single implementation      │
│           └──────────┬──────────┘                               │
│                      │                                          │
│         ┌───────────┼───────────┐                               │
│         ▼           ▼           ▼                               │
│  ┌────────────┐ ┌─────────┐ ┌──────────┐                        │
│  │ChatContext │ │Context  │ │ Decision │                        │
│  │Builder     │ │Manager  │ │ Engine   │                        │
│  └────────────┘ └─────────┘ └──────────┘                        │
│         │           │           │                               │
│         └───────────┼───────────┘                               │
│                     ▼                                           │
│          ┌─────────────────────┐                                │
│          │   Database          │                                │
│          │ (ChatMessage,       │                                │
│          │  Conversation,      │                                │
│          │  AuditLog)          │                                │
│          └─────────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Design

### 3.1 Unified Chat Service (`backend/services/chat_service.py`)

**New Method**: `ChatService.process_turn()`

```python
@staticmethod
async def process_turn(
    head: HeadOfCouncil,
    message: str,
    db: Session,
    *,
    stream: bool = False,
    on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    on_tool_start: Optional[Callable[[List[Dict], int], Awaitable[None]]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    extra_metadata: Optional[dict] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single entry point for both REST and WebSocket.
    
    Args:
        stream: If True, yields deltas via on_delta/on_tool_start.
                If False, returns complete response dict.
        conversation_id: Optional conversation to associate messages with.
    """
    # ... existing process_message logic, but:
    # - Accepts conversation_id for message persistence
    # - Returns AsyncGenerator if stream=True, else dict
    # - WebSocket and REST both call this
```

**Changes to Existing Methods**:
- `process_message()` → wraps `process_turn(stream=False)`
- `_stream_response()` in `chat.py` → wraps `process_turn(stream=True)`

**Key Unification Points**:
| Logic | Currently In | After |
|-------|--------------|-------|
| Model config fallback | Both | `process_turn` only |
| User message persistence | Both | `process_turn` only |
| Context building (ChatContextBuilder) | REST only | Both |
| `decide` tool injection | REST only | Both |
| Reincarnation check | Both | `process_turn` only |
| Background task creation | REST only | Both |
| Media interception | Both | `process_turn` only |
| Channel broadcast | Both | `process_turn` only |

---

### 3.2 Conversation Management

#### 3.2.1 Backend Endpoints (Already Exist — Activate Them)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/chat/conversations` | GET | List user's conversations with last message preview |
| `/api/v1/chat/conversations` | POST | Create new conversation (title optional) |
| `/api/v1/chat/conversations/{id}` | GET | Get conversation + paginated messages |
| `/api/v1/chat/conversations/{id}` | PATCH | Update title, archive status |
| `/api/v1/chat/conversations/{id}` | DELETE | Soft delete conversation |

#### 3.2.2 Message Association Logic

```python
# In process_turn(), when persisting messages:
if conversation_id is None and sovereign_user:
    # Auto-create or reuse "General" conversation
    conv = db.query(Conversation).filter(
        Conversation.user_id == sovereign_user.id,
        Conversation.title == "General",
        Conversation.is_deleted == "N"
    ).first()
    if not conv:
        conv = Conversation(user_id=sovereign_user.id, title="General")
        db.add(conv)
        db.flush()
    conversation_id = conv.id

# Attach to both user and agent messages
user_msg.conversation_id = conversation_id
agent_msg.conversation_id = conversation_id
conv.update_last_message_time()
```

#### 3.2.3 Migration on First Load

```python
# In loadChatHistory() or ChatPage mount:
# If messages exist but have no conversation_id, bulk-assign to "General"
if messages_without_conversation > 0:
    general_conv = get_or_create_general_conversation(user_id)
    bulk_update_conversation_id(messages, general_conv.id)
```

---

### 3.3 WebSocket Context Window Enforcement

**File**: `backend/api/routes/websocket.py`

**Location**: Inside `_run_generation()` before `ChatService.process_message()` call

```python
# ─── Add context window management ───
from backend.services.chat_context import (
    ChatContextBuilder, load_summary, format_summary_for_prompt,
    set_chat_request, clear_chat_request
)
from backend.services.user_preference_service import UserPreferenceService

# Get window size from user preference (default 10)
window_size = 10
if sovereign_user:
    try:
        pref_svc = UserPreferenceService(db)
        ws = pref_svc.get_value("chat.context_window_size", user_id=sovereign_user.id)
        if ws is not None:
            window_size = int(ws)
    except Exception:
        pass

# Build compacted history
summary_json = await load_summary(str(sovereign_user.id)) if sovereign_user else None
summary_text = format_summary_for_prompt(summary_json) if summary_json else ""

if sovereign_user:
    built = ChatContextBuilder(window_size=window_size).build(
        db, str(sovereign_user.id), summary=summary_json
    )
    history = built["history"]
    context_compressed = built["context_compressed"]
    raw_turn_count = built["raw_turn_count"]
    
    # Register for full-history tools
    set_chat_request(user_id=str(sovereign_user.id), db=db)
else:
    history = []
    context_compressed = False
    raw_turn_count = 0

# Inject summary into system prompt
if summary_text:
    full_prompt = f"{system_prompt}\n\n[Conversation summary — earlier turns compressed]\n{summary_text}\n\nCurrent System State:\n{context}"
else:
    full_prompt = f"{system_prompt}\n\nCurrent System State:\n{context}"

# Pass history to process_turn (new param)
response = await ChatService.process_turn(
    gen_head, enriched_message, gen_db,
    stream=True,
    on_delta=on_delta,
    on_tool_start=on_tool_start,
    cancel_event=cevent,
    extra_metadata=extra_metadata,
    history=history,  # NEW: pass compacted history
)
clear_chat_request()
```

**Note**: `ChatService.process_turn()` needs a new optional `history` parameter to accept pre-built context.

---

### 3.4 Clarification Card Integration

#### 3.4.1 Backend: Emit Card on Clarification Request

In `ChatService.process_turn()`, when agent calls `clarification` tool or uncertainty detector triggers:

```python
# After getting result from LLM:
if result.get("metadata", {}).get("card"):
    card_payload = result["metadata"]["card"]
    # Persist card message
    card_msg = ChatMessageEntity.create_agent_message(
        user_id=user_id,
        content=card_payload.get("title", "Clarification needed"),
        agent_id=head.agentium_id,
        conversation_id=conversation_id,
        metadata={"card": card_payload, "agent_id": head.agentium_id}
    )
    db.add(card_msg)
    db.commit()
    
    # Emit via WebSocket (if streaming)
    if stream and on_delta:
        await ws_manager.broadcast({
            "type": "message",
            "role": "head_of_council",
            "message": card_msg.to_dict(),
            "metadata": {"card": card_payload},
        })
```

#### 3.4.2 Frontend: Render Card in Chat

**File**: `frontend/src/pages/ChatPage.tsx` (message render loop)

```tsx
// In message list rendering:
{message.metadata?.card && (
    <StructuredInputCard
        card={message.metadata.card}
        onSubmit={(answer) => {
            // Send card_response via WebSocket
            sendWsMessage('', [], { card_response: answer });
        }}
        onDismiss={() => {
            useChatStore.getState().dismissCard(message.metadata.card.id);
        }}
    />
)}
```

#### 3.4.3 Frontend: Handle Card Response

**File**: `frontend/src/pages/ChatPage.tsx` → `handleSubmit`

```tsx
// If active card exists, send as card_response instead of new message
const activeCardId = useChatStore.getState().activeCardId;
if (activeCardId && input.trim()) {
    sendWsMessage('', [], { card_response: { card_id: activeCardId, answer: input.trim() } });
    setInput('');
    return;
}
```

---

### 3.5 Token Usage Transparency

#### 3.5.1 Backend: Include Metadata in Response

Already implemented — `process_message` returns:
```python
{
    "context_compressed": True,
    "raw_turn_count": 47,
    "estimated_tokens": 12500,
    ...
}
```

#### 3.5.2 Frontend: Display Badge

**File**: `frontend/src/pages/ChatPage.tsx` (message bubble for agent messages)

```tsx
{message.metadata?.context_compressed && (
    <Tooltip content={`Context compressed: ${message.metadata.raw_turn_count} earlier turns summarized (~${message.metadata.estimated_tokens} tokens saved)`}>
        <Badge className="ml-2 px-2 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
            ⚡ Compressed
        </Badge>
    </Tooltip>
)}

{message.metadata?.context_compressed && (
    <Button 
        variant="ghost" 
        size="sm" 
        className="ml-1 p-1"
        onClick={() => {
            // Call get_full_history tool via WebSocket
            sendWsMessage('', [], { tool_call: { name: 'get_full_history', arguments: { limit: 100 }}});
        }}
    >
        <History className="w-3.5 h-3.5" />
        <span className="ml-1 text-xs">View full</span>
    </Button>
)}
```

---

### 3.6 Frontend Conversation Sidebar

#### 3.6.1 State in `chatStore.ts`

```typescript
interface ChatState {
    // ... existing
    conversations: Conversation[];
    activeConversationId: string | null;
    setConversations: (convs: Conversation[]) => void;
    setActiveConversation: (id: string | null) => void;
    createConversation: (title?: string) => Promise<Conversation>;
    loadConversations: () => Promise<void>;
}
```

#### 3.6.2 UI Layout (AI Tab)

```
┌─────────────────────────────────────────────────────────────┐
│  Header: [Crown] Head of Council  ● Connected   [New Chat] │
├──────────────┬──────────────────────────────────────────────┤
│ Conversations│                                              │
│ ──────────── │            Chat Messages                     │
│ 📝 General   │  ┌────────────────────────────────────────┐  │
│ 📝 Research  │  │  Sovereign: Hello                      │  │
│ 📝 Coding    │  │  Head: Hi there!                       │  │
│ ➕ New Chat  │  │  ⚡ Compressed [View full]             │  │
│              │  │  ────────────────────────────────────  │  │
│              │  │  Sovereign: [file]                     │  │
│              │  │  Head: Analyzed...                     │  │
│              │  └────────────────────────────────────────┘  │
│              │  ┌────────────────────────────────────────┐  │
│              │  │  [Input] [📎] [🎤] [Send]  [Stop]      │  │
│              │  └────────────────────────────────────────┘  │
└──────────────┴──────────────────────────────────────────────┘
```

#### 3.6.3 Conversation Switching

```typescript
// On conversation click:
const switchConversation = async (conversationId: string) => {
    setActiveConversation(conversationId);
    const history = await chatApi.getConversationMessages(conversationId);
    setMessages(formatHistory(history));
    // Scroll to bottom
};
```

---

## 4. API Contracts

### 4.1 REST Endpoints (No Changes — Activate Existing)

| Endpoint | Request | Response |
|----------|---------|----------|
| `POST /chat/send` | `{ message, stream?, attachments?, card_response?, conversation_id? }` | Streaming SSE or `{ response, agent_id, task_created, task_id }` |
| `GET /chat/conversations` | `?include_archived=` | `{ conversations: [...], total }` |
| `POST /chat/conversations` | `{ title?, context? }` | Conversation |
| `GET /chat/conversations/{id}` | `?include_messages=&limit=&offset=` | Conversation + messages |
| `PATCH /chat/conversations/{id}` | `{ title?, is_archived? }` | Conversation |
| `DELETE /chat/conversations/{id}` | — | `{ success: true }` |

### 4.2 WebSocket Frames (No Changes — Use Existing)

**Client → Server**:
```json
{ "type": "message", "content": "hello", "attachments": [...], "card_response": {...} }
{ "type": "cancel", "stream_id": "uuid" }
{ "type": "ping" }
```

**Server → Client**:
```json
{ "type": "message_start", "stream_id": "uuid", "role": "head_of_council", "thinking": true }
{ "type": "message_delta", "stream_id": "uuid", "delta": "token" }
{ "type": "tool_progress", "stream_id": "uuid", "tool_count": 2 }
{ "type": "message_end", "stream_id": "uuid", "content": "...", "metadata": {...} }
{ "type": "message", "role": "head_of_council", "content": "...", "metadata": { "card": {...} } }
```

---

## 5. Data Model Changes

### 5.1 ChatMessage — No Schema Changes

Existing fields sufficient:
- `conversation_id` (nullable FK) — now populated
- `message_metadata` — carries `card`, `context_compressed`, `raw_turn_count`, `estimated_tokens`
- `attachments` — stores file metadata

### 5.2 Conversation — No Schema Changes

Existing fields sufficient:
- `title`, `context`, `is_archived`, `is_deleted`
- `last_message_at` — updated on each message

### 5.3 New Index (Optional, for Performance)

```sql
-- Add to migration if not exists
CREATE INDEX idx_chat_conversation_user ON chat_messages (conversation_id, user_id, created_at);
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| No model config | Return structured error (already implemented) |
| Context window exceeded | Reincarnation triggered (already implemented) |
| WebSocket disconnect mid-stream | Generation completes in background; message persisted; client reloads from history on reconnect |
| Conversation not found | 404; frontend falls back to "General" |
| Card response for expired card | Ignored; user notified via toast |

---

## 7. Testing Requirements

### 7.1 Unit Tests
- `ChatService.process_turn()` with `stream=True/False`
- `ChatContextBuilder` windowing + pinning + truncation
- Conversation CRUD via API

### 7.2 Integration Tests
- REST `/chat/send` → message persisted with `conversation_id`
- WebSocket `/ws/chat` → streaming deltas + `message_end` with metadata
- Conversation switch → history loads correctly
- Clarification card → user responds → incorporated into next turn

### 7.3 E2E Scenarios
1. New user → "General" conversation created → messages persist
2. User creates "Research" conversation → switches back → history preserved
3. Long conversation (>20 turns) → summary injected → token badge shown
4. Agent requests clarification → card renders → user answers → agent continues
5. Context critical → reincarnation → successor receives wisdom

---

## 8. Implementation Plan

| Phase | Tasks | Files | Estimate |
|-------|-------|-------|----------|
| **1. Unify Service** | Extract `process_turn()`; refactor `process_message()` and `_stream_response()` to call it | `chat_service.py`, `chat.py` | 3h |
| **2. WebSocket Context** | Add `ChatContextBuilder` call in `_run_generation()`; pass `history` to `process_turn()` | `websocket.py`, `chat_service.py` | 1h |
| **3. Conversation Backend** | Verify endpoints work; add `conversation_id` to message persistence | `chat.py` | 1h |
| **4. Conversation Frontend** | Add sidebar, state, switching logic to `ChatPage.tsx` and `chatStore.ts` | `ChatPage.tsx`, `chatStore.ts` | 3h |
| **5. Clarification UI** | Render `StructuredInputCard` when `metadata.card` present; handle `card_response` | `ChatPage.tsx` | 2h |
| **6. Token Badge** | Add compressed badge + "View full" button to agent message bubble | `ChatPage.tsx` | 1h |
| **7. Migration** | Bulk-assign existing messages to "General" on first load | `ChatPage.tsx` (effect) | 0.5h |
| **8. Tests** | Unit + integration for unified path, conversations, clarification | `test_chat_service.py`, `test_chat_api.py` | 3h |

**Total**: ~14.5 hours

---

## 9. Acceptance Criteria

| ID | Criterion | Verified By |
|----|-----------|-------------|
| 9.1 | REST `/chat/send` and WebSocket `/ws/chat` produce identical results for same input | Integration test |
| 9.2 | Conversation list loads, new conversation creates, switching preserves history | E2E test |
| 9.3 | WebSocket streaming respects `window_size` (last N turns + pinned first + summary) | Unit test |
| 9.4 | Clarification card renders, user response sent as `card_response`, agent receives it | E2E test |
| 9.5 | Token badge appears when `context_compressed=true` | Visual verification |
| 9.6 | Existing messages migrated to "General" conversation on first load | Manual test |
| 9.7 | Reincarnation still triggers at 90% context usage | Existing test |
| 9.8 | All Section 9 TODO items marked `[x]` | Checklist |

---

## 10. Rollback Plan

If issues arise:
1. **Feature flag**: `CHAT_UNIFIED_SERVICE=false` reverts to old `process_message`/`_stream_response`
2. **Conversation UI**: Hide sidebar via `SHOW_CONVERSATIONS=false` env var
3. **WebSocket context**: Disable with `WS_CONTEXT_WINDOW=false`

All changes are additive; no breaking schema changes.

---

## 11. Future Enhancements (Out of Scope)

- Message edit/delete (P3)
- Conversation search/filter
- Shared conversations (multi-user)
- Export conversation (PDF/Markdown)
- Conversation-level model config override
- Voice conversation history separate from text

---

**Approval**: ✅ Ready for implementation. Invoke `writing-plans` skill to create task breakdown.