import React from 'react';
import { Task } from '../../types';
import { Clock, User, Zap, CheckCircle2, AlertCircle, Loader2, MessageSquare } from 'lucide-react';

interface TaskCardProps {
    task: Task;
    onClick?: (task: Task) => void;
}

// Enhanced status configuration with icons and proper dark mode tokens
const STATUS_CONFIG: Record<string, { 
    bg: string; 
    text: string; 
    border: string; 
    darkBg: string; 
    darkText: string; 
    darkBorder: string;
    icon: React.ReactNode;
    label: string;
}> = {
    pending: {
        bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200',
        darkBg: 'dark:bg-amber-500/10', darkText: 'dark:text-amber-300', darkBorder: 'dark:border-amber-500/20',
        icon: <Clock className="w-3 h-3" />, label: 'Pending'
    },
    deliberating: {
        bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200',
        darkBg: 'dark:bg-purple-500/10', darkText: 'dark:text-purple-300', darkBorder: 'dark:border-purple-500/20',
        icon: <MessageSquare className="w-3 h-3" />, label: 'Deliberating'
    },
    in_progress: {
        bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200',
        darkBg: 'dark:bg-blue-500/10', darkText: 'dark:text-blue-300', darkBorder: 'dark:border-blue-500/20',
        icon: <Loader2 className="w-3 h-3 animate-spin" />, label: 'In Progress'
    },
    executing: {
        bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200',
        darkBg: 'dark:bg-blue-500/10', darkText: 'dark:text-blue-300', darkBorder: 'dark:border-blue-500/20',
        icon: <Zap className="w-3 h-3" />, label: 'Executing'
    },
    completed: {
        bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200',
        darkBg: 'dark:bg-emerald-500/10', darkText: 'dark:text-emerald-300', darkBorder: 'dark:border-emerald-500/20',
        icon: <CheckCircle2 className="w-3 h-3" />, label: 'Completed'
    },
    failed: {
        bg: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200',
        darkBg: 'dark:bg-rose-500/10', darkText: 'dark:text-rose-300', darkBorder: 'dark:border-rose-500/20',
        icon: <AlertCircle className="w-3 h-3" />, label: 'Failed'
    },
    cancelled: {
        bg: 'bg-gray-50', text: 'text-gray-600', border: 'border-gray-200',
        darkBg: 'dark:bg-gray-500/10', darkText: 'dark:text-gray-400', darkBorder: 'dark:border-gray-500/20',
        icon: <AlertCircle className="w-3 h-3" />, label: 'Cancelled'
    },
};

// Priority configuration with desaturated dark mode colors
const PRIORITY_CONFIG: Record<string, { 
    dot: string; 
    label: string;
    darkDot: string;
}> = {
    critical: { 
        dot: 'bg-rose-500', 
        label: 'text-rose-600 dark:text-rose-400',
        darkDot: 'dark:bg-rose-400'
    },
    high: { 
        dot: 'bg-orange-500', 
        label: 'text-orange-600 dark:text-orange-400',
        darkDot: 'dark:bg-orange-400'
    },
    urgent: { 
        dot: 'bg-orange-500', 
        label: 'text-orange-600 dark:text-orange-400',
        darkDot: 'dark:bg-orange-400'
    },
    normal: { 
        dot: 'bg-blue-500', 
        label: 'text-blue-600 dark:text-blue-400',
        darkDot: 'dark:bg-blue-400'
    },
    low: { 
        dot: 'bg-gray-400', 
        label: 'text-gray-500 dark:text-gray-400',
        darkDot: 'dark:bg-gray-500'
    },
};

