/**
 * Custom error classes for the Agentium TypeScript SDK.
 */

export class AgentiumError extends Error {
  public readonly statusCode?: number;
  public readonly detail: Record<string, unknown>;

  constructor(message: string, statusCode?: number, detail?: Record<string, unknown>) {
    super(message);
    this.name = 'AgentiumError';
    this.statusCode = statusCode;
    this.detail = detail ?? {};
  }
}

export class AuthenticationError extends AgentiumError {
  constructor(message = 'Authentication failed', detail?: Record<string, unknown>) {
    super(message, 401, detail);
    this.name = 'AuthenticationError';
  }
}

export class AuthorizationError extends AgentiumError {
  constructor(message = 'Insufficient permissions', detail?: Record<string, unknown>) {
    super(message, 403, detail);
    this.name = 'AuthorizationError';
  }
}

export class ConstitutionalViolationError extends AgentiumError {
  constructor(message = 'Constitutional violation', detail?: Record<string, unknown>) {
    super(message, 403, detail);
    this.name = 'ConstitutionalViolationError';
  }
}

export class NotFoundError extends AgentiumError {
  constructor(message = 'Resource not found', detail?: Record<string, unknown>) {
    super(message, 404, detail);
    this.name = 'NotFoundError';
  }
}

export class ValidationError extends AgentiumError {
  constructor(message = 'Validation error', detail?: Record<string, unknown>) {
    super(message, 422, detail);
    this.name = 'ValidationError';
  }
}

export class RateLimitError extends AgentiumError {
  public readonly retryAfter?: number;

  constructor(message = 'Rate limit exceeded', retryAfter?: number, detail?: Record<string, unknown>) {
    super(message, 429, detail);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}

export class ServerError extends AgentiumError {
  constructor(message = 'Server error', statusCode = 500, detail?: Record<string, unknown>) {
    super(message, statusCode, detail);
    this.name = 'ServerError';
  }
}
