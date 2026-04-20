/**
 * VotingInterface Component - Real-time voting display for active amendments.
 * Can be embedded in MonitoringPage or used standalone.
 *
 * Fixes:
 * - alert() → toast
 * - Static getTimeRemaining → live countdown via setInterval
 * - Unused XCircle import removed
 */

import React, { useState, useEffect } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    votingService,
    AmendmentVoting,
    VoteType,
    calculateVotePercentage,
    isVotingActive,
    getStatusColor,
} from '../../services/voting';
import { ThumbsUp, ThumbsDown, Minus, Clock, Users, CheckCircle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface VotingInterfaceProps {
    embedded?: boolean;
    onVoteCast?: (amendmentId: string) => void;
}

// Live countdown that ticks every second
function LiveCountdown({ endedAt }: { endedAt: string | undefined }) {
    const [label, setLabel] = useState('');

    useEffect(() => {
        const compute = () => {
            if (!endedAt) { setLabel('—'); return; }
            const diff = new Date(endedAt).getTime() - Date.now();
            if (diff <= 0) { setLabel('Ended'); return; }
            const h = Math.floor(diff / 3_600_000);
            const m = Math.floor((diff % 3_600_000) / 60_000);
            const s = Math.floor((diff % 60_000) / 1_000);
            setLabel(h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`);
        };
        compute();
        const id = setInterval(compute, 1000);
        return () => clearInterval(id);
    }, [endedAt]);

    return (
        <span className="flex items-center gap-1 text-sm text-orange-600 dark:text-orange-400">
            <Clock className="w-4 h-4" />
            {label}
        </span>
    );
}

export const VotingInterface: React.FC<VotingInterfaceProps> = ({ embedded = false, onVoteCast }) => {
    const [amendments, setAmendments] = useState<AmendmentVoting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [selectedAmendment, setSelectedAmendment] = useState<AmendmentVoting | null>(null);
    const [castVote, setCastVote] = useState<VoteType | null>(null);
    const [rationale, setRationale] = useState('');
    const [isVoting, setIsVoting] = useState(false);

    useEffect(() => {
        loadAmendments();
        const interval = setInterval(loadAmendments, 30000);
        return () => clearInterval(interval);
    }, []);

    const loadAmendments = async () => {
        try {
            const data = await votingService.getAmendmentVotings();
            setAmendments(data);
        } catch (error) {
            console.error('Failed to load amendments:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleVote = async (amendmentId: string) => {
        if (!castVote) return;
        setIsVoting(true);
        try {
            await votingService.castVote(amendmentId, castVote, rationale || undefined);
            showToast.success(`Vote cast: ${castVote}`);
            setCastVote(null);
            setRationale('');
            setSelectedAmendment(null);
            await loadAmendments();
            onVoteCast?.(amendmentId);
        } catch (error: any) {
            showToast.error(`Failed to cast vote: ${error.response?.data?.detail || error.message}`);
        } finally {
            setIsVoting(false);
        }
    };

    const activeAmendments = amendments.filter((a) => isVotingActive(a));
    const totalVotes = (a: AmendmentVoting) => a.votes_for + a.votes_against + a.votes_abstain;

    if (isLoading) {
        return (
            <div className="flex items-center justify-center p-8">
                <LoadingSpinner size="md" />
                <span className="text-sm text-gray-500 dark:text-gray-400">Loading active votes...</span>
            </div>
        );
    }

    return (
        <div className={embedded ? '' : 'space-y-4'}>
            {!embedded && (
                <div className="mb-6">
                    <h2 className="text-xl font-semibold flex items-center gap-2 text-gray-900 dark:text-white">
                        <CheckCircle className="w-5 h-5 text-blue-600" />
                        Active Council Votes
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Real-time voting on constitutional amendments
                    </p>
                </div>
            )}

            {activeAmendments.length === 0 ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    <CheckCircle className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
                    <p>No active votes at this time.</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {activeAmendments.map((amendment) => (
                        <div
                            key={amendment.id}
                            className={`bg-white dark:bg-[#161b27] rounded-lg border border-gray-200 dark:border-[#1e2535] p-4 cursor-pointer transition-shadow hover:shadow-sm ${
                                selectedAmendment?.id === amendment.id ? 'ring-2 ring-blue-500' : ''
                            }`}
                            onClick={() => setSelectedAmendment(prev =>
                                prev?.id === amendment.id ? null : amendment
                            )}
                        >
                            <div className="flex justify-between items-start mb-3">
                                <div>
                                    <h3 className="font-semibold text-gray-900 dark:text-white">
                                        {amendment.title || amendment.agentium_id}
                                    </h3>
                                    <div className="flex items-center gap-3 mt-1">
                                        <span
                                            className="text-xs px-2 py-0.5 rounded"
                                            style={{
                                                backgroundColor: `${getStatusColor(amendment.status)}20`,
                                                color: getStatusColor(amendment.status),
                                            }}
                                        >
                                            {amendment.status.toUpperCase()}
                                        </span>
                                        <span className="text-xs text-gray-500 flex items-center gap-1">
                                            <Users className="w-3 h-3" />
                                            {amendment.eligible_voters?.length || 0} eligible
                                        </span>
                                    </div>
                                </div>
                                <LiveCountdown endedAt={amendment.ended_at} />
                            </div>

                            {/* Vote Progress */}
                            <div className="mb-3">
                                <div className="flex justify-between text-sm mb-1">
                                    <span className="text-green-600 font-medium">For: {amendment.votes_for}</span>
                                    <span className="text-gray-500 text-xs">
                                        {totalVotes(amendment)} / {amendment.eligible_voters?.length || 0} voted
                                    </span>
                                    <span className="text-red-600 font-medium">Against: {amendment.votes_against}</span>
                                </div>
                                <div className="flex h-2 rounded-full overflow-hidden bg-gray-200 dark:bg-[#1e2535]">
                                    {totalVotes(amendment) > 0 && (
                                        <>
                                            <div
                                                className="bg-green-500 transition-all duration-500"
                                                style={{ width: `${calculateVotePercentage(amendment.votes_for, totalVotes(amendment))}%` }}
                                            />
                                            <div
                                                className="bg-red-500 transition-all duration-500"
                                                style={{ width: `${calculateVotePercentage(amendment.votes_against, totalVotes(amendment))}%` }}
                                            />
                                            <div
                                                className="bg-gray-400 transition-all duration-500"
                                                style={{ width: `${calculateVotePercentage(amendment.votes_abstain, totalVotes(amendment))}%` }}
                                            />
                                        </>
                                    )}
                                </div>
                            </div>

                            {/* Vote Actions — only when this card is selected */}
                            {selectedAmendment?.id === amendment.id && (
                                <div
                                    className="mt-4 pt-4 border-t border-gray-200 dark:border-[#1e2535]"
                                    onClick={e => e.stopPropagation()}
                                >
                                    <p className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                                        Cast your vote:
                                    </p>
                                    <div className="flex gap-2 mb-3">
                                        {([ 
                                            { type: 'for' as VoteType,     Icon: ThumbsUp,   active: 'bg-green-600 text-white', inactive: 'bg-gray-100 dark:bg-[#1e2535] hover:bg-green-100 dark:hover:bg-green-900' },
                                            { type: 'against' as VoteType, Icon: ThumbsDown, active: 'bg-red-600 text-white',   inactive: 'bg-gray-100 dark:bg-[#1e2535] hover:bg-red-100 dark:hover:bg-red-900'   },
                                            { type: 'abstain' as VoteType, Icon: Minus,      active: 'bg-gray-600 text-white',  inactive: 'bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-gray-600' },
                                        ]).map(({ type, Icon, active, inactive }) => (
                                            <button
                                                key={type}
                                                className={`flex-1 py-2 px-3 rounded-lg flex items-center justify-center gap-1.5 text-sm font-medium capitalize transition-colors ${castVote === type ? active : inactive}`}
                                                onClick={() => setCastVote(type)}
                                            >
                                                <Icon className="w-4 h-4" />
                                                {type}
                                            </button>
                                        ))}
                                    </div>

                                    {castVote && (
                                        <>
                                            <textarea
                                                className="w-full p-2 border border-gray-300 dark:border-[#2a3347] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500/40 resize-none"
                                                placeholder="Optional: Provide rationale for your vote..."
                                                value={rationale}
                                                onChange={(e) => setRationale(e.target.value)}
                                                rows={2}
                                            />
                                            <button
                                                className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                                                onClick={() => handleVote(amendment.id)}
                                                disabled={isVoting}
                                            >
                                                {isVoting && <LoadingSpinner size="sm" />}
                                                {isVoting ? 'Submitting...' : 'Submit Vote'}
                                            </button>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default VotingInterface;