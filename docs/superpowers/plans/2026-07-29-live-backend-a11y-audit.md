# Live-Backend Accessibility Audit CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CI gate that runs `axe-core` color-contrast audits against every protected route with a live backend database and API, catching real-world contrast violations that static/mocked tests miss.

**Architecture:** Create a new `integration-a11y.yml` workflow that reuses the existing `docker-compose.test.yml` stack (PostgreSQL, Redis, ChromaDB) + starts the FastAPI backend, then runs the existing `npm run test:a11y` (vitest + Playwright Chromium) against `http://localhost:3000` with `VITE_API_URL=http://localhost:8000`.

**Tech Stack:** GitHub Actions, docker-compose.test.yml, vitest browser project (Playwright Chromium), axe-core with `color-contrast: { enabled: true }`, FastAPI/uvicorn backend.

## Global Constraints

- **Node:** 22 (per frontend-a11y.yml)
- **Python:** 3.11 (per integration-tests.yml)
- **Playwright Chromium:** installed via `npx playwright install --with-deps chromium`
- **Vitest config:** `frontend/vite.config.ts` already defines `a11y` browser project
- **Test command:** `npm run test:a11y` in `frontend/` (runs `vitest run --project a11y`)
- **Axe config:** `frontend/src/test/a11yBrowser.tsx` enables `color-contrast` rule
- **Theme testing:** `auditRoute()` toggles `dark` class on `<html>` for light/dark modes
- **Auth/WS mocking:** Use existing store mock patterns from `Dashboard.a11y.browser.test.tsx`
- **Plan location:** `docs/superpowers/plans/2026-07-29-live-backend-a11y-audit.md`
- **Spec location:** `docs/superpowers/specs/2026-07-29-live-backend-a11y-audit-design.md`
- **CI workflow location:** `.github/workflows/integration-a11y.yml`

---

### Task 1: Create Integration A11y Workflow

**Files:**
- Create: `.github/workflows/integration-a11y.yml`

**Interfaces:**
- Produces: CI job that passes iff all route a11y tests pass against live backend

- [ ] **Step 1: Write the workflow file**

