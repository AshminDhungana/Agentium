/**
 * plugins.ts — Plugin Marketplace Service
 *
 * Covers /api/v1/plugins/* (the plugin marketplace) and also exposes a
 * helper for the Tool Creation Marketplace endpoint:
 *
 *   POST /api/v1/tools/marketplace/{tool_name}/update-listing   (NEW)
 *
 * This endpoint refreshes a tool's marketplace listing to its current
 * active version — useful in the ToolMarketplacePage after a tool update.
 */

import { api } from './api';
import type {
  MarketplaceListing,
  MarketplaceBrowseParams,
  MarketplaceResult,
  ToolListResponse,
  VoteChoice,
  PublishListingRequest,
  ImportToolResponse,
  FinalizeImportRequest,
  FinalizeImportResponse,
  RateToolRequest,
  YankListingRequest,
  VoteRequest,
  ProposeToolRequest,
  ExecuteToolRequest,
  DeprecateRequest,
  ScheduleSunsetRequest,
  ExecuteSunsetRequest,
  RestoreToolRequest,
  ProposeUpdateRequest,
  ApproveUpdateRequest,
  RollbackRequest,
  AnalyticsReport,
  ToolStats,
  ErrorsResponse,
  AgentUsageResponse,
  ApiActionResponse,
} from '../types/toolManagement';

export interface PluginItem {
    id: string;
    name: string;
    description: string;
    author: string;
    version: string;
    plugin_type: string;
    rating: number;
    install_count: number;
    status?: string;
}

export interface UpdateListingResult {
    updated: boolean;
    tool_name: string;
    listing_id?: string;
    version_tag?: string;
    code_hash?: string;
    error?: string;
}

// ─── Plugin Marketplace (/api/v1/plugins) ─────────────────────────────────────

const pluginMarketplaceService = {
    /**
     * List published plugins with optional full-text search and type filter.
     * Uses axios `params` for query-string serialisation — avoids manually
     * appending URLSearchParams to the path string.
     */
    async listPlugins(query?: string, typeFilter?: string): Promise<PluginItem[]> {
        const response = await api.get('/api/v1/plugins', {
            params: {
                ...(query ? { query } : {}),
                ...(typeFilter ? { type_filter: typeFilter } : {}),
            },
        });
        return response.data;
    },

    async submitPlugin(payload: {
        name: string;
        description: string;
        author: string;
        version: string;
        plugin_type: string;
        entry_point: string;
        source_url?: string;
        config_schema?: Record<string, unknown>;
        dependencies?: string[];
    }): Promise<{ id: string; status: string }> {
        const response = await api.post('/api/v1/plugins', payload);
        return response.data;
    },

    async installPlugin(
        pluginId: string,
        config: Record<string, unknown>,
    ): Promise<{ id: string; is_active: boolean }> {
        const response = await api.post(`/api/v1/plugins/${pluginId}/install`, { config });
        return response.data;
    },

    async submitReview(
        pluginId: string,
        rating: number,
        reviewText?: string,
    ): Promise<{ id: string; rating: number }> {
        const response = await api.post(`/api/v1/plugins/${pluginId}/reviews`, {
            rating,
            review_text: reviewText,
        });
        return response.data;
    },

    async verifyPlugin(pluginId: string): Promise<{ id: string; status: string }> {
        const response = await api.post(`/api/v1/plugins/${pluginId}/verify`);
        return response.data;
    },

    async publishPlugin(pluginId: string): Promise<{ id: string; status: string }> {
        const response = await api.post(`/api/v1/plugins/${pluginId}/publish`);
        return response.data;
    },
};

// ─── Tool Creation Marketplace (/api/v1/tools/marketplace) ────────────────────
//
// Separate from the plugin marketplace above — these tools are created via the
// ToolCreationService and council-approved workflow, not the plugin registry.

const toolCreationMarketplaceService = {
    /**
     * Refresh a marketplace listing to the tool's current active version.
     *
     * Only Head (0xxxx) or Council (1xxxx) agents can call this endpoint.
     * Call this after updating a tool to keep the marketplace listing
     * in sync with the latest approved version.
     *
     * Maps to: POST /api/v1/tools/marketplace/{tool_name}/update-listing
     */
    async updateListing(toolName: string): Promise<UpdateListingResult> {
        const response = await api.post<UpdateListingResult>(
            `/api/v1/tools/marketplace/${encodeURIComponent(toolName)}/update-listing`,
        );
        return response.data;
    },
};

// ─── Tool Management API (/api/v1/tool-management) ─────────────────────────────
//
// Comprehensive API for tool management including marketplace, versioning,
// deprecation, and analytics. Replaces the local callApi wrapper in
// ToolMarketplacePage with fully typed service calls.

const BASE = '/api/v1/tool-management';
const mkt = (path = '') => `${BASE}/marketplace${path}`;
const tool = (name: string, path = '') => `${BASE}/${encodeURIComponent(name)}${path}`;

