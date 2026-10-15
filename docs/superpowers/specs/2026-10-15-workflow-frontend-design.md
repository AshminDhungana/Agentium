# Workflow Frontend Design (18.3)

**Date:** 2026-10-15  
**Status:** Approved  
**Related:** TODO §18.3 — Workflow Frontend

---

## Overview

This spec defines the frontend architecture for workflow management, splitting the current monolithic `WorkflowAutomationPanel` into three focused pages with clear responsibilities.

---

## Architecture

| Page | Route | Responsibility |
|------|-------|----------------|
| **WorkflowsPage** | `/workflows` | List workflows with name, version, schedule, status; "New Workflow" CTA |
| **WorkflowDesignerPage** | `/workflows/:id` | Visual DAG editor (React Flow) for creating/editing workflows |
| **WorkflowExecutionsPage** | `/workflows/:id/executions` | Execution history + live monitoring |

---

## 1. WorkflowsPage — List View (`/workflows`)

### UI Structure

```
<Header>
  <h1>Workflows</h1>
  <Button variant="primary">+ New Workflow</Button>
</Header>

<EmptyState | WorkflowGrid>
  <WorkflowCard /> × N
</EmptyState | WorkflowGrid>
```

### WorkflowCard

| Element | Details |
|---------|---------|
| **Name** | Truncated, font-semibold |
| **Description** | 2-line clamp, text-sm, text-gray-600 |
| **Badges** | `v{version}` (mono), `{schedule_cron \| 'Manual'}`, `Active` (green) |
| **Actions** | `[Edit]` → `/workflows/:id` · `[Run]` → triggers execution, navigates to executions page |
| **Hover** | Border highlight, elevated shadow |

### Empty State

- Illustration: `workflows` (existing `EmptyState` component)
- Title: "No workflows yet"
- Description: "Create an automated sequence to orchestrate multi-step agent tasks."
- CTA: "Create First Workflow" → `/workflows/new`

### API

- `GET /api/v1/workflows` — returns array of `{ id, name, description, version, schedule_cron, is_active }`

---

## 2. WorkflowDesignerPage — Visual Editor (`/workflows/:id`)

### Current State (Verified Complete)

- **Canvas:** React Flow with `workflowStep` nodes, `conditional` edges
- **Palette:** `StepPalette` sidebar (desktop ≥1024px) / FAB + bottom-sheet (tablet)
- **Config:** `NodeConfigDrawer` — step config, success/failure routing, delete
- **History:** `VersionHistorySidebar` — auto-open desktop, toggle tablet
- **Mobile:** `MobileWorkflowViewer` — read-only on phones (<640px)
- **Drag-and-Drop:** HTML5 (desktop) + touch (tablet) via `StepPalette`
- **Save:** `PUT /api/v1/workflows/:id` with `{ name, template_json: { steps } }`

### New Workflow Mode (`/workflows/new`)

| Aspect | Behavior |
|--------|----------|
| **Route** | `/workflows/new` (lazy-loaded same component) |
| **Detection** | `useParams().id === 'new'` |
| **Initial State** | Empty canvas, `nextStepIndexRef = 0`, `workflow = null` |
| **Header** | Shows "New Workflow" until first save |
| **First Save** | `POST /api/v1/workflows` → returns `id` → `navigate(/workflows/${id})` |
| **Subsequent Saves** | `PUT /api/v1/workflows/:id` |

### Responsive Breakpoints

| Breakpoint | Layout |
|------------|--------|
| `< 640px` (phone) | `MobileWorkflowViewer` only |
| `640–1023px` (tablet) | Canvas + FAB → bottom-sheet palette; version sidebar toggle |
| `≥ 1024px` (desktop) | Sidebar palette + canvas + version sidebar (auto-open) |

---

## 3. WorkflowExecutionsPage — Monitoring (`/workflows/:id/executions`)

### Extracted from `WorkflowAutomationPanel`

### UI Structure

```
<Header>
  ← Back to Designer
  <h2>Execution History: {workflowName}</h2>
  <Button>Run Now</Button>
</Header>

<ExecutionList | LiveExecutionView>
```

### ExecutionList

| Column | Details |
|--------|---------|
| **Status** | Badge: COMPLETED (green), FAILED (red), RUNNING (indigo pulse) |
| **Started** | ISO timestamp, localized |
| **Completed** | ISO timestamp or "—" |
| **Current Step** | Step index (0-based) |
| **Action** | `[View]` → shows live/detail view |

### LiveExecutionView (when `executionId` selected)

- Real-time status via WebSocket (`useWebSocketStore`) + 5s polling fallback
- Progress bar / activity pulse while running
- Context JSON viewer (monospace, syntax highlighted)
- Auto-refresh until COMPLETED/FAILED

### API

- `GET /api/v1/workflows/:id/executions` — list executions
- `POST /api/v1/workflows/:id/execute` — trigger new execution
- `GET /api/v1/workflows/executions/:executionId` — poll single execution
- WebSocket: `workflow_execution` events (already implemented)

