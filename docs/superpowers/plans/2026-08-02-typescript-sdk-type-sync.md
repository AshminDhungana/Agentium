# TypeScript SDK Type Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom `generate-types.ts` script with `openapi-typescript` CLI and add a CI drift check that fails the build if committed types don't match a fresh generation from the live backend OpenAPI spec.

**Architecture:** Use industry-standard `openapi-typescript` to generate types from the backend's `/openapi.json` endpoint. Commit generated types to git (`src/generated-types.ts`). Manual SDK types in `src/types.ts` import and extend the generated base. CI starts the backend via `docker-compose.test.yml`, regenerates types, and runs `git diff --exit-code` to detect drift.

**Tech Stack:** `openapi-typescript@^7.0.0`, `ts-node`, `typescript@^5.3.0`, Jest, GitHub Actions, Docker Compose

## Global Constraints

- Generated file: `sdk/typescript/src/generated-types.ts` (committed to git)
- Manual types file: `sdk/typescript/src/types.ts` (imports from generated-types.ts)
- Generation script: `sdk/typescript/scripts/generate-types.ts` (thin wrapper around CLI)
- CI workflow: `.github/workflows/sdk-smoke-tests.yml` (extends existing `typescript-sdk-smoke` job)
- Test backend: `docker-compose.test.yml` (reused from integration tests)
- TypeScript strict flags: `noUncheckedIndexedAccess: true` in `tsconfig.json`
- Union enums: `--generate-union-enums` flag for better TypeScript types
- Node versions: 18, 20, 22 (matrix)
- All commands must work identically locally and in CI

---

### Task 1: Add Dependencies to package.json

**Files:**
- Modify: `sdk/typescript/package.json`

**Interfaces:**
- Produces: `devDependencies.openapi-typescript`, `devDependencies.@types/node`

- [ ] **Step 1: Update package.json with new devDependencies**

```json
{
  "name": "@agentium/sdk",
  "version": "0.1.0",
  "description": "TypeScript SDK for the Agentium AI Agent Governance platform",
  "main": "dist/index.js",
  "module": "dist/index.mjs",
  "types": "dist/index.d.ts",
  "license": "AGPL-3.0",
  "author": "Ashmin Dhungana",
  "repository": {
    "type": "git",
    "url": "https://github.com/AshminDhungana/Agentium"
  },
  "keywords": ["agentium", "ai", "agents", "governance", "sdk"],
  "scripts": {
    "build": "tsc",
    "test": "jest --config jest.config.js",
    "generate-types": "ts-node scripts/generate-types.ts"
  },
  "devDependencies": {
    "@types/jest": "^29.5.0",
    "@types/node": "^20.0.0",
    "jest": "^29.7.0",
    "openapi-typescript": "^7.0.0",
    "ts-jest": "^29.1.0",
    "ts-node": "^10.9.0",
    "typescript": "^5.3.0"
  },
  "files": [
    "dist/",
    "README.md"
  ]
}
```

- [ ] **Step 2: Install dependencies**

```bash
cd sdk/typescript && npm install
```

- [ ] **Step 3: Verify openapi-typescript is available**

```bash
cd sdk/typescript && npx openapi-typescript --version
```
Expected: `7.x.x` or similar

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/package.json sdk/typescript/package-lock.json
git commit -m "deps: add openapi-typescript and @types/node for type generation"
```

---

### Task 2: Update Generation Script to Use CLI

**Files:**
- Modify: `sdk/typescript/scripts/generate-types.ts`

**Interfaces:**
- Consumes: `package.json` has `openapi-typescript` dependency
- Produces: Updated script that invokes CLI with proper args

- [ ] **Step 1: Replace script content**

```typescript
/**
 * Script to fetch the OpenAPI spec from a running Agentium backend
 * and generate TypeScript interfaces using openapi-typescript CLI.
 *
 * Usage:
 *   npm run generate-types [base-url]
 *
 * Default base URL: http://localhost:8000
 */

import { execSync } from 'child_process';

