# Chat Follow-up Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PenLine follow-up button to each chat message that populates the compose box for editing and resending.

**Architecture:** Single button in the existing hover-action bar on every message (user + AI). On click, `setInput(content)` + focus the textarea with cursor at end.

**Tech Stack:** React 18, TypeScript, lucide-react, Zustand

## Global Constraints

- Icon must be `PenLine` from `lucide-react`
- Button identical styling to Copy button: `p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-600 dark:text-gray-500 transition-colors`
- Hidden for card messages (existing `!message.metadata?.card` guard)
- Hover-only visibility (existing `opacity-0 group-hover:opacity-100`)
- No toast, no scroll on click

---

### Task 1: Add follow-up button to ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx` (import + handler + JSX)

**Interfaces:**
- Consumes: `setInput`, `textareaRef` (already exist in `ChatPage`)
- Produces: `<PenLine />` button in hover-action bar, `followUpMessage` handler

- [ ] **Step 1: Import PenLine**

In `frontend/src/pages/ChatPage.tsx`, add `PenLine` to the `lucide-react` import block (line 21-28).

Change:
```tsx
import {
    Send, Crown, User, UserRoundSearch, AlertCircle, Wifi, WifiOff, CheckCircle,
    RefreshCw, Paperclip, Image as ImageIcon, File, X, Mic, MicOff, Pause, Square,
    Download, Copy, Sparkles, Code, FileText, Video, Music, Archive,
    Maximize2, MoreHorizontal, Smile, Plus, MessageCircle, Smartphone,
    Slack, Mail, Inbox, Volume2, VolumeX, Settings2, ChevronDown, Globe,
    FolderOpen, Trash2, Eye, UploadCloud, HardDrive, Search, Filter,
} from 'lucide-react';
```

To:
```tsx
import {
    Send, Crown, User, UserRoundSearch, AlertCircle, Wifi, WifiOff, CheckCircle,
    RefreshCw, Paperclip, Image as ImageIcon, File, X, Mic, MicOff, Pause, Square,
    Download, Copy, PenLine, Sparkles, Code, FileText, Video, Music, Archive,
    Maximize2, MoreHorizontal, Smile, Plus, MessageCircle, Smartphone,
    Slack, Mail, Inbox, Volume2, VolumeX, Settings2, ChevronDown, Globe,
    FolderOpen, Trash2, Eye, UploadCloud, HardDrive, Search, Filter,
} from 'lucide-react';
```

- [ ] **Step 2: Add followUpMessage handler**

After `copyMessage` (line 721), add:

```tsx
const followUpMessage = (content: string, ref: React.RefObject<HTMLTextAreaElement | null>) => {
    setInput(content);
    ref.current?.focus();
    ref.current?.setSelectionRange(content.length, content.length);
};
```

- [ ] **Step 3: Add PenLine button JSX**

In the hover-action `<div>` (line 1208), add the follow-up button after the Copy button:

```tsx
<div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
    <button onClick={() => copyMessage(message.content)}
        className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-600 dark:text-gray-500 transition-colors" title="Copy" aria-label="Copy">
        <Copy className="w-3 h-3" />
    </button>
    <button onClick={() => followUpMessage(message.content, textareaRef)}
        className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-600 dark:text-gray-500 transition-colors" title="Follow up" aria-label="Follow up">
        <PenLine className="w-3 h-3" />
    </button>
    {!isUser && voiceAvailable && (
        <button onClick={() => handleSpeakMessage(message.id, message.content)}
            className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-600 dark:text-gray-500 transition-colors" title="Read aloud" aria-label="Read aloud">
            {isSpeaking === message.id ? <VolumeX className="w-3 h-3" /> : <Volume2 className="w-3 h-3" />}
        </button>
    )}
</div>
```

- [ ] **Step 4: Build and verify**

Run: `npx tsc --noEmit` in `frontend/`
Expected: No TypeScript errors.

Run: `npm run build` in `frontend/`
Expected: Build succeeds.

- [ ] **Step 5: Manual smoke test**

1. `make up` and open the dashboard
2. Hover over any AI message → PenLine icon appears in the footer row
3. Click it → message text populates the compose box, cursor at end
4. Type additional text → Enter → message sends with original + additions
5. Hover over any user message → PenLine also appears
6. Hover over a card message → PenLine does not appear
7. Hover out → button hides

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat: add follow-up button to chat messages"
```
