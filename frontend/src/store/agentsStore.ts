import { create } from 'zustand';
import { Agent } from '../types';

interface AgentsState {
    agents:      Agent[];
    lastFetched: number | null;
    isLoading:   boolean;
    /** Signals to subscribers (e.g. LifecycleDashboard) that a refresh is needed */
    refreshToken: number;
}

interface AgentsActions {
    setAgents:    (agents: Agent[]) => void;
    updateAgent:  (agentiumId: string, updates: Partial<Agent>) => void;
    addAgent:     (agent: Agent) => void;
    setLoading:   (loading: boolean) => void;
    invalidate:   () => void;
    triggerRefreshToken: () => void;
    isStale:      () => boolean;
}

/** Consider cached data stale after 30 seconds */
const CACHE_TTL_MS = 30_000;

export const useAgentsStore = create<AgentsState & AgentsActions>()((set, get) => ({
    agents:       [],
    lastFetched:  null,
    isLoading:    false,
    refreshToken: 0,

    setAgents: (agents) =>
        set({ agents, lastFetched: Date.now() }),

    updateAgent: (agentiumId, updates) =>
        set(state => ({
            agents: state.agents.map(a =>
                a.agentium_id === agentiumId ? { ...a, ...updates } : a
            ),
        })),

    addAgent: (agent) =>
        set(state => ({
            agents: [
                ...state.agents.filter(a => a.agentium_id !== agent.agentium_id),
                agent,
            ],
        })),

    setLoading: (isLoading) => set({ isLoading }),

    /** Mark cache as stale so next mount forces a fresh fetch */
    invalidate: () => set({ lastFetched: null }),

    /** Bump the token so components (e.g. LifecycleDashboard) re-fetch */
    triggerRefreshToken: () => set(s => ({ refreshToken: s.refreshToken + 1 })),

    isStale: () => {
        const { lastFetched } = get();
        if (!lastFetched) return true;
        return Date.now() - lastFetched > CACHE_TTL_MS;
    },
}));