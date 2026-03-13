/**
 * Agentium TypeScript SDK — fully typed HTTP client.
 *
 * Every request includes `X-SDK-Source: typescript-sdk` so that audit
 * trails are identical to direct API calls.
 */

import {
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
  LoginResponse,
} from './types';

import {
  AgentiumError,
  AuthenticationError,
  AuthorizationError,
  ConstitutionalViolationError,
  NotFoundError,
  RateLimitError,
  ValidationError,
  ServerError,
} from './errors';

const SDK_HEADER = 'X-SDK-Source';
const SDK_VALUE = 'typescript-sdk';

export class AgentiumClient {
  private readonly baseUrl: string;
  private apiKey?: string;
  private token?: string;
  private readonly timeout: number;

  constructor(config: AgentiumClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, '');
    this.apiKey = config.apiKey;
    this.token = config.token;
    this.timeout = config.timeout ?? 30000;
  }

  // ── Authentication ───────────────────────────────────────

  async login(username: string, password: string): Promise<string> {
    const data = await this.request<LoginResponse>('POST', '/api/v1/auth/login', {
      body: { username, password },
      skipAuth: true,
    });
    this.token = data.access_token;
    return this.token;
  }

  // ── Agent endpoints ──────────────────────────────────────

  async listAgents(params?: { tier?: number; status?: string }): Promise<Agent[]> {
    const query: Record<string, string> = {};
    if (params?.tier !== undefined) query.tier = String(params.tier);
    if (params?.status) query.status = params.status;
    const data = await this.request<{ agents: Agent[] }>('GET', '/api/v1/agents', { query });
    return data.agents ?? [];
  }

  async getAgent(agentiumId: string): Promise<Agent> {
    return this.request<Agent>('GET', `/api/v1/agents/${agentiumId}`);
  }

  async createAgent(role: string, responsibilities: string[], tier = 3): Promise<Agent> {
    return this.request<Agent>('POST', '/api/v1/agents/create', {
      query: { role, tier: String(tier) },
      body: responsibilities,
    });
  }

  // ── Task endpoints ───────────────────────────────────────

  async listTasks(params?: { status?: string; limit?: number }): Promise<Task[]> {
    const query: Record<string, string> = {};
    if (params?.status) query.status = params.status;
    if (params?.limit) query.limit = String(params.limit);
    const data = await this.request<{ tasks: Task[] }>('GET', '/api/v1/tasks', { query });
    return data.tasks ?? [];
  }

  async getTask(taskId: string): Promise<Task> {
    return this.request<Task>('GET', `/api/v1/tasks/${taskId}`);
  }

  async createTask(params: CreateTaskParams): Promise<Task> {
    return this.request<Task>('POST', '/api/v1/tasks', { body: params });
  }

  // ── Constitution endpoints ───────────────────────────────

  async getConstitution(): Promise<Constitution> {
    return this.request<Constitution>('GET', '/api/v1/constitution');
  }

  async updateConstitution(params: UpdateConstitutionParams): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('POST', '/api/v1/constitution/update', {
      body: params,
    });
  }

  // ── Voting endpoints ─────────────────────────────────────

  async listVotes(status?: string): Promise<Vote[]> {
    const query: Record<string, string> = {};
    if (status) query.status = status;
    const data = await this.request<{ proposals: Vote[] }>('GET', '/api/v1/voting/proposals', { query });
    return data.proposals ?? [];
  }

  async castVote(proposalId: string, vote: string, reason?: string): Promise<Record<string, unknown>> {
    const body: Record<string, unknown> = { vote };
    if (reason) body.reason = reason;
    return this.request<Record<string, unknown>>('POST', `/api/v1/voting/proposals/${proposalId}/vote`, { body });
  }

  // ── Chat endpoints ───────────────────────────────────────

  async sendMessage(content: string, agentId?: string): Promise<ChatResponse> {
    const body: Record<string, unknown> = { content };
    if (agentId) body.agent_id = agentId;
    return this.request<ChatResponse>('POST', '/api/v1/chat/send', { body });
  }

  // ── Webhook subscription endpoints ───────────────────────

  async listWebhookSubscriptions(): Promise<WebhookSubscription[]> {
    const data = await this.request<{ subscriptions: WebhookSubscription[] }>('GET', '/api/v1/webhooks/subscriptions');
    return data.subscriptions ?? [];
  }

  async createWebhookSubscription(params: CreateWebhookParams): Promise<WebhookSubscription> {
    return this.request<WebhookSubscription>('POST', '/api/v1/webhooks/subscriptions', { body: params });
  }

  async updateWebhookSubscription(id: string, params: Partial<CreateWebhookParams>): Promise<WebhookSubscription> {
    return this.request<WebhookSubscription>('PUT', `/api/v1/webhooks/subscriptions/${id}`, { body: params });
  }

  async deleteWebhookSubscription(id: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('DELETE', `/api/v1/webhooks/subscriptions/${id}`);
  }

  async getWebhookDeliveries(subscriptionId: string, limit = 50): Promise<WebhookDelivery[]> {
    const data = await this.request<{ deliveries: WebhookDelivery[] }>(
      'GET',
      `/api/v1/webhooks/subscriptions/${subscriptionId}/deliveries`,
      { query: { limit: String(limit) } },
    );
    return data.deliveries ?? [];
  }

  async testWebhook(subscriptionId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>('POST', `/api/v1/webhooks/subscriptions/${subscriptionId}/test`);
  }

  // ── Health / Status ──────────────────────────────────────

  async health(): Promise<HealthStatus> {
    return this.request<HealthStatus>('GET', '/api/health', { skipAuth: true });
  }

  async tokenStatus(): Promise<TokenStatus> {
    return this.request<TokenStatus>('GET', '/api/v1/status/tokens');
  }

  // ══════════════════════════════════════════════════════════
  // Internal helpers
  // ══════════════════════════════════════════════════════════

  private buildHeaders(skipAuth = false): Record<string, string> {
    const headers: Record<string, string> = {
      [SDK_HEADER]: SDK_VALUE,
      'Content-Type': 'application/json',
    };
    if (!skipAuth) {
      if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
      if (this.apiKey) headers['X-API-Key'] = this.apiKey;
    }
    return headers;
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      query?: Record<string, string>;
      body?: unknown;
      skipAuth?: boolean;
    },
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (options?.query && Object.keys(options.query).length > 0) {
      const qs = new URLSearchParams(options.query).toString();
      url += `?${qs}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const init: RequestInit = {
        method,
        headers: this.buildHeaders(options?.skipAuth),
        signal: controller.signal,
      };

      if (options?.body !== undefined && method !== 'GET') {
        init.body = JSON.stringify(options.body);
      }

      const response = await fetch(url, init);
      return await this.handleResponse<T>(response);
    } catch (err) {
      if (err instanceof AgentiumError) throw err;
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new AgentiumError('Request timed out');
      }
      throw new AgentiumError(`Connection error: ${err}`);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (response.ok) {
      try {
        return (await response.json()) as T;
      } catch {
        return { raw: await response.text() } as unknown as T;
      }
    }

    let detail: Record<string, unknown> = {};
    let message = `HTTP ${response.status}`;

    try {
      const body = await response.json();
      if (typeof body === 'object' && body !== null) {
        detail = body as Record<string, unknown>;
        const rawDetail = (body as Record<string, unknown>).detail ?? (body as Record<string, unknown>).message;
        if (Array.isArray(rawDetail)) {
          message = rawDetail.map(String).join('; ');
        } else if (typeof rawDetail === 'string') {
          message = rawDetail;
        }
      }
    } catch {
      message = (await response.text()) || message;
    }

    const status = response.status;

    if (status === 401) throw new AuthenticationError(message, detail);
    if (status === 403) {
      if (message.toLowerCase().includes('constitutional') || message.toLowerCase().includes('constitution')) {
        throw new ConstitutionalViolationError(message, detail);
      }
      throw new AuthorizationError(message, detail);
    }
    if (status === 404) throw new NotFoundError(message, detail);
    if (status === 422) throw new ValidationError(message, detail);
    if (status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      throw new RateLimitError(message, retryAfter ? Number(retryAfter) : undefined, detail);
    }
    if (status >= 500) throw new ServerError(message, status, detail);

    throw new AgentiumError(message, status, detail);
  }
}
