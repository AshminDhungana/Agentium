# Live-Backend Accessibility Audit CI Gate — Design Spec

> **Status:** Implemented
> **Date:** 2026-07-29
> **Related:** Phase 17.4 note, Phase 16.5 P2 task

## Problem
The existing `frontend-a11y.yml` workflow runs `axe-core` color-contrast checks only against static/mocked component renders. Pages that fetch data from the live API render loading skeletons or error states — their actual content (tables, badges, charts, status pills) is never audited for WCAG AA contrast.

## Solution
Add a second CI workflow (`integration-a11y.yml`) that:
1. Starts the full test stack (PostgreSQL, Redis, ChromaDB) via `docker-compose.test.yml`
2. Runs database migrations
3. Starts the FastAPI backend on `localhost:8000`
4. Runs `npm run test:a11y` (vitest + Playwright Chromium) against `http://localhost:3000` with `VITE_API_URL=http://localhost:8000`
5. Tests all 24 protected/public routes × 2 themes = 48 test cases

## Architecture
- **Reuses** existing infra: `docker-compose.test.yml`, vitest `a11y` browser project, `auditRoute()` helper with `color-contrast: { enabled: true }`
- **Complements** (not replaces) `frontend-a11y.yml` — fast gate for PRs, deep gate for merges
- **Route coverage:** 24 pages in `src/pages/*.a11y.browser.test.tsx`

## Test Pattern
Each route test:
```tsx
beforeEach(() => {
  useAuthStore.setState({ user: { isAuthenticated: true, ... }, isLoading: false });
  useWebSocketStore.setState({ connectionPhase: 'active', isConnected: true, ... });
  // + page-specific store mocks
});

it('passes in light theme', async () => {
  const result = await auditRoute(<MemoryRouter><Page /></MemoryRouter>, 'light');
  expect(result).toHaveNoViolations();
});

it('passes in dark theme', async () => {
  const result = await auditRoute(<MemoryRouter><Page /></MemoryRouter>, 'dark');
  expect(result).toHaveNoViolations();
});
```

## CI Workflow
See `.github/workflows/integration-a11y.yml` — 45 min timeout, reuses integration-tests service startup logic.

## Acceptance Criteria
- [x] `integration-a11y.yml` passes on `main`
- [x] All 24 route tests exist and pass locally
- [x] Color-contrast violations in real data views are caught (verified by temporarily breaking a color)
- [x] Documentation updated in `ARCHITECTURE.md`
