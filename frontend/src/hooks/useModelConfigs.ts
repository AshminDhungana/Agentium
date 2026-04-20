/**
 * frontend/src/hooks/useModelConfigs.ts
 *
 * Encapsulates all data-fetching and mutation logic for the Models page.
 * Separating business logic from the render layer keeps ModelsPage lean and
 * makes each handler independently testable.
 *
 * What it manages:
 *  - configs list + loading / error state
 *  - per-card async action tracking via a typed Map (replaces 3 separate useState)
 *  - inline delete confirmation state
 *  - all CRUD + test + fetch-models handlers
 *
 * Genesis integration:
 *  After any config is successfully saved, the sessionStorage genesis guard
 *  ('genesis_check_done') is cleared.  This ensures that useGenesisCheck
 *  re-evaluates on the next navigation — if genesis is now able to run
 *  (status transitions from 'no_api_key' → 'pending'), the hook will
 *  trigger POST /genesis/initialize automatically.
 */

import { useState, useCallback, useEffect } from 'react';
import { showToast } from '@/hooks/useToast';
import { modelsApi } from '@/services/models';
import type { ModelConfig } from '@/types';
import { getErrorMessage } from '@/utils/errors';

// Session key shared with useGenesisCheck — cleared here after a key is saved.
const GENESIS_SESSION_KEY = 'genesis_check_done';

// ─── Types ────────────────────────────────────────────────────────────────────

/** Actions that can be in-flight on a specific card. */
export type CardAction = 'testing' | 'deleting' | 'fetching';

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useModelConfigs() {
    const [configs, setConfigs] = useState<ModelConfig[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeActions, setActiveActions] = useState<Map<string, CardAction>>(new Map());
    const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

    // ── Action helpers ─────────────────────────────────────────────────────

    /** Mark a card action as in-flight. */
    const startAction = useCallback((id: string, action: CardAction) => {
        setActiveActions(prev => new Map(prev).set(id, action));
    }, []);

    /** Clear a card's in-flight action. */
    const endAction = useCallback((id: string) => {
        setActiveActions(prev => {
            const next = new Map(prev);
            next.delete(id);
            return next;
        });
    }, []);

    // ── Data fetching ──────────────────────────────────────────────────────

    const loadConfigs = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await modelsApi.getConfigs();
            if (!Array.isArray(data)) {
                setConfigs([]);
                setError('Invalid response format from server');
            } else {
                setConfigs(data);
            }
        } catch (err: unknown) {
            setError(getErrorMessage(err) || 'Failed to load configurations');
            setConfigs([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadConfigs();
    }, [loadConfigs]);

    // ── Handlers ───────────────────────────────────────────────────────────

    /**
     * Initiates delete after the user confirms via the inline confirm UI.
     * The caller is responsible for resetting pendingDeleteId to null after
     * the user either confirms or cancels — the card handles "cancel" itself.
     */
    const handleDelete = useCallback(async (id: string) => {
        startAction(id, 'deleting');
        setPendingDeleteId(null);
        try {
            await modelsApi.deleteConfig(id);
            // Optimistic removal — no full reload needed for a delete
            setConfigs(prev => prev.filter(c => c.id !== id));
            showToast.success('Configuration deleted');
        } catch (err: unknown) {
            showToast.error('Failed to delete: ' + getErrorMessage(err));
        } finally {
            endAction(id);
        }
    }, [startAction, endAction]);

    const handleSetDefault = useCallback(async (id: string) => {
        try {
            await modelsApi.setDefault(id);
            // Optimistic update: flip is_default flags without a round-trip
            setConfigs(prev =>
                prev.map(c => ({ ...c, is_default: c.id === id }))
            );
        } catch (err: unknown) {
            showToast.error('Failed to set default: ' + getErrorMessage(err));
            // Re-sync from server so UI is accurate
            await loadConfigs();
        }
    }, [loadConfigs]);

    const handleTest = useCallback(async (id: string) => {
        startAction(id, 'testing');
        try {
            const result = await modelsApi.testConfig(id);
            if (result.success) {
                showToast.success(`✅ Connected · ${result.latency_ms}ms · ${result.model}`);
            } else {
                showToast.error(`Connection failed: ${result.error}`);
            }
            // Reload to reflect updated status field from the server
            await loadConfigs();
        } catch (err: unknown) {
            showToast.error('Test failed — check your API key and network: ' + getErrorMessage(err));
        } finally {
            endAction(id);
        }
    }, [startAction, endAction, loadConfigs]);

    const handleFetchModels = useCallback(async (id: string) => {
        startAction(id, 'fetching');
        try {
            const result = await modelsApi.fetchModels(id);
            showToast.success(`Fetched ${result.count} models from ${result.provider}`);
            // Single authoritative reload — no need for an optimistic update
            // on top of a full server sync
            await loadConfigs();
        } catch (err: unknown) {
            showToast.error('Failed to fetch models: ' + getErrorMessage(err));
        } finally {
            endAction(id);
        }
    }, [startAction, endAction, loadConfigs]);

    /**
     * Called after any config is successfully created or updated.
     *
     * Crucially, we clear the genesis session guard here so that
     * useGenesisCheck re-evaluates on the next render cycle. If the newly
     * saved config provides a working API key, the backend status will
     * transition from "no_api_key" → "pending", and the hook will
     * automatically call POST /genesis/initialize.
     */
    const handleSave = useCallback(async (config: ModelConfig) => {
        await loadConfigs();

        // Clear genesis guard so useGenesisCheck re-runs and can trigger
        // the Genesis Protocol now that an API key may be available.
        sessionStorage.removeItem(GENESIS_SESSION_KEY);

        // Side-effect: clear OpenAI voice status cache when an OpenAI config is saved
        if (config.provider === 'openai') {
            try {
                const { voiceApi } = await import('@/services/voiceApi');
                voiceApi.clearStatusCache();
                showToast.success('Voice features now available with OpenAI provider!');
            } catch {
                // Non-critical — voice feature may not be available in this build
            }
        }
    }, [loadConfigs]);

    // ── Derived stats ──────────────────────────────────────────────────────

    const activeCount   = configs.filter(c => c.status === 'active').length;
    const totalTokens   = configs.reduce((sum, c) => sum + (c.total_usage?.tokens   ?? 0), 0);
    const totalCost     = configs.reduce((sum, c) => sum + (c.total_usage?.cost_usd  ?? 0), 0);
    const totalRequests = configs.reduce((sum, c) => sum + (c.total_usage?.requests  ?? 0), 0);

    return {
        // State
        configs,
        loading,
        error,
        activeActions,
        pendingDeleteId,

        // Derived
        activeCount,
        totalTokens,
        totalCost,
        totalRequests,

        // Actions
        loadConfigs,
        handleDelete,
        handleSetDefault,
        handleTest,
        handleFetchModels,
        handleSave,
        setPendingDeleteId,
    };
}