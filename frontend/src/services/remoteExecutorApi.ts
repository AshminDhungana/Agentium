/**
 * remoteExecutorApi.ts
 *
 * Frontend service for the Remote Code Executor (Phase 6.6 — Brains vs Hands).
 * Covers four backend routes not yet wired into the React layer:
 *   GET    /api/v1/remote-executor/sandboxes
 *   POST   /api/v1/remote-executor/sandboxes
 *   DELETE /api/v1/remote-executor/sandboxes/{sandbox_id}
 *   GET    /api/v1/remote-executor/executions/{execution_id}
 *
 * The existing POST /remote-executor/execute is already consumed by the
 * agent orchestrator and does not need a separate frontend binding.
 */

import { api } from './api';

const BASE = '/api/v1/remote-executor';

// ─── Types ────────────────────────────────────────────────────────────────────

export type SandboxStatus = 'creating' | 'ready' | 'busy' | 'stopped' | 'error';

export interface SandboxRecord {
  id: string;
  name: string | null;
  status: SandboxStatus;
  language: string;
  memory_limit_mb: number;
  cpu_limit: number;
  network_access: boolean;
  created_at: string;
  last_used_at: string | null;
  execution_count: number;
}

export interface CreateSandboxRequest {
  name?: string;
  language?: string;
  memory_limit_mb?: number;
  cpu_limit?: number;
  network_access?: boolean;
}

export interface ExecutionRecord {
  id: string;
  sandbox_id: string | null;
  agent_id: string;
  task_id: string | null;
  language: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout';
  exit_code: number | null;
  stdout_summary: string | null;
  stderr_summary: string | null;
  execution_time_ms: number | null;
  memory_used_mb: number | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const remoteExecutorApi = {
  /**
   * List all persistent sandboxes visible to the current user.
   * Used by the Execution / Developer panel to manage sandbox lifecycle.
   */
  listSandboxes: async (): Promise<SandboxRecord[]> => {
    const response = await api.get<SandboxRecord[]>(`${BASE}/sandboxes`);
    return response.data;
  },

  /**
   * Create a new persistent sandbox.
   * Returns the sandbox record once the container is provisioned.
   *
   * @param request  Configuration options — all fields are optional.
   */
  createSandbox: async (
    request: CreateSandboxRequest = {},
  ): Promise<SandboxRecord> => {
    const response = await api.post<SandboxRecord>(`${BASE}/sandboxes`, request);
    return response.data;
  },

  /**
   * Destroy a persistent sandbox and release its container resources.
   *
   * @param sandboxId  UUID of the sandbox to delete.
   */
  deleteSandbox: async (
    sandboxId: string,
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.delete<{ success: boolean; message: string }>(
      `${BASE}/sandboxes/${sandboxId}`,
    );
    return response.data;
  },

  /**
   * Fetch the full record for a specific code execution, including
   * stdout/stderr summaries and timing.
   *
   * @param executionId  UUID of the execution record.
   */
  getExecution: async (executionId: string): Promise<ExecutionRecord> => {
    const response = await api.get<ExecutionRecord>(
      `${BASE}/executions/${executionId}`,
    );
    return response.data;
  },
};