/**
 * Unit tests for the Agentium TypeScript SDK.
 *
 * Mocks the global `fetch` to avoid needing a real server.
 */

import { AgentiumClient } from '../src/client';
import {
  AuthenticationError,
  NotFoundError,
  RateLimitError,
  ConstitutionalViolationError,
  ServerError,
  ValidationError,
} from '../src/errors';

// Helper to create a mock Response
function mockResponse(status: number, body: unknown, headers?: Record<string, string>): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

const BASE = 'http://testserver';

let fetchMock: jest.SpyInstance;

beforeEach(() => {
  fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse(200, {}));
});

afterEach(() => {
  fetchMock.mockRestore();
});

// ═══════════════════════════════════════════════════════════
// Health
// ═══════════════════════════════════════════════════════════

test('health returns status', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { status: 'healthy', timestamp: '2026-01-01T00:00:00' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const health = await client.health();
  expect(health.status).toBe('healthy');
});

// ═══════════════════════════════════════════════════════════
// Auth
// ═══════════════════════════════════════════════════════════

test('login stores token', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { access_token: 'jwt-abc' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE });
  const token = await client.login('admin', 'pass');
  expect(token).toBe('jwt-abc');
});

test('login failure throws AuthenticationError', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(401, { detail: 'Invalid credentials' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE });
  await expect(client.login('bad', 'wrong')).rejects.toThrow(AuthenticationError);
});

// ═══════════════════════════════════════════════════════════
// Agents
// ═══════════════════════════════════════════════════════════

test('listAgents returns agents', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, {
      agents: [
        { agentium_id: '00001', role: 'Head', status: 'active', tier: 0 },
        { agentium_id: '10001', role: 'Ethics', status: 'active', tier: 1 },
      ],
    }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const agents = await client.listAgents();
  expect(agents).toHaveLength(2);
  expect(agents[0].agentium_id).toBe('00001');
});

test('getAgent returns single agent', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { agentium_id: '00001', role: 'Head', status: 'active', tier: 0 }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const agent = await client.getAgent('00001');
  expect(agent.role).toBe('Head');
});

test('getAgent not found throws NotFoundError', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(404, { detail: 'Agent 99999 not found' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  await expect(client.getAgent('99999')).rejects.toThrow(NotFoundError);
});

// ═══════════════════════════════════════════════════════════
// Tasks
// ═══════════════════════════════════════════════════════════

test('createTask returns task', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { id: 't1', title: 'Test', status: 'pending' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const task = await client.createTask({ title: 'Test', description: 'desc' });
  expect(task.id).toBe('t1');
  expect(task.status).toBe('pending');
});

// ═══════════════════════════════════════════════════════════
// Constitution
// ═══════════════════════════════════════════════════════════

test('getConstitution returns constitution', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { version: 'v1.0.0', is_active: true, preamble: 'We the agents...' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const constitution = await client.getConstitution();
  expect(constitution.version).toBe('v1.0.0');
  expect(constitution.is_active).toBe(true);
});

// ═══════════════════════════════════════════════════════════
// Voting
// ═══════════════════════════════════════════════════════════

test('listVotes returns proposals', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, {
      proposals: [{ id: 'v1', title: 'Amend Art 3', status: 'active', votes_for: 2 }],
    }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const votes = await client.listVotes();
  expect(votes).toHaveLength(1);
  expect(votes[0].votes_for).toBe(2);
});

// ═══════════════════════════════════════════════════════════
// Webhooks
// ═══════════════════════════════════════════════════════════

test('createWebhookSubscription returns subscription', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { id: 'wh-1', url: 'https://example.com/hook', events: ['task.created'], is_active: true }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const sub = await client.createWebhookSubscription({
    url: 'https://example.com/hook',
    events: ['task.created'],
  });
  expect(sub.id).toBe('wh-1');
  expect(sub.is_active).toBe(true);
});

test('deleteWebhookSubscription succeeds', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(200, { status: 'deleted' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  const result = await client.deleteWebhookSubscription('wh-1');
  expect(result).toHaveProperty('status', 'deleted');
});

// ═══════════════════════════════════════════════════════════
// Error handling
// ═══════════════════════════════════════════════════════════

test('rate limit throws RateLimitError with retryAfter', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(429, { detail: 'Too many requests' }, { 'Retry-After': '30' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  try {
    await client.listAgents();
    fail('Expected RateLimitError');
  } catch (err) {
    expect(err).toBeInstanceOf(RateLimitError);
    expect((err as RateLimitError).retryAfter).toBe(30);
  }
});

test('constitutional violation throws ConstitutionalViolationError', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(403, { detail: 'Constitutional violation: action prohibited' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  await expect(
    client.createTask({ title: 'Bad', description: 'rm -rf /' }),
  ).rejects.toThrow(ConstitutionalViolationError);
});

test('server error throws ServerError', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(500, { detail: 'Internal error' }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  await expect(client.listAgents()).rejects.toThrow(ServerError);
});

test('validation error throws ValidationError', async () => {
  fetchMock.mockResolvedValueOnce(
    mockResponse(422, { detail: [{ msg: 'field required', loc: ['body', 'title'] }] }),
  );
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  await expect(
    client.createTask({ title: '', description: '' }),
  ).rejects.toThrow(ValidationError);
});

// ═══════════════════════════════════════════════════════════
// SDK Header verification
// ═══════════════════════════════════════════════════════════

test('X-SDK-Source header is sent on every request', async () => {
  fetchMock.mockResolvedValueOnce(mockResponse(200, { agents: [] }));
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'key' });
  await client.listAgents();

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [, init] = fetchMock.mock.calls[0];
  expect(init.headers['X-SDK-Source']).toBe('typescript-sdk');
});

test('API key is sent via X-API-Key header', async () => {
  fetchMock.mockResolvedValueOnce(mockResponse(200, { agents: [] }));
  const client = new AgentiumClient({ baseUrl: BASE, apiKey: 'my-secret' });
  await client.listAgents();

  const [, init] = fetchMock.mock.calls[0];
  expect(init.headers['X-API-Key']).toBe('my-secret');
});
