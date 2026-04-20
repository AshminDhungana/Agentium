/**
 * VotingCard
 *
 * Summary card for a single amendment or deliberation.
 * Improvement: uses useCountdownTick() from the shared provider instead of
 * mounting its own setInterval — eliminating per-card timer overhead.
 */

import React from 'react';
import { Users, ChevronRight } from 'lucide-react';
import { AmendmentVoting, TaskDeliberation, isVotingActive, getStatusColor, formatCountdown } from '../../services/voting';
import { useCountdownTick } from '../../hooks/useCountdownTick';

interface VotingCardProps {
    item: AmendmentVoting | TaskDeliberation;
    isSelected: boolean;
    onClick: () => void;
    isAmendment: boolean;
}

export function VotingCard({ item, isSelected, onClick, isAmendment }: VotingCardProps) {
    // Single shared tick from provider — no per-card interval
    const tick = useCountdownTick();

    const active = isVotingActive(item);
    const totalVotes = item.votes_for + item.votes_against + item.votes_abstain;
    const totalEligible = isAmendment
        ? (item as AmendmentVoting).eligible_voters?.length ?? 0
        : (item as TaskDeliberation).participating_members?.length ?? 0;

    return (
        <div
            onClick={onClick}
            className={`group bg-white dark:bg-[#161b27] rounded-xl border transition-all duration-200 cursor-pointer p-5 ${
                isSelected
                    ? 'border-blue-500 dark:border-blue-500 ring-1 ring-blue-500/30 shadow-md'
                    : 'border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-sm'
            }`}
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    {/* Status badge + countdown */}
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <span
                            className="text-xs px-2 py-0.5 rounded-full font-medium"
                            style={{
                                backgroundColor: `${getStatusColor(item.status)}18`,
                                color: getStatusColor(item.status),
                            }}
                        >
                            {item.status.toUpperCase()}
                        </span>
                        {active && (
                            <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                                {/* tick dependency ensures re-render each second */}
                                {tick >= 0 && formatCountdown(item.ended_at)}
                            </span>
                        )}
                    </div>

                    {/* Title */}
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                        {isAmendment
                            ? (item as AmendmentVoting).title || item.agentium_id
                            : `Task: ${(item as TaskDeliberation).task_id}`}
                    </h3>

                    {/* Meta */}
                    {isAmendment && (item as AmendmentVoting).sponsors?.length > 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {(item as AmendmentVoting).sponsors.join(', ')}
                        </p>
                    )}
                    {!isAmendment && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {(item as TaskDeliberation).participating_members?.length ?? 0} participants
                        </p>
                    )}
                </div>

                <ChevronRight
                    className={`w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5 transition-transform ${
                        isSelected ? 'rotate-90' : 'group-hover:translate-x-0.5'
                    }`}
                />
            </div>

            {/* Mini tally bar */}
            <div className="mt-3">
                <div className="relative h-1.5 rounded-full overflow-hidden bg-gray-100 dark:bg-[#1e2535]">
                    <div className="absolute inset-0 flex">
                        <div
                            className="bg-green-500"
                            style={{ width: totalEligible > 0 ? `${(item.votes_for / totalEligible) * 100}%` : '0%' }}
                        />
                        <div
                            className="bg-red-500"
                            style={{ width: totalEligible > 0 ? `${(item.votes_against / totalEligible) * 100}%` : '0%' }}
                        />
                        <div
                            className="bg-gray-400"
                            style={{ width: totalEligible > 0 ? `${(item.votes_abstain / totalEligible) * 100}%` : '0%' }}
                        />
                    </div>
                </div>
                <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500 mt-1">
                    <span>{totalVotes} votes cast</span>
                    <span>
                        {totalEligible > 0 ? Math.round((totalVotes / totalEligible) * 100) : 0}% turnout
                    </span>
                </div>
            </div>
        </div>
    );
}