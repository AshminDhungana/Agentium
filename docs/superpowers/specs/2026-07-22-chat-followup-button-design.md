# Chat Follow-up Button

Populate the compose box with a message's content for editing and resending.

## Scope

Add a **PenLine** icon button in the hover action bar on every chat message (user + AI). Clicking it copies the message text into the compose textarea and focuses it for immediate editing.

## Design

### Button placement

Inside the existing hover action `<div>` (ChatPage.tsx ~line 1208), immediately after the Copy button, before the Speak conditional. Same visual treatment: `p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-600 dark:text-gray-500 transition-colors`.

Hidden for card messages via the existing `!message.metadata?.card` guard.

### Handler — `followUpMessage`

```tsx
const followUpMessage = (content: string, ref: React.RefObject<HTMLTextAreaElement | null>) => {
    setInput(content);
    ref.current?.focus();
    ref.current?.setSelectionRange(content.length, content.length);
};
```

- `setInput` populates the textarea state
- `.focus()` activates the compose box
- `setSelectionRange` places cursor at end so the user can append

No toast, no scroll — the user is already looking at the message.

### Icon

`PenLine` from `lucide-react`, imported alongside existing icons.

## Edge cases

| Case | Behavior |
|------|----------|
| Streaming message | Populates whatever content has arrived — same risk as copy. Acceptable. |
| Empty content | `setInput('')` → focused textarea, harmless no-op. |
| Card message | Action div hidden by existing guard; button excluded automatically. |
| Very long content | Auto-resize effect handles up to 150px, internal scroll beyond. |
| Own message | Works identically to AI messages. |

## Files changed

- `frontend/src/pages/ChatPage.tsx` — import `PenLine`, add button JSX, add handler function

## Testing

Manual: click button on AI message → text in compose, cursor at end. Click on own message → same. Card message → no button. Hover out → hides.
