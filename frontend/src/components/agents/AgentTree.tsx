/**
 * AgentTree — uses DragDropContext instead of prop-drilling 7 DnD props.
 * React.memo on all heavy sub-components to stop re-renders on drag events.
 */

import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { Agent } from '../../types';
import { AgentCard } from './AgentCard';
import { ChevronRight, ChevronDown, ShieldAlert } from 'lucide-react';
import { useDragDrop } from '../../context/DragDropContext';
import { isCriticAgentId } from '../../utils/agentIds';
import { useVirtualizer } from '@tanstack/react-virtual';

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
    agent:           Agent; // Usually the Head of Council
    agentsMap:       Map<string, Agent>;
    onSpawn:         (agent: Agent) => void;
    onTerminate:     (agent: Agent) => void;
    onPromote?:      (agent: Agent) => void;
    level?:          number; // Backward compat flag (usually 0 now)
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
                'relative transition-all duration-150 rounded-xl w-full',
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

// ─── Flattening Logic ─────────────────────────────────────────────────────────

type FlattenedNode = {
    agent: Agent;
    level: number;
    hasChildren: boolean;
    isExpanded: boolean;
    isCriticHeader?: boolean;
    isCritic?: boolean;
};

// ─── Virtualized Tree Component ───────────────────────────────────────────────

