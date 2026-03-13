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
  apiKey: 'your-api-key',
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
  apiKey: 'sk-...',
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
npx ts-node scripts/generate-types.ts http://localhost:8000
```

## License

AGPL-3.0 — same as the Agentium project.