```yaml
# .github/workflows/integration-a11y.yml
name: Integration Accessibility

on:
  push:
    branches: ["main", "master", "develop"]
    paths:
      - "frontend/**"
      - "backend/**"
      - ".github/workflows/integration-a11y.yml"
  pull_request:
    branches: ["main", "master", "develop"]
    paths:
      - "frontend/**"
      - "backend/**"
      - ".github/workflows/integration-a11y.yml"
  workflow_dispatch:

env:
  NODE_VERSION: "22"
  PYTHON_VERSION: "3.11"

jobs:
  a11y-with-backend:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    permissions:
      contents: read

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      # ── Reuse integration-tests.yml service startup (Postgres, Redis, ChromaDB) ──
      - name: Start test services
        run: docker compose -f docker-compose.test.yml up -d

      - name: Wait for services to be healthy
        run: |
          echo "=== Service startup logs ==="
          docker compose -f docker-compose.test.yml logs
          echo "=== Waiting for healthy services ==="
          for i in {1..60}; do
            sleep 2
            healthy_count=$(docker compose -f docker-compose.test.yml ps | grep -ci "healthy" || true)
            if [ "$healthy_count" -eq 3 ]; then
              echo "All 3 services healthy."
              break
            fi
            echo "Waiting for services ($healthy_count/3 healthy) — attempt $i/60"
          done
          if [ "$healthy_count" -ne 3 ]; then
            echo "ERROR: Services did not become healthy within timeout."
            docker compose -f docker-compose.test.yml ps
            docker compose -f docker-compose.test.yml logs
            exit 1
          fi
          echo "=== Final service status ==="
          docker compose -f docker-compose.test.yml ps

      - name: Initialize test databases
        run: |
          # Reuse exact logic from integration-tests.yml lines 52-80
          PSQL_USER="$(docker compose -f docker-compose.test.yml exec -T postgres bash -lc 'echo "${POSTGRES_USER:-agentium}"' | tr -d '\r')"
          echo "Using DB user: $PSQL_USER"

          for i in {1..30}; do
            if docker compose -f docker-compose.test.yml exec -T postgres bash -lc "pg_isready -U '$PSQL_USER'" >/dev/null 2>&1; then
              echo "Postgres is ready."
              break
            fi
            echo "Waiting for Postgres to be ready ($i/30)..."
            sleep 1
          done

          for db in agentium agentium_test; do
            echo "Ensuring database exists: $db"
            docker compose -f docker-compose.test.yml exec -T postgres \
              psql -U "$PSQL_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || \
              docker compose -f docker-compose.test.yml exec -T postgres \
                psql -U "$PSQL_USER" -d postgres -c "CREATE DATABASE $db"
          done

          # Verify databases exist
          echo "=== Verifying databases ==="
          docker compose -f docker-compose.test.yml exec -T postgres \
            psql -U "$PSQL_USER" -d postgres -c "\l" | grep -E "agentium|agentium_test"

      - name: Run database migrations
        run: |
          docker compose -f docker-compose.test.yml exec -T postgres \
            psql -U "$PSQL_USER" -d agentium_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
          # Apply migrations via alembic
          cd backend
          pip install --upgrade pip setuptools wheel
          pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
          alembic upgrade head

      - name: Start backend API
        run: |
          cd backend
          DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test \
          REDIS_URL=redis://localhost:6379/1 \
          CHROMA_HOST=localhost \
          CHROMA_PORT=8001 \
          nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
          echo $! > /tmp/backend.pid
          echo "Backend PID: $(cat /tmp/backend.pid)"
          # Wait for the server to respond
          echo "Waiting for backend to be ready..."
          for i in {1..30}; do
            if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
              echo "Backend is ready!"
              break
            fi
            echo "  attempt $i/30..."
            sleep 2
          done
          # Show last few lines of server log for debugging
          tail -20 /tmp/backend.log

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install frontend dependencies
        working-directory: ./frontend
        run: npm ci

      - name: Install Playwright Chromium
        working-directory: ./frontend
        run: npx playwright install --with-deps chromium

      - name: Run accessibility tests against live backend
        working-directory: ./frontend
        env:
          VITE_API_URL: http://localhost:8000
          VITE_WS_URL: ws://localhost:8000
        run: npm run test:a11y

      - name: Stop backend
        if: always()
        run: kill $(cat /tmp/backend.pid) || true

      - name: Stop test services
        if: always()
        run: docker compose -f docker-compose.test.yml down
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/integration-a11y.yml
git commit -m "ci: add integration-a11y workflow with live backend"
```

---

### Task 2: Add ChatPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ChatPage.a11y.browser.test.tsx`

**Interfaces:**
- Consumes: `auditRoute` from `@/test/a11yBrowser`, stores from `@/store/authStore`, `@/store/websocketStore`
- Produces: 2 test cases (light/dark theme)

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ChatPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ChatPage } from '@/pages/ChatPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useChatStore } from '@/store/chatStore';

