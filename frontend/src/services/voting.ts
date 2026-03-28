/**
 * Voting Service - Frontend API for amendment voting and task deliberations.
 */

import { api } from './api';

// ============================================================================
// Types
// ============================================================================

export type VoteType = 'for' | 'against' | 'abstain';
export type AmendmentStatus = 'proposed' | 'deliberating' | 'voting' | 'passed' | 'rejected' | 'ratified';
export type DeliberationStatus = 'pending' | 'active' | 'quorum' | 'concluded' | 'executed';

export interface AmendmentVoting {
    id: string;
    agentium_id: string;
    status: AmendmentStatus;
    title?: string;
    sponsors: string[];
    sponsors_needed: number;
    eligible_voters: string[];
    votes_for: number;
    votes_against: number;
    votes_abstain: number;
    final_result?: string;
    started_at?: string;
    ended_at?: string;
    created_at?: string;
    discussion_thread: DiscussionEntry[];
}

export interface DiscussionEntry {
    timestamp: string;
    agent: string;
    message: string;
}

export interface AmendmentDetails extends AmendmentVoting {
    debate_document?: string;
    diff_markdown?: string;
    rationale?: string;
    discussion_thread: DiscussionEntry[];
}

export interface AmendmentProposal {
    title: string;
    diff_markdown: string;
    rationale: string;
    voting_period_hours?: number;
    affected_articles?: string[];
}

export interface TaskDeliberation {
    id: string;
    agentium_id: string;
    task_id: string;
    status: DeliberationStatus;
    participating_members: string[];
    votes_for: number;
    votes_against: number;
    votes_abstain: number;
    final_decision?: string;
    head_overridden: boolean;
    started_at?: string;
    ended_at?: string;
    time_limit_minutes: number;
    discussion_thread: DiscussionEntry[];
}

export interface DeliberationDetails extends TaskDeliberation {
    required_approvals: number;
    min_quorum: number;
    head_override_reason?: string;
    individual_votes: IndividualVote[];
}

export interface IndividualVote {
    voter_id: string;
    vote: VoteType;
    rationale?: string;
    changed_at?: string;
}

export interface VoteResponse {
    amendment_id?: string;
    deliberation_id?: string;
    voter: string;
    vote: VoteType;
    tally: {
        for: number;
        against: number;
        abstain: number;
    };
}

// ============================================================================
// Voting Service
// ============================================================================