export const TaskCard: React.FC<TaskCardProps> = ({ task, onClick }) => {
    const assignedAgents = task.assigned_agents?.task_agents ?? [];
    const progress = task.progress ?? 0;

    const statusConfig = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.cancelled;
    const priorityConfig = PRIORITY_CONFIG[task.priority] ?? PRIORITY_CONFIG.normal;

    // Keep exact same date format as original for light mode consistency
    const formattedDate = task.created_at
        ? new Date(task.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
        : '—';

    const isActive = task.status === 'in_progress' || task.status === 'executing';
    const isCompleted = task.status === 'completed';

    // Helper to safely get agent initial (handles string[] or object[])
    const getAgentInitial = (agent: string | { name?: string }): string => {
        if (typeof agent === 'string') return agent.charAt(0).toUpperCase();
        return agent.name?.charAt(0).toUpperCase() || 'A';
    };

    // Helper to get unique key for agent
    const getAgentKey = (agent: string | { id?: string; agentium_id?: string }, idx: number): string => {
        if (typeof agent === 'string') return `${agent}-${idx}`;
        return agent.agentium_id || agent.id || `${idx}`;
    };

    return (
        <div 
            onClick={() => onClick?.(task)}
            className={`
                group relative overflow-hidden rounded-xl border p-5 
                bg-white dark:bg-[#161b27]
                border-gray-200 dark:border-[#1e2535]
                hover:border-gray-300 dark:hover:border-[#2a3347]
                hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)]
                transition-all duration-200 ease-out
                flex flex-col gap-3
                ${onClick ? 'cursor-pointer' : ''}
            `}
        >
            {/* Left accent line for status - adds visual hierarchy in dark mode */}
            <div className={`
                absolute left-0 top-0 bottom-0 w-1 
                ${statusConfig.bg.replace('bg-', 'bg-').replace('50', '500')}
                ${statusConfig.darkBg.replace('/10', '').replace('dark:bg-', 'dark:bg-')}
                opacity-0 dark:opacity-40
                group-hover:opacity-100 dark:group-hover:opacity-60
                transition-opacity duration-200
            `} />

            {/* Top row: priority dot + status badge */}
            <div className="flex items-center justify-between pl-3">
                <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide ${priorityConfig.label}`}>
                    <span className={`
                        w-1.5 h-1.5 rounded-full 
                        ${priorityConfig.dot} 
                        ${priorityConfig.darkDot}
                        ${isActive ? 'animate-pulse' : ''}
                    `} />
                    {task.priority}
                </div>
                
                {/* Enhanced status badge with icon */}
                <span className={`
                    flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border capitalize
                    ${statusConfig.bg} ${statusConfig.text} ${statusConfig.border}
                    ${statusConfig.darkBg} ${statusConfig.darkText} ${statusConfig.darkBorder}
                    transition-colors duration-200
                `}>
                    {statusConfig.icon}
                    {task.status?.replace('_', ' ')}
                </span>
            </div>

            {/* Title & description */}
            <div className="pl-3">
                <h3 className="
                    text-gray-900 dark:text-gray-100 font-semibold text-sm leading-snug line-clamp-2 mb-1
                    group-hover:text-blue-600 dark:group-hover:text-blue-400
                    transition-colors duration-200
                ">
                    {task.title}
                </h3>
                <p className="text-gray-500 dark:text-gray-400 text-xs leading-relaxed line-clamp-3">
                    {task.description}
                </p>
            </div>

            {/* Progress bar — only when in flight */}
            {progress > 0 && progress < 100 && (
                <div className="pl-3">
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Progress</span>
                        <span className={`
                            text-xs font-semibold tabular-nums
                            ${isCompleted ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-700 dark:text-gray-300'}
                        `}>
                            {progress}%
                        </span>
                    </div>
                    <div className="
                        w-full bg-gray-100 dark:bg-[#0f1117] rounded-full h-1.5 overflow-hidden
                        border border-gray-200 dark:border-[#1e2535]
                    ">
                        <div
                            className={`
                                h-full rounded-full transition-all duration-500
                                ${isCompleted 
                                    ? 'bg-emerald-500 dark:bg-emerald-400' 
                                    : 'bg-blue-500 dark:bg-blue-400'
                                }
                                ${isActive ? 'animate-pulse' : ''}
                            `}
                            style={{ width: `${Math.max(progress, isActive ? 5 : 0)}%` }}
                        />
                    </div>
                </div>
            )}

            {/* Footer: date + agents */}
            <div className="
                flex items-center justify-between pt-2 border-t border-gray-100 dark:border-[#1e2535] mt-auto pl-3
            ">
                <div className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                    <Clock className="w-3 h-3" />
                    {formattedDate}
                </div>

                {/* Enhanced agent assignment display */}
                {assignedAgents.length > 0 ? (
                    <div className="flex items-center gap-2">
                        {/* Avatar stack */}
                        <div className="flex -space-x-1.5">
                            {assignedAgents.slice(0, 3).map((agent, idx) => (
                                <div 
                                    key={getAgentKey(agent, idx)}
                                    className="
                                        w-5 h-5 rounded-full 
                                        bg-blue-100 dark:bg-blue-500/20 
                                        border border-white dark:border-[#161b27]
                                        flex items-center justify-center 
                                        text-[9px] font-bold text-blue-600 dark:text-blue-400
                                    "
                                >
                                    {getAgentInitial(agent)}
                                </div>
                            ))}
                            {assignedAgents.length > 3 && (
                                <div className="
                                    w-5 h-5 rounded-full 
                                    bg-gray-100 dark:bg-[#1e2535] 
                                    border border-white dark:border-[#161b27]
                                    flex items-center justify-center 
                                    text-[9px] font-medium text-gray-600 dark:text-gray-400
                                ">
                                    +{assignedAgents.length - 3}
                                </div>
                            )}
                        </div>
                        <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
                            {assignedAgents.length} Agent{assignedAgents.length > 1 ? 's' : ''}
                        </span>
                    </div>
                ) : (
                    <div className="
                        flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500
                        bg-gray-50 dark:bg-[#0f1117] px-2 py-0.5 rounded-full
                        border border-gray-200 dark:border-[#1e2535]
                    ">
                        <Zap className="w-3 h-3" />
                        Unassigned
                    </div>
                )}
            </div>
        </div>
    );
};
