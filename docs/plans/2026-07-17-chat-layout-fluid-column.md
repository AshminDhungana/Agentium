# Chat Layout: Fluid Column with Readable Measure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the chat column so it scales fluidly with the viewport (centered against the space right of the sidebar), bubbles widen gracefully, and long assistant prose stays readable — instead of a frozen 768px strip on wide screens.

**Architecture:** Replace the two frozen `max-w-3xl mx-auto` blocks (message column + input bar) in `ChatPage.tsx` with a single container-relative width token (`--chat-col: clamp(560px, 92%, 940px)`) applied to both so they always align. Cap bubble width at `min(88%, var(--chat-col))` and inner prose at `68ch` for readability. No changes to `MainLayout`/`Sidebar` (sidebar is already a real flex track).

**Tech Stack:** React 18 + TypeScript, Tailwind CSS (JIT, arbitrary values supported), Vite. Single file touched: `frontend/src/pages/ChatPage.tsx`. No new dependencies.

## Global Constraints

- Width token must be container-relative (`92%` of the ChatPage flex region), NOT viewport units (`vw`/`vh`), to stay correct under any sidebar state and avoid layout shift.
- Prose readability cap: text content limited to ~65–75ch (use `68ch`).
- Keep role-colored avatar bubbles and existing dark-mode tokens unchanged.
- No changes to `MainLayout.tsx` or `Sidebar.tsx`.
- Adaptive gutters: `px-4 md:px-8 xl:px-12` on the scroll container.
- Verify at 1366px / 1920px / 2560px: column scales 560→940px, input aligns to messages, assistant prose ≤ ~68ch, no horizontal overflow, dark-mode contrast intact.

---

### Task 1: Add the `--chat-col` width token to the ChatPage root

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:911` (the `h-full ... flex flex-col` root div)

**Interfaces:**
- Consumes: nothing external.
- Produces: the CSS custom property `--chat-col` on the ChatPage root, consumed by Tasks 2–4 via `var(--chat-col)`.

- [ ] **Step 1: Locate the root wrapper**

The render returns at line 911:
```tsx
<div className="h-full bg-gray-50 dark:bg-[#0f1117] flex flex-col overflow-hidden transition-colors duration-200">
```

- [ ] **Step 2: Add the inline CSS variable**

Change it to:
```tsx
<div
    className="h-full bg-gray-50 dark:bg-[#0f1117] flex flex-col overflow-hidden transition-colors duration-200"
    style={{ ['--chat-col' as any]: 'clamp(560px, 92%, 940px)' }}
>
```
(Keep the two child `div` wrappers that follow it unchanged.)

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: No new TypeScript errors referencing `ChatPage.tsx` (the `as any` cast avoids a CSSProperties index error).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(chat): add --chat-col fluid width token to ChatPage root"
```

---

### Task 2: Make the message column fluid and aligned

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1046-1047` (scroll container padding + inner column)

**Interfaces:**
- Consumes: `--chat-col` from Task 1.
- Produces: fluid, centered message column used by all rendered messages.

- [ ] **Step 1: Update scroll container padding (adaptive gutters)**

At line 1046, change:
```tsx
className="h-full overflow-y-auto px-4 py-6"
```
to:
```tsx
className="h-full overflow-y-auto px-4 md:px-8 xl:px-12 py-6"
```

- [ ] **Step 2: Replace the frozen column max-width**

At line 1047, change:
```tsx
<div className="max-w-3xl mx-auto space-y-6">
```
to:
```tsx
<div className="mx-auto w-full space-y-6" style={{ maxWidth: 'var(--chat-col)' }}>
```

- [ ] **Step 3: Verify it compiles and renders**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: No new errors. (Visual confirmation happens in Task 5.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(chat): fluid message column with adaptive gutters"
```

---

### Task 3: Make the input bar fluid and aligned to the column

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1165` (input bar wrapper)

**Interfaces:**
- Consumes: `--chat-col` from Task 1.
- Produces: input bar that always aligns exactly with the message column from Task 2.

- [ ] **Step 1: Replace the frozen input max-width**

At line 1165, change:
```tsx
<div className="max-w-3xl mx-auto">
```
to:
```tsx
<div className="mx-auto w-full" style={{ maxWidth: 'var(--chat-col)' }}>
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(chat): fluid input bar aligned to message column"
```

---

### Task 4: Widen bubbles and cap prose readability

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1085` (bubble flex container)
- Modify: `frontend/src/pages/ChatPage.tsx:1092` (bubble inner `div`)

