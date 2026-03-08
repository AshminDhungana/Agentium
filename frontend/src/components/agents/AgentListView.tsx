import React from 'react';
import { Agent } from '../../types';
import { Shield, Brain, Users, Terminal, Activity, Zap, TrendingUp, Trash2, CheckSquare } from 'lucide-react';
import { AGENT_TYPE_LABELS } from '../../constants/agents';

interface AgentListViewProps {
    agents:      Agent[];
    onSpawn:     (agent: Agent) => void;
    onTerminate: (agent: Agent) => void;
    onPromote?:  (agent: Agent) => void;
}

function TypeIcon({ type }: { type: Agent['agent_type'] }) {
    switch (type) {
        case 'head_of_council': return <Shield   className="w-4 h-4 text-violet-600 dark:text-violet-400" />;
        case 'council_member':  return <Users    className="w-4 h-4 text-blue-600 dark:text-blue-400"   />;
        case 'lead_agent':      return <Brain    className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />;
        case 'task_agent':      return <Terminal className="w-4 h-4 text-amber-600 dark:text-amber-400" />;
        default:                return <Activity className="w-4 h-4 text-slate-500 dark:text-slate-400" />;
    }
}

function StatusBadge({ status }: { status: Agent['status'] }) {
    const map: Record<string, string> = {
        active:       'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/30',
        working:      'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30',
        deliberating: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30',
        terminated:   'bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/30',
        terminating:  'bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/30',
        suspended:    'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-500/20 dark:text-orange-300 dark:border-orange-500/30',
        initializing: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:border-slate-600',
    };
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${map[status] ?? map.initializing}`}>
            {status}
        </span>
    );
}

export const AgentListView: React.FC<AgentListViewProps> = React.memo(({
    agents, onSpawn, onTerminate, onPromote,
}) => {
    // Filter out critics (4–6 prefix) from list view; they render separately in tree
    const displayAgents = agents.filter(a => {
        const prefix = (a.agentium_id ?? a.id ?? '')[0];
        return !['4', '5', '6'].includes(prefix);
    });

    if (displayAgents.length === 0) {
        return (
            <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-8">
                No agents to display.
            </p>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                        {['Agent', 'Type', 'Status', 'Subordinates', 'Tasks Done', 'Actions'].map(h => (
                            <th
                                key={h}
                                className="text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider py-3 px-4 first:pl-0"
                            >
                                {h}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {displayAgents.map(agent => {
                        const isTerminated  = agent.status === 'terminated' || agent.status === 'terminating';
                        const isHead        = agent.agent_type === 'head_of_council';
                        const isTask        = agent.agent_type === 'task_agent';
                        const subordinates  = Array.isArray(agent.subordinates) ? agent.subordinates.length : 0;
                        const tasksCompleted = agent.stats?.tasks_completed ?? 0;
                        const activeCount    = agent.active_task_count ?? 0;

                        return (
                            <tr
                                key={agent.id || agent.agentium_id}
                                className={`transition-colors duration-100 ${
                                    isTerminated
                                        ? 'opacity-50'
                                        : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                                }`}
                            >
                                {/* Agent name + ID */}
                                <td className="py-3 px-4 pl-0">
                                    <div className="flex items-center gap-2.5">
                                        <div className="w-8 h-8 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg flex items-center justify-center flex-shrink-0">
                                            <TypeIcon type={agent.agent_type} />
                                        </div>
                                        <div>
                                            <p className="font-medium text-slate-900 dark:text-slate-100 leading-none">
                                                {agent.name}
                                            </p>
                                            <p className="text-xs text-slate-400 dark:text-slate-500 font-mono mt-0.5">
                                                {agent.agentium_id}
                                            </p>
                                        </div>
                                    </div>
                                </td>

                                {/* Type */}
                                <td className="py-3 px-4">
                                    <span className="text-xs text-slate-600 dark:text-slate-400">
                                        {AGENT_TYPE_LABELS[agent.agent_type] ?? agent.agent_type}
                                    </span>
                                </td>

                                {/* Status */}
                                <td className="py-3 px-4">
                                    <div className="flex items-center gap-1.5">
                                        <StatusBadge status={agent.status} />
                                        {activeCount > 0 && (
                                            <span className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
                                                <CheckSquare className="w-3 h-3" />
                                                {activeCount}
                                            </span>
                                        )}
                                    </div>
                                </td>

                                {/* Subordinates */}
                                <td className="py-3 px-4">
                                    <span className="text-slate-700 dark:text-slate-300 font-mono text-xs">
                                        {subordinates}
                                    </span>
                                </td>

                                {/* Tasks done */}
                                <td className="py-3 px-4">
                                    <span className="text-slate-700 dark:text-slate-300 font-mono text-xs">
                                        {tasksCompleted}
                                    </span>
                                </td>

                                {/* Actions */}
                                <td className="py-3 px-4">
                                    <div className="flex items-center gap-1.5">
                                        {!isTerminated && !isTask && (
                                            <button
                                                onClick={() => onSpawn(agent)}
                                                title="Spawn subordinate"
                                                className="p-1.5 rounded-lg text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors"
                                            >
                                                <Zap className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                        {!isTerminated && isTask && onPromote && (
                                            <button
                                                onClick={() => onPromote(agent)}
                                                title="Promote to Lead"
                                                className="p-1.5 rounded-lg text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
                                            >
                                                <TrendingUp className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                        {!isTerminated && !isHead && (
                                            <button
                                                onClick={() => onTerminate(agent)}
                                                title="Terminate"
                                                className="p-1.5 rounded-lg text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
});

AgentListView.displayName = 'AgentListView';