/**
 * @description Dashboard widget listing the top-6 non-terminated agents sorted by activity.
 * Shows a per-row loading skeleton, per-widget error fallback, and ARIA labels.
 * @example
 * ```tsx
 * import { AgentsList } from '@/components/dashboard/AgentsList';
 *
 * <AgentsList agents={agents} isLoading={false} isError={false} onRetry={refetch} />
 * ```
 * @param {Agent[]} props.agents - Array of agents to display.
 * @param {boolean} props.isLoading - Whether to show loading skeletons.
 * @param {boolean} props.isError - Whether to show the error fallback.
 * @param {() => void} props.onRetry - Callback to retry fetching on error.
 */

import { Users } from 'lucide-react';
import type { Agent } from '@/types';
import { getAgentStatusColors } from '@/utils/statusColors';
import { WidgetCard } from './WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { WidgetErrorFallback } from '@/components/ui/WidgetErrorFallback';

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

function AgentRow({ agent }: { agent: Agent }) {
    const colors = getAgentStatusColors(agent.status);
    return (
        <li className="flex items-center gap-3 px-6 py-3 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-100">
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
        </li>
    );
}

export function AgentsList({ agents, isLoading, isError, onRetry }: AgentsListProps) {
  return (
    <WidgetCard title="Active Agents" icon={Users} aria-label="Active agents">
      {isError ? (
        <WidgetErrorFallback widgetName="Could not load agents" onRetry={onRetry} />
      ) : isLoading ? (
        <div className="divide-y divide-hairline">
          {Array.from({ length: 4 }).map((_, i) => (<SkeletonRow key={i} />))}
        </div>
      ) : agents.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No active agents"
          description="Spawn agents from the Agents page to see them here."
          size="sm"
        />
      ) : (
        <ul className="divide-y divide-hairline" role="status" aria-live="polite">
          {agents.slice(0, 6).map((agent) => (<AgentRow key={agent.id} agent={agent} />))}
        </ul>
      )}
    </WidgetCard>
  );
}