**Interfaces:**
- Consumes: `--chat-col` from Task 1.
- Produces: bubbles that widen with the column but never overflow it; inner prose capped at 68ch.

- [ ] **Step 1: Widen the bubble container cap**

At line 1085, change:
```tsx
<div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
```
to:
```tsx
<div className={`flex flex-col max-w-[min(88%,var(--chat-col))] ${isUser ? 'items-end' : 'items-start'}`}>
```

- [ ] **Step 2: Cap inner prose at 68ch**

At line 1092, the bubble inner div currently is:
```tsx
<div className={`px-4 py-3 rounded-2xl ${isUser ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/40'
        : isError ? 'bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 text-orange-900 dark:text-orange-300'
            : message.role === 'system' ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-900 dark:text-red-300'
                : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]'
    }`}>
```
Add `max-w-[68ch]` as the first class inside the template literal:
```tsx
<div className={`max-w-[68ch] px-4 py-3 rounded-2xl ${isUser ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/40'
        : isError ? 'bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 text-orange-900 dark:text-orange-300'
            : message.role === 'system' ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-900 dark:text-red-300'
                : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]'
    }`}>
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: No new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat(chat): widen bubbles and cap prose at 68ch"
```

---

### Task 5: Visual verification across breakpoints

**Files:**
- None (verification only). Uses `frontend/src/pages/ChatPage.tsx` from Tasks 1–4.

**Interfaces:**
- Consumes: the full set of changes from Tasks 1–4.
- Produces: confirmation that the layout holds at target widths; fixes if attachments are over-constrained.

- [ ] **Step 1: Start the frontend dev server**

Run: `cd frontend && npm run dev`
(Use the project's documented dev command; open the served URL, log in, and open the Chat page.)

- [ ] **Step 2: Verify at 1366px**

Resize viewport / devtools to 1366px wide.
Expected: column ≈ clamp result (~1256px available → 92% ≈ 1155px, capped at 940px → 940px). Input bar aligns with messages. Bubbles widen but stay ≤ column. Prose ≤ ~68ch.

- [ ] **Step 3: Verify at 1920px**

Resize to 1920px.
Expected: column pinned at 940px ceiling, centered in remaining space. No full-window dead strip; gutters intentional via `xl:px-12`.

- [ ] **Step 4: Verify at 2560px**

Resize to 2560px.
Expected: column still 940px (ceiling holds), comfortable reading measure, no overflow.

- [ ] **Step 5: Check attachments are not over-constrained**

Send or recall a message with an image/file attachment. Confirm the attachment (rendered by `renderAttachment`, a sibling inside the bubble `div`) is not clipped by `max-w-[68ch]`. Images should display up to bubble width.

If an attachment IS clipped: move `max-w-[68ch]` off the bubble `div` (line 1092) and onto the `<MarkdownMessage>` element instead (line 1097), leaving attachments at full bubble width. Re-run `npx tsc --noEmit` and commit the adjustment:
```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "fix(chat): scope 68ch cap to markdown only, not attachments"
```

- [ ] **Step 6: Confirm dark mode + reduced motion**

Toggle dark mode and enable `prefers-reduced-motion`. Expected: contrast and the existing `motion-safe` bounce behavior unchanged (no regression from this work).

- [ ] **Step 7: Final commit (if any fix from Step 5 applied)**

If Step 5 required a fix, it was committed in that step. If no fix was needed, no commit is required here. Confirm `git status` is clean of unintended changes:
```bash
git status --short
```
Expected: no uncommitted modifications to `ChatPage.tsx`.

---

## Self-Review

**1. Spec coverage:**
- Frozen `max-w-3xl` message column → Task 2. ✅
- Frozen `max-w-3xl` input bar → Task 3. ✅
- `max-w-[75%]` bubble → Task 4 (bubble container). ✅
- Prose 68ch cap → Task 4 (inner div). ✅
- `--chat-col` token, container-relative → Task 1. ✅
- Adaptive gutters `px-4 md:px-8 xl:px-12` → Task 2. ✅
- No MainLayout/Sidebar changes → respected (not touched). ✅
- Verification at 1366/1920/2560 + dark mode → Task 5. ✅

**2. Placeholder scan:** No TBD/TODO/“similar to” — every step shows exact code or exact commands. ✅

**3. Type consistency:** `--chat-col` defined in Task 1 and consumed in Tasks 2, 3, 4 with identical spelling. `max-w-[68ch]` and `max-w-[min(88%,var(--chat-col))]` use the same token. No renamed symbols. ✅