export const AgentTree: React.FC<AgentTreeProps> = React.memo(({
    agent: rootAgent, agentsMap, onSpawn, onTerminate, onPromote,
}) => {
    // Keep track of expanded nodes. Default to all expanded for small trees, 
    // or we could track this per-instance. We'll default to expanding everything initially
    // by not having it in the Set mean "collapsed", but rather we will build a Set of collapsed nodes.
    const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set());
    const [criticExpanded, setCriticExpanded] = useState(true);

    const toggleNode = useCallback((agentId: string) => {
        setCollapsedNodes(prev => {
            const next = new Set(prev);
            if (next.has(agentId)) next.delete(agentId);
            else next.add(agentId);
            return next;
        });
    }, []);

    // Flatten tree structure visible based on expanded state
    const { flattenedNodes, critics } = useMemo(() => {
        const nodes: FlattenedNode[] = [];
        const allCritics: Agent[] = [];

        // Pre-filter all agents if this is the root to separate critics
        const allAgents = Array.from(agentsMap.values());
        for (const a of allAgents) {
            if (isCriticAgent(a)) {
                allCritics.push(a);
            }
        }

        const flattenDeep = (agentId: string, depth: number) => {
            const ag = agentsMap.get(agentId);
            if (!ag || isCriticAgent(ag)) return; // Critics handled separately

            const subordinateIds = Array.isArray(ag.subordinates) ? ag.subordinates : [];
            const mainChildren = subordinateIds.filter(subId => {
                const sub = agentsMap.get(subId);
                return sub && !isCriticAgent(sub);
            });
            const hasChildren = mainChildren.length > 0;
            const isCollapsed = collapsedNodes.has(ag.agentium_id);

            nodes.push({
                agent: ag,
                level: depth,
                hasChildren,
                isExpanded: !isCollapsed,
            });

            if (!isCollapsed && hasChildren) {
                for (const subId of mainChildren) {
                    flattenDeep(subId, depth + 1);
                }
            }
        };

        if (rootAgent) {
            flattenDeep(rootAgent.agentium_id, 0);
        }

        return { flattenedNodes: nodes, critics: allCritics };
    }, [rootAgent, agentsMap, collapsedNodes]);

    // Construct the final linear array for the virtualizer
    const virtualItems = useMemo(() => {
        const items: FlattenedNode[] = [...flattenedNodes];
        
        if (critics.length > 0) {
            // Add a special header item for critics
            items.push({
                agent: { agentium_id: '__critic_header__', name: 'Critic Header', agent_type: 'task_agent', status: 'active', stats: {tasks_completed:0, tasks_failed:0}, subordinates: [], is_terminated: false, constitution_version: '' } as unknown as Agent,
                level: 0,
                hasChildren: true,
                isExpanded: criticExpanded,
                isCriticHeader: true,
            });

            if (criticExpanded) {
                // Determine how many critics per row, or just list them sequentially.
                // We'll list them sequentially for simplicity in the virtual list.
                for (const critic of critics) {
                    items.push({
                        agent: critic,
                        level: 1, // Indent critics slightly
                        hasChildren: false,
                        isExpanded: false,
                        isCritic: true,
                    });
                }
            }
        }
        return items;
    }, [flattenedNodes, critics, criticExpanded]);

    // Virtualizer setup
    const parentRef = useRef<HTMLDivElement>(null);

    const virtualizer = useVirtualizer({
        count: virtualItems.length,
        getScrollElement: () => parentRef.current,
        estimateSize: useCallback((index) => {
            const item = virtualItems[index];
            if (item.isCriticHeader) return 60;
            return 110; // Approximate height of AgentCard + margins
        }, [virtualItems]),
        overscan: 5,
    });

    if (!rootAgent) return null;

    return (
        <div ref={parentRef} className="h-full w-full overflow-y-auto" style={{ minHeight: '500px' }}>
            <div
                style={{
                    height: `${virtualizer.getTotalSize()}px`,
                    width: '100%',
                    position: 'relative',
                }}
            >
                {virtualizer.getVirtualItems().map((virtualItem) => {
                    const node = virtualItems[virtualItem.index];
                    const leftOffset = node.level * 40; // 40px per indent level

                    return (
                        <div
                            key={virtualItem.key}
                            style={{
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                width: '100%',
                                transform: `translateY(${virtualItem.start}px)`,
                                paddingRight: '16px',
                                paddingBottom: '16px'
                            }}
                        >
                            <div style={{ marginLeft: `${leftOffset}px`, width: `calc(100% - ${leftOffset}px)` }}>
                                {node.isCriticHeader ? (
                                    <div className="mt-4 mb-2">
                                        <button
                                            onClick={() => setCriticExpanded(x => !x)}
                                            className="flex items-center gap-2 w-full"
                                        >
                                            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-rose-700 dark:text-rose-300 hover:bg-rose-100 dark:hover:bg-rose-500/20 transition-colors">
                                                <ShieldAlert className="w-4 h-4" />
                                                <span className="text-sm font-semibold">Critic Agents</span>
                                                <span className="text-xs font-mono opacity-70">({critics.length})</span>
                                                {criticExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                                            </div>
                                            <div className="flex-1 h-px bg-rose-200 dark:bg-rose-500/20" />
                                        </button>
                                    </div>
                                ) : node.isCritic ? (
                                    <div className="relative rounded-xl border border-rose-200 dark:border-rose-500/20 bg-rose-50/40 dark:bg-rose-500/5 p-4 mb-2">
                                        <div className="relative z-10 flex">
                                            <div className="flex-shrink-0 flex-1">
                                                <AgentCard agent={node.agent} onSpawn={onSpawn} onTerminate={onTerminate} />
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="flex items-start gap-2 relative group w-full">
                                        {/* Connecting lines for deep levels */}
                                        {node.level > 0 && (
                                            <>
                                                <div
                                                    className="absolute w-6 border-t-2 border-slate-300 dark:border-slate-600 rounded-bl-xl"
                                                    style={{ left: '-24px', top: '24px' }}
                                                />
                                                <div
                                                    className="absolute border-l-2 border-slate-300 dark:border-slate-600"
                                                    style={{ left: '-24px', height: '120%', top: '-24px', zIndex: -1 }}
                                                />
                                            </>
                                        )}

                                        {node.hasChildren ? (
                                            <button
                                                onClick={() => toggleNode(node.agent.agentium_id)}
                                                aria-label={node.isExpanded ? 'Collapse' : 'Expand'}
                                                className="mt-3 p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors duration-150 flex-shrink-0 z-10 bg-white dark:bg-[#161b27]"
                                            >
                                                {node.isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                            </button>
                                        ) : (
                                            <div className="w-6 flex-shrink-0" />
                                        )}

                                        <div className="flex-1 w-full min-w-0">
                                            <DraggableCard
                                                agent={node.agent}
                                                onSpawn={onSpawn}
                                                onTerminate={onTerminate}
                                                onPromote={onPromote}
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
});

AgentTree.displayName = 'AgentTree';