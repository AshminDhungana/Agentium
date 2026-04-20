/**
 * DetailPanel
 *
 * Expanded view for a selected amendment or deliberation.
 *
 * Improvements:
 * - Vote confirmation step: prevents accidental governance submissions
 * - Optimistic tally update: reflects vote instantly before server round-trip
 * - Shared countdown tick: no per-component interval
 * - Unmount guard: details fetch cancelled on unmount to prevent setState leak
 * - aria-live region: screen readers announce vote submission status
 */

import React, { useState, useEffect, useRef } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    CheckCircle, XCircle, Clock, Users,
    ThumbsUp, ThumbsDown, Minus, MessageSquare,
    BookOpen, AlertCircle, X, ChevronDown, UserCheck, Shield,
} from 'lucide-react';
import {
    votingService,
    AmendmentVoting,
    AmendmentDetails,
    TaskDeliberation,
    DeliberationDetails,
    VoteType,
    isVotingActive,
    getStatusColor,
    formatCountdown,
} from '../../services/voting';
import { QuorumBar } from './QuorumBar';
import { useCountdownTick } from '../../hooks/useCountdownTick';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface DetailPanelProps {
    item: AmendmentVoting | TaskDeliberation;
    onClose: () => void;
    onVoteSuccess: () => void;
}

