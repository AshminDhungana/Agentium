/**
 * AgentTree — uses DragDropContext instead of prop-drilling 7 DnD props.
 * React.memo on all heavy sub-components to stop re-renders on drag events.
 */

import React, { useState } from 'react';
import { Agent } from '../../types';
import { AgentCard } from './AgentCard';
import { ChevronRight, ChevronDown, ShieldAlert } from 'lucide-react';
import { useDragDrop } from '../../context/DragDropContext';
import { isCriticAgentId } from '../../utils/agentIds';

// ─── DragDropProps — kept for external backward-compat but no longer used internally ──

/** @deprecated Pass DnD state via DragDropProvider wrapping AgentTree instead. */
export interface DragDropProps {
    draggingAgentId: string | null;
    dropTargetId:    string | null;
    onDragStart: (agent: Agent) => void;
    onDragEnd:   () => void;
    onDragEnter: (targetId: string) => void;
    onDragLeave: (targetId: string) => void;
    onDrop:      (newParentId: string) => void;
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentTreeProps {
    agent:           Agent;
    agentsMap:       Map<string, Agent>;
    onSpawn:         (agent: Agent) => void;
    onTerminate:     (agent: Agent) => void;
    onPromote?:      (agent: Agent) => void;
    level?:          number;
    includeCritics?: boolean;
}

// ─── Draggable / droppable card wrapper ───────────────────────────────────────

const DraggableCard: React.FC<{
    agent:       Agent;
    onSpawn:     (agent: Agent) => void;
    onTerminate: (agent: Agent) => void;
    onPromote?:  (agent: Agent) => void;
}> = React.memo(({ agent, onSpawn, onTerminate, onPromote }) => {
    const { draggingAgentId, dropTargetId, onDragStart, onDragEnd, onDragEnter, onDragLeave, onDrop } = useDragDrop();

    const isDraggable       = agent.agent_type !== 'head_of_council';
    const isDragging        = draggingAgentId === agent.agentium_id;
    const isDropTarget      = dropTargetId    === agent.agentium_id;
    const somethingDragging = !!draggingAgentId;

    return (
        <div
            draggable={isDraggable}

            onDragStart={e => {
                if (!isDraggable) { e.preventDefault(); return; }
                e.dataTransfer.effectAllowed = 'move';
                requestAnimationFrame(() => onDragStart(agent));
            }}
            onDragEnd={onDragEnd}
            onDragOver={e => {
                if (somethingDragging && draggingAgentId !== agent.agentium_id) {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                }
            }}
            onDragEnter={e => {
                e.preventDefault();
                if (somethingDragging && draggingAgentId !== agent.agentium_id) {
                    onDragEnter(agent.agentium_id);
                }
            }}
            onDragLeave={() => onDragLeave(agent.agentium_id)}
            onDrop={e => {
                e.preventDefault();
                if (somethingDragging && draggingAgentId !== agent.agentium_id) {
                    onDrop(agent.agentium_id);
                }
            }}

            className={[
                'relative transition-all duration-150 rounded-xl',
                isDraggable ? 'cursor-grab active:cursor-grabbing' : '',
                isDragging  ? 'opacity-40 scale-95 pointer-events-none' : '',
                isDropTarget && !isDragging
                    ? 'ring-2 ring-blue-500 ring-offset-2 dark:ring-offset-slate-900 scale-[1.02] shadow-lg'
                    : '',
            ].filter(Boolean).join(' ')}
        >
            <AgentCard
                agent={agent}
                onSpawn={onSpawn}
                onTerminate={onTerminate}
                onPromote={onPromote}
            />

            {isDropTarget && !isDragging && (
                <div className="absolute inset-0 rounded-xl bg-blue-500/10 flex items-center justify-center pointer-events-none">
                    <span className="text-xs font-semibold text-blue-600 dark:text-blue-300 bg-white dark:bg-[#161b27] px-2 py-0.5 rounded-full shadow">
                        Drop here
                    </span>
                </div>
            )}
        </div>
    );
});

DraggableCard.displayName = 'DraggableCard';

// ─── Critic helper function ───────────────────────────────────────────────────

function isCriticAgent(agent: Agent): boolean {
    return isCriticAgentId(agent.agentium_id ?? agent.id);
}

// ─── Recursive tree node ──────────────────────────────────────────────────────

export const AgentTree: React.FC<AgentTreeProps> = React.memo(({
    agent, agentsMap, onSpawn, onTerminate, onPromote,
    level = 0, includeCritics = false,
}) => {
    const [isExpanded,     setIsExpanded]     = useState(true);
    const [criticExpanded, setCriticExpanded] = useState(true);

    if (!agent) return null;

    const subordinateIds = Array.isArray(agent?.subordinates) ? agent.subordinates : [];
    const allChildren    = subordinateIds
        .map(id => agentsMap.get(id))
        .filter((a): a is Agent => a !== undefined);

    const isRoot         = level === 0 && !includeCritics;
    const mainChildren   = isRoot ? allChildren.filter(a => !isCriticAgent(a)) : allChildren;
    const criticAgents   = isRoot ? [...agentsMap.values()].filter(isCriticAgent) : [];
    const hasMainChildren = mainChildren.length > 0;
    const hasCritics      = criticAgents.length > 0;

    return (
        <div className="relative" role="tree" aria-label={level === 0 ? 'Agent hierarchy' : undefined}>
            {level > 0 && (
                <div
                    className="absolute border-l-2 border-slate-400 dark:border-slate-500"
                    style={{ left: '-24px', height: '100%', top: 0 }}
                />
            )}

            <div className="flex items-start gap-2 mb-4 relative" role="treeitem" aria-expanded={hasMainChildren ? isExpanded : undefined}>
                {level > 0 && (
                    <div
                        className="absolute w-6 border-t-2 border-slate-400 dark:border-slate-500"
                        style={{ left: '-24px', top: '24px' }}
                    />
                )}

                {hasMainChildren ? (
                    <button
                        onClick={() => setIsExpanded(v => !v)}
                        aria-label={isExpanded ? 'Collapse' : 'Expand'}
                        className="mt-3 p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors duration-150 flex-shrink-0"
                    >
                        {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                ) : (
                    <div className="w-6 flex-shrink-0" />
                )}

                <DraggableCard
                    agent={agent}
                    onSpawn={onSpawn}
                    onTerminate={onTerminate}
                    onPromote={onPromote}
                />
            </div>

            {isExpanded && hasMainChildren && (
                <div className="ml-12 pl-6 border-l-2 border-slate-400 dark:border-slate-500">
                    <div className="border-l border-slate-300 dark:border-slate-600 -ml-6 pl-6 pt-2">
                        {mainChildren.map(child => (
                            <AgentTree
                                key={child.id || child.agentium_id}
                                agent={child}
                                agentsMap={agentsMap}
                                onSpawn={onSpawn}
                                onTerminate={onTerminate}
                                onPromote={onPromote}
                                level={level + 1}
                                includeCritics={false}
                            />
                        ))}
                    </div>
                </div>
            )}

            {/* ── Critic branch (root level only) ─────────────────────── */}
            {isRoot && hasCritics && (
                <div className="mt-8">
                    <button
                        onClick={() => setCriticExpanded(x => !x)}
                        className="flex items-center gap-2 mb-4 w-full"
                    >
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-500/20 transition-colors">
                            <ShieldAlert className="w-4 h-4" />
                            <span className="text-sm font-semibold">Critic Agents</span>
                            <span className="text-xs font-mono opacity-70">({criticAgents.length})</span>
                            {criticExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        </div>
                        <div className="flex-1 h-px bg-rose-200 dark:bg-rose-500/20" />
                    </button>

                    {criticExpanded && (
                        <div className="relative rounded-xl border border-rose-200 dark:border-rose-500/20 bg-rose-50/40 dark:bg-rose-500/5 p-4">
                            <div
                                className="absolute inset-0 rounded-xl bg-[radial-gradient(circle,_#fca5a5_1px,_transparent_1px)] dark:bg-[radial-gradient(circle,_#7f1d1d30_1px,_transparent_1px)] bg-[length:20px_20px] opacity-40 pointer-events-none"
                                aria-hidden="true"
                            />
                            <div className="relative z-10 flex flex-wrap gap-4">
                                {criticAgents.map(critic => (
                                    <div key={critic.id || critic.agentium_id} className="flex-shrink-0">
                                        {/* Critics are intentionally NOT drag sources or drop targets */}
                                        <AgentCard agent={critic} onSpawn={onSpawn} onTerminate={onTerminate} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
});

AgentTree.displayName = 'AgentTree';