const BASE_URL = process.argv[2] || 'http://localhost:8000';
const OUT_PATH = './src/generated-types.ts';

console.log(`Generating types from ${BASE_URL}/openapi.json...`);

try {
  execSync(
    `npx openapi-typescript ${BASE_URL}/openapi.json -o ${OUT_PATH} --generate-union-enums`,
    { stdio: 'inherit' }
  );
  console.log(`✅ Generated ${OUT_PATH}`);
} catch (error) {
  console.error('❌ Failed to generate types');
  console.error('Ensure the backend is running at', BASE_URL);
  console.error('Start it with: cd ../../backend && docker compose up -d');
  process.exit(1);
}
```

- [ ] **Step 2: Test script locally (requires running backend)**

```bash
# In another terminal, start backend:
cd backend && docker compose up -d

# Then run generation:
cd sdk/typescript && npm run generate-types
```
Expected: `✅ Generated ./src/generated-types.ts`

- [ ] **Step 3: Verify generated file exists and has content**

```bash
ls -la sdk/typescript/src/generated-types.ts
head -50 sdk/typescript/src/generated-types.ts
```
Expected: File exists with TypeScript interfaces/types

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/scripts/generate-types.ts
git commit -m "feat: update generate-types.ts to use openapi-typescript CLI"
```

---

### Task 3: Generate Initial Types and Commit

**Files:**
- Create: `sdk/typescript/src/generated-types.ts`

**Interfaces:**
- Consumes: Running backend at `http://localhost:8000`, updated generation script
- Produces: Committed generated types file

- [ ] **Step 1: Ensure backend is running**

```bash
cd backend && docker compose up -d
# Wait for health check
curl -sf http://localhost:8000/api/health
```

- [ ] **Step 2: Generate types**

```bash
cd sdk/typescript && npm run generate-types
```

- [ ] **Step 3: Review generated file**

```bash
cat sdk/typescript/src/generated-types.ts | head -100
```
Expected: TypeScript interfaces matching OpenAPI components/schemas

- [ ] **Step 4: Add to git and commit**

```bash
git add sdk/typescript/src/generated-types.ts
git commit -m "chore: add initial generated-types.ts from OpenAPI spec"
```

---

### Task 4: Update Manual Types Layer (src/types.ts)

**Files:**
- Modify: `sdk/typescript/src/types.ts`

**Interfaces:**
- Consumes: `src/generated-types.ts` exists
- Produces: Updated types.ts that re-exports generated types + adds SDK-specific types

- [ ] **Step 1: Replace src/types.ts content**

```typescript
/**
 * TypeScript interfaces mirroring the Agentium backend models.
 * 
 * Generated base types come from src/generated-types.ts (auto-generated from OpenAPI spec).
 * This file re-exports them and adds SDK-specific helpers, constants, and non-OpenAPI types.
 */

// Re-export all generated API types
export * from './generated-types';

// ─────────────────────────────────────────────────────────────────
// SDK-specific types (not in OpenAPI spec)
// ─────────────────────────────────────────────────────────────────

export interface AgentiumClientConfig {
  baseUrl: string;
  apiKey?: string;
  token?: string;
  timeout?: number;
}

export type WebhookEventType =
  | 'task.created'
  | 'task.completed'
  | 'task.failed'
  | 'vote.started'
  | 'vote.resolved'
  | 'constitution.amended'
  | 'agent.spawned'
  | 'agent.terminated';

// ─────────────────────────────────────────────────────────────────
// Convenience type aliases for common generated types
// ─────────────────────────────────────────────────────────────────

// These map to generated types from components.schemas in OpenAPI
// Example: export type Agent = components['schemas']['Agent'];
// Actual aliases depend on generated output structure
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd sdk/typescript && npm run build
```
Expected: Build succeeds, `dist/` created

- [ ] **Step 3: Run existing tests**

