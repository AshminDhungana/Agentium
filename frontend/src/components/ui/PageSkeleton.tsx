// ─── PageSkeleton ────────────────────────────────────────────────────────────
// Generic configurable skeleton loader for pages that currently show bare
// Loader2 spinners during data fetch. Matches the target layout to prevent
// layout shift and provides a polished loading experience.
// ─────────────────────────────────────────────────────────────────────────────

export interface PageSkeletonProps {
    /** Layout variant matching the page structure. */
    variant: 'cards' | 'table' | 'list' | 'detail';
    /** Number of skeleton items to render. Defaults based on variant. */
    count?: number;
    /** Grid columns for the 'cards' variant. Defaults to 3. */
    columns?: 1 | 2 | 3 | 4;
}

function Pulse({ className, style }: { className: string, style?: React.CSSProperties }) {
    return <div className={`animate-pulse rounded-xl bg-gray-200 dark:bg-[#1e2535] ${className}`} style={style} />;
}

function SkeletonCards({ count, columns }: { count: number; columns: number }) {
    const colClass =
        columns === 1 ? 'grid-cols-1'
      : columns === 2 ? 'grid-cols-1 md:grid-cols-2'
      : columns === 4 ? 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4'
      :                  'grid-cols-1 md:grid-cols-2 lg:grid-cols-3';

    return (
        <div className={`grid ${colClass} gap-5`}>
            {Array.from({ length: count }).map((_, i) => (
                <div
                    key={i}
                    className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6"
                    style={{ animationDelay: `${i * 60}ms` }}
                >
                    <div className="flex items-center gap-3 mb-4">
                        <Pulse className="w-10 h-10 rounded-lg" />
                        <div className="flex-1 space-y-2">
                            <Pulse className="h-4 w-3/4" />
                            <Pulse className="h-3 w-1/2" />
                        </div>
                    </div>
                    <Pulse className="h-3 w-full mb-2" />
                    <Pulse className="h-3 w-2/3" />
                </div>
            ))}
        </div>
    );
}

function SkeletonTable({ count }: { count: number }) {
    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden">
            {/* Header row */}
            <div className="flex items-center gap-4 p-4 border-b border-gray-200 dark:border-[#1e2535]">
                {[120, 160, 100, 80, 60].map((w, i) => (
                    <Pulse key={i} className="h-3" style={{ width: `${w}px` } as React.CSSProperties} />
                ))}
            </div>
            {/* Data rows */}
            {Array.from({ length: count }).map((_, i) => (
                <div
                    key={i}
                    className="flex items-center gap-4 p-4 border-b border-gray-100 dark:border-[#1e2535]/50 last:border-0"
                    style={{ animationDelay: `${i * 40}ms` }}
                >
                    <Pulse className="w-8 h-8 rounded-full" />
                    <Pulse className="h-3 w-32" />
                    <Pulse className="h-3 w-24" />
                    <Pulse className="h-3 w-16" />
                    <Pulse className="h-6 w-16 rounded-full" />
                </div>
            ))}
        </div>
    );
}

function SkeletonList({ count }: { count: number }) {
    return (
        <div className="space-y-3">
            {Array.from({ length: count }).map((_, i) => (
                <div
                    key={i}
                    className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 flex items-center gap-4"
                    style={{ animationDelay: `${i * 50}ms` }}
                >
                    <Pulse className="w-10 h-10 rounded-lg flex-shrink-0" />
                    <div className="flex-1 space-y-2">
                        <Pulse className="h-4 w-2/5" />
                        <Pulse className="h-3 w-3/4" />
                    </div>
                    <Pulse className="h-6 w-20 rounded-full" />
                </div>
            ))}
        </div>
    );
}

function SkeletonDetail() {
    return (
        <div className="space-y-6">
            <div className="flex items-center gap-4">
                <Pulse className="w-14 h-14 rounded-xl" />
                <div className="space-y-2">
                    <Pulse className="h-5 w-48" />
                    <Pulse className="h-3 w-32" />
                </div>
            </div>
            <Pulse className="h-40 w-full" />
            <div className="grid grid-cols-2 gap-4">
                <Pulse className="h-24" />
                <Pulse className="h-24" />
            </div>
        </div>
    );
}

export function PageSkeleton({ variant, count, columns = 3 }: PageSkeletonProps) {
    const itemCount = count ?? (variant === 'table' ? 8 : variant === 'cards' ? 6 : 5);

    return (
        <div className="space-y-6 p-6" aria-busy="true" aria-label="Loading…">
            {/* Page title skeleton */}
            <div className="flex items-center justify-between">
                <Pulse className="h-7 w-48" />
                <Pulse className="h-9 w-32 rounded-lg" />
            </div>

            {variant === 'cards'  && <SkeletonCards count={itemCount} columns={columns} />}
            {variant === 'table'  && <SkeletonTable count={itemCount} />}
            {variant === 'list'   && <SkeletonList count={itemCount} />}
            {variant === 'detail' && <SkeletonDetail />}
        </div>
    );
}
