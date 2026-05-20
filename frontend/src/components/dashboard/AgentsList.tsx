// ─── AgentsList ───────────────────────────────────────────────────────────────
// Dashboard widget listing the top-6 non-terminated agents sorted by activity.
// Shows a per-row loading skeleton, per-widget error fallback, and ARIA labels.

import { Users, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Agent } from '@/types';
import { getAgentStatusColors } from '@/utils/statusColors';
import { WidgetErrorFallback }  from '@/components/ui/WidgetErrorFallback';

interface AgentsListProps {
    agents:    Agent[];
    isLoading: boolean;
    isError:   boolean;
    onRetry:   () => void;
}

function SkeletonRow() {
    return (
        <div className="flex items-center gap-3 px-6 py-3 animate-pulse">
            <div className="w-2 h-2 rounded-full bg-gray-200 dark:bg-[#1e2535] flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
                <div className="h-4 w-36 rounded bg-gray-100 dark:bg-[#252f40]" />
                <div className="h-3 w-24 rounded bg-gray-100 dark:bg-[#252f40]" />
            </div>
            <div className="w-14 h-5 rounded-full bg-gray-100 dark:bg-[#252f40]" />
        </div>
    );
}

export function AgentsList({ agents, isLoading, isError, onRetry }: AgentsListProps) {
    if (isError) {
        return <WidgetErrorFallback widgetName="Agents" onRetry={onRetry} />;
    }

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                        <Users className="w-4 h-4 text-green-600 dark:text-green-400" aria-hidden="true" />
                    </div>
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                        Active Agents
                    </h2>
                </div>
                <Link
                    to="/agents"
                    className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
                    aria-label="View all agents"
                >
                    View all
                    <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
                </Link>
            </div>

            {/* Rows */}
            <div
                className="divide-y divide-gray-100 dark:divide-[#1e2535]"
                aria-live="polite"
                aria-atomic="false"
            >
                {isLoading ? (
                    Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
                ) : agents.length === 0 ? (
                    <div className="px-6 py-8 text-center text-sm text-gray-600 dark:text-gray-400">
                        No active agents
                    </div>
                ) : (
                    agents.map(agent => {
                        const colors = getAgentStatusColors(agent.status);
                        return (
                            <div
                                key={agent.id}
                                className="flex items-center gap-3 px-6 py-3 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-100"
                            >
                                <span
                                    className={`w-2 h-2 rounded-full flex-shrink-0 ${colors.dot}`}
                                    role="status"
                                    aria-label={`${agent.name} is ${colors.label}`}
                                />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                        {agent.name}
                                    </p>
                                    {agent.current_task_title && (
                                        <p className="text-xs text-gray-600 dark:text-gray-500 truncate">
                                            {agent.current_task_title}
                                        </p>
                                    )}
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