import React, { useState } from 'react';
import { Agent } from '../../types';
import { AgentCard } from './AgentCard';
import { ChevronRight, ChevronDown } from 'lucide-react';

interface AgentTreeProps {
    agent: Agent;
    agentsMap: Map<string, Agent>;
    onSpawn: (agent: Agent) => void;
    onTerminate: (agent: Agent) => void;
    level?: number;
}

export const AgentTree: React.FC<AgentTreeProps> = ({
    agent,
    agentsMap,
    onSpawn,
    onTerminate,
    level = 0,
}) => {
    const [isExpanded, setIsExpanded] = useState(true);

    if (!agent) return null;

    const subordinateIds = Array.isArray(agent?.subordinates) ? agent.subordinates : [];
    const children = subordinateIds
        .map(id => agentsMap.get(id))
        .filter((a): a is Agent => a !== undefined);
    const hasChildren = children.length > 0;

    return (
        <div className="relative">
            {/* Vertical connector line - Dark in light mode, light in dark mode */}
            {level > 0 && (
                <div
                    className="
                        absolute 
                        border-l-2 
                        border-slate-400 
                        dark:border-slate-500
                    "
                    style={{ left: '-24px', height: '100%', top: 0 }}
                />
            )}

            <div className="flex items-start gap-2 mb-4 relative">
                {/* Horizontal connector line */}
                {level > 0 && (
                    <div
                        className="
                            absolute 
                            w-6 
                            border-t-2 
                            border-slate-400 
                            dark:border-slate-500
                        "
                        style={{ left: '-24px', top: '24px' }}
                    />
                )}

                {hasChildren ? (
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="
                            mt-3 
                            p-1 
                            rounded-lg 
                            hover:bg-slate-200 
                            dark:hover:bg-slate-700
                            text-slate-600 
                            dark:text-slate-300
                            transition-colors 
                            duration-150 
                            flex-shrink-0
                        "
                    >
                        {isExpanded
                            ? <ChevronDown className="w-4 h-4" />
                            : <ChevronRight className="w-4 h-4" />
                        }
                    </button>
                ) : (
                    <div className="w-6 flex-shrink-0" />
                )}

                <AgentCard agent={agent} onSpawn={onSpawn} onTerminate={onTerminate} />
            </div>

            {/* Recursively render children */}
            {isExpanded && hasChildren && (
                <div className="
                    ml-12 
                    pl-6 
                    space-y-0 
                    border-l-2 
                    border-slate-400 
                    dark:border-slate-500
                ">
                    <div className="
                        border-l 
                        border-slate-300 
                        dark:border-slate-600
                        -ml-6 
                        pl-6 
                        pt-2
                    ">
                        {children.map(child => (
                            <AgentTree
                                key={child.id || child.agentium_id}
                                agent={child}
                                agentsMap={agentsMap}
                                onSpawn={onSpawn}
                                onTerminate={onTerminate}
                                level={level + 1}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
