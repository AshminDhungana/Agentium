/**
 * TypeScript interfaces mirroring the Agentium backend models.
 *
 * This file combines:
 * 1. Manual SDK-specific types (config, event types, etc.)
 * 2. Re-exports of generated OpenAPI types where they match SDK needs
 * 3. Convenience aliases for commonly used generated types
 */

// ─────────────────────────────────────────────────────────────────
// Re-export generated OpenAPI types
// ─────────────────────────────────────────────────────────────────

// Export all types from generated-types for consumers who want full access
export * from './generated-types';

// ─────────────────────────────────────────────────────────────────
// Import generated schema types for convenience aliases
// ─────────────────────────────────────────────────────────────────

import type { components } from './generated-types';

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
// Manual type definitions (matching SDK client usage)
// These mirror the OpenAPI schemas but provide stable, documented interfaces
// ─────────────────────────────────────────────────────────────────

export interface Agent {
  id?: string;
  agentium_id: string;
  role: string;
  status: string;
  tier: number;
  current_task?: string | null;
  performance_score?: number | null;
  supervised_by?: string | null;
  total_tasks_completed?: number;
  successful_tasks?: number;
  failed_tasks?: number;
  is_persistent?: boolean;
  responsibilities?: string | null;
  created_at?: string | null;
  last_active?: string | null;
  [key: string]: unknown;
}

export interface Task {
  id?: string;
  title?: string;
  description?: string;
  status: string;
  priority?: string | null;
  task_type?: string | null;
  assigned_to?: string | null;
  created_by?: string | null;
  result?: string | null;
  error?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  [key: string]: unknown;
}

export interface CreateTaskParams {
  title: string;
  description: string;
  priority?: string;
  [key: string]: unknown;
}

export interface Constitution {
  id?: string;
  agentium_id?: string;
  version: string;
  version_number?: number;
  preamble?: string | null;
  articles?: Record<string, unknown> | null;
  prohibited_actions?: string[] | null;
  sovereign_preferences?: Record<string, unknown> | null;
  is_active: boolean;
  effective_date?: string | null;
  changelog?: Array<Record<string, unknown>> | null;
  [key: string]: unknown;
}

export interface UpdateConstitutionParams {
  preamble?: string;
  articles?: Record<string, unknown>;
  prohibited_actions?: string[];
  sovereign_preferences?: Record<string, unknown>;
}

export interface Vote {
  id?: string;
  proposal_type?: string;
  title?: string;
  description?: string;
  status: string;
  proposed_by?: string;
  votes_for?: number;
  votes_against?: number;
  votes_abstain?: number;
  quorum_required?: number;
  deadline?: string | null;
  created_at?: string | null;
  resolved_at?: string | null;
  [key: string]: unknown;
}

export interface WebhookSubscription {
  id?: string;
  url: string;
  events: string[];
  secret?: string | null;
  is_active: boolean;
  description?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

export interface CreateWebhookParams {
  url: string;
  events: string[];
  secret?: string;
  description?: string;
}

export interface WebhookDelivery {
  id?: string;
  subscription_id?: string;
  event_type: string;
  payload?: Record<string, unknown> | null;
  status_code?: number | null;
  attempts?: number;
  delivered_at?: string | null;
  error?: string | null;
  [key: string]: unknown;
}

export interface ChatMessage {
  content: string;
  agent_id?: string;
}

export interface ChatResponse {
  message?: string;
  agent_id?: string;
  task_id?: string;
  response?: string;
  [key: string]: unknown;
}

export interface HealthStatus {
  status: string;
  database?: Record<string, unknown>;
  timestamp?: string;
}

export interface TokenStatus {
  optimizer?: Record<string, unknown>;
  idle_budget?: Record<string, unknown>;
  mode: string;
}

export interface LoginResponse {
  access_token: string;
  [key: string]: unknown;
}

// ─────────────────────────────────────────────────────────────────
// Convenience type aliases for generated OpenAPI schema types
// These provide direct access to the generated schemas when needed
// ─────────────────────────────────────────────────────────────────

/**
 * Alias for generated TaskResponse schema from OpenAPI
 * Use when you need the exact API response shape
 */
export type GeneratedTaskResponse = components['schemas']['TaskResponse'];

/**
 * Alias for generated TaskCreate schema from OpenAPI
 */
export type GeneratedTaskCreate = components['schemas']['TaskCreate'];

/**
 * Alias for generated AgentSpawnRequest schema from OpenAPI
 */
export type GeneratedAgentSpawnRequest = components['schemas']['AgentSpawnRequest'];

/**
 * Alias for generated ConstitutionUpdateRequest schema from OpenAPI
 */
export type GeneratedConstitutionUpdateRequest = components['schemas']['ConstitutionUpdateRequest'];

/**
 * Alias for generated VoteCast schema from OpenAPI
 */
export type GeneratedVoteCast = components['schemas']['VoteCast'];

/**
 * Alias for generated VoteRequest schema from OpenAPI
 */
export type GeneratedVoteRequest = components['schemas']['VoteRequest'];

/**
 * Alias for generated WebhookWithSecretResponse schema from OpenAPI
 */
export type GeneratedWebhookWithSecretResponse = components['schemas']['WebhookWithSecretResponse'];

/**
 * Alias for generated CreateWebhookRequest schema from OpenAPI
 */
export type GeneratedCreateWebhookRequest = components['schemas']['CreateWebhookRequest'];

/**
 * Alias for generated HealthReportResponse schema from OpenAPI
 */
export type GeneratedHealthReportResponse = components['schemas']['HealthReportResponse'];

/**
 * Alias for generated LoginResponse schema from OpenAPI
 */
export type GeneratedLoginResponse = components['schemas']['LoginResponse'];