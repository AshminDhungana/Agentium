import { api } from "./api";
import { MonitoringDashboard, ViolationReport } from "../types";

// ─── Reasoning Trace Types ────────────────────────────────────────────────────

export interface ReasoningTraceStep {
  step_id: string;
  phase: string;
  description: string;
  rationale: string | null;
  outcome: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  duration_ms: number;
  tokens_used: number;
}

export interface ReasoningTrace {
  trace_id: string;
  task_id: string;
  agent_id: string;
  agent_tier: number;
  goal: string;
  incarnation: number;
  current_phase: string;
  final_outcome: string | null;
  validation_passed: boolean | null;
  validation_notes: string | null;
  failure_reason: string | null;
  total_steps: number;
  total_tokens: number;
  total_duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
  steps: ReasoningTraceStep[];
}

export interface ReasoningTraceSummary {
  trace_id: string;
  agent_id: string;
  agent_tier: number;
  incarnation: number;
  current_phase: string;
  final_outcome: string | null;
  validation_passed: boolean | null;
  validation_notes: string | null;
  total_steps: number;
  steps_by_phase: Record<string, number>;
  total_tokens: number;
  total_duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentReasoningTracesResponse {
  agent_id: string;
  period_days: number;
  filters: {
    outcome: string | null;
    validation_failed: boolean | null;
  };
  stats: {
    total_traces: number;
    successful: number;
    failed: number;
    validation_passed: number;
    validation_failed: number;
    avg_duration_ms: number;
    avg_tokens_per_trace: number;
  };
  traces: ReasoningTrace[];
}

export interface ValidationFailuresResponse {
  period_days: number;
  total_failures: number;
  failures: Array<{
    trace_id: string;
    task_id: string;
    agent_id: string;
    agent_tier: number;
    current_phase: string;
    final_outcome: string | null;
    validation_passed: boolean | null;
    validation_notes: string | null;
    failure_reason: string | null;
    total_tokens: number;
    total_duration_ms: number;
    started_at: string | null;
    completed_at: string | null;
  }>;
  generated_at: string;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const monitoringService = {
  getDashboard: async (monitorId: string): Promise<MonitoringDashboard> => {
    const response = await api.get<MonitoringDashboard>(
      `/api/v1/monitoring/dashboard/${monitorId}`,
    );
    return response.data;
  },

  getAgentHealth: async (agentId: string): Promise<any> => {
    const response = await api.get(
      `/api/v1/monitoring/agents/${agentId}/health`,
    );
    return response.data;
  },

  /**
   * Fetch violations with optional filters.
   * Maps to GET /api/v1/monitoring/violations
   */
  getViolations: async (filters?: {
    status?: string;
    severity?: string;
    agentId?: string;
    days?: number;
    limit?: number;
  }): Promise<ViolationReport[]> => {
    const params = new URLSearchParams();
    if (filters?.status)   params.append("status",   filters.status);
    if (filters?.severity) params.append("severity", filters.severity);
    if (filters?.agentId)  params.append("agent_id", filters.agentId);
    if (filters?.days)     params.append("days",     String(filters.days));
    if (filters?.limit)    params.append("limit",    String(filters.limit));

    const query = params.toString() ? `?${params.toString()}` : "";
    const response = await api.get<{ violations: ViolationReport[] }>(
      `/api/v1/monitoring/violations${query}`,
    );
    return response.data.violations;
  },

  /**
   * Mark a violation as resolved with resolution notes.
   * Maps to PATCH /api/v1/monitoring/violations/{id}/resolve
   */
  resolveViolation: async (
    violationId: string,
    resolutionNotes: string,
  ): Promise<void> => {
    const params = new URLSearchParams();
    params.append("resolution_notes", resolutionNotes);

    await api.patch(
      `/api/v1/monitoring/violations/${violationId}/resolve?${params.toString()}`,
    );
  },

  reportViolation: async (data: {
    reporterId: string;
    violatorId: string;
    severity: string;
    violationType: string;
    description: string;
  }): Promise<ViolationReport> => {
    const params = new URLSearchParams();
    params.append("reporter_id", data.reporterId);
    params.append("violator_id", data.violatorId);
    params.append("severity", data.severity);
    params.append("violation_type", data.violationType);
    params.append("description", data.description);

    const response = await api.post<{ report: ViolationReport }>(
      `/api/v1/monitoring/report-violation?${params.toString()}`,
    );
    return response.data.report;
  },

  // ─── Reasoning Traces ──────────────────────────────────────────────────────

  /**
   * Fetch all reasoning traces for a specific task.
   * Returns the full 5-phase execution record including per-step rationale,
   * inputs/outputs, and outcome validation results.
   *
   * Maps to: GET /api/v1/monitoring/tasks/{task_id}/reasoning-trace
   */
  getTaskReasoningTrace: async (taskId: string): Promise<{
    task_id: string;
    trace_count: number;
    traces: ReasoningTrace[];
  }> => {
    const response = await api.get(
      `/api/v1/monitoring/tasks/${taskId}/reasoning-trace`,
    );
    return response.data;
  },

  /**
   * Lightweight summary of reasoning traces for a task.
   * Returns phase completion counts and validation results without full step
   * detail — suitable for dashboard widgets and task-list views.
   *
   * Maps to: GET /api/v1/monitoring/tasks/{task_id}/reasoning-trace/summary
   */
  getTaskReasoningTraceSummary: async (taskId: string): Promise<{
    task_id: string;
    trace_count: number;
    summaries: ReasoningTraceSummary[];
  }> => {
    const response = await api.get(
      `/api/v1/monitoring/tasks/${taskId}/reasoning-trace/summary`,
    );
    return response.data;
  },

  /**
   * Fetch recent reasoning traces for a specific agent with optional filters.
   *
   * @param agentId          Agent ID string
   * @param days             Look-back window in days (1–90, default 7)
   * @param outcome          Filter by "success" or "failure"
   * @param validationFailed If true, only return traces where validation failed
   * @param limit            Max traces to return (1–100, default 20)
   *
   * Maps to: GET /api/v1/monitoring/agents/{agent_id}/reasoning-traces
   */
  getAgentReasoningTraces: async (
    agentId: string,
    options: {
      days?: number;
      outcome?: 'success' | 'failure';
      validationFailed?: boolean;
      limit?: number;
    } = {},
  ): Promise<AgentReasoningTracesResponse> => {
    const params = new URLSearchParams();
    if (options.days !== undefined)             params.append('days', String(options.days));
    if (options.outcome)                        params.append('outcome', options.outcome);
    if (options.validationFailed !== undefined) params.append('validation_failed', String(options.validationFailed));
    if (options.limit !== undefined)            params.append('limit', String(options.limit));

    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get<AgentReasoningTracesResponse>(
      `/api/v1/monitoring/agents/${agentId}/reasoning-traces${query}`,
    );
    return response.data;
  },

  /**
   * Return recent traces where outcome validation failed across all agents.
   * Use to identify systematic reasoning or generation failures.
   *
   * @param days   Look-back window in days (1–30, default 1)
   * @param limit  Max failures to return (1–200, default 50)
   *
   * Maps to: GET /api/v1/monitoring/reasoning-traces/validation-failures
   */
  getValidationFailures: async (
    days = 1,
    limit = 50,
  ): Promise<ValidationFailuresResponse> => {
    const response = await api.get<ValidationFailuresResponse>(
      '/api/v1/monitoring/reasoning-traces/validation-failures',
      { params: { days, limit } },
    );
    return response.data;
  },
};