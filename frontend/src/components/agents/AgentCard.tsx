import React from 'react';
import { Agent } from '../../types';
import { Shield, Brain, Users, Terminal, Activity, Zap } from 'lucide-react';

interface AgentCardProps {
    agent: Agent;
    onSpawn: (agent: Agent) => void;
    onTerminate: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onSpawn, onTerminate }) => {
    if (!agent) return null;

    const isTerminated = agent.status === 'terminated';
    const isHead = agent.agent_type === 'head_of_council';
    const subordinateCount = Array.isArray(agent.subordinates) ? agent.subordinates.length : 0;
    const tasksCompleted = agent.stats?.tasks_completed ?? 0;

    const getTypeIcon = () => {
        switch (agent.agent_type) {
            case 'head_of_council': return <Shield className="w-5 h-5 text-violet-600 dark:text-violet-400" />;
            case 'council_member': return <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />;
            case 'lead_agent': return <Brain className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />;
            case 'task_agent': return <Terminal className="w-5 h-5 text-amber-600 dark:text-amber-400" />;
            default: return <Activity className="w-5 h-5 text-slate-500 dark:text-slate-400" />;
        }
    };

    const getTypeLabel = () =>
        agent.agent_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Unknown';

    const getStatusClasses = () => {
        switch (agent.status) {
            case 'active': return 'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/30';
            case 'working': return 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/30';
            case 'deliberating': return 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30';
            case 'terminated': return 'bg-rose-100 text-rose-800 border-rose-200 dark:bg-rose-500/20 dark:text-rose-300 dark:border-rose-500/30';
            default: return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:border-slate-600';
        }
    };

    return (
        <div className={`
            relative
            rounded-xl 
            border 
            p-4 
            w-full 
            max-w-sm
            transition-all 
            duration-150
            ${isTerminated
                ? 'opacity-50 border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800/50'
                : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600 hover:border-slate-400 dark:hover:border-slate-500 hover:shadow-md dark:hover:shadow-lg dark:hover:shadow-black/20'
            }
        `}>
            {/* Header row */}
            <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                    <div className="
                        w-10 
                        h-10 
                        bg-slate-100 
                        dark:bg-slate-700 
                        border 
                        border-slate-200 
                        dark:border-slate-600
                        rounded-lg 
                        flex 
                        items-center 
                        justify-center 
                        flex-shrink-0
                    ">
                        {getTypeIcon()}
                    </div>
                    <div>
                        <h3 className="
                            text-sm 
                            font-semibold 
                            text-slate-900 
                            dark:text-slate-100
                            flex 
                            items-center 
                            gap-1.5
                        ">
                            {agent.name || 'Unnamed Agent'}
                            <span className="
                                text-xs 
                                text-slate-500 
                                dark:text-slate-400
                                font-mono
                            ">
                                #{agent.agentium_id || '???'}
                            </span>
                        </h3>
                        <p className="
                            text-xs 
                            text-slate-600 
                            dark:text-slate-400 
                            mt-0.5
                        ">
                            {getTypeLabel()}
                        </p>
                    </div>
                </div>
                <span className={`
                    px-2 
                    py-0.5 
                    rounded-full 
                    text-xs 
                    font-medium 
                    border 
                    capitalize 
                    shrink-0 
                    ${getStatusClasses()}
                `}>
                    {agent.status || 'unknown'}
                </span>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 mb-4">
                <div className="
                    bg-slate-50 
                    dark:bg-slate-700/50
                    border 
                    border-slate-200 
                    dark:border-slate-600
                    rounded-lg 
                    p-2.5
                ">
                    <span className="
                        text-xs 
                        text-slate-600 
                        dark:text-slate-400
                        block 
                        mb-0.5
                    ">
                        Task Success
                    </span>
                    <span className="
                        text-sm 
                        font-semibold 
                        text-slate-900 
                        dark:text-slate-100
                    ">
                        {tasksCompleted}
                    </span>
                </div>
                <div className="
                    bg-slate-50 
                    dark:bg-slate-700/50
                    border 
                    border-slate-200 
                    dark:border-slate-600
                    rounded-lg 
                    p-2.5
                ">
                    <span className="
                        text-xs 
                        text-slate-600 
                        dark:text-slate-400
                        block 
                        mb-0.5
                    ">
                        Subordinates
                    </span>
                    <span className="
                        text-sm 
                        font-semibold 
                        text-slate-900 
                        dark:text-slate-100
                    ">
                        {subordinateCount}
                    </span>
                </div>
            </div>

            {/* Actions */}
            <div className="
                flex 
                gap-2 
                pt-3 
                border-t 
                border-slate-200 
                dark:border-slate-600
            ">
                {!isTerminated && agent.agent_type !== 'task_agent' && (
                    <button
                        onClick={() => onSpawn(agent)}
                        className="
                            flex-1 
                            px-3 
                            py-1.5 
                            bg-blue-100 
                            dark:bg-blue-500/20
                            text-blue-800 
                            dark:text-blue-300
                            border 
                            border-blue-200 
                            dark:border-blue-500/30
                            rounded-lg 
                            hover:bg-blue-200 
                            dark:hover:bg-blue-500/30
                            text-xs 
                            font-medium 
                            transition-colors 
                            duration-150 
                            flex 
                            items-center 
                            justify-center 
                            gap-1.5
                        "
                    >
                        <Zap className="w-3 h-3" />
                        Spawn
                    </button>
                )}
                {!isTerminated && !isHead && (
                    <button
                        onClick={() => onTerminate(agent)}
                        className="
                            px-3 
                            py-1.5 
                            bg-rose-100 
                            dark:bg-rose-500/20
                            text-rose-800 
                            dark:text-rose-300
                            border 
                            border-rose-200 
                            dark:border-rose-500/30
                            rounded-lg 
                            hover:bg-rose-200 
                            dark:hover:bg-rose-500/30
                            text-xs 
                            font-medium 
                            transition-colors 
                            duration-150
                        "
                    >
                        Terminate
                    </button>
                )}
            </div>
        </div>
    );
};