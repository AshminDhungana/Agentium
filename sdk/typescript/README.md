# Agentium TypeScript SDK

Fully typed TypeScript client for the [Agentium](https://github.com/AshminDhungana/Agentium) AI Agent Governance platform.

## Installation

```bash
npm install @agentium/sdk
```

## Quick Start

```typescript
import { AgentiumClient } from '@agentium/sdk';

const client = new AgentiumClient({
  baseUrl: 'http://localhost:8000',
  apiKey: 'your-api-key', // pragma: allowlist secret
});

// List agents
const agents = await client.listAgents();
agents.forEach((a) => console.log(`${a.agentium_id} — ${a.role}`));

// Create a task
const task = await client.createTask({
  title: 'Summarize report',
  description: 'Summarize Q4 financials',
});
console.log(`Task created: ${task.id}`);
```

## Authentication

### API Key
```typescript
const client = new AgentiumClient({
  baseUrl: 'http://localhost:8000',
  apiKey: 'sk-...', // pragma: allowlist secret
});
```

### JWT (username/password)
```typescript
const client = new AgentiumClient({ baseUrl: 'http://localhost:8000' });
const token = await client.login('admin', 'password');
const agents = await client.listAgents();
```

## Error Handling

```typescript
import { AgentiumClient, NotFoundError, RateLimitError } from '@agentium/sdk';

try {
  const agent = await client.getAgent('99999');
} catch (err) {
  if (err instanceof NotFoundError) {
    console.log('Agent not found');
  } else if (err instanceof RateLimitError) {
    console.log(`Retry after ${err.retryAfter}s`);
  }
}
```

## Auto-Generated Types

Generate TypeScript interfaces from a running Agentium backend:

```bash
npm run generate-types
```

This uses [openapi-typescript](https://github.com/openapi-ts/openapi-typescript) to fetch the OpenAPI spec from `http://localhost:8000/openapi.json` and generate types to `src/generated-types.ts`.

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

## License

AGPL-3.0 — same as the Agentium project.
