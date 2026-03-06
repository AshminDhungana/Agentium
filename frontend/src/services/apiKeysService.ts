/**
 * apiKeysService.ts
 *
 * Frontend service for extended API key management operations.
 * Covers the three backend endpoints not yet wired into the React layer:
 *   DELETE  /api/v1/api-keys/{key_id}
 *   GET     /api/v1/api-keys/{key_id}/spend-history
 *   POST    /api/v1/api-keys/test-failover
 */

import { api } from './api';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DeleteKeyResponse {
  success: boolean;
  message: string;
  key_id: string;
}

export interface SpendDay {
  date: string;
  cost_usd: number;
  tokens: number;
  requests: number;
}

export interface SpendHistoryResponse {
  key_id: string;
  provider: string;
  period_days: number;
  total_spend_usd: number;
  total_tokens: number;
  total_requests: number;
  daily_breakdown: SpendDay[];
}

export interface FailoverTestResponse {
  tested_provider: string;
  attempted_keys: number;
  successful_key_id: string | null;
  failed_keys: string[];
  latency_ms: number;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const apiKeysService = {
  /**
   * Soft-delete an API key configuration.
   *
   * By default only keys in cooldown / error state can be deleted.
   * Pass force=true to delete healthy keys (use with caution).
   */
  deleteKey: async (
    keyId: string,
    force = false,
  ): Promise<DeleteKeyResponse> => {
    const response = await api.delete<DeleteKeyResponse>(
      `/api/v1/api-keys/${keyId}`,
      { params: { force } },
    );
    return response.data;
  },

  /**
   * Retrieve daily spend history for a specific API key.
   *
   * @param keyId  UUID of the key
   * @param days   Look-back window in days (1–365, default 30)
   */
  getSpendHistory: async (
    keyId: string,
    days = 30,
  ): Promise<SpendHistoryResponse> => {
    const response = await api.get<SpendHistoryResponse>(
      `/api/v1/api-keys/${keyId}/spend-history`,
      { params: { days } },
    );
    return response.data;
  },

  /**
   * Test the failover mechanism for a provider without making real API calls.
   * Useful in the Models / Settings page to verify multi-key configuration.
   *
   * @param provider  Provider name string, e.g. "openai", "groq"
   */
  testFailover: async (provider: string): Promise<FailoverTestResponse> => {
    const response = await api.post<FailoverTestResponse>(
      '/api/v1/api-keys/test-failover',
      null,
      { params: { provider } },
    );
    return response.data;
  },
};