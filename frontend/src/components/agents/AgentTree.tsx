/**
 * AgentTree — virtualized, flattened tree with proper card sizing and connectors.
 */

import React, { useState, useMemo, useRef, useCallback } from 'react';
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

// ─── Size constants (stable — not inside component to avoid re-creation) ─────

/**
 * Estimated row height used by the virtualizer for initial layout.
 * AgentCard renders to ~220–240 px (header 56 + task-indicator 0–52 + stats 64 +
 * actions 48 + paddings/borders) + 16 px gap = ~256 px worst case.
 * measureElement corrects this automatically after first render.
 */
const ESTIMATE_CARD_HEIGHT   = 256;
const ESTIMATE_CRITIC_HEADER = 68;
const ESTIMATE_CRITIC_CARD   = 220; // Critics have no actions row

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

// ─── Critic helper ────────────────────────────────────────────────────────────

function isCriticAgent(agent: Agent): boolean {
    return isCriticAgentId(agent.agentium_id ?? agent.id);
}

// ─── Flattened node type ──────────────────────────────────────────────────────

type FlattenedNode = {
    agent:           Agent;
    level:           number;
    hasChildren:     boolean;
    isExpanded:      boolean;
    isCriticHeader?: boolean;
    isCritic?:       boolean;
};

// ─── AgentTree (virtualized) ──────────────────────────────────────────────────

