/**
 * mcpToolsApi.ts
 *
 * Centralised service for MCP (Model Context Protocol) tool operations.
 *
 * The MCPToolRegistry component previously called the API inline.
 * This file consolidates all MCP tool calls and adds the missing
 *   GET /api/v1/mcp-tools/{tool_id}
 * endpoint that was not yet reachable from the frontend.
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

// ─── Service ──────────────────────────────────────────────────────────────────

export const mcpToolsApi = {
  /** List all registered MCP tools. */
  listTools: async (): Promise<MCPTool[]> => {
    const response = await api.get<MCPTool[]>(BASE);
    return response.data;
  },

  /**
   * Fetch a single MCP tool by its ID.
   * Previously missing from the frontend — added to support detail modals
   * and audit drill-downs in MCPToolRegistry.
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
};