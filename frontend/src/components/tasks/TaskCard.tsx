import React from 'react';
import { Task } from '../../types';
import { Clock, User, Zap } from 'lucide-react';

interface TaskCardProps {
    task: Task;
}

const STATUS_STYLES: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
    deliberating: 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800',
    in_progress: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800',
    executing: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800',
    completed: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
    failed: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
    cancelled: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-700 dark:text-gray-400 dark:border-gray-600',
};

const PRIORITY_STYLES: Record<string, { dot: string; label: string }> = {
    critical: { dot: 'bg-red-500', label: 'text-red-600 dark:text-red-400' },
    high: { dot: 'bg-orange-500', label: 'text-orange-600 dark:text-orange-400' },
    urgent: { dot: 'bg-orange-500', label: 'text-orange-600 dark:text-orange-400' },
    normal: { dot: 'bg-blue-500', label: 'text-blue-600 dark:text-blue-400' },
    low: { dot: 'bg-gray-400', label: 'text-gray-500 dark:text-gray-400' },
};

const PROGRESS_COLOR: Record<string, string> = {
    completed: 'bg-green-500',
    failed: 'bg-red-500',
    in_progress: 'bg-blue-500',
    default: 'bg-blue-500',
};

export const TaskCard: React.FC<TaskCardProps> = ({ task }) => {
    const assignedAgents = task.assigned_agents?.task_agents ?? [];
    const progress = task.progress ?? 0;

    const statusStyle = STATUS_STYLES[task.status] ?? STATUS_STYLES.cancelled;
    const priorityStyle = PRIORITY_STYLES[task.priority] ?? PRIORITY_STYLES.normal;
    const progressColor = PROGRESS_COLOR[task.status] ?? PROGRESS_COLOR.default;

    const formattedDate = task.created_at
        ? new Date(task.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
        : '—';

    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 hover:shadow-md dark:hover:border-gray-600 transition-all duration-150 flex flex-col gap-3">

            {/* Top row: priority dot + status badge */}
            <div className="flex items-center justify-between">
                <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${priorityStyle.label}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${priorityStyle.dot}`} />
                    {task.priority}
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${statusStyle}`}>
                    {task.status?.replace('_', ' ')}
                </span>
            </div>

            {/* Title & description */}
            <div>
                <h3 className="text-gray-900 dark:text-white font-semibold text-sm leading-snug line-clamp-2 mb-1">
                    {task.title}
                </h3>
                <p className="text-gray-500 dark:text-gray-400 text-xs leading-relaxed line-clamp-3">
                    {task.description}
                </p>
            </div>

            {/* Progress bar — only when in flight */}
            {progress > 0 && progress < 100 && (
                <div>
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Progress</span>
                        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{progress}%</span>
                    </div>
                    <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                        <div
                            className={`${progressColor} h-full rounded-full transition-all duration-500`}
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>
            )}

            {/* Footer: date + agents */}
            <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-gray-700 mt-auto">
                <div className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                    <Clock className="w-3 h-3" />
                    {formattedDate}
                </div>

                {assignedAgents.length > 0 ? (
                    <div className="flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400">
                        <User className="w-3 h-3" />
                        {assignedAgents.length} Agent{assignedAgents.length > 1 ? 's' : ''}
                    </div>
                ) : (
                    <div className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                        <Zap className="w-3 h-3" />
                        Unassigned
                    </div>
                )}
            </div>
        </div>
    );
};
