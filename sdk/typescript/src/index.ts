/**
 * Agentium TypeScript SDK
 *
 * Usage:
 *   import { AgentiumClient } from '@agentium/sdk';
 *
 *   const client = new AgentiumClient({ baseUrl: 'http://localhost:8000', apiKey: 'sk-...' });
 *   const agents = await client.listAgents();
 */

export { AgentiumClient } from './client';
export {
  AgentiumError,
  AuthenticationError,
  AuthorizationError,
  ConstitutionalViolationError,
  NotFoundError,
  RateLimitError,
  ValidationError,
  ServerError,
} from './errors';
export type {
  Agent,
  Task,
  Constitution,
  Vote,
  WebhookSubscription,
  WebhookDelivery,
  ChatResponse,
  HealthStatus,
  TokenStatus,
  AgentiumClientConfig,
  CreateTaskParams,
  UpdateConstitutionParams,
  CreateWebhookParams,
  WebhookEventType,
  LoginResponse,
} from './types';