```bash
cd sdk/typescript && npm test
```
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add sdk/typescript/src/types.ts
git commit -m "refactor: update types.ts to import generated types as base layer"
```

---

### Task 5: Update tsconfig.json with Strict Flags

**Files:**
- Modify: `sdk/typescript/tsconfig.json`

**Interfaces:**
- Produces: TypeScript config with `noUncheckedIndexedAccess: true`

- [ ] **Step 1: Read current tsconfig.json**

```bash
cat sdk/typescript/tsconfig.json
```

- [ ] **Step 2: Update with recommended strict flags**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "module": "ESNext",
    "moduleResolution": "node",
    "declaration": true,
    "declarationMap": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "noUncheckedIndexedAccess": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": false
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 3: Verify build still passes**

```bash
cd sdk/typescript && npm run build
```

- [ ] **Step 4: Run tests**

```bash
cd sdk/typescript && npm test
```

- [ ] **Step 5: Commit**

```bash
git add sdk/typescript/tsconfig.json
git commit -m "config: enable noUncheckedIndexedAccess for stricter type checking"
```

---

### Task 6: Add CI Drift Check to sdk-smoke-tests.yml

**Files:**
- Modify: `.github/workflows/sdk-smoke-tests.yml`

**Interfaces:**
- Consumes: `docker-compose.test.yml` backend, `npm run generate-types:ci` script
- Produces: Updated workflow with drift detection steps

- [ ] **Step 1: Read current workflow**

```bash
cat .github/workflows/sdk-smoke-tests.yml
```

- [ ] **Step 2: Update the typescript-sdk-smoke job**

```yaml
name: SDK Smoke Tests

on:
  push:
    branches: ["main", "master", "develop"]
  pull_request:
    branches: ["main", "master", "develop"]
  workflow_dispatch:

