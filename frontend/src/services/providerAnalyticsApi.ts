/**
 * providerAnalyticsApi.ts — Provider Analytics Service
 *
 * Consolidates the provider analytics calls previously made inline inside
 * ProviderAnalytics.tsx and adds the previously missing endpoint:
 *
 *   GET /api/v1/provider-analytics/latency-percentiles   (NEW)
 *
 * Existing endpoints now have a typed service home:
 *   GET /api/v1/provider-analytics/summary
 *   GET /api/v1/provider-analytics/cost-over-time
 *   GET /api/v1/provider-analytics/model-breakdown
 */

import { api } from './api';

const BASE = '/api/v1/provider-analytics';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ProviderSummary {
  provider: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate_pct: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
  avg_cost_per_request: number;
}

export interface DailyCostEntry {
  date: string;
  provider: string;
  cost_usd: number;
  requests: number;
  tokens: number;
}

export interface ModelBreakdown {
  provider: string;
  model: string;
  total_requests: number;
  successful_requests: number;
  success_rate_pct: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
  cost_per_1k_tokens: number;
}

export interface LatencyPercentile {
  provider: string;
  avg_ms: number;
  min_ms: number;
  max_ms: number;
  /** Approximate P50 computed server-side from a representative sample. */
  sample_count: number;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const providerAnalyticsApi = {
  /**
   * Aggregated per-provider stats over the given look-back window.
   * Used by the ProviderAnalytics dashboard card.
   *
   * @param days  1–365 (default 30)
   */
  getSummary: async (days = 30): Promise<ProviderSummary[]> => {
    const response = await api.get<{ providers: ProviderSummary[]; period_days: number }>(
      `${BASE}/summary`,
      { params: { days } },
    );
    // Backend returns top-level array or a wrapper depending on version
    const data = response.data as any;
    return Array.isArray(data) ? data : data.providers ?? [];
  },

  /**
   * Daily cost breakdown per provider.
   *
   * @param days  1–14 (default 14 — backend caps at 14 days for this view)
   */
  getCostOverTime: async (days = 14): Promise<DailyCostEntry[]> => {
    const response = await api.get<DailyCostEntry[]>(
      `${BASE}/cost-over-time`,
      { params: { days: Math.min(days, 14) } },
    );
    return response.data;
  },

  /**
   * Per-model usage and cost breakdown.
   *
   * @param days      1–365 (default 30)
   * @param provider  Optional filter, e.g. "openai"
   */
  getModelBreakdown: async (days = 30, provider?: string): Promise<{
    period_days: number;
    models: ModelBreakdown[];
    generated_at: string;
  }> => {
    const response = await api.get(
      `${BASE}/model-breakdown`,
      { params: { days, ...(provider ? { provider } : {}) } },
    );
    return response.data;
  },

  /**
   * Per-provider latency: avg, min, max, and approximate P50.
   *
   * Previously missing from the frontend — added to support the latency
   * comparison chart in the Models / Analytics panel.
   *
   * Maps to: GET /api/v1/provider-analytics/latency-percentiles
   *
   * @param days  1–30 (default 7)
   */
  getLatencyPercentiles: async (days = 7): Promise<{
    period_days: number;
    providers: LatencyPercentile[];
    generated_at: string;
  }> => {
    const response = await api.get(
      `${BASE}/latency-percentiles`,
      { params: { days } },
    );
    return response.data;
  },
};