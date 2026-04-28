// ─── WidgetErrorFallback ──────────────────────────────────────────────────────
// Inline error state rendered inside a single widget when its query fails.
// Keeps every other widget on the page functional (graceful degradation).

import { AlertTriangle, RefreshCw } from 'lucide-react';

interface WidgetErrorFallbackProps {
    /** Human-readable name displayed in the error message. */
    widgetName: string;
    /** When provided a Retry button is rendered. */
    onRetry?:   () => void;
}

export function WidgetErrorFallback({ widgetName, onRetry }: WidgetErrorFallbackProps) {
    return (
        <div
            role="alert"
            className="flex flex-col items-center justify-center gap-3 p-6 bg-red-50 dark:bg-red-500/10 rounded-xl border border-red-200 dark:border-red-500/20 text-center"
        >
            <AlertTriangle
                className="w-6 h-6 text-red-500 dark:text-red-400"
                aria-hidden="true"
            />
            <p className="text-sm font-medium text-red-600 dark:text-red-400">
                Failed to load {widgetName}
            </p>
            {onRetry && (
                <button
                    onClick={onRetry}
                    className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 rounded-lg hover:bg-red-200 dark:hover:bg-red-500/30 transition-all duration-200"
                >
                    <RefreshCw className="w-3 h-3" aria-hidden="true" />
                    Retry
                </button>
            )}
        </div>
    );
}