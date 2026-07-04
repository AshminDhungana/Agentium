/**
 * @description Animated placeholder that matches the exact shape of ModelCard.
 * Shown in the grid while configs are loading or refreshing, instead of
 * replacing the whole page with a full-screen spinner.
 * @example
 * ```tsx
 * import { ModelCardSkeleton } from '@/components/models/ModelCardSkeleton';
 *
 * <ModelCardSkeleton />
 * ```
 */

import React from 'react';

export const ModelCardSkeleton: React.FC = () => (
    <div
        className="relative bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden"
        aria-hidden="true"
    >
        {/* Gradient accent bar placeholder */}
        <div className="h-0.5 bg-gray-200 dark:bg-[#1e2535] animate-pulse" />

        <div className="p-5 space-y-4">
            {/* Header row */}
            <div className="flex items-start justify-between">
                {/* Provider badge */}
                <div className="h-8 w-28 rounded-lg bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                {/* Status badge */}
                <div className="h-6 w-16 rounded-full bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
            </div>

            {/* Config name */}
            <div className="h-4 w-3/4 rounded bg-gray-100 dark:bg-[#1e2535] animate-pulse" />

            {/* Model info rows */}
            <div className="space-y-2">
                <div className="flex justify-between items-center">
                    <div className="h-3 w-12 rounded bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                    <div className="h-5 w-36 rounded-md bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                </div>
                <div className="flex justify-between items-center">
                    <div className="h-3 w-14 rounded bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                    <div className="h-5 w-20 rounded-md bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                </div>
            </div>

            {/* Model tag strip */}
            <div className="flex gap-1.5">
                {[1, 2, 3].map((i) => (
                    <div
                        key={i}
                        className="h-5 w-20 rounded-md bg-gray-100 dark:bg-[#1e2535] animate-pulse"
                    />
                ))}
            </div>

            {/* Usage stats bar */}
            <div className="h-14 rounded-lg bg-gray-100 dark:bg-[#0f1117] animate-pulse" />

            {/* Action buttons row */}
            <div className="flex gap-2">
                {[1, 2, 3, 4].map((i) => (
                    <div
                        key={i}
                        className="h-8 flex-1 rounded-lg bg-gray-100 dark:bg-[#1e2535] animate-pulse"
                    />
                ))}
            </div>
        </div>
    </div>
);