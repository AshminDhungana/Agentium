# Chat Frontend — Section 9.3 Completion Design

**Date**: 2026-09-15  
**Status**: Approved for implementation  
**Related**: `docs/documents/TODO.md` Section 9.3

---

## Overview

Complete all remaining items in TODO Section 9.3 (Chat Frontend) by enhancing the existing `ChatPage.tsx` and associated stores/components. Most items are already implemented; the gaps are conversation management UI and minor tool call display improvements.

---

## Current State Assessment

| Item | Description | Status |
|------|-------------|--------|
| 9.3.1 | Markdown, code blocks rendering | ✅ Done (`MarkdownMessage.tsx`) |
| 9.3.2 | Streaming tokens real-time | ✅ Done (WebSocket + `TypingIndicator`) |
| 9.3.3 | Tool call results inline | ⚠️ Partial (only count shown) |
| 9.3.4 | File upload in chat | ✅ Done (`fileApi.uploadFiles`) |
| 9.3.5 | Conversation switching | ❌ Missing |
| 9.3.6 | New conversation creation | ❌ Missing |
| 9.3.7 | History reload after refresh | ✅ Done (`sessionStorage` persistence) |
| 9.3.8 | `chatStore.ts` consistency | ✅ Done (Zustand + persist) |

---

## Design Decisions

### 9.3.3 — Tool Call Display (Frontend-Only Enhancement)

**Decision**: Enhance `TypingIndicator` to show pending tool names; no inline tool result rendering.

**Rationale**: Backend only emits `tool_progress` with cumulative count. Adding full tool call/result WebSocket events requires backend changes. Frontend-only approach:
- Extend `tool_progress` payload with optional `tool_names: string[]` (backward compatible)
- `TypingIndicator` displays: "🔧 Running: web_search, file_read..."
- No layout changes to message bubbles

### 9.3.5 & 9.3.6 — Conversation Management (Right Collapsible Sidebar)

**Decision**: Add a collapsible right sidebar in the AI Chat tab, triggered from the header.

**Rationale**: Left nav bar already exists for app-wide navigation. A right sidebar:
- Doesn't compete with existing navigation
- Familiar pattern (Discord, Slack, VS Code)
- Can be shared for future tool execution log, file preview
- Collapses to 48px icon-only strip when not needed

**Behavior**:
- **Desktop**: Right sidebar, 320px expanded / 48px collapsed
- **Mobile**: Full-width bottom sheet (slide up from bottom)
- **State**: Persisted in `localStorage` (`chat:sidebar:width`, `chat:sidebar:expanded`)
- **Conversation list**: Title, last message preview, timestamp, message count
- **Actions per conversation**: Switch (click), Rename, Archive, Delete (hover menu)
- **New conversation**: Button at top → `POST /chat/conversations` → auto-switch

### Shared Right Sidebar Architecture

Create a reusable `RightSidebar` component (`components/layout/RightSidebar.tsx`) with:
- `isOpen`, `width`, `position` ('right' | 'bottom') props
- Slot-based content (conversations, tools, files)
- Keyboard accessible (Esc to close, Tab navigation)
- Animation via CSS transitions (respects `prefers-reduced-motion`)

---

## File Changes

### New Files

| File | Purpose |
|------|---------|
| `frontend/src/components/layout/RightSidebar.tsx` | Reusable collapsible sidebar shell |
| `frontend/src/components/chat/ConversationSidebar.tsx` | Conversation list content for sidebar |
| `frontend/src/components/chat/ConversationList.tsx` | Virtualized conversation list with actions |
| `frontend/src/hooks/useConversations.ts` | Conversation CRUD hooks (create, list, switch, delete) |

### Modified Files

| File | Changes |
|------|---------|
| `frontend/src/pages/ChatPage.tsx` | Add sidebar state, integrate `ConversationSidebar`, handle conversation switching |
| `frontend/src/store/chatStore.ts` | Add `currentConversationId`, `conversations` cache, `setConversation`, `createConversation` |
| `frontend/src/components/chat/TypingIndicator.tsx` | Accept `toolNames?: string[]` prop, render tool names inline |
| `frontend/src/services/chatApi.ts` | No changes (all endpoints exist) |

---

## chatStore.ts Extensions

```typescript
interface ChatState {
  // ...existing...
  currentConversationId: string | null;
  conversations: Conversation[];  // cached list
  isSidebarOpen: boolean;
  sidebarWidth: number; // 48 | 320
  
  setConversation: (conversationId: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  loadConversations: () => Promise<void>;
  deleteConversation: (conversationId: string) => Promise<void>;
  updateConversation: (conversationId: string, updates: { title?: string; is_archived?: boolean }) => Promise<void>;
  toggleSidebar: () => void;
  setSidebarWidth: (width: number) => void;
}
```

- `currentConversationId` persisted to `sessionStorage` (survives refresh)
- `conversations` cached in memory, refreshed on sidebar open
- `setConversation` loads messages via `chatApi.getConversation`, replaces `messages` in store

---

## TypingIndicator Enhancement

