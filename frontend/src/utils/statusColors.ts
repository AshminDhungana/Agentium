// ─── Status → Colour Maps ─────────────────────────────────────────────────────
// Single source of truth for every status badge / dot-indicator colour.
// Eliminates the duplication that previously existed across Dashboard,
// ChannelsPage, FederationPage, and other pages.

import type { Agent } from '@/types';

// ── Types ─────────────────────────────────────────────────────────────────────

export type AgentStatusType = Agent['status'];

export interface StatusColors {
    /** Tailwind class for the small filled circle indicator. */
    dot:   string;
    /** Tailwind classes for the pill / badge element. */
    badge: string;
    /** Human-readable display label. */
    label: string;
}

// ── Agent status map ──────────────────────────────────────────────────────────

export const AGENT_STATUS_COLORS: Record<AgentStatusType, StatusColors> = {
    active: {
        dot:   'bg-green-500',
        badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',
        label: 'Active',
    },
    working: {
        dot:   'bg-blue-500',
        badge: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
        label: 'Working',
    },
    deliberating: {
        dot:   'bg-yellow-400',
        badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400',
        label: 'Deliberating',
    },
    initializing: {
        dot:   'bg-purple-400',
        badge: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400',
        label: 'Initializing',
    },
    suspended: {
        dot:   'bg-orange-400',
        badge: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400',
        label: 'Suspended',
    },
    terminated: {
        dot:   'bg-gray-400',
        badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',
        label: 'Terminated',
    },
    terminating: {
        dot:   'bg-red-400',
        badge: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
        label: 'Terminating',
    },
};

/**
 * Safe getter — falls back to a neutral grey style for any unknown status
 * string so new backend statuses don't crash the UI.
 */
export function getAgentStatusColors(status: AgentStatusType): StatusColors {
    return (
        AGENT_STATUS_COLORS[status] ?? {
            dot:   'bg-gray-400',
            badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',
            label: status,
        }
    );
}

// ── Task status map ───────────────────────────────────────────────────────────

export const TASK_STATUS_COLORS: Record<string, StatusColors> = {
    pending: {
        dot:   'bg-yellow-400',
        badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400',
        label: 'Pending',
    },
    deliberating: {
        dot:   'bg-purple-400',
        badge: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400',
        label: 'Deliberating',
    },
    planning: {
        dot:   'bg-sky-400',
        badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-400',
        label: 'Planning',
    },
    in_progress: {
        dot:   'bg-blue-500',
        badge: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
        label: 'In Progress',
    },
    completed: {
        dot:   'bg-green-500',
        badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',
        label: 'Completed',
    },
    failed: {
        dot:   'bg-red-500',
        badge: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
        label: 'Failed',
    },
    cancelled: {
        dot:   'bg-gray-400',
        badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',
        label: 'Cancelled',
    },
    blocked: {
        dot:   'bg-orange-400',
        badge: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400',
        label: 'Blocked',
    },
};

/** Safe getter — falls back to neutral grey for any unknown task status. */
export function getTaskStatusColors(status: string): StatusColors {
    return (
        TASK_STATUS_COLORS[status] ?? {
            dot:   'bg-gray-400',
            badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',
            label: status,
        }
    );
}

// ── Federation peer status map ────────────────────────────────────────────────
// Used by FederationPage's PeerTable component.

export type PeerStatusType = 'active' | 'suspended' | 'pending';

export const PEER_STATUS_COLORS: Record<PeerStatusType, StatusColors> = {
    active: {
        dot:   'bg-green-500',
        badge: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
        label: 'Active',
    },
    suspended: {
        dot:   'bg-orange-400',
        badge: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-500/10 dark:text-orange-400 dark:border-orange-500/20',
        label: 'Suspended',
    },
    pending: {
        dot:   'bg-yellow-400',
        badge: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
        label: 'Pending',
    },
};

/**
 * Safe getter for peer status colours. Falls back to neutral grey for
 * any status string not in the map (e.g. future backend values).
 */
export function getPeerStatusColors(status: string): StatusColors {
    return (
        PEER_STATUS_COLORS[status as PeerStatusType] ?? {
            dot:   'bg-gray-400',
            badge: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]',
            label: status,
        }
    );
}

// ── Federated task status map ─────────────────────────────────────────────────
// Used by FederationPage's Tasks tab.

export type FedTaskStatusType =
    | 'pending'
    | 'delivered'
    | 'accepted'
    | 'rejected'
    | 'completed'
    | 'failed';

export const FED_TASK_STATUS_COLORS: Record<FedTaskStatusType, StatusColors> = {
    pending: {
        dot:   'bg-yellow-400',
        badge: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
        label: 'Pending',
    },
    delivered: {
        dot:   'bg-blue-400',
        badge: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20',
        label: 'Delivered',
    },
    accepted: {
        dot:   'bg-sky-400',
        badge: 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-500/10 dark:text-sky-400 dark:border-sky-500/20',
        label: 'Accepted',
    },
    rejected: {
        dot:   'bg-red-400',
        badge: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
        label: 'Rejected',
    },
    completed: {
        dot:   'bg-green-500',
        badge: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
        label: 'Completed',
    },
    failed: {
        dot:   'bg-red-500',
        badge: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
        label: 'Failed',
    },
};

/**
 * Safe getter for federated task status colours.
 */
export function getFedTaskStatusColors(status: string): StatusColors {
    return (
        FED_TASK_STATUS_COLORS[status as FedTaskStatusType] ?? {
            dot:   'bg-gray-400',
            badge: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]',
            label: status,
        }
    );
}