// ─── DashboardSkeleton ────────────────────────────────────────────────────────
// Full-page loading skeleton shown while ALL dashboard queries are still on
// their first fetch.  Matches the real page layout to prevent layout shift.

/**
 * @description Full-page loading skeleton that mirrors the dashboard layout to prevent layout shift.
 * Renders animated pulse placeholders for the stats grid, charts, and bottom row.
 * @example
 * ```tsx
 * import { DashboardSkeleton } from '@/components/ui/DashboardSkeleton';
 *
 * <DashboardSkeleton />
 * ```
 */
export function DashboardSkeleton() {
    return (
        <div
            className="space-y-8"
            aria-busy="true"
            aria-label="Loading dashboard…"
        >
            {/* Stats grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div
                        key={i}
                        className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] animate-pulse"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-gray-200 dark:bg-[#1e2535]" />
                            <div className="w-10 h-7 rounded bg-gray-200 dark:bg-[#1e2535]" />
                        </div>
                        <div className="w-28 h-4 rounded bg-gray-100 dark:bg-[#252f40]" />
                    </div>
                ))}
            </div>

            {/* Wide single-column block (ProviderAnalytics / BudgetControl) */}
            <div className="h-40 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] animate-pulse" />
            <div className="h-32 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] animate-pulse" />

            {/* Two-column bottom row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="h-48 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] animate-pulse" />
                <div className="h-48 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] animate-pulse" />
            </div>
        </div>
    );
}