jobs:
  python-sdk-smoke:
    name: Python SDK Smoke Tests (${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
      fail-fast: false

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Python SDK dependencies
        working-directory: ./sdk/python
        run: |
          pip install --upgrade pip setuptools wheel
          pip install -e ".[dev]"

      - name: Run Python SDK smoke tests
        working-directory: ./sdk/python
        run: pytest tests/test_sdk.py -v

  typescript-sdk-smoke:
    name: TypeScript SDK Smoke Tests (Node ${{ matrix.node-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: ["18", "20", "22"]
      fail-fast: false

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Node ${{ matrix.node-version }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
          cache-dependency-path: sdk/typescript/package-lock.json

      # ── Start backend for live OpenAPI spec ──────────────────────────────────
      - name: Start test services
        run: |
          docker compose -f docker-compose.test.yml up -d

      - name: Wait for backend to be healthy
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
            echo "ERROR: Services did not become healthy within the timeout."
            docker compose -f docker-compose.test.yml ps
            docker compose -f docker-compose.test.yml logs
            exit 1
          fi

      - name: Install TypeScript SDK dependencies
        working-directory: ./sdk/typescript
        run: npm install

      - name: Build TypeScript SDK
        working-directory: ./sdk/typescript
        run: npm run build

      # ── Type Drift Check ─────────────────────────────────────────────────────
      - name: Generate Types from Live Spec
        working-directory: ./sdk/typescript
        run: npm run generate-types:ci

      - name: Check for Type Drift
        run: |
          if ! git diff --exit-code -- sdk/typescript/src/generated-types.ts; then
            echo "::error file=sdk/typescript/src/generated-types.ts::Type drift detected — generated types don't match committed files"
            echo "Run 'npm run generate-types' in sdk/typescript and commit the changes."
            git diff sdk/typescript/src/generated-types.ts
            exit 1
          fi

      - name: Run TypeScript SDK smoke tests
        working-directory: ./sdk/typescript
        run: npm test

      - name: Stop test services
        if: always()
        run: docker compose -f docker-compose.test.yml down
```

- [ ] **Step 3: Add generate-types:ci script to package.json**

```json
{
  "scripts": {
    "build": "tsc",
    "test": "jest --config jest.config.js",
    "generate-types": "ts-node scripts/generate-types.ts",
    "generate-types:ci": "npx openapi-typescript http://localhost:8000/openapi.json -o src/generated-types.ts --generate-union-enums"
  }
}
```

- [ ] **Step 4: Test workflow locally with act (optional) or push to test**

```bash
cd sdk/typescript && npm run generate-types:ci
# Then check if git diff shows changes
git diff --exit-code -- sdk/typescript/src/generated-types.ts && echo "No drift" || echo "Drift detected"
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/sdk-smoke-tests.yml sdk/typescript/package.json
git commit -m "ci: add type drift check to TypeScript SDK smoke tests"
```

---

### Task 7: Verify Full CI Pipeline Locally

**Files:**
- No new files (verification only)

**Interfaces:**
- Consumes: All previous tasks complete
- Produces: Confidence that CI will pass

- [ ] **Step 1: Clean build and test**

```bash
cd sdk/typescript
rm -rf dist node_modules
npm install
npm run build
npm test
```

- [ ] **Step 2: Simulate CI generation and drift check**

```bash
# Ensure backend is running
cd ../../backend && docker compose up -d
# Wait for health
sleep 10
curl -sf http://localhost:8000/api/health

# Generate types (CI command)
cd ../sdk/typescript
npm run generate-types:ci

# Check for drift
git diff --exit-code -- src/generated-types.ts && echo "✅ No drift" || echo "❌ Drift detected"
```

- [ ] **Step 3: Verify generated file compiles**

```bash
npm run build
```

- [ ] **Step 4: Run full test suite**

```bash
npm test
```

- [ ] **Step 5: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: final adjustments after local CI verification"
```

---

### Task 8: Documentation Update

**Files:**
- Modify: `sdk/typescript/README.md`

**Interfaces:**
- Produces: Updated README with generation instructions

- [ ] **Step 1: Add generation instructions to README**

```markdown
## Type Generation

Types are generated from the backend's OpenAPI spec using [openapi-typescript](https://github.com/openapi-ts/openapi-typescript).

### Regenerate Types Locally

```bash
# 1. Start the backend
cd ../../backend
docker compose up -d

# 2. Generate types
cd ../sdk/typescript
npm run generate-types

# 3. Review changes
git diff src/generated-types.ts

# 4. Commit if satisfied
git add src/generated-types.ts
git commit -m "chore: regenerate API types from OpenAPI spec"
```

### CI Drift Check

The CI pipeline (`sdk-smoke-tests.yml`) automatically:
1. Starts the backend via Docker Compose
2. Generates types from the live `/openapi.json` endpoint
3. Compares against committed `src/generated-types.ts`
4. Fails the build if any drift is detected

To fix a CI drift failure, follow the local regeneration steps above and push the updated `generated-types.ts`.
```

- [ ] **Step 2: Commit**

```bash
git add sdk/typescript/README.md
git commit -m "docs: add type generation instructions to README"
```

---

## Acceptance Criteria Verification

After all tasks complete, verify:

- [ ] `openapi-typescript` in `package.json` devDependencies
- [ ] `scripts/generate-types.ts` uses CLI wrapper
- [ ] `src/generated-types.ts` committed and non-empty
- [ ] `src/types.ts` imports from `generated-types.ts`
- [ ] `tsconfig.json` has `"noUncheckedIndexedAccess": true`
- [ ] `sdk-smoke-tests.yml` has drift check steps
- [ ] `package.json` has `generate-types:ci` script
- [ ] Local `npm run generate-types` works
- [ ] Local `npm run generate-types:ci` works
- [ ] `npm run build` passes
- [ ] `npm test` passes
- [ ] `git diff --exit-code` passes on clean state

---

## Rollback Plan

If issues arise after merge:

```bash
# 1. Revert package.json dependencies
git revert <commit-hash-for-deps>

# 2. Restore original generation script
git revert <commit-hash-for-script>

# 3. Remove drift check from CI
git revert <commit-hash-for-ci>

# 4. Delete generated-types.ts
git rm sdk/typescript/src/generated-types.ts

# 5. Restore types.ts to manual-only
git revert <commit-hash-for-types>
```