export const votingService = {
    // ------------------ Amendment Operations ------------------

    /**
     * Get all amendment votings, optionally filtered by status.
     */
    getAmendmentVotings: async (status_filter?: AmendmentStatus): Promise<AmendmentVoting[]> => {
        const params = status_filter ? `?status_filter=${status_filter}` : '';
        const response = await api.get<AmendmentVoting[]>(`/api/v1/voting/amendments${params}`);
        return response.data;
    },

    /**
     * Get detailed information about a specific amendment.
     */
    getAmendmentDetails: async (amendmentId: string): Promise<AmendmentDetails> => {
        const response = await api.get<AmendmentDetails>(`/api/v1/voting/amendments/${amendmentId}`);
        return response.data;
    },

    /**
     * Propose a new constitutional amendment.
     */
    proposeAmendment: async (proposal: AmendmentProposal): Promise<any> => {
        const response = await api.post('/api/v1/voting/amendments', proposal);
        return response.data;
    },

    /**
     * Cast a vote on an amendment.
     */
    castVote: async (amendmentId: string, vote: VoteType, rationale?: string): Promise<VoteResponse> => {
        const response = await api.post<VoteResponse>(`/api/v1/voting/amendments/${amendmentId}/vote`, {
            vote,
            rationale,
        });
        return response.data;
    },

    /**
     * Sponsor an amendment (add your name as a sponsor).
     */
    sponsorAmendment: async (amendmentId: string): Promise<any> => {
        const response = await api.post(`/api/v1/voting/amendments/${amendmentId}/sponsor`);
        return response.data;
    },

    /**
     * Start voting on an amendment (transition from DELIBERATING to VOTING).
     */
    startVoting: async (amendmentId: string): Promise<any> => {
        const response = await api.post(`/api/v1/voting/amendments/${amendmentId}/start-voting`);
        return response.data;
    },

    /**
     * Conclude voting on an amendment and execute the result.
     */
    concludeVoting: async (amendmentId: string): Promise<any> => {
        const response = await api.post(`/api/v1/voting/amendments/${amendmentId}/conclude`);
        return response.data;
    },

    // ------------------ Task Deliberation Operations ------------------

    /**
     * Get all task deliberations.
     */
    getTaskDeliberations: async (status_filter?: DeliberationStatus): Promise<TaskDeliberation[]> => {
        const params = status_filter ? `?status_filter=${status_filter}` : '';
        const response = await api.get<TaskDeliberation[]>(`/api/v1/voting/deliberations${params}`);
        return response.data;
    },

    /**
     * Get detailed information about a specific deliberation.
     */
    getDeliberationDetails: async (deliberationId: string): Promise<DeliberationDetails> => {
        const response = await api.get<DeliberationDetails>(`/api/v1/voting/deliberations/${deliberationId}`);
        return response.data;
    },

    /**
     * Cast a vote in a task deliberation.
     */
    castDeliberationVote: async (
        deliberationId: string,
        vote: VoteType,
        rationale?: string
    ): Promise<VoteResponse> => {
        const response = await api.post<VoteResponse>(
            `/api/v1/voting/deliberations/${deliberationId}/vote`,
            { vote, rationale }
        );
        return response.data;
    },

    /**
     * Start a deliberation (transition from PENDING to ACTIVE).
     */
    startDeliberation: async (deliberationId: string): Promise<any> => {
        const response = await api.post(`/api/v1/voting/deliberations/${deliberationId}/start`);
        return response.data;
    },

    /**
     * Conclude a deliberation and calculate the result.
     */
    concludeDeliberation: async (deliberationId: string): Promise<any> => {
        const response = await api.post(`/api/v1/voting/deliberations/${deliberationId}/conclude`);
        return response.data;
    },
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Calculate time remaining until voting ends.
 */
export function getTimeRemaining(endedAt?: string): string {
    if (!endedAt) return 'No deadline';

    const end = new Date(endedAt);
    const now = new Date();
    const diff = end.getTime() - now.getTime();

    if (diff <= 0) return 'Ended';

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

    if (days > 0) return `${days}d ${hours}h remaining`;
    if (hours > 0) return `${hours}h ${minutes}m remaining`;
    return `${minutes}m remaining`;
}

/**
 * Calculate vote percentage.
 */
export function calculateVotePercentage(votes: number, total: number): number {
    if (total === 0) return 0;
    return Math.round((votes / total) * 100);
}

/**
 * Check if voting is still active.
 * FIX: Added 'quorum' status — a deliberation in QUORUM_REACHED state still
 * accepts votes but was previously treated as inactive, hiding vote buttons.
 */
export function isVotingActive(amendment: AmendmentVoting | TaskDeliberation): boolean {
    const status = (amendment as any).status;
    if (status === 'voting' || status === 'active' || status === 'quorum') {
        if (amendment.ended_at) {
            return new Date(amendment.ended_at) > new Date();
        }
        return true;
    }
    return false;
}

/**
 * Get status color for display.
 */
export function getStatusColor(status: string): string {
    switch (status) {
        case 'proposed':
        case 'pending':
            return '#6b7280'; // gray
        case 'deliberating':
        case 'active':
            return '#3b82f6'; // blue
        case 'voting':
        case 'quorum':
            return '#f59e0b'; // amber
        case 'passed':
        case 'executed':
        case 'ratified':
            return '#10b981'; // green
        case 'rejected':
        case 'concluded':
            return '#ef4444'; // red
        default:
            return '#6b7280';
    }
}

/**
 * Format countdown string from an ISO end date.
 */
export function formatCountdown(endedAt: string | undefined): string {
    if (!endedAt) return '—';
    const diff = new Date(endedAt).getTime() - Date.now();
    if (diff <= 0) return 'Ended';
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    const s = Math.floor((diff % 60_000) / 1_000);
    if (h > 0) return `${h}h ${m}m remaining`;
    if (m > 0) return `${m}m ${s}s remaining`;
    return `${s}s remaining`;
}