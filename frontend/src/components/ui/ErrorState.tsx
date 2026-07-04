// src/components/ui/ErrorState.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Reusable empty / error panel used wherever a data-fetch fails.
// Replaces the silent `return null` pattern that left users staring at
// a blank card with no indication of what went wrong.
// ─────────────────────────────────────────────────────────────────────────────

import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * @description Reusable error panel shown when a data fetch fails.
 * Renders an alert icon, an error message, and an optional retry button.
 * @example
 * ```tsx
 * import { ErrorState } from '@/components/ui/ErrorState';
 *
 * <ErrorState message="Failed to load agents" onRetry={retry} size="md" />
 * ```
 * @param {string} [props.message] - Human-readable description of what failed (default: 'Failed to load data').
 * @param {() => void} [props.onRetry] - If provided, a "Try again" button is rendered that calls this function.
 * @param {'sm' | 'md'} [props.size] - Visual size variant (default: 'md').
 */

export interface ErrorStateProps {
    /** Human-readable description of what failed. */
    message?: string;
    /** If provided, a "Try again" button is rendered that calls this function. */
    onRetry?: () => void;
    /** Visual size variant. Defaults to 'md'. */
    size?: 'sm' | 'md';
}

export function ErrorState({
    message = 'Failed to load data',
    onRetry,
    size = 'md',
}: ErrorStateProps) {
    const py = size === 'sm' ? 'py-4' : 'py-8';
    const iconSize = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';
    const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

    return (
        <div role="alert" className={`flex flex-col items-center gap-2 ${py} text-center`}>
            <AlertTriangle className={`${iconSize} text-amber-700 flex-shrink-0`} />
            <p className={`${textSize} text-gray-600 dark:text-gray-400`}>{message}</p>
            {onRetry && (
                <button
                    onClick={onRetry}
                    className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline transition-all duration-200"
                >
                    <RefreshCw className="w-3 h-3" />
                    Try again
                </button>
            )}
        </div>
    );
}