---

## 4. Routing (App.tsx)

```tsx
// Lazy-loaded
const WorkflowsPage = lazy(() => import('@/pages/WorkflowsPage'));
const WorkflowDesignerPage = lazy(() => import('@/pages/WorkflowDesignerPage'));
const WorkflowExecutionsPage = lazy(() => import('@/pages/WorkflowExecutionsPage'));

// Routes
<Route path="workflows" element={<WorkflowsPage />} />
<Route path="workflows/new" element={<WorkflowDesignerPage />} />
<Route path="workflows/:id" element={<WorkflowDesignerPage />} />
<Route path="workflows/:id/executions" element={<WorkflowExecutionsPage />} />
```

---

## 5. Component Deprecation

| Component | Status | Migration |
|-----------|--------|-----------|
| `WorkflowAutomationPanel` | **Deprecate** | Responsibilities split across 3 pages above |
| `WorkflowBuilder` (form-based) | **Deprecate** | Replaced by visual designer for new workflows |
| `WorkflowAutomationPanel` list view | → `WorkflowsPage` |
| `WorkflowAutomationPanel` create view | → `WorkflowDesignerPage` (new mode) |
| `WorkflowAutomationPanel` execution view | → `WorkflowExecutionsPage` |

---

## 6. Implementation Checklist

### WorkflowsPage.tsx (Rewrite)
- [ ] Remove `WorkflowAutomationPanel` wrapper
- [ ] Implement `WorkflowCard` component
- [ ] Implement empty state with CTA to `/workflows/new`
- [ ] Fetch workflows via `api.get('/api/v1/workflows')`
- [ ] "New Workflow" button → `navigate('/workflows/new')`
- [ ] Card click / Edit button → `navigate(\`/workflows/${wf.id}\`)`
- [ ] Run button → `POST /execute` → `navigate(\`/workflows/${wf.id}/executions\`)`

### WorkflowDesignerPage.tsx (Enhance)
- [ ] Detect `id === 'new'` in `useParams`
- [ ] Conditional loading: skip `api.get` for new workflows
- [ ] Initialize empty `nodes/edges`, `nextStepIndexRef = 0`
- [ ] Header: show "New Workflow" badge until first save
- [ ] `handleSave`: if `id === 'new'` → POST → redirect; else PUT
- [ ] Add "View Executions" button → `navigate(\`/workflows/${id}/executions\`)`

### WorkflowExecutionsPage.tsx (Create New)
- [ ] Extract execution list + live view from `WorkflowAutomationPanel`
- [ ] Accept `workflowId` from `useParams`
- [ ] Fetch workflow name for header
- [ ] Implement execution list with status badges
- [ ] Implement live view with WebSocket + polling
- [ ] "Run Now" button triggers execution
- [ ] Back button → `/workflows/:id`

### App.tsx
- [ ] Add `WorkflowExecutionsPage` lazy import
- [ ] Add three workflow routes

### Cleanup
- [ ] Verify no remaining imports of `WorkflowAutomationPanel`
- [ ] Delete `WorkflowAutomationPanel.tsx` (or archive)
- [ ] Delete `WorkflowBuilder.tsx` (or archive)
- [ ] Update any cross-references in nav/sidebar

---

## 7. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| 18.3.1 | `/workflows` displays list of workflows with name, version, schedule, status |
| 18.3.1 | Clicking workflow or "Edit" navigates to `/workflows/:id` |
| 18.3.1 | "New Workflow" button navigates to `/workflows/new` |
| 18.3.2 | `/workflows/:id` loads visual DAG editor with existing workflow |
| 18.3.2 | `/workflows/new` opens empty designer for new workflow creation |
| 18.3.3 | Drag-and-drop from palette adds nodes (desktop + tablet) |
| 18.3.3 | Connecting handles creates edges (success/failure) |
| 18.3.3 | Node config drawer edits step config and routing |
| 18.3.4 | `/workflows/:id/executions` shows execution history |
| 18.3.4 | "Run Now" triggers execution and shows live status |
| 18.3.4 | WebSocket updates reflect real-time execution progress |

---

## 8. Testing Notes

- **Unit:** `WorkflowsPage.test.tsx`, `WorkflowExecutionsPage.test.tsx`
- **A11y:** `WorkflowsPage.a11y.browser.test.tsx`, `WorkflowExecutionsPage.a11y.browser.test.tsx`
- **Integration:** Verify full flow: create → edit → run → monitor
- **Existing:** `WorkflowDesignerPage.a11y.browser.test.tsx` already passes

---

## 9. Rollback Plan

If issues arise:
1. Keep `WorkflowAutomationPanel` functional during transition
2. Feature flag: `VITE_WORKFLOW_NEW_PAGES=true` to enable new routes
3. Revert App.tsx routes to single `/workflows` → `WorkflowAutomationPanel`

---

*Spec written per brainstorming skill process. Next: invoke `writing-plans` skill for implementation plan.*