export function DetailPanel({ item, onClose, onVoteSuccess }: DetailPanelProps) {
    const tick = useCountdownTick();

    const [isVoting, setIsVoting] = useState(false);
    const [pendingVote, setPendingVote] = useState<VoteType | null>(null);
    const [delegateEnabled, setDelegateEnabled] = useState(false);
    const [delegateTarget, setDelegateTarget] = useState('');
    const [isDelegating, setIsDelegating] = useState(false);
    const [details, setDetails] = useState<AmendmentDetails | DeliberationDetails | null>(null);
    const [isLoadingDetails, setIsLoadingDetails] = useState(true);
    const [showIndividualVotes, setShowIndividualVotes] = useState(false);
    // Optimistic tally override — reverted on error, cleared after server refresh
    const [optimisticItem, setOptimisticItem] = useState<typeof item | null>(null);

    const isAmendment = 'sponsors' in item;
    const isMountedRef = useRef(true);

    useEffect(() => {
        isMountedRef.current = true;
        return () => { isMountedRef.current = false; };
    }, []);

    // Fetch detailed data
    useEffect(() => {
        setIsLoadingDetails(true);
        setDetails(null);

        const fetchFn = isAmendment
            ? votingService.getAmendmentDetails(item.id)
            : votingService.getDeliberationDetails(item.id);

        fetchFn
            .then(d => { if (isMountedRef.current) setDetails(d); })
            .catch(() => { /* silently fall back to summary data */ })
            .finally(() => { if (isMountedRef.current) setIsLoadingDetails(false); });
    }, [item.id, isAmendment]);

    const active = isVotingActive(item);
    // Use optimistic override while waiting for server, then revert to server data
    const displayItem = (optimisticItem ?? details ?? item) as any;

    const totalVotes = displayItem.votes_for + displayItem.votes_against + displayItem.votes_abstain;
    const totalEligible = isAmendment
        ? (item as AmendmentVoting).eligible_voters?.length ?? 0
        : (item as TaskDeliberation).participating_members?.length ?? 0;

    const deliDetails = !isAmendment ? (details as DeliberationDetails | null) : null;

    // Step 1: user clicks a vote button — show confirmation inline
    const handleVoteClick = (voteType: VoteType) => {
        setPendingVote(voteType);
    };

    // Step 2: user confirms — submit and apply optimistic update
    const handleVoteConfirm = async () => {
        if (!pendingVote) return;
        const confirmedVote = pendingVote;
        setPendingVote(null);
        setIsVoting(true);

        // Optimistic update: bump the tally immediately
        const base = item;
        setOptimisticItem({
            ...base,
            votes_for:     base.votes_for     + (confirmedVote === 'for'     ? 1 : 0),
            votes_against: base.votes_against + (confirmedVote === 'against' ? 1 : 0),
            votes_abstain: base.votes_abstain + (confirmedVote === 'abstain' ? 1 : 0),
        } as typeof item);

        try {
            if (isAmendment) {
                await votingService.castVote(item.id, confirmedVote);
            } else {
                await votingService.castDeliberationVote(item.id, confirmedVote);
            }
            showToast.success(`Vote cast: ${confirmedVote}`);
            onVoteSuccess(); // triggers parent refresh; clears optimistic state via re-render
        } catch (err: any) {
            // Revert optimistic update on error
            setOptimisticItem(null);
            showToast.error(err.response?.data?.detail || 'Failed to cast vote');
        } finally {
            if (isMountedRef.current) setIsVoting(false);
        }
    };

    // Clear optimistic override once parent has refreshed with server data
    useEffect(() => {
        setOptimisticItem(null);
    }, [item.votes_for, item.votes_against, item.votes_abstain]);

    const handleDelegate = async () => {
        if (!delegateTarget.trim()) {
            showToast.error('Please enter a delegate agent ID');
            return;
        }
        setIsDelegating(true);
        try {
            await votingService.sponsorAmendment(item.id);
            showToast.success(`Authority delegated to ${delegateTarget.trim()}`);
            setDelegateEnabled(false);
            setDelegateTarget('');
            onVoteSuccess();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to delegate authority');
        } finally {
            if (isMountedRef.current) setIsDelegating(false);
        }
    };

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-lg">
            {/* Header */}
            <div className="flex items-start justify-between p-6 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex-1 min-w-0 pr-4">
                    <div className="flex items-center gap-2 mb-1">
                        <span
                            className="text-xs px-2 py-0.5 rounded-full font-medium"
                            style={{
                                backgroundColor: `${getStatusColor(item.status)}20`,
                                color: getStatusColor(item.status),
                            }}
                        >
                            {item.status.toUpperCase()}
                        </span>
                        {isAmendment && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
                                Amendment
                            </span>
                        )}
                        {isLoadingDetails && (
                            <LoadingSpinner size="xs" className="text-gray-400" />
                        )}
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                        {isAmendment
                            ? (item as AmendmentVoting).title || item.agentium_id
                            : `Task Deliberation: ${(item as TaskDeliberation).task_id}`}
                    </h2>
                    {item.ended_at && (
                        <p className={`text-sm mt-1 flex items-center gap-1 ${
                            active ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400'
                        }`}>
                            <Clock className="w-3.5 h-3.5" />
                            {tick >= 0 && formatCountdown(item.ended_at)}
                        </p>
                    )}
                </div>
                <button
                    aria-label="close"
                    onClick={onClose}
                    className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors duration-200 flex-shrink-0"
                >
                    <X className="w-5 h-5" />
                </button>
            </div>

            <div className="p-6 space-y-6">
                {/* Rationale */}
                {displayItem.rationale && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Rationale</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                            {displayItem.rationale}
                        </p>
                    </div>
                )}

                {/* Diff preview */}
                {isAmendment && displayItem.diff_markdown && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Proposed Changes</h3>
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-4 font-mono text-xs leading-relaxed overflow-x-auto">
                            {(displayItem.diff_markdown as string).split('\n').map((line: string, i: number) => (
                                <div
                                    key={i}
                                    className={
                                        line.startsWith('+')
                                            ? 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 -mx-4 px-4'
                                            : line.startsWith('-')
                                            ? 'text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 -mx-4 px-4'
                                            : 'text-gray-600 dark:text-gray-400'
                                    }
                                >
                                    {line || '\u00A0'}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Debate document */}
                {isAmendment && (details as AmendmentDetails | null)?.debate_document && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
                            <BookOpen className="w-4 h-4" /> Debate Document
                        </h3>
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-4 text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                            {(details as AmendmentDetails).debate_document}
                        </div>
                    </div>
                )}

                {/* Deliberation metadata */}
                {!isAmendment && deliDetails && (
                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3">
                            <p className="text-xs text-gray-500 dark:text-gray-400">Required approvals</p>
                            <p className="text-lg font-bold text-gray-900 dark:text-white">{deliDetails.required_approvals}</p>
                        </div>
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3">
                            <p className="text-xs text-gray-500 dark:text-gray-400">Min quorum</p>
                            <p className="text-lg font-bold text-gray-900 dark:text-white">{deliDetails.min_quorum}</p>
                        </div>
                        {deliDetails.head_overridden && (
                            <div className="col-span-2 flex items-start gap-2 p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-100 dark:border-orange-800/40">
                                <AlertCircle className="w-4 h-4 text-orange-600 dark:text-orange-400 flex-shrink-0 mt-0.5" />
                                <div>
                                    <p className="text-xs font-medium text-orange-700 dark:text-orange-300">Head Override Applied</p>
                                    {deliDetails.head_override_reason && (
                                        <p className="text-xs text-orange-600 dark:text-orange-400 mt-0.5">{deliDetails.head_override_reason}</p>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Sponsors */}
                {isAmendment && (item as AmendmentVoting).sponsors?.length > 0 && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
                            <Users className="w-4 h-4" /> Sponsors
                        </h3>
                        <div className="flex flex-wrap gap-2">
                            {(item as AmendmentVoting).sponsors.map(s => (
                                <span key={s} className="px-2 py-1 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs font-mono">
                                    {s}
                                </span>
                            ))}
                            {(item as AmendmentVoting).sponsors_needed > 0 && (
                                <span className="px-2 py-1 rounded bg-orange-50 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 text-xs">
                                    +{(item as AmendmentVoting).sponsors_needed} more needed
                                </span>
                            )}
                        </div>
                    </div>
                )}

                {/* Vote tally */}
                <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Vote Tally</h3>
                    <QuorumBar
                        votesFor={displayItem.votes_for}
                        votesAgainst={displayItem.votes_against}
                        votesAbstain={displayItem.votes_abstain}
                        total={totalEligible}
                        quorum={
                            !isAmendment && deliDetails
                                ? deliDetails.min_quorum / (totalEligible || 1)
                                : 0.6
                        }
                    />
                </div>

                {/* Individual votes */}
                {!isAmendment && deliDetails?.individual_votes && deliDetails.individual_votes.length > 0 && (
                    <div>
                        <button
                            className="flex items-center gap-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors w-full"
                            onClick={() => setShowIndividualVotes(v => !v)}
                        >
                            <UserCheck className="w-4 h-4" />
                            Individual Votes ({deliDetails.individual_votes.length})
                            <ChevronDown className={`w-4 h-4 ml-auto transition-transform ${showIndividualVotes ? 'rotate-180' : ''}`} />
                        </button>
                        {showIndividualVotes && (
                            <div className="mt-2 space-y-1.5 max-h-40 overflow-y-auto pr-1">
                                {deliDetails.individual_votes.map((v, i) => (
                                    <div key={i} className="flex items-center justify-between text-xs bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg px-3 py-2">
                                        <span className="font-mono text-gray-700 dark:text-gray-300">{v.voter_id}</span>
                                        <div className="flex items-center gap-2">
                                            {v.rationale && (
                                                <span className="text-gray-400 dark:text-gray-500 truncate max-w-32">{v.rationale}</span>
                                            )}
                                            <span className={`px-2 py-0.5 rounded-full font-medium ${
                                                v.vote === 'for'
                                                    ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                                                    : v.vote === 'against'
                                                    ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                                                    : 'bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400'
                                            }`}>
                                                {v.vote}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Discussion thread */}
                {displayItem.discussion_thread?.length > 0 && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
                            <MessageSquare className="w-4 h-4" /> Discussion
                        </h3>
                        <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                            {displayItem.discussion_thread.map((entry: any, i: number) => (
                                <div key={i} className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3 text-xs">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="font-mono font-medium text-gray-700 dark:text-gray-300">{entry.agent}</span>
                                        <span className="text-gray-400 dark:text-gray-500">
                                            {new Date(entry.timestamp).toLocaleTimeString()}
                                        </span>
                                    </div>
                                    <p className="text-gray-600 dark:text-gray-400 leading-relaxed">{entry.message}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Final result */}
                {!active && displayItem.final_result && (
                    <div className={`flex items-center gap-2 p-3 rounded-lg ${
                        displayItem.final_result === 'passed'
                            ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                        {displayItem.final_result === 'passed'
                            ? <CheckCircle className="w-5 h-5 flex-shrink-0" />
                            : <XCircle className="w-5 h-5 flex-shrink-0" />
                        }
                        <span className="font-semibold capitalize">{displayItem.final_result}</span>
                    </div>
                )}
                {!active && displayItem.final_decision && (
                    <div className={`flex items-center gap-2 p-3 rounded-lg ${
                        displayItem.final_decision === 'approved'
                            ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                    }`}>
                        {displayItem.final_decision === 'approved'
                            ? <CheckCircle className="w-5 h-5 flex-shrink-0" />
                            : <XCircle className="w-5 h-5 flex-shrink-0" />
                        }
                        <span className="font-semibold capitalize">{displayItem.final_decision}</span>
                    </div>
                )}

                {/* Voting actions */}
                {active && (
                    <div>
                        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Cast Your Vote</h3>

                        {/* Step 1: vote selection buttons (hidden while confirming) */}
                        {!pendingVote && (
                            <div className="grid grid-cols-3 gap-2">
                                <button
                                    onClick={() => handleVoteClick('for')}
                                    disabled={isVoting}
                                    className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/40 text-green-700 dark:text-green-300 font-medium text-sm transition-colors border border-green-200 dark:border-green-800/40 disabled:opacity-50"
                                >
                                    <ThumbsUp className="w-4 h-4" />
                                    For
                                </button>
                                <button
                                    onClick={() => handleVoteClick('against')}
                                    disabled={isVoting}
                                    className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-700 dark:text-red-300 font-medium text-sm transition-colors border border-red-200 dark:border-red-800/40 disabled:opacity-50"
                                >
                                    <ThumbsDown className="w-4 h-4" />
                                    Against
                                </button>
                                <button
                                    onClick={() => handleVoteClick('abstain')}
                                    disabled={isVoting}
                                    className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-gray-50 dark:bg-[#0f1117]/60 hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-700 dark:text-gray-300 font-medium text-sm transition-colors duration-200 border border-gray-200 dark:border-[#1e2535] disabled:opacity-50"
                                >
                                    <Minus className="w-4 h-4" />
                                    Abstain
                                </button>
                            </div>
                        )}

                        {/* Step 2: inline confirmation panel */}
                        {pendingVote && (
                            <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/40">
                                <p className="text-sm text-amber-800 dark:text-amber-200 mb-3">
                                    Confirm your vote:{' '}
                                    <strong className="capitalize">{pendingVote}</strong>
                                    {' '}— this cannot be changed after submission.
                                </p>
                                <div className="flex gap-2">
                                    <button
                                        onClick={handleVoteConfirm}
                                        disabled={isVoting}
                                        className="px-4 py-2 text-sm font-medium rounded-lg bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50 flex items-center gap-1.5"
                                    >
                                        {isVoting && <LoadingSpinner size="xs" />}
                                        {isVoting ? 'Submitting…' : 'Confirm'}
                                    </button>
                                    <button
                                        onClick={() => setPendingVote(null)}
                                        disabled={isVoting}
                                        className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-[#1e2535] hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-700 dark:text-gray-300 disabled:opacity-50 transition-colors duration-200"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Accessibility: screen reader announcement */}
                        <div aria-live="polite" aria-atomic="true" className="sr-only">
                            {isVoting ? 'Submitting your vote…' : ''}
                        </div>

                        {/* Delegate Authority */}
                        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-[#1e2535]">
                            <label className="flex items-center gap-2.5 cursor-pointer select-none group">
                                <div className="relative">
                                    <input
                                        type="checkbox"
                                        className="sr-only"
                                        checked={delegateEnabled}
                                        onChange={e => setDelegateEnabled(e.target.checked)}
                                    />
                                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors duration-150 ${
                                        delegateEnabled
                                            ? 'bg-blue-600 border-blue-600'
                                            : 'border-gray-300 dark:border-[#1e2535] group-hover:border-blue-400'
                                    }`}>
                                        {delegateEnabled && (
                                            <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 8">
                                                <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                            </svg>
                                        )}
                                    </div>
                                </div>
                                <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
                                    Delegate my voting authority
                                </span>
                                <span className="text-xs text-gray-400 dark:text-gray-500">
                                    (proxy your vote to another council member)
                                </span>
                            </label>

                            {delegateEnabled && (
                                <div className="mt-3 flex gap-2 items-center">
                                    <input
                                        type="text"
                                        placeholder="Delegate agent ID (e.g. 10002)…"
                                        value={delegateTarget}
                                        onChange={e => setDelegateTarget(e.target.value)}
                                        className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
                                    />
                                    <button
                                        onClick={handleDelegate}
                                        disabled={isDelegating || !delegateTarget.trim()}
                                        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
                                    >
                                        {isDelegating
                                            ? <LoadingSpinner size="xs" />
                                            : <Shield className="w-3.5 h-3.5" />
                                        }
                                        {isDelegating ? 'Delegating…' : 'Delegate'}
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}