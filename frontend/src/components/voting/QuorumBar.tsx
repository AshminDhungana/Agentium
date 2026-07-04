/**
 * @description Visual vote tally bar with a quorum threshold marker.
 * Quorum prop is clamped to [0, 1] before rendering.
 * @example
 * ```tsx
 * import { QuorumBar } from '@/components/voting/QuorumBar';
 *
 * <QuorumBar votesFor={12} votesAgainst={3} votesAbstain={1} total={20} quorum={0.6} />
 * ```
 * @param {number} props.votesFor - Number of "for" votes.
 * @param {number} props.votesAgainst - Number of "against" votes.
 * @param {number} props.votesAbstain - Number of "abstain" votes.
 * @param {number} props.total - Total eligible voters.
 * @param {number} [props.quorum] - Quorum threshold as a fraction (0.0–1.0, default: 0.6).
 */

import React from 'react';

interface QuorumBarProps {
    votesFor: number;
    votesAgainst: number;
    votesAbstain: number;
    /** Total eligible voters — used to calculate percentages. */
    total: number;
    /**
     * Quorum threshold as a fraction of total (0.0 – 1.0, default 0.6).
     * Values outside [0, 1] are clamped automatically.
     */
    quorum?: number;
}

export function QuorumBar({
    votesFor,
    votesAgainst,
    votesAbstain,
    total,
    quorum = 0.6,
}: QuorumBarProps) {
    const cast = votesFor + votesAgainst + votesAbstain;

    const forPct     = total > 0 ? (votesFor     / total) * 100 : 0;
    const againstPct = total > 0 ? (votesAgainst / total) * 100 : 0;
    const abstainPct = total > 0 ? (votesAbstain / total) * 100 : 0;

    // FIX: clamp quorum to [0, 1] so the marker never escapes the bar
    const clampedQuorum = Math.min(1.0, Math.max(0.0, quorum));
    const quorumPct = clampedQuorum * 100;

    return (
        <div>
            {/* Progress bar */}
            <div className="relative h-3 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700">
                <div className="absolute inset-0 flex">
                    <div
                        className="bg-green-500 transition-all duration-500"
                        style={{ width: `${forPct}%` }}
                    />
                    <div
                        className="bg-red-500 transition-all duration-500"
                        style={{ width: `${againstPct}%` }}
                    />
                    <div
                        className="bg-gray-400 transition-all duration-500"
                        style={{ width: `${abstainPct}%` }}
                    />
                </div>

                {/* Quorum threshold marker */}
                <div
                    className="absolute top-0 bottom-0 w-0.5 bg-white/80 dark:bg-white/60"
                    style={{ left: `${quorumPct}%` }}
                    title={`${Math.round(quorumPct)}% quorum required`}
                />
            </div>

            {/* Legend */}
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mt-1.5">
                <div className="flex gap-3">
                    <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-green-500" />
                        For {votesFor}
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-red-500" />
                        Against {votesAgainst}
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-gray-400" />
                        Abstain {votesAbstain}
                    </span>
                </div>
                <span>{cast} / {total} voted</span>
            </div>
        </div>
    );
}