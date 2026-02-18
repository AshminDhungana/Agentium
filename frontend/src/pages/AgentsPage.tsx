import React, { useEffect, useState } from 'react';
import { Agent } from '../types';
import { agentsService } from '../services/agents';
import { AgentTree } from '../components/agents/AgentTree';
import { SpawnAgentModal } from '../components/agents/SpawnAgentModal';
import { LayoutGrid, List, Users, AlertCircle, Loader2 } from 'lucide-react';
import { toast } from 'react-hot-toast';

// Valid agent types for type checking
const VALID_AGENT_TYPES = ['head_of_council', 'council_member', 'lead_agent', 'task_agent'] as const;

const AGENT_TYPE_LABELS: Record<string, string> = {
    head_of_council: 'Head of Council',
    council_member: 'Council Member',
    lead_agent: 'Lead Agent',
    task_agent: 'Task Agent',
};

const AGENT_TYPE_COLORS: Record<string, {
    light: { bg: string; text: string; dot: string };
    dark: { bg: string; text: string; dot: string; border: string };
}> = {
    head_of_council: {
        light: { bg: 'bg-violet-50', text: 'text-violet-700', dot: 'bg-violet-500' },
        dark:  { bg: 'dark:bg-violet-500/10', text: 'dark:text-violet-300', dot: 'dark:bg-violet-400', border: 'dark:border-violet-500/20' },
    },
    council_member: {
        light: { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' },
        dark:  { bg: 'dark:bg-blue-500/10', text: 'dark:text-blue-300', dot: 'dark:bg-blue-400', border: 'dark:border-blue-500/20' },
    },
    lead_agent: {
        light: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
        dark:  { bg: 'dark:bg-emerald-500/10', text: 'dark:text-emerald-300', dot: 'dark:bg-emerald-400', border: 'dark:border-emerald-500/20' },
    },
    task_agent: {
        light: { bg: 'bg-slate-100', text: 'text-slate-600', dot: 'bg-slate-400' },
        dark:  { bg: 'dark:bg-slate-500/10', text: 'dark:text-slate-400', dot: 'dark:bg-slate-500', border: 'dark:border-slate-600/30' },
    },
};

export const AgentsPage: React.FC = () => {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [viewMode, setViewMode] = useState<'tree' | 'list'>('tree');
    const [spawnParent, setSpawnParent] = useState<Agent | null>(null);

    useEffect(() => {
        loadAgents();
    }, []);

    const loadAgents = async () => {
        try {
            setIsLoading(true);
            const data = await agentsService.getAgents();

            const normalizedAgents = (data || []).map(agent => {
                const rawType = agent.agent_type;
                const validType = VALID_AGENT_TYPES.includes(rawType as any)
                    ? rawType
                    : 'task_agent';

                return {
                    ...agent,
                    subordinates: Array.isArray(agent.subordinates) ? agent.subordinates : [],
                    stats: agent.stats || { tasks_completed: 0, tasks_failed: 0, success_rate: 0 },
                    status: agent.status || 'unknown',
                    name: agent.name || 'Unnamed Agent',
                    agent_type: validType as Agent['agent_type'],
                    agentium_id: agent.agentium_id || agent.id || 'unknown'
                };
            }) as Agent[];

            setAgents(normalizedAgents);
        } catch (err) {
            console.error('Failed to load agents:', err);
            toast.error('Failed to load agents');
        } finally {
            setIsLoading(false);
        }
    };

    const handleSpawn = async (name: string, childType: 'council_member' | 'lead_agent' | 'task_agent') => {
        if (!spawnParent) return;
        try {
            await agentsService.spawnAgent(spawnParent.agentium_id, {
                child_type: childType,
                name
            });
            await loadAgents();
            toast.success('Agent spawned successfully');
        } catch (err) {
            console.error(err);
            throw err;
        }
    };

    const handleTerminate = async (agent: Agent) => {
        if (!window.confirm(`Are you sure you want to terminate ${agent.name}?`)) return;

        try {
            await agentsService.terminateAgent(agent.agentium_id, 'Manual termination by Sovereign');
            await loadAgents();
            toast.success('Agent terminated');
        } catch (err) {
            console.error(err);
            toast.error('Failed to terminate agent');
        }
    };

    const agentsMap = new Map<string, Agent>();
    agents.forEach(a => {
        if (a && a.agentium_id) {
            agentsMap.set(a.agentium_id, a);
        }
    });

    const headOfCouncil = agents.find(a => a.agent_type === 'head_of_council');

    return (
        <div className="p-6 h-full flex flex-col bg-white dark:bg-[#0f1117] transition-colors duration-200 min-h-full">

            {/* ── Header ──────────────────────────────────────────── */}
            <div className="flex justify-between items-start mb-6">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <Users className="w-4 h-4 text-slate-400 dark:text-slate-500" />
                        <span className="text-xs font-semibold tracking-widest uppercase text-slate-400 dark:text-slate-500">
                            Workforce
                        </span>
                    </div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white leading-tight">
                        Agent Hierarchy
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                        Manage your AI workforce
                    </p>
                </div>

                {/* View toggle */}
                <div className="flex rounded-lg overflow-hidden border border-slate-200 dark:border-[#1e2535] bg-slate-50 dark:bg-[#161b27] shadow-sm">
                    <button
                        onClick={() => setViewMode('tree')}
                        title="Tree view"
                        className={[
                            'flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-all duration-150 border-r border-slate-200 dark:border-[#1e2535]',
                            viewMode === 'tree'
                                ? 'bg-white dark:bg-[#1e2535] text-slate-900 dark:text-white shadow-sm'
                                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-white/60 dark:hover:bg-white/5',
                        ].join(' ')}
                    >
                        <LayoutGrid className="w-4 h-4" />
                        <span>Tree</span>
                    </button>
                    <button
                        onClick={() => setViewMode('list')}
                        title="List view"
                        className={[
                            'flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-all duration-150',
                            viewMode === 'list'
                                ? 'bg-white dark:bg-[#1e2535] text-slate-900 dark:text-white shadow-sm'
                                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-white/60 dark:hover:bg-white/5',
                        ].join(' ')}
                    >
                        <List className="w-4 h-4" />
                        <span>List</span>
                    </button>
                </div>
            </div>

            {/* ── Content area ──────────────────────────────────────── */}
            <div className="flex-1 overflow-auto rounded-xl border border-slate-200 dark:border-[#1e2535] p-6 bg-white dark:bg-[#161b27] shadow-sm dark:shadow-[0_2px_20px_rgba(0,0,0,0.3)] transition-colors duration-200">

                {isLoading ? (
                    <div className="flex flex-col items-center justify-center h-40 gap-3 text-slate-400 dark:text-slate-500">
                        <Loader2 className="w-6 h-6 animate-spin" />
                        <span className="text-sm">Loading agents…</span>
                    </div>

                ) : agents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-40 gap-2 text-slate-400 dark:text-slate-500">
                        <Users className="w-8 h-8 opacity-40" />
                        <span className="text-sm">No agents found. System not initialized?</span>
                    </div>

                ) : viewMode === 'tree' ? (
                    headOfCouncil ? (
                        <div className="
                            relative
                            rounded-xl
                            border border-slate-200 dark:border-slate-700/50
                            bg-slate-50 dark:bg-slate-900
                            p-6
                            min-h-[500px]
                            overflow-auto
                        ">
                            {/* Dotted background pattern */}
                            <div 
                                className="
                                    absolute 
                                    inset-0 
                                    rounded-xl
                                    bg-[radial-gradient(circle,_#cbd5e1_1px,_transparent_1px)] 
                                    dark:bg-[radial-gradient(circle,_#334155_1px,_transparent_1px)]
                                    bg-[length:20px_20px]
                                    opacity-60
                                    pointer-events-none
                                "
                                aria-hidden="true"
                            />
                            
                            {/* Tree content */}
                            <div className="relative z-10">
                                <AgentTree
                                    agent={headOfCouncil}
                                    agentsMap={agentsMap}
                                    onSpawn={setSpawnParent}
                                    onTerminate={handleTerminate}
                                />
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            <span>Head of Council not found in agent list.</span>
                        </div>
                    )

                ) : (
                    /* ── List / Grid view ───────────────────────────────── */
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {agents.map(agent => {
                            const colorSet = AGENT_TYPE_COLORS[agent.agent_type] ?? AGENT_TYPE_COLORS.task_agent;
                            const label = AGENT_TYPE_LABELS[agent.agent_type] ?? agent.agent_type;
                            const { light, dark } = colorSet;

                            return (
                                <div
                                    key={agent.id || agent.agentium_id}
                                    className="rounded-xl border border-slate-200 dark:border-[#1e2535] p-4 bg-white dark:bg-[#0f1117] hover:border-slate-300 dark:hover:border-[#2a3347] hover:shadow-sm dark:hover:shadow-[0_4px_16px_rgba(0,0,0,0.3)] transition-all duration-150"
                                >
                                    {/* Agent name + type badge */}
                                    <div className="flex items-start justify-between gap-2 mb-3">
                                        <h3 className="text-sm font-semibold text-slate-900 dark:text-gray-100 leading-snug">
                                            {agent.name}
                                        </h3>
                                        <span
                                            className={[
                                                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap flex-shrink-0 border',
                                                // Light mode
                                                light.bg, light.text,
                                                // Dark mode
                                                dark.bg, dark.text, dark.border,
                                            ].join(' ')}
                                        >
                                            <span className={`w-1.5 h-1.5 rounded-full ${light.dot} ${dark.dot}`} />
                                            {label}
                                        </span>
                                    </div>

                                    {/* ID */}
                                    <p className="text-xs text-slate-400 dark:text-slate-600 font-mono truncate">
                                        {agent.agentium_id}
                                    </p>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {spawnParent && (
                <SpawnAgentModal
                    parent={spawnParent}
                    onConfirm={handleSpawn}
                    onClose={() => setSpawnParent(null)}
                />
            )}
        </div>
    );
};
