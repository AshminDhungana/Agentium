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
import { getTaskStatusColors } from '@/utils/statusColors';
import { WidgetCard } from './WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { WidgetErrorFallback } from '@/components/ui/WidgetErrorFallback';

interface RecentTasksProps {
    tasks: Task[];
    isLoading: boolean;
    isError: boolean;
    onRetry: () => void;
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

function TaskRow({ task }: { task: Task }) {
    const colors = getTaskStatusColors(task.status);
    const dateStr = formatDate(task.updated_at ?? task.created_at);
    return (
        <li
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
        </li>
    );
}

export function RecentTasks({ tasks, isLoading, isError, onRetry }: RecentTasksProps) {
    return (
        <WidgetCard title="Recent Tasks" icon={ClipboardList} aria-label="Recent tasks">
            {isError ? (
                <WidgetErrorFallback widgetName="Recent Tasks" onRetry={onRetry} />
            ) : isLoading ? (
                <div className="divide-y divide-hairline">
                    {Array.from({ length: 5 }).map((_, i) => (<SkeletonRow key={i} />))}
                </div>
            ) : tasks.length === 0 ? (
                <EmptyState
                    icon={ClipboardList}
                    title="No tasks yet"
                    description="Tasks you create will appear here in real time."
                    size="sm"
                />
            ) : (
                <ul className="divide-y divide-hairline" role="status" aria-live="polite">
                    {tasks.slice(0, 5).map((task) => (<TaskRow key={task.id} task={task} />))}
                </ul>
            )}
        </WidgetCard>
    );
}