export const toolManagementApi = {
  // ── Marketplace ───────────────────────────────────────────────────────────
  
  /** Browse marketplace listings with filters and pagination */
  browseMarketplace: (params: MarketplaceBrowseParams) =>
    api.get<MarketplaceResult>(mkt(), { params }).then(r => r.data),

  /** Publish a tool to the marketplace */
  publishTool: (data: PublishListingRequest) =>
    api.post<ApiActionResponse>(mkt('/publish'), data).then(r => r.data),

  /** Stage a tool import from marketplace */
  stageImport: (listingId: string) =>
    api.post<ImportToolResponse>(mkt(`/${encodeURIComponent(listingId)}/import`)).then(r => r.data),

  /** Finalize a staged import - REQUIRES listing_id (fix for route/service mismatch) */
  finalizeImport: (data: FinalizeImportRequest) =>
    api.post<FinalizeImportResponse>(mkt('/finalize-import'), data).then(r => r.data),

  /** Rate a marketplace listing */
  rateTool: (listingId: string, data: RateToolRequest) =>
    api.post<ApiActionResponse>(mkt(`/${encodeURIComponent(listingId)}/rate`), data).then(r => r.data),

  /** Yank a marketplace listing */
  yankTool: (listingId: string, data: YankListingRequest) =>
    api.post<ApiActionResponse>(mkt(`/${encodeURIComponent(listingId)}/yank`), data).then(r => r.data),

  // ── Tools ─────────────────────────────────────────────────────────────────

  /** List all tools with optional status filter */
  listTools: (statusFilter?: string) =>
    api.get<ToolListResponse>(`${BASE}/${statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ''}`).then(r => r.data),

  /** Propose a new tool */
  proposeTool: (data: ProposeToolRequest) =>
    api.post<ApiActionResponse>(`${BASE}/propose`, data).then(r => r.data),

  /** Vote on a pending tool proposal */
  voteOnTool: (toolName: string, data: VoteRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/vote'), data).then(r => r.data),

  /** Execute a tool */
  executeTool: (toolName: string, data: ExecuteToolRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/execute'), data).then(r => r.data),

  /** Deprecate a tool */
  deprecateTool: (toolName: string, data: DeprecateRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/deprecate'), data).then(r => r.data),

  /** Restore a deprecated tool */
  restoreTool: (toolName: string, data: RestoreToolRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/restore'), data).then(r => r.data),

  /** Schedule sunset for a tool */
  scheduleSunset: (toolName: string, data: ScheduleSunsetRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/schedule-sunset'), data).then(r => r.data),

  /** Execute sunset (hard removal) */
  executeSunset: (toolName: string, data: ExecuteSunsetRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/execute-sunset'), data).then(r => r.data),

  // ── Versions ──────────────────────────────────────────────────────────────

  /** Get changelog for a tool */
  getChangelog: (toolName: string) =>
    api.get(tool(toolName, '/versions/changelog')).then(r => r.data),

  /** Get diff between two versions */
  getVersionDiff: (toolName: string, versionA: number, versionB: number) =>
    api.get(`${tool(toolName, '/versions/diff')}?version_a=${versionA}&version_b=${versionB}`).then(r => r.data),

  /** Propose a code update */
  proposeUpdate: (toolName: string, data: ProposeUpdateRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/versions/propose-update'), data).then(r => r.data),

  /** Approve a pending update */
  approveUpdate: (toolName: string, data: ApproveUpdateRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/versions/approve-update'), data).then(r => r.data),

  /** Rollback to a specific version */
  rollback: (toolName: string, data: RollbackRequest) =>
    api.post<ApiActionResponse>(tool(toolName, '/versions/rollback'), data).then(r => r.data),

  // ── Sunset ──────────────────────────────────────────────────────────────

  /** List deprecated tools */
  listDeprecated: () =>
    api.get(`${BASE}/deprecated`).then(r => r.data),

  /** Run sunset cleanup */
  runSunsetCleanup: () =>
    api.post<ApiActionResponse>(`${BASE}/run-sunset-cleanup`).then(r => r.data),

  // ── Analytics ─────────────────────────────────────────────────────────────

  /** Get full analytics report */
  getAnalyticsReport: (days: number) =>
    api.get<AnalyticsReport>(`${BASE}/analytics/report?days=${days}`).then(r => r.data),

  /** Get recent errors */
  getRecentErrors: (toolName?: string, limit: number = 50) =>
    api.get<ErrorsResponse>(`${BASE}/analytics/errors?${toolName ? `tool_name=${encodeURIComponent(toolName)}&` : ''}limit=${limit}`).then(r => r.data),

  /** Get agent tool usage */
  getAgentToolUsage: (agentiumId: string, days: number) =>
    api.get<AgentUsageResponse>(`${BASE}/analytics/agent/${encodeURIComponent(agentiumId)}?days=${days}`).then(r => r.data),

  /** Get per-tool analytics */
  getToolStats: (toolName: string, days: number) =>
    api.get<ToolStats>(tool(toolName, `/analytics?days=${days}`)).then(r => r.data),
};