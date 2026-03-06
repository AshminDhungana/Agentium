// frontend/src/services/abTesting.ts
// API service layer for A/B Model Testing

import { api } from './api';

// ── Typed status enums (prevents passing invalid strings to the API) ───────────

export type ExperimentStatus =
  | 'draft'
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed';

// ── Response types ────────────────────────────────────────────────────────────

export interface ExperimentSummary {
  id: string;
  name: string;
  description: string;
  status: ExperimentStatus;
  models_tested: number;
  progress: number;
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ExperimentRun {
  id: string;
  model: string;
  config_id: string;
  iteration: number;
  status: RunStatus;
  tokens: number | null;
  latency_ms: number | null;
  cost_usd: number | null;
  quality_score: number | null;
  critic_plan_score: number | null;
  critic_code_score: number | null;
  critic_output_score: number | null;
  constitutional_violations: number;
  output_preview: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ModelComparison {
  config_id: string;
  model_name: string;
  avg_tokens: number;
  avg_cost_usd: number;
  avg_latency_ms: number;
  avg_quality_score: number;
  success_rate: number;
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
}

export interface ExperimentDetail extends ExperimentSummary {
  task_template: string;
  system_prompt: string | null;
  test_iterations: number;
  runs: ExperimentRun[];
  comparison: {
    winner: {
      config_id: string;
      model: string;
      reason: string;
      confidence: number;
    };
    model_comparisons: { models: ModelComparison[] };
    created_at: string | null;
  } | null;
}

export interface CreateExperimentPayload {
  name: string;
  task_template: string;
  config_ids: string[];
  description?: string;
  system_prompt?: string;
  iterations?: number;
}

export interface Recommendation {
  task_category: string;
  recommended_model: string;
  avg_quality_score: number;
  avg_cost_usd: number;
  avg_latency_ms: number;
  success_rate: number;
  sample_size: number;
  last_updated: string | null;
}

export interface ABTestingStats {
  total_experiments: number;
  completed_experiments: number;
  running_experiments: number;
  total_model_runs: number;
  cached_recommendations: number;
}

export interface PaginatedExperiments {
  items: ExperimentSummary[];
  total: number;
  limit: number;
  offset: number;
}

// ── API error normalizer ───────────────────────────────────────────────────────

function normalizeError(err: unknown): never {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as { response?: { data?: { detail?: string }; status?: number } };
    const detail = axiosErr.response?.data?.detail;
    const status = axiosErr.response?.status;
    throw new Error(detail ?? `Request failed with status ${status}`);
  }
  throw err;
}

// ── API client ────────────────────────────────────────────────────────────────

const BASE = '/api/v1/ab-testing';

export const abTestingApi = {
  createExperiment: (data: CreateExperimentPayload): Promise<ExperimentSummary> =>
    api.post(`${BASE}/experiments`, data).then(r => r.data).catch(normalizeError),

  listExperiments: (
    status?: ExperimentStatus,
    limit = 50,
    offset = 0,
  ): Promise<PaginatedExperiments> => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    return api.get(`${BASE}/experiments?${params}`).then(r => r.data).catch(normalizeError);
  },

  getExperiment: (id: string): Promise<ExperimentDetail> =>
    api.get(`${BASE}/experiments/${id}`).then(r => r.data).catch(normalizeError),

  cancelExperiment: (id: string): Promise<{ message: string }> =>
    api.post(`${BASE}/experiments/${id}/cancel`, {}).then(r => r.data).catch(normalizeError),

  deleteExperiment: (id: string): Promise<{ message: string }> =>
    api.delete(`${BASE}/experiments/${id}`).then(r => r.data).catch(normalizeError),

  getRecommendations: (
    taskCategory?: string,
  ): Promise<{ recommendations: Recommendation[]; total_categories: number }> => {
    const params = taskCategory ? `?task_category=${encodeURIComponent(taskCategory)}` : '';
    return api.get(`${BASE}/recommendations${params}`).then(r => r.data).catch(normalizeError);
  },

  // Quick test now returns a summary immediately; client polls for completion
  quickTest: (task: string, configIds: string[]): Promise<ExperimentSummary> =>
    api.post(`${BASE}/quick-test`, { task, config_ids: configIds }).then(r => r.data).catch(normalizeError),

  getStats: (): Promise<ABTestingStats> =>
    api.get(`${BASE}/stats`).then(r => r.data).catch(normalizeError),
};