export const AgentTree: React.FC<AgentTreeProps> = React.memo(({
    agent: rootAgent, agentsMap, onSpawn, onTerminate, onPromote,
}) => {
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

    // ── Flatten tree into a linear list ──────────────────────────────────────

    const { flattenedNodes, critics } = useMemo(() => {
        const nodes: FlattenedNode[] = [];
        const allCritics: Agent[] = [];

        for (const a of agentsMap.values()) {
            if (isCriticAgent(a)) allCritics.push(a);
        }

        const flattenDeep = (agentId: string, depth: number) => {
            const ag = agentsMap.get(agentId);
            if (!ag || isCriticAgent(ag)) return;

            const subordinateIds = Array.isArray(ag.subordinates) ? ag.subordinates : [];
            const mainChildren   = subordinateIds.filter(subId => {
                const sub = agentsMap.get(subId);
                return sub && !isCriticAgent(sub);
            });
            const hasChildren = mainChildren.length > 0;
            const isCollapsed = collapsedNodes.has(ag.agentium_id);

            nodes.push({ agent: ag, level: depth, hasChildren, isExpanded: !isCollapsed });

            if (!isCollapsed && hasChildren) {
                for (const subId of mainChildren) flattenDeep(subId, depth + 1);
            }
        };

        if (rootAgent) flattenDeep(rootAgent.agentium_id, 0);

        return { flattenedNodes: nodes, critics: allCritics };
    }, [rootAgent, agentsMap, collapsedNodes]);

    // ── Append critic section ─────────────────────────────────────────────────

    const virtualItems = useMemo(() => {
        const items: FlattenedNode[] = [...flattenedNodes];

        if (critics.length > 0) {
            items.push({
                agent: {
                    agentium_id: '__critic_header__', name: 'Critic Header',
                    agent_type: 'task_agent', status: 'active',
                    stats: { tasks_completed: 0, tasks_failed: 0 },
                    subordinates: [], is_terminated: false, constitution_version: '',
                } as unknown as Agent,
                level: 0, hasChildren: true, isExpanded: criticExpanded, isCriticHeader: true,
            });

            if (criticExpanded) {
                for (const critic of critics) {
                    items.push({ agent: critic, level: 1, hasChildren: false, isExpanded: false, isCritic: true });
                }
            }
        }
        return items;
    }, [flattenedNodes, critics, criticExpanded]);

    // ── Virtualizer ───────────────────────────────────────────────────────────

    const parentRef = useRef<HTMLDivElement>(null);

    const virtualizer = useVirtualizer({
        count:           virtualItems.length,
        getScrollElement: () => parentRef.current,

        // Stable estimateSize — does NOT close over virtualItems to avoid
        // forcing full remeasure on every agent update.
        estimateSize: useCallback((index: number) => {
            const item = virtualItems[index];
            if (!item) return ESTIMATE_CARD_HEIGHT;
            if (item.isCriticHeader) return ESTIMATE_CRITIC_HEADER;
            if (item.isCritic)       return ESTIMATE_CRITIC_CARD;
            return ESTIMATE_CARD_HEIGHT;
        // eslint-disable-next-line react-hooks/exhaustive-deps
        }, [virtualItems]),

        // measureElement — corrects estimates after actual render.
        // Requires data-index on each row div + ref={virtualizer.measureElement}.
        measureElement: (el) => el.getBoundingClientRect().height,

        overscan:   10,  // was 5 — prevents blank flashes during fast scroll
        paddingEnd: 16,  // bottom breathing room (replaces the no-op paddingBottom on abs divs)
    });

    if (!rootAgent) return null;

    return (
        // Scroll container must have a concrete height — set by parent (AgentsPage).
        // h-full works when the parent has overflow-hidden + fixed height.
        <div
            ref={parentRef}
            className="w-full overflow-y-auto"
            style={{ height: '100%', minHeight: '400px' }}
        >
            <div
                style={{
                    height:   `${virtualizer.getTotalSize()}px`,
                    width:    '100%',
                    position: 'relative',
                }}
            >
                {virtualizer.getVirtualItems().map((virtualItem) => {
                    const node       = virtualItems[virtualItem.index];
                    const leftOffset = node.level * 40; // 40 px per indent level

                    return (
                        <div
                            key={virtualItem.key}
                            // data-index + ref enable measureElement to auto-correct heights
                            data-index={virtualItem.index}
                            ref={virtualizer.measureElement}
                            style={{
                                position:  'absolute',
                                top:       0,
                                left:      0,
                                width:     '100%',
                                transform: `translateY(${virtualItem.start}px)`,
                                paddingRight:  '16px',
                                paddingBottom: '16px', // measured by measureElement → correct spacing
                            }}
                        >
                            <div style={{ marginLeft: `${leftOffset}px`, width: `calc(100% - ${leftOffset}px)` }}>

                                {/* ── Critic section header ─────────────────── */}
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
                                                {criticExpanded
                                                    ? <ChevronDown  className="w-3.5 h-3.5" />
                                                    : <ChevronRight className="w-3.5 h-3.5" />}
                                            </div>
                                            <div className="flex-1 h-px bg-rose-200 dark:bg-rose-500/20" />
                                        </button>
                                    </div>

                                /* ── Critic card ─────────────────────────── */
                                ) : node.isCritic ? (
                                    <div className="relative rounded-xl border border-rose-200 dark:border-rose-500/20 bg-rose-50/40 dark:bg-rose-500/5 p-4">
                                        <AgentCard
                                            agent={node.agent}
                                            onSpawn={onSpawn}
                                            onTerminate={onTerminate}
                                        />
                                    </div>

                                /* ── Regular agent card ──────────────────── */
                                ) : (
                                    <div className="flex items-start gap-2 relative group w-full">

                                        {/*
                                         * Connecting lines — self-contained per row.
                                         *
                                         * In a virtualizer, items are independent absolutely-positioned divs.
                                         * We CANNOT draw a line that spans from one item into the next —
                                         * the previous approach used height:'120%' + top:'-24px' which broke
                                         * layout by escaping the item's bounds into unrelated cards.
                                         *
                                         * New approach: a short vertical stub (top-half only) + horizontal
                                         * elbow, both fully contained within this row's div. This gives a
                                         * clear indent cue without cross-item bleeding.
                                         */}
                                        {node.level > 0 && (
                                            <div
                                                className="absolute pointer-events-none"
                                                style={{ left: '-20px', top: 0, width: '20px', height: '28px' }}
                                                aria-hidden="true"
                                            >
                                                {/* Vertical stub — top of item to elbow */}
                                                <div
                                                    className="absolute border-l-2 border-slate-200 dark:border-slate-700"
                                                    style={{ left: 0, top: 0, height: '28px' }}
                                                />
                                                {/* Horizontal elbow */}
                                                <div
                                                    className="absolute border-t-2 border-slate-200 dark:border-slate-700"
                                                    style={{ left: 0, top: '27px', width: '20px' }}
                                                />
                                            </div>
                                        )}

                                        {/* Expand / collapse toggle */}
                                        {node.hasChildren ? (
                                            <button
                                                onClick={() => toggleNode(node.agent.agentium_id)}
                                                aria-label={node.isExpanded ? 'Collapse' : 'Expand'}
                                                className="mt-3 p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors duration-150 flex-shrink-0 z-10 bg-white dark:bg-[#161b27]"
                                            >
                                                {node.isExpanded
                                                    ? <ChevronDown  className="w-4 h-4" />
                                                    : <ChevronRight className="w-4 h-4" />}
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