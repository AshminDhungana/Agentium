import { api } from './api';
import { Agent } from '../types';

// ─── Request / Response types ─────────────────────────────────────────────────

export interface PromoteAgentRequest {
    task_agentium_id:        string;
    promoted_by_agentium_id: string;
    reason:                  string;
}

export interface PromotionResult {
    success:           boolean;
    old_agentium_id:   string;
    new_agentium_id:   string;
    promoted_by:       string;
    reason:            string;
    tasks_transferred: number;
    message:           string;
}

export interface CapacityTier {
    used:       number;
    available:  number;
    total:      number;
    percentage: number;
    warning:    boolean;
    critical:   boolean;
}

export interface CapacityData {
    head:     CapacityTier;
    council:  CapacityTier;
    lead:     CapacityTier;
    task:     CapacityTier;
    warnings: string[];
}

export interface LifecycleStats {
    period_days: number;
    lifecycle_events: {
        spawned:      number;
        promoted:     number;
        liquidated:   number;
        reincarnated: number;
    };
    active_agents_by_tier: {
        tier_0: number;
        tier_1: number;
        tier_2: number;
        tier_3: number;
    };
    capacity: {
        head:    CapacityTier;
        council: CapacityTier;
        lead:    CapacityTier;
        task:    CapacityTier;
    };
}

export interface BulkLiquidateDryRunResult {
    dry_run:           true;
    idle_agents_found: number;
    idle_agents:       { agentium_id: string; name: string; idle_days: number }[];
    message:           string;
}

export interface BulkLiquidateResult {
    dry_run:         false;
    liquidated_count: number;
    liquidated:       { agentium_id: string; name: string }[];
    skipped_count:    number;
    skipped:          { agentium_id: string; reason: string }[];
    message:          string;
}

export interface SpawnAgentRequest {
    child_type:        'council_member' | 'lead_agent' | 'task_agent';
    name:              string;
    description:       string;
    parent_agentium_id: string;
}

export interface ReassignAgentRequest {
    new_parent_id: string;
    reason?:       string;
}

export interface CapabilityProfile {
    tier:                    string;
    agentium_id:             string;
    base_capabilities:       string[];
    granted_capabilities:    string[];
    revoked_capabilities:    string[];
    effective_capabilities:  string[];
    total_count:             number;
}

// ─── Agents service ───────────────────────────────────────────────────────────

export const agentsService = {
    getAgents: async (filters?: { type?: string; status?: string }): Promise<Agent[]> => {
        const params = new URLSearchParams();
        if (filters?.type)   params.append('agent_type', filters.type);
        if (filters?.status) params.append('status', filters.status);

        const response = await api.get<{ agents: Agent[] }>(`/api/v1/agents?${params.toString()}`);
        return response.data.agents;
    },

    getAgent: async (id: string): Promise<Agent> => {
        const response = await api.get<Agent>(`/api/v1/agents/${id}`);
        return response.data;
    },

    spawnAgent: async (parentId: string, data: SpawnAgentRequest): Promise<Agent> => {
        // Backend has two separate spawn endpoints: /spawn/task and /spawn/lead.
        // task_agent              → POST /spawn/task  (parent: Lead 2xxxx or Council 1xxxx)
        // lead_agent/council_member → POST /spawn/lead  (parent: Council 1xxxx or Head 0xxxx)
        const endpoint = data.child_type === 'task_agent'
            ? '/api/v1/agents/lifecycle/spawn/task'
            : '/api/v1/agents/lifecycle/spawn/lead';

        const response = await api.post<{ agent: Agent }>(endpoint, {
            parent_agentium_id: data.parent_agentium_id,
            name:               data.name,
            description:        data.description,
        });
        return response.data.agent;
    },

    /**
     * Terminate an agent.
     * reason must be >= 20 chars (backend LiquidateAgentRequest constraint).
     * authorizedById must be a Head (0xxxx) or Council (1xxxx) agent.
     */
    terminateAgent: async (
        id:             string,
        reason:         string,
        authorizedById: string,
    ): Promise<void> => {
        await api.post('/api/v1/agents/lifecycle/liquidate', {
            target_agentium_id:        id,
            liquidated_by_agentium_id: authorizedById,
            reason,
            force: false,
        });
    },

    reassignAgent: async (agentId: string, data: ReassignAgentRequest): Promise<Agent> => {
        const response = await api.post<{ agent: Agent }>(
            `/api/v1/agents/lifecycle/${agentId}/reassign`,
            data,
        );
        return response.data.agent;
    },
};

