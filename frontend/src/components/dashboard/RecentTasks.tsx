/**
 * @description Dashboard widget listing the 5 most-recently updated tasks.
 * Includes status badge, priority tag, relative date, loading skeletons,
 * and a per-widget error fallback with retry.
 * @example
 * ```tsx
 * import { RecentTasks } from '@/components/dashboard/RecentTasks';
 *
 * <RecentTasks tasks={tasks} isLoading={false} isError={false} onRetry={refetch} />
 * ```
 * @param {Task[]} props.tasks - Array of tasks to display.
 * @param {boolean} props.isLoading - Whether to show loading skeletons.
 * @param {boolean} props.isError - Whether to show the error fallback.
 * @param {() => void} props.onRetry - Callback to retry fetching on error.
 */

import { ClipboardList, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import type { Task } from '@/types';
import { getTaskStatusColors }  from '@/utils/statusColors';
import { WidgetErrorFallback }  from '@/components/ui/WidgetErrorFallback';

interface RecentTasksProps {
    tasks:     Task[];
    isLoading: boolean;
    isError:   boolean;
    onRetry:   () => void;
}

function SkeletonRow() {
    return (
        <div className="flex items-center gap-3 px-6 py-3 animate-pulse">
            <div className="flex-1 space-y-1.5">
                <div className="h-4 rounded bg-gray-100 dark:bg-[#252f40] w-3/4" />
                <div className="h-3 rounded bg-gray-100 dark:bg-[#252f40] w-1/3" />
            </div>
            <div className="w-16 h-5 rounded-full bg-gray-100 dark:bg-[#252f40]" />
        </div>
    );
}

function formatDate(dateStr: string | null | undefined): string | null {
    if (!dateStr) return null;
    try {
        return format(new Date(dateStr), 'MMM d');
    } catch {
        return null;
    }
}

export function RecentTasks({ tasks, isLoading, isError, onRetry }: RecentTasksProps) {
    if (isError) {
        return <WidgetErrorFallback widgetName="Recent Tasks" onRetry={onRetry} />;
    }

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <ClipboardList className="w-4 h-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />
                    </div>
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                        Recent Tasks
                    </h2>
                </div>
                <Link
                    to="/tasks"
                    className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    aria-label="View all tasks"
                >
                    View all
                    <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
                </Link>
            </div>

            {/* Rows */}
            <div
                role="status"
                className="divide-y divide-gray-100 dark:divide-[#1e2535]"
                aria-live="polite"
                aria-atomic="false"
            >
                {isLoading ? (
                    Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
                ) : tasks.length === 0 ? (
                    <div className="px-6 py-8 text-center text-sm text-gray-600 dark:text-gray-400">
                        No tasks yet
                    </div>
                ) : (
                    tasks.map(task => {
                        const colors  = getTaskStatusColors(task.status);
                        const dateStr = formatDate(task.updated_at ?? task.created_at);
                        return (
                            <div
                                key={task.id}
                                className="flex items-center gap-3 px-6 py-3 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-100"
                            >
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                        {task.title}
                                    </p>
                                    <div className="flex items-center gap-1.5 mt-0.5">
                                        <span className="text-xs text-gray-600 dark:text-gray-500 capitalize">
                                            {task.priority}
                                        </span>
                                        {dateStr && (
                                            <>
                                                <span className="text-xs text-gray-300 dark:text-gray-600">·</span>
                                                <span className="text-xs text-gray-600 dark:text-gray-500">
                                                    {dateStr}
                                                </span>
                                            </>
                                        )}
                                    </div>
                                </div>
                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${colors.badge}`}>
                                    {colors.label}
                                </span>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}