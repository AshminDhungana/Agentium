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

export const pluginMarketplaceService = {
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

export const toolCreationMarketplaceService = {
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