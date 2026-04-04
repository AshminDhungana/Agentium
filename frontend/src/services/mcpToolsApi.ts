/**
 * mcpToolsApi.ts
 *
 * Centralised service for MCP (Model Context Protocol) tool operations.
 */

import { api } from './api';

const BASE = '/api/v1/mcp-tools';

// ─── Types ────────────────────────────────────────────────────────────────────

export type MCPApprovalStatus = 'pending' | 'approved' | 'revoked' | 'rejected';
export type MCPTierAccess = 'tier1' | 'tier2' | 'tier3' | 'all';

export interface MCPTool {
  id: string;
  name: string;
  description: string;
  server_url: string;
  approval_status: MCPApprovalStatus;
  tier_access: MCPTierAccess;
  proposed_by: string;
  approved_by: string | null;
  created_at: string;
  approved_at: string | null;
  revoked_at: string | null;
  invocation_count: number;
  last_invoked_at: string | null;
  schema: Record<string, unknown> | null;
}

export interface MCPToolAuditEntry {
  id: string;
  tool_id: string;
  agent_id: string;
  invoked_at: string;
  input_hash: string;
  outcome: 'success' | 'failure' | 'blocked';
  error_message: string | null;
}

export interface MCPToolHealth {
  tool_id: string;
  reachable: boolean;
  latency_ms: number | null;
  last_checked_at: string;
  error: string | null;
}

export interface ProposeMCPToolRequest {
  name: string;
  description: string;
  server_url: string;
  tier_access?: MCPTierAccess;
  schema?: Record<string, unknown>;
}

// ─── Phase 15.2: Stats types ──────────────────────────────────────────────────

/** Real-time per-tool invocation stats read from Redis. */
export interface MCPToolStats {
  /** DB UUID of the tool */
  tool_id: string;
  /** Human-readable tool name — only present on per-tool endpoint */
  tool_name?: string;
  /** Total number of invocations recorded */
  invocation_count: number;
  /** Total number of failed invocations */
  error_count: number;
  /** Rolling average latency in milliseconds */
  avg_latency_ms: number;
  /** Error rate: 0.0 – 1.0 (divide by 100 for percentage) */
  error_rate: number;
  /** Unix timestamp of last invocation (null if never invoked) */
  last_used_ts: number | null;
}

export interface MCPStatsHealthResponse {
  status: 'healthy' | 'unavailable';
  redis_version?: string;
  tools_with_stats?: number;
  error?: string;
}

export interface MCPRevokedResponse {
  revoked_tool_ids: string[];
  count: number;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const mcpToolsApi = {
  /** List all registered MCP tools. */
  listTools: async (): Promise<MCPTool[]> => {
    const response = await api.get<MCPTool[]>(BASE);
    return response.data;
  },

  /**
   * Fetch a single MCP tool by its ID.
   */
  getTool: async (toolId: string): Promise<MCPTool> => {
    const response = await api.get<MCPTool>(`${BASE}/${toolId}`);
    return response.data;
  },

  /** Propose a new MCP tool for council approval. */
  proposeTool: async (request: ProposeMCPToolRequest): Promise<MCPTool> => {
    const response = await api.post<MCPTool>(BASE, request);
    return response.data;
  },

  /** Approve a pending MCP tool (admin / council action). */
  approveTool: async (toolId: string): Promise<MCPTool> => {
    const response = await api.post<MCPTool>(`${BASE}/${toolId}/approve`);
    return response.data;
  },

  /** Revoke an approved MCP tool. */
  revokeTool: async (toolId: string): Promise<MCPTool> => {
    const response = await api.post<MCPTool>(`${BASE}/${toolId}/revoke`);
    return response.data;
  },

  /** Fetch the invocation audit trail for a specific tool. */
  getToolAudit: async (
    toolId: string,
    limit = 100,
  ): Promise<MCPToolAuditEntry[]> => {
    const response = await api.get<MCPToolAuditEntry[]>(
      `${BASE}/${toolId}/audit`,
      { params: { limit } },
    );
    return response.data;
  },

  /** Check connectivity and latency for a specific tool's server. */
  getToolHealth: async (toolId: string): Promise<MCPToolHealth> => {
    const response = await api.get<MCPToolHealth>(`${BASE}/${toolId}/health`);
    return response.data;
  },

  // ─── Phase 15.2: Real-time stats ──────────────────────────────────────────

  /**
   * Fetch real-time invocation stats for ALL tools from Redis.
   * Response time target: <50 ms (pure Redis read, no DB query).
   *
   * Used by MCPToolRegistry to populate the stats columns on initial load
   * and after WebSocket reconnect.
   */
  getStats: async (): Promise<MCPToolStats[]> => {
    const response = await api.get<MCPToolStats[]>(`${BASE}/stats`);
    return response.data;
  },

  /**
   * Fetch real-time invocation stats for a SINGLE tool.
   * Returns zero values if the tool has never been invoked.
   */
  getToolStats: async (toolId: string): Promise<MCPToolStats> => {
    const response = await api.get<MCPToolStats>(`${BASE}/${toolId}/stats`);
    return response.data;
  },

  /**
   * Check health of the Redis stats layer.
   * Use this to verify connectivity before relying on stats data.
   */
  getStatsHealth: async (): Promise<MCPStatsHealthResponse> => {
    const response = await api.get<MCPStatsHealthResponse>(`${BASE}/stats/health`);
    return response.data;
  },

  /**
   * Return all tool IDs currently in the Redis revocation SET.
   * Admin / Sovereign only.
   */
  getRevoked: async (): Promise<MCPRevokedResponse> => {
    const response = await api.get<MCPRevokedResponse>(`${BASE}/revoked`);
    return response.data;
  },
};