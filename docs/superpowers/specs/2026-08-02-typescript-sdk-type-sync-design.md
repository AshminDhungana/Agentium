# TypeScript SDK Type Synchronization Design

**Status**: Approved  
**Date**: 2026-08-02  
**Author**: Ashmin Dhungana  
**Related**: [Task 19.3](#) — SDK type drift prevention

---

## 1. Problem Statement

The TypeScript SDK (`sdk/typescript/`) maintains manual type definitions in `src/types.ts` that mirror the backend's 80+ API endpoints. Currently:

- Types are manually maintained and easily drift from the backend OpenAPI spec
- Custom `scripts/generate-types.ts` exists but is not integrated into CI
- No automated verification that generated types match committed types
- Python SDK has the same problem (`sdk/python/agentium_sdk/models.py`)

**Goal**: Guarantee that SDK types stay in sync with the backend OpenAPI spec on every PR.

---

## 2. Solution Overview

Replace the custom generator with **`openapi-typescript`** (industry-standard CLI tool) and add a **CI drift check** that fails the build if committed types don't match a fresh generation from the live backend spec.

### Architecture

```
┌──────────────┐    HTTP GET    ┌─────────────────┐    CLI    ┌─────────────────────┐
│  Backend     │  /openapi.json │  openapi-typescript │──▶│ src/generated-types.ts │
│  (FastAPI)   │ ─────────────▶ │  (npx)          │     │  (committed to git)   │
└──────────────┘                └─────────────────┘     └──────────┬──────────┘
                                                                   │
                        ┌──────────────────┐                      │
                        │  src/types.ts    │◀─────────────────────┘
                        │  (manual layer)  │   Imports generated base
                        │  + extensions    │   Adds SDK-specific types
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │ src/index.ts     │  (re-exports all types)
                        └──────────────────┘
```

### CI Pipeline (TypeScript SDK job in `sdk-smoke-tests.yml`)

```yaml
- name: Start test backend
  run: docker compose -f docker-compose.test.yml up -d
  # ... wait for health ...

- name: Generate Types
  run: |
    npx openapi-typescript http://localhost:8000/openapi.json \
      -o sdk/typescript/src/generated-types.ts \
      --generate-union-enums

- name: Check for Type Drift
  run: |
    if ! git diff --exit-code -- sdk/typescript/src/generated-types.ts; then
      echo "::error::Type drift detected in generated-types.ts"
      echo "Run 'npm run generate-types' in sdk/typescript and commit the changes."
      git diff sdk/typescript/src/generated-types.ts
      exit 1
    fi
```

---

## 3. Detailed Implementation

### 3.1 Package Dependencies

Add to `sdk/typescript/package.json`:

```json
{
  "devDependencies": {
    "openapi-typescript": "^7.0.0",
    "@types/node": "^20.0.0"
  }
}
```

### 3.2 Updated Generation Script

Replace `scripts/generate-types.ts` with a thin wrapper that invokes the CLI:

```typescript
// scripts/generate-types.ts
import { execSync } from 'child_process';

const BASE_URL = process.argv[2] || 'http://localhost:8000';
const OUT_PATH = './src/generated-types.ts';

console.log(`Generating types from ${BASE_URL}/openapi.json...`);

execSync(
  `npx openapi-typescript ${BASE_URL}/openapi.json -o ${OUT_PATH} --generate-union-enums`,
  { stdio: 'inherit' }
);

console.log(`✅ Generated ${OUT_PATH}`);
```

### 3.3 Updated package.json Scripts

```json
{
  "scripts": {
    "generate-types": "ts-node scripts/generate-types.ts",
    "generate-types:ci": "npx openapi-typescript http://localhost:8000/openapi.json -o src/generated-types.ts --generate-union-enums",
    "build": "tsc",
    "test": "jest --config jest.config.js"
  }
}
```

### 3.4 Manual Types Layer (`src/types.ts`)

```typescript
/**
 * TypeScript SDK types — manual extensions on top of generated API types.
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

### 3.5 TypeScript Config

Ensure `tsconfig.json` has recommended strict flags:

```json
{
  "compilerOptions": {
    "noUncheckedIndexedAccess": true,
    "strict": true,
    "esModuleInterop": true,
    "moduleResolution": "node",
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "module": "ESNext"
  }
}
```

---

## 4. CI Integration Details

### 4.1 Updated `sdk-smoke-tests.yml`

Add the TypeScript drift check to the existing `typescript-sdk-smoke` job:

```yaml
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

### 4.2 Why Start Backend in CI?

- **Live validation**: Ensures the actual running backend's spec matches types (catches runtime config issues)
- **Reuses infrastructure**: Same `docker-compose.test.yml` as integration tests
- **No snapshot maintenance**: Avoids committing/updating `openapi.json` snapshots

---

## 5. Developer Workflow

### Local Development

```bash
# 1. Start backend (if not running)
cd backend && docker compose up -d

# 2. Regenerate types
cd ../sdk/typescript
npm run generate-types

# 3. Review changes
git diff src/generated-types.ts

# 4. Commit if satisfied
git add src/generated-types.ts
git commit -m "chore: regenerate API types from OpenAPI spec"
```

### CI Failure Resolution

If CI fails with type drift:

```bash
# 1. Pull latest changes
git pull origin main

# 2. Start backend locally
cd backend
docker compose up -d

# 3. Regenerate and commit
cd ../sdk/typescript
npm run generate-types
git add src/generated-types.ts
git commit -m "chore: fix type drift — regenerate from OpenAPI spec"
git push
```

---

## 6. Edge Cases & Mitigations

| Scenario | Mitigation |
|----------|------------|
| Backend not running locally | `generate-types.ts` exits with clear error; docs explain `docker compose up -d` |
| Spec has invalid schemas | `openapi-typescript` fails fast with line/column; add Redocly lint step if needed |
| Breaking API changes | CI catches it; developer must update SDK usage code accordingly |
| Network flakiness in CI | Backend health check waits 2min; retries handled by Docker healthcheck |
| Generated types break SDK build | `npm run build` runs after generation in CI; catches compile errors |

---

## 7. Future Extensions

### 7.1 Python SDK (Separate Task)

Use `datamodel-code-generator` for Pydantic models:

```bash
pip install datamodel-code-generator
datamodel-codegen --input http://localhost:8000/openapi.json \
  --input-type openapi --output sdk/python/agentium_sdk/models_generated.py \
  --target-python-version 3.10 --use-standard-collections
```

### 7.2 Breaking Change Detection

Add `oasdiff` or `openapi-diff` to compare spec versions and warn on breaking changes:

```yaml
- name: Check for Breaking API Changes
  run: |
    npx @apidevtools/openapi-diff@latest \
      http://localhost:8000/openapi.json \
      ./docs/openapi-baseline.json \
      --fail-on-breaking
```

### 7.3 Spec Quality Gate

Add Redocly lint before generation:

```yaml
- name: Lint OpenAPI Spec
  run: npx @redocly/openapi-cli@latest lint http://localhost:8000/openapi.json
```

---

## 8. Acceptance Criteria

- [ ] `openapi-typescript` added to `sdk/typescript/package.json`
- [ ] `scripts/generate-types.ts` updated to use CLI
- [ ] `src/generated-types.ts` committed to git (initial generation)
- [ ] `src/types.ts` imports from `generated-types.ts`
- [ ] `tsconfig.json` has `noUncheckedIndexedAccess: true`
- [ ] `sdk-smoke-tests.yml` includes drift check step
- [ ] CI passes on clean main branch
- [ ] CI fails with clear error when types are stale
- [ ] Local `npm run generate-types` works and produces identical output to CI

---

## 9. Rollback Plan

If issues arise:

1. Revert `package.json` dependencies
2. Restore original `scripts/generate-types.ts`
3. Remove drift check from CI
4. Delete `src/generated-types.ts`
5. Restore `src/types.ts` to manual-only

All changes are additive and isolated to the TypeScript SDK.