describe('ChatPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
    useChatStore.setState({
      messages: [],
      activeStreamId: null,
      isAwaitingReply: false,
      isThinking: false,
      toolCount: 0,
      conversations: [],
      selectedId: null,
      inboxLoading: false,
      replyContent: '',
      isSending: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ChatPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ChatPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify it works**

```bash
cd frontend && npm run test:a11y -- ChatPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChatPage.a11y.browser.test.tsx
git commit -m "test: add ChatPage accessibility test (light/dark themes)"
```

---

### Task 3: Add AgentsPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/AgentsPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/AgentsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { AgentsPage } from '@/pages/AgentsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAgentStore } from '@/store/agentStore';

describe('AgentsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
    useAgentStore.setState({
      agents: [],
      isLoading: false,
      error: null,
      selectedAgent: null,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><AgentsPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><AgentsPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- AgentsPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AgentsPage.a11y.browser.test.tsx
git commit -m "test: add AgentsPage accessibility test"
```

---

### Task 4: Add TasksPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/TasksPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/TasksPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { TasksPage } from '@/pages/TasksPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useTaskStore } from '@/store/taskStore';

describe('TasksPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
    useTaskStore.setState({
      tasks: [],
      isLoading: false,
      error: null,
      selectedTask: null,
      filters: {},
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><TasksPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><TasksPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- TasksPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/TasksPage.a11y.browser.test.tsx
git commit -m "test: add TasksPage accessibility test"
```

---

### Task 5: Add MonitoringPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/MonitoringPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/MonitoringPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { MonitoringPage } from '@/pages/MonitoringPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('MonitoringPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><MonitoringPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><MonitoringPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- MonitoringPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/MonitoringPage.a11y.browser.test.tsx
git commit -m "test: add MonitoringPage accessibility test"
```

---

### Task 6: Add VotingPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/VotingPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/VotingPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { VotingPage } from '@/pages/VotingPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('VotingPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><VotingPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><VotingPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- VotingPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/VotingPage.a11y.browser.test.tsx
git commit -m "test: add VotingPage accessibility test"
```

---

### Task 7: Add ConstitutionPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ConstitutionPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ConstitutionPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ConstitutionPage } from '@/pages/ConstitutionPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ConstitutionPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ConstitutionPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ConstitutionPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ConstitutionPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ConstitutionPage.a11y.browser.test.tsx
git commit -m "test: add ConstitutionPage accessibility test"
```

---

### Task 8: Add ModelsPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ModelsPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ModelsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ModelsPage } from '@/pages/ModelsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ModelsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ModelsPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ModelsPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ModelsPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ModelsPage.a11y.browser.test.tsx
git commit -m "test: add ModelsPage accessibility test"
```

---

### Task 9: Add ChannelsPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ChannelsPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ChannelsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ChannelsPage } from '@/pages/ChannelsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ChannelsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ChannelsPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ChannelsPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ChannelsPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChannelsPage.a11y.browser.test.tsx
git commit -m "test: add ChannelsPage accessibility test"
```

---

### Task 10: Add MessageLogPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/MessageLogPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/MessageLogPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { MessageLogPage } from '@/pages/MessageLogPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('MessageLogPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><MessageLogPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><MessageLogPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- MessageLogPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/MessageLogPage.a11y.browser.test.tsx
git commit -m "test: add MessageLogPage accessibility test"
```

---

### Task 11: Add ABTestingPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ABTestingPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ABTestingPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ABTestingPage } from '@/pages/ABTestingPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ABTestingPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ABTestingPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ABTestingPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ABTestingPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ABTestingPage.a11y.browser.test.tsx
git commit -m "test: add ABTestingPage accessibility test"
```

---

### Task 12: Add SovereignDashboard Accessibility Test

**Files:**
- Create: `frontend/src/pages/SovereignDashboard.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/SovereignDashboard.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { SovereignDashboard } from '@/pages/SovereignDashboard';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('SovereignDashboard color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: true, isSovereign: true },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><SovereignDashboard /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><SovereignDashboard /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- SovereignDashboard
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SovereignDashboard.a11y.browser.test.tsx
git commit -m "test: add SovereignDashboard accessibility test"
```

---

### Task 13: Add SettingsPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/SettingsPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/SettingsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { SettingsPage } from '@/pages/SettingsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('SettingsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><SettingsPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><SettingsPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- SettingsPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SettingsPage.a11y.browser.test.tsx
git commit -m "test: add SettingsPage accessibility test"
```

---

### Task 14: Add WorkflowsPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/WorkflowsPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/WorkflowsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { WorkflowsPage } from '@/pages/WorkflowsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('WorkflowsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><WorkflowsPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><WorkflowsPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- WorkflowsPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WorkflowsPage.a11y.browser.test.tsx
git commit -m "test: add WorkflowsPage accessibility test"
```

---

### Task 15: Add WorkflowDesignerPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/WorkflowDesignerPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/WorkflowDesignerPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { WorkflowDesignerPage } from '@/pages/WorkflowDesignerPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('WorkflowDesignerPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><WorkflowDesignerPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><WorkflowDesignerPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- WorkflowDesignerPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WorkflowDesignerPage.a11y.browser.test.tsx
git commit -m "test: add WorkflowDesignerPage accessibility test"
```

---

### Task 16: Add LoginPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/LoginPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/LoginPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { LoginPage } from '@/pages/LoginPage';

describe('LoginPage color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><LoginPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><LoginPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- LoginPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LoginPage.a11y.browser.test.tsx
git commit -m "test: add LoginPage accessibility test"
```

---

### Task 17: Add SignupPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/SignupPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/SignupPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { SignupPage } from '@/pages/SignupPage';

describe('SignupPage color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><SignupPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><SignupPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- SignupPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SignupPage.a11y.browser.test.tsx
git commit -m "test: add SignupPage accessibility test"
```

---

### Task 18: Add DeveloperPortalPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/DeveloperPortalPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/DeveloperPortalPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { DeveloperPortalPage } from '@/pages/DeveloperPortalPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('DeveloperPortalPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><DeveloperPortalPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><DeveloperPortalPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- DeveloperPortalPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/DeveloperPortalPage.a11y.browser.test.tsx
git commit -m "test: add DeveloperPortalPage accessibility test"
```

---

### Task 19: Add FederationPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/FederationPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/FederationPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { FederationPage } from '@/pages/FederationPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('FederationPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><FederationPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><FederationPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- FederationPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/FederationPage.a11y.browser.test.tsx
git commit -m "test: add FederationPage accessibility test"
```

---

### Task 20: Add LearningImpactDashboard Accessibility Test

**Files:**
- Create: `frontend/src/pages/LearningImpactDashboard.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/LearningImpactDashboard.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { LearningImpactDashboard } from '@/pages/LearningImpactDashboard';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('LearningImpactDashboard color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><LearningImpactDashboard /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><LearningImpactDashboard /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- LearningImpactDashboard
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LearningImpactDashboard.a11y.browser.test.tsx
git commit -m "test: add LearningImpactDashboard accessibility test"
```

---

### Task 21: Add MobilePage Accessibility Test

**Files:**
- Create: `frontend/src/pages/MobilePage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/MobilePage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { MobilePage } from '@/pages/MobilePage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('MobilePage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><MobilePage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><MobilePage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- MobilePage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/MobilePage.a11y.browser.test.tsx
git commit -m "test: add MobilePage accessibility test"
```

---

### Task 22: Add RBACManagement Accessibility Test

**Files:**
- Create: `frontend/src/pages/RBACManagement.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/RBACManagement.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { RBACManagement } from '@/pages/RBACManagement';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('RBACManagement color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: true, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><RBACManagement /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><RBACManagement /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- RBACManagement
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/RBACManagement.a11y.browser.test.tsx
git commit -m "test: add RBACManagement accessibility test"
```

---

### Task 23: Add ScalingDashboard Accessibility Test

**Files:**
- Create: `frontend/src/pages/ScalingDashboard.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ScalingDashboard.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ScalingDashboard } from '@/pages/ScalingDashboard';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ScalingDashboard color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ScalingDashboard /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ScalingDashboard /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ScalingDashboard
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ScalingDashboard.a11y.browser.test.tsx
git commit -m "test: add ScalingDashboard accessibility test"
```

---

### Task 24: Add WebhookManagementPage Accessibility Test

**Files:**
- Create: `frontend/src/pages/WebhookManagementPage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/WebhookManagementPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { WebhookManagementPage } from '@/pages/WebhookManagementPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('WebhookManagementPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><WebhookManagementPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><WebhookManagementPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- WebhookManagementPage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WebhookManagementPage.a11y.browser.test.tsx
git commit -m "test: add WebhookManagementPage accessibility test"
```

---

### Task 25: Add ToolMarketplacePage Accessibility Test

**Files:**
- Create: `frontend/src/pages/ToolMarketplacePage.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/ToolMarketplacePage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { ToolMarketplacePage } from '@/pages/ToolMarketplacePage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('ToolMarketplacePage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><ToolMarketplacePage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><ToolMarketplacePage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- ToolMarketplacePage
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ToolMarketplacePage.a11y.browser.test.tsx
git commit -m "test: add ToolMarketplacePage accessibility test"
```

---

### Task 26: Add Usermanagement Accessibility Test

**Files:**
- Create: `frontend/src/pages/Usermanagement.a11y.browser.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
// frontend/src/pages/Usermanagement.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { Usermanagement } from '@/pages/Usermanagement';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

describe('Usermanagement color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: true, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><Usermanagement /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><Usermanagement /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test to verify**

```bash
cd frontend && npm run test:a11y -- Usermanagement
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Usermanagement.a11y.browser.test.tsx
git commit -m "test: add Usermanagement accessibility test"
```

---

### Task 27: Update ARCHITECTURE.md Documentation

**Files:**
- Modify: `ARCHITECTURE.md`

**Interfaces:**
- Produces: Documented a11y CI gates in architecture docs

- [ ] **Step 1: Add accessibility CI gates section to ARCHITECTURE.md**

Find the CI/CD or Testing section and add:

```markdown
## Accessibility CI Gates

Agentium runs two complementary accessibility gates:

### 1. Fast PR Gate — `frontend-a11y.yml`
- **Trigger:** Push/PR to main/develop affecting `frontend/**`
- **Environment:** Frontend only (no backend services)
- **Command:** `npm run test:a11y` (vitest + Playwright Chromium)
- **Scope:** Component-level tests (`src/components/**/*.a11y.browser.test.tsx`) + smoke test
- **Time:** ~2-3 minutes
- **Purpose:** Catch regressions in shared UI components quickly

### 2. Deep Merge Gate — `integration-a11y.yml`
- **Trigger:** Push to main/develop (required check)
- **Environment:** Full stack via `docker-compose.test.yml` (Postgres, Redis, ChromaDB) + FastAPI backend
- **Command:** `npm run test:a11y` against `http://localhost:3000` with `VITE_API_URL=http://localhost:8000`
- **Scope:** All 24 route-level tests (`src/pages/*.a11y.browser.test.tsx`) × 2 themes = 48 test cases
- **Time:** ~8 minutes
- **Purpose:** Catch color-contrast violations in real rendered pages with live data

### Adding a New Page
1. Create component in `src/pages/NewPage.tsx`
2. Add route in `src/App.tsx` (protected or public)
3. Create `src/pages/NewPage.a11y.browser.test.tsx` using existing template
4. Run locally: `npm run test:a11y -- NewPage`
5. Both CI gates will auto-include the new test
```

- [ ] **Step 2: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: document accessibility CI gates in architecture"
```

---

### Task 28: Create Spec Document

**Files:**
- Create: `docs/superpowers/specs/2026-07-29-live-backend-a11y-audit-design.md`

- [ ] **Step 1: Write spec document**

```markdown
# Live-Backend Accessibility Audit CI Gate — Design Spec

> **Status:** Approved for implementation
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
5. Tests every protected route in both light and dark themes

## Architecture
- **Reuses** existing infra: `docker-compose.test.yml`, vitest `a11y` browser project, `auditRoute()` helper
- **Complements** (not replaces) `frontend-a11y.yml` — fast gate for PRs, deep gate for merges
- **Route coverage:** 24 pages × 2 themes = 48 test cases

## Test Pattern
Each page gets `PageName.a11y.browser.test.tsx`:
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
```

## CI Workflow
See `.github/workflows/integration-a11y.yml` — 45 min timeout, reuses integration-tests.yml service startup.

## Acceptance Criteria
- [ ] `integration-a11y.yml` passes on `main`
- [ ] All 24 route tests exist and pass locally
- [ ] Color-contrast violations in real data views are caught (verify by temporarily breaking a color)
- [ ] Documentation updated in `ARCHITECTURE.md`
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-29-live-backend-a11y-audit-design.md
git commit -m "docs: add live-backend a11y audit design spec"
```

---

## Spec Coverage Checklist

| Spec Requirement | Task(s) |
|------------------|---------|
| New CI workflow with live backend | 1 |
| Reuses docker-compose.test.yml | 1 (steps 1-5) |
| Runs vitest a11y project against backend | 1 (step "Run accessibility tests") |
| Tests all 20+ protected routes × 2 themes | 2-26 |
| Tests public routes (login, signup) | 16-17 |
| Uses existing auditRoute + color-contrast config | All test tasks |
| Documents in ARCHITECTURE.md | 27 |
| Spec document created | 28 |

---

## Placeholder Scan

✅ No TBD/TODO/implement later  
✅ Every step has exact code/commands  
✅ Types match (all tests use same `auditRoute` signature)  
✅ File paths are exact and consistent  
✅ Commit messages follow convention

---

**Plan complete and saved to** `docs/superpowers/plans/2026-07-29-live-backend-a11y-audit.md`