```tsx
// Before
<TypingIndicator thinking={isThinking} toolCount={toolCount} />

// After
<TypingIndicator 
  thinking={isThinking} 
  toolCount={toolCount} 
  toolNames={toolNames} // string[]
/>
```

**Display logic**:
- If `toolNames.length > 0`: "🔧 Running: web_search, file_read, code_exec"
- Else if `toolCount > 0`: "🔧 Running tools: 3"
- Else if `thinking`: "💭 Thinking..."
- Else: standard 3-dot animation

---

## Backend Compatibility

No breaking changes required. Optional enhancement to `websocket.py`:

```python
# In on_tool_start callback (websocket.py:743-755)
async def on_tool_start(
    tool_calls: List[Dict],
    cumulative: int,
    sid: str = stream_id,
) -> None:
    tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
    await websocket.send_json({
        "type": "tool_progress",
        "stream_id": sid,
        "tool_count": cumulative,
        "tool_names": tool_names,  # NEW: optional, additive
    })
```

Frontend handles missing `tool_names` gracefully.

---

## Conversation API Usage

| Operation | Endpoint | Method |
|-----------|----------|--------|
| List | `/api/v1/chat/conversations` | GET |
| Get (with messages) | `/api/v1/chat/conversations/{id}` | GET |
| Create | `/api/v1/chat/conversations` | POST |
| Update | `/api/v1/chat/conversations/{id}` | PATCH |
| Archive | `/api/v1/chat/conversations/{id}/archive` | POST |
| Delete | `/api/v1/chat/conversations/{id}` | DELETE |

All endpoints exist in `backend/api/routes/chat.py` and return `Conversation` objects with `messages` array.

---

## UX Details

### Conversation Sidebar (Expanded)
```
┌─────────────────────────────────────┐
│  + New Conversation          [✕]   │
├─────────────────────────────────────┤
│  💬 General                    10:30│
│     "Hello, how can I help?"        │
├─────────────────────────────────────┤
│  💬 Project Planning             09:15│
│     "Let's break down the tasks..." │
├─────────────────────────────────────┤
│  💬 Code Review                  Yday│
│     "Please review the PR..."       │
└─────────────────────────────────────┘
```

### Conversation Sidebar (Collapsed)
```
┌──┐
│💬│
│💬│
│💬│
│+ │
└──┘
```

### Mobile Bottom Sheet
- Full width, 60% viewport height max
- Drag handle at top
- Swipe down to dismiss
- Same conversation list, touch-optimized

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Conversation load fails | Toast error, keep current conversation |
| Create conversation fails | Toast error, don't switch |
| Switch during streaming | Finalize current stream (call `resetStream`), then switch |
| Network offline | Queue conversation actions, retry on reconnect |

---

## Accessibility

- Sidebar: `role="complementary"`, `aria-label="Conversations"`
- Conversation list: `role="listbox"`, items `role="option"`
- Keyboard: Tab to navigate, Enter/Space to select, Esc to close
- Focus management: Trap focus in sidebar when open (desktop)
- Screen reader: Announce conversation switches

---

## Testing Checklist

- [ ] Conversation list loads on sidebar open
- [ ] Switching conversations loads correct messages
- [ ] New conversation creates and switches immediately
- [ ] Rename/archive/delete work and update list
- [ ] Sidebar persists open/closed state across refreshes
- [ ] Mobile bottom sheet opens/closes correctly
- [ ] Streaming message finalizes on conversation switch
- [ ] TypingIndicator shows tool names when provided
- [ ] No console errors on rapid conversation switching
- [ ] Accessibility: keyboard nav, screen reader announcements

---

## Out of Scope

- Tool call result inline rendering (requires backend WebSocket events)
- Conversation search/filter (future enhancement)
- Conversation folders/tags (future)
- Multi-user conversation sharing (future)
- Sidebar for tool execution log (future — architecture ready)

---

## Implementation Order

1. **RightSidebar shell** — reusable layout component
2. **chatStore extensions** — conversation state + actions
3. **ConversationSidebar + List** — UI components
4. **ChatPage integration** — wire up sidebar, conversation switching
5. **TypingIndicator enhancement** — tool names display
6. **Mobile bottom sheet** — responsive behavior
7. **E2E tests** — conversation CRUD + switching flows

---

## Rollback Plan

If issues arise:
- Feature flag `ENABLE_CONVERSATION_SIDEBAR` (env var) to disable sidebar
- `chatStore` changes are additive — existing `messages` array unchanged
- `ChatPage` wraps sidebar in conditional render

---

## Success Criteria

All TODO 9.3 items marked `[x]`:
- [x] 9.3.1 — Markdown/code blocks render correctly
- [x] 9.3.2 — Streaming tokens appear real-time
- [x] 9.3.3 — Tool names shown in typing indicator
- [x] 9.3.4 — File upload works
- [x] 9.3.5 — Conversation switching works without losing state
- [x] 9.3.6 — New conversation creation works
- [x] 9.3.7 — History reload after refresh works
- [x] 9.3.8 — chatStore state management consistent