// ─── Lifecycle service ────────────────────────────────────────────────────────

export const lifecycleService = {
    /** Promote a Task Agent (3xxxx) to Lead Agent (2xxxx). */
    promoteAgent: async (data: PromoteAgentRequest): Promise<PromotionResult> => {
        const response = await api.post<PromotionResult>(
            '/api/v1/agents/lifecycle/promote',
            data,
        );
        return response.data;
    },

    /**
     * Bulk-liquidate idle agents.
     * dry_run=true (default) only detects — does NOT liquidate.
     *
     * Note: params sent as query params to match current backend signature.
     * Backend improvement (moving to request body) can be adopted transparently here.
     */
    bulkLiquidateIdle: async (
        idleDaysThreshold = 7,
        dryRun = true,
    ): Promise<BulkLiquidateDryRunResult | BulkLiquidateResult> => {
        const params = new URLSearchParams({
            idle_days_threshold: String(idleDaysThreshold),
            dry_run:             String(dryRun),
        });
        const response = await api.post<BulkLiquidateDryRunResult | BulkLiquidateResult>(
            `/api/v1/agents/lifecycle/bulk/liquidate-idle?${params}`,
        );
        return response.data;
    },

    getCapacity: async (): Promise<CapacityData> => {
        const response = await api.get<CapacityData>('/api/v1/agents/lifecycle/capacity');
        return response.data;
    },

    getLifecycleStats: async (): Promise<LifecycleStats> => {
        const response = await api.get<LifecycleStats>('/api/v1/agents/lifecycle/stats/lifecycle');
        return response.data;
    },
};

// ─── Capabilities service ─────────────────────────────────────────────────────

export const capabilitiesService = {
    getAgentCapabilities: async (agentiumId: string): Promise<CapabilityProfile> => {
        const response = await api.get<CapabilityProfile>(`/api/v1/capabilities/agent/${agentiumId}`);
        return response.data;
    },

    checkCapability: async (agentiumId: string, capability: string): Promise<boolean> => {
        const response = await api.post<{ has_capability: boolean }>('/api/v1/capabilities/check', {
            agentium_id: agentiumId,
            capability,
        });
        return response.data.has_capability;
    },

    /**
     * Validate whether an agent can be reassigned to a new parent.
     * Performs a local tier-based check first, then hits the backend
     * /validate-reassignment endpoint for a capability check.
     */
    validateReassignment: async (
        agentiumId:  string,
        newParentId: string,
    ): Promise<{ valid: boolean; reason?: string }> => {
        const agentTier  = agentiumId[0];
        const parentTier = newParentId[0];

        // Quick local guard — head cannot be reassigned
        if (!agentTier || agentTier === '0') {
            return { valid: false, reason: 'Head of Council cannot be reassigned.' };
        }
        // Parent must outrank agent (lower prefix number)
        if (parentTier >= agentTier) {
            return { valid: false, reason: 'New parent must outrank the agent.' };
        }

        // Hit backend for capability check
        try {
            const response = await api.post<{ valid: boolean; reason?: string }>(
                '/api/v1/capabilities/validate-reassignment',
                { agent_agentium_id: agentiumId, new_parent_agentium_id: newParentId },
            );
            return response.data;
        } catch {
            // Fall back to local capability inference if endpoint doesn't exist yet
            const capabilityNeeded =
                agentTier === '3' ? 'spawn_task_agent' :
                agentTier === '2' ? 'spawn_lead'       : null;

            if (!capabilityNeeded) return { valid: false, reason: 'Cannot reassign this agent type.' };

            const hasCapability = await capabilitiesService.checkCapability(newParentId, capabilityNeeded);
            return hasCapability
                ? { valid: true }
                : { valid: false, reason: `New parent lacks '${capabilityNeeded}' capability.` };
        }
    },
};