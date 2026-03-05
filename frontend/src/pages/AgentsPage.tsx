import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Agent } from '../types';
import { agentsService, capabilitiesService, lifecycleService } from '../services/agents';
import { AgentTree } from '../components/agents/AgentTree';
import { SpawnAgentModal } from '../components/agents/SpawnAgentModal';
import { PromoteAgentModal } from '../components/agents/PromoteAgentModal';
import { BulkLiquidateModal } from '../components/agents/BulkLiquidateModal';
import { LifecycleDashboard } from '../components/agents/LifecycleDashboard';
import { useWebSocketStore } from '@/store/websocketStore';
import {
    LayoutGrid, List, Users, AlertCircle, Loader2, RefreshCw,
    BarChart2, ChevronLeft, ChevronRight as ChevronRightIcon,
} from 'lucide-react';
import { toast } from 'react-hot-toast';

// ─── Constants ────────────────────────────────────────────────────────────────

const VALID_AGENT_TYPES = ['head_of_council', 'council_member', 'lead_agent', 'task_agent'] as const;

const AGENT_TYPE_LABELS: Record<string, string> = {
    head_of_council: 'Head of Council',
    council_member:  'Council Member',
    lead_agent:      'Lead Agent',
    task_agent:      'Task Agent',
};

const AGENT_TYPE_COLORS: Record<string, {
    light: { bg: string; text: string; dot: string };
    dark:  { bg: string; text: string; dot: string; border: string };
}> = {
    head_of_council: {
        light: { bg: 'bg-violet-50',  text: 'text-violet-700',  dot: 'bg-violet-500'  },
        dark:  { bg: 'dark:bg-violet-500/10', text: 'dark:text-violet-300', dot: 'dark:bg-violet-400', border: 'dark:border-violet-500/20' },
    },
    council_member: {
        light: { bg: 'bg-blue-50',    text: 'text-blue-700',    dot: 'bg-blue-500'    },
        dark:  { bg: 'dark:bg-blue-500/10',   text: 'dark:text-blue-300',   dot: 'dark:bg-blue-400',   border: 'dark:border-blue-500/20'   },
    },
    lead_agent: {
        light: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
        dark:  { bg: 'dark:bg-emerald-500/10',text: 'dark:text-emerald-300',dot: 'dark:bg-emerald-400',border: 'dark:border-emerald-500/20' },
    },
    task_agent: {
        light: { bg: 'bg-slate-100',  text: 'text-slate-600',   dot: 'bg-slate-400'   },
        dark:  { bg: 'dark:bg-slate-500/10',  text: 'dark:text-slate-400',  dot: 'dark:bg-slate-500',  border: 'dark:border-slate-600/30'  },
    },
};

const AGENT_WS_PREFIXES = ['agent_spawned', 'agent_terminated', 'agent_status', 'agent_updated'];
function isAgentEvent(content: string): boolean {
    return AGENT_WS_PREFIXES.some(p => content?.startsWith(p));
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeAgent(agent: any): Agent {
    const rawType  = agent.agent_type;
    const validType = VALID_AGENT_TYPES.includes(rawType) ? rawType : 'task_agent';
    return {
        ...agent,
        subordinates:  Array.isArray(agent.subordinates) ? agent.subordinates : [],
        stats:         agent.stats || { tasks_completed: 0, tasks_failed: 0 },
        status:        agent.status || 'unknown',
        name:          agent.name   || 'Unnamed Agent',
        agent_type:    validType    as Agent['agent_type'],
        agentium_id:   agent.agentium_id || agent.id || 'unknown',
    } as Agent;
}

// ─── Reassign Confirmation Modal ──────────────────────────────────────────────

interface ReassignModalProps {
    agent:           Agent;
    newParent:       Agent;
    validating:      boolean;
    validationError: string | null;
    onConfirm:       () => void;
    onClose:         () => void;
}

const ReassignModal: React.FC<ReassignModalProps> = ({
    agent, newParent, validating, validationError, onConfirm, onClose,
}) => (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
        <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl w-full max-w-sm border border-gray-200 dark:border-[#1e2535] p-6 space-y-4">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Confirm Reassignment</h3>

            {validating ? (
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Validating capabilities…
                </div>
            ) : validationError ? (
                <div className="flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl px-4 py-3">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    {validationError}
                </div>
            ) : (
                <p className="text-sm text-gray-700 dark:text-gray-300">
                    Move <span className="font-semibold">{agent.name}</span> under{' '}
                    <span className="font-semibold">{newParent.name}</span>?
                </p>
            )}

            <div className="flex gap-3 pt-1">
                <button
                    onClick={onClose}
                    className="flex-1 px-4 py-2 border border-gray-200 dark:border-[#1e2535] text-sm font-medium rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors"
                >
                    Cancel
                </button>
                <button
                    onClick={onConfirm}
                    disabled={validating || !!validationError}
                    className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                    Reassign
                </button>
            </div>
        </div>
    </div>
);

// ─── Main Page ────────────────────────────────────────────────────────────────

export const AgentsPage: React.FC = () => {
    const [agents,       setAgents]       = useState<Agent[]>([]);
    const [isLoading,    setIsLoading]    = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [viewMode,     setViewMode]     = useState<'tree' | 'list'>('tree');
    const [spawnParent,  setSpawnParent]  = useState<Agent | null>(null);

    // ── Promote state ─────────────────────────────────────────────────────────
    const [promoteTarget, setPromoteTarget] = useState<Agent | null>(null);

    // ── Bulk liquidate state ──────────────────────────────────────────────────
    const [showBulkLiquidate, setShowBulkLiquidate] = useState(false);

    // ── Lifecycle sidebar ─────────────────────────────────────────────────────
    const [sidebarOpen, setSidebarOpen] = useState(false);
    /** Key to force LifecycleDashboard to remount/refetch after bulk liquidation */
    const [dashboardKey, setDashboardKey] = useState(0);

    // ── DnD state ─────────────────────────────────────────────────────────────
    const [draggingAgent,   setDraggingAgent]   = useState<Agent | null>(null);
    const [dropTarget,      setDropTarget]      = useState<string | null>(null);
    const [pendingReassign, setPendingReassign] = useState<{ agent: Agent; newParent: Agent } | null>(null);
    const [validating,      setValidating]      = useState(false);
    const [validationError, setValidationError] = useState<string | null>(null);
    const dragCounter = useRef(0);

    // ── Real-time ─────────────────────────────────────────────────────────────
    const lastMessage = useWebSocketStore(state => state.lastMessage);
    const prevMsgRef  = useRef<typeof lastMessage>(null);

    // ─────────────────────────────────────────────────────────────────────────
    // Data loading
    // ─────────────────────────────────────────────────────────────────────────

    const loadAgents = useCallback(async (silent = false) => {
        try {
            if (!silent) setIsLoading(true);
            else         setIsRefreshing(true);
            const data = await agentsService.getAgents();
            setAgents((data || []).map(normalizeAgent));
        } catch (err) {
            console.error('Failed to load agents:', err);
            if (!silent) toast.error('Failed to load agents');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    }, []);

    useEffect(() => { loadAgents(); }, [loadAgents]);

    // ─────────────────────────────────────────────────────────────────────────
    // Real-time hierarchy updates via WebSocket
    // ─────────────────────────────────────────────────────────────────────────

    useEffect(() => {
        if (!lastMessage || lastMessage === prevMsgRef.current) return;
        prevMsgRef.current = lastMessage;

        const { type, content, metadata } = lastMessage;

        if (type === 'system' && content && isAgentEvent(content)) {
            loadAgents(true);
            return;
        }

        if (metadata?.agent_id) {
            const agentId = metadata.agent_id;

            const statusMatch = content?.match(/^agent_status:(\w+):/);
            if (statusMatch) {
                const newStatus = statusMatch[1] as Agent['status'];
                setAgents(prev =>
                    prev.map(a => a.agentium_id === agentId ? { ...a, status: newStatus } : a)
                );
            }

            if (content?.startsWith('agent_spawned'))    loadAgents(true);
            if (content?.startsWith('agent_terminated')) {
                setAgents(prev =>
                    prev.map(a =>
                        a.agentium_id === agentId
                            ? { ...a, status: 'terminated', is_terminated: true }
                            : a
                    )
                );
            }
        }
    }, [lastMessage, loadAgents]);

    // ─────────────────────────────────────────────────────────────────────────
    // Spawn
    // ─────────────────────────────────────────────────────────────────────────

    const handleSpawn = async (name: string, childType: 'council_member' | 'lead_agent' | 'task_agent') => {
        if (!spawnParent) return;

        const placeholderId = `pending-${Date.now()}`;
        const placeholder   = normalizeAgent({
            id: placeholderId, agentium_id: placeholderId, name,
            agent_type: childType, status: 'initializing',
            subordinates: [], stats: { tasks_completed: 0, tasks_failed: 0 },
            constitution_version: '', is_terminated: false, parent: spawnParent.agentium_id,
        });

        setAgents(prev => [
            ...prev.map(a =>
                a.agentium_id === spawnParent.agentium_id
                    ? { ...a, subordinates: [...a.subordinates, placeholderId] }
                    : a
            ),
            placeholder,
        ]);

        try {
            // FIX: Added missing required fields 'description' and 'parent_agentium_id'
            await agentsService.spawnAgent(spawnParent.agentium_id, { 
                child_type: childType, 
                name,
                description: `Spawned ${childType} agent: ${name}`, // Added
                parent_agentium_id: spawnParent.agentium_id // Added
            });
            toast.success('Agent spawned successfully');
            await loadAgents(true);
        } catch (err) {
            setAgents(prev =>
                prev
                    .filter(a => a.agentium_id !== placeholderId)
                    .map(a =>
                        a.agentium_id === spawnParent.agentium_id
                            ? { ...a, subordinates: a.subordinates.filter(id => id !== placeholderId) }
                            : a
                    )
            );
            throw err;
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Terminate
    // ─────────────────────────────────────────────────────────────────────────

    const handleTerminate = async (agent: Agent) => {
        if (!window.confirm(`Terminate ${agent.name}?`)) return;

        setAgents(prev =>
            prev.map(a =>
                a.agentium_id === agent.agentium_id
                    ? { ...a, status: 'terminated', is_terminated: true }
                    : a
            )
        );

        try {
            // FIX: Added third argument (sovereign user ID or agent ID)
            await agentsService.terminateAgent(
                agent.agentium_id, 
                'Manual termination by Sovereign',
                'sovereign' // Added third argument - the acting user/agent ID
            );
            toast.success('Agent terminated');
            await loadAgents(true);
        } catch {
            setAgents(prev =>
                prev.map(a =>
                    a.agentium_id === agent.agentium_id
                        ? { ...a, status: 'active', is_terminated: false }
                        : a
                )
            );
            toast.error('Failed to terminate agent');
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Promote
    // ─────────────────────────────────────────────────────────────────────────

    const handlePromoteConfirm = async (promotedByAgentiumId: string, reason: string) => {
        if (!promoteTarget) return;
        await lifecycleService.promoteAgent({
            task_agentium_id:       promoteTarget.agentium_id,
            promoted_by_agentium_id: promotedByAgentiumId,
            reason,
        });
        toast.success(`${promoteTarget.name} promoted to Lead Agent`);
        setPromoteTarget(null);
        await loadAgents(true);
        // Refresh dashboard stats to reflect promotion event
        setDashboardKey(k => k + 1);
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Bulk liquidate callback
    // ─────────────────────────────────────────────────────────────────────────

    const handleBulkLiquidateSuccess = async (count: number) => {
        toast.success(`${count} idle agent${count !== 1 ? 's' : ''} liquidated`);
        await loadAgents(true);
        setDashboardKey(k => k + 1);
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Drag-and-drop
    // ─────────────────────────────────────────────────────────────────────────

    const handleDragStart = useCallback((agent: Agent) => {
        if (agent.agent_type === 'head_of_council') return;
        setDraggingAgent(agent);
    }, []);

    const handleDragEnd = useCallback(() => {
        setDraggingAgent(null);
        setDropTarget(null);
        dragCounter.current = 0;
    }, []);

    const handleDragEnter = useCallback((targetId: string) => {
        if (!draggingAgent || targetId === draggingAgent.agentium_id) return;
        dragCounter.current += 1;
        setDropTarget(targetId);
    }, [draggingAgent]);

    const handleDragLeave = useCallback((_targetId: string) => {
        dragCounter.current = Math.max(0, dragCounter.current - 1);
        if (dragCounter.current === 0) setDropTarget(null);
    }, []);

    const handleDrop = useCallback(async (newParentId: string) => {
        setDropTarget(null);
        dragCounter.current = 0;
        if (!draggingAgent || newParentId === draggingAgent.agentium_id) return;

        const newParent = agentsMapRef.current.get(newParentId);
        if (!newParent) return;

        const agentSnapshot = draggingAgent;
        setDraggingAgent(null);

        setPendingReassign({ agent: agentSnapshot, newParent });
        setValidating(true);
        setValidationError(null);

        try {
            const result = await capabilitiesService.validateReassignment(
                agentSnapshot.agentium_id, newParentId,
            );
            setValidationError(result.valid ? null : (result.reason ?? 'Invalid reassignment'));
        } catch {
            setValidationError('Could not validate capabilities.');
        } finally {
            setValidating(false);
        }
    }, [draggingAgent]);

    const confirmReassign = async () => {
        if (!pendingReassign) return;
        const { agent, newParent } = pendingReassign;
        setPendingReassign(null);

        setAgents(prev => {
            const oldParent = prev.find(a => a.subordinates.includes(agent.agentium_id));
            return prev.map(a => {
                if (oldParent && a.agentium_id === oldParent.agentium_id)
                    return { ...a, subordinates: a.subordinates.filter(id => id !== agent.agentium_id) };
                if (a.agentium_id === newParent.agentium_id)
                    return { ...a, subordinates: [...a.subordinates, agent.agentium_id] };
                return a;
            });
        });

        try {
            await (agentsService as any).reassignAgent(agent.agentium_id, {
                new_parent_id: newParent.agentium_id,
                reason: 'Manual reassignment via drag-and-drop',
            });
            toast.success(`${agent.name} moved under ${newParent.name}`);
            await loadAgents(true);
        } catch (err: any) {
            toast.error(err?.response?.data?.detail || 'Reassignment failed');
            await loadAgents(true);
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Derived data
    // ─────────────────────────────────────────────────────────────────────────

    const agentsMapRef = useRef(new Map<string, Agent>());
    const agentsMap    = new Map<string, Agent>();
    agents.forEach(a => { if (a?.agentium_id) agentsMap.set(a.agentium_id, a); });
    agentsMapRef.current = agentsMap;

    const headOfCouncil = agents.find(a => a.agent_type === 'head_of_council');

    // ─────────────────────────────────────────────────────────────────────────
    // Render
    // ─────────────────────────────────────────────────────────────────────────

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
                        {draggingAgent && (
                            <span className="ml-2 text-blue-500 font-medium animate-pulse">
                                · Drop on a parent to reassign
                            </span>
                        )}
                    </p>
                </div>

                <div className="flex items-center gap-2">
                    {/* Lifecycle sidebar toggle */}
                    <button
                        onClick={() => setSidebarOpen(v => !v)}
                        title={sidebarOpen ? 'Hide lifecycle panel' : 'Show lifecycle panel'}
                        className={[
                            'p-2 rounded-lg border text-slate-500 dark:text-slate-400 transition-colors shadow-sm',
                            sidebarOpen
                                ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20 text-blue-600 dark:text-blue-400'
                                : 'border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] hover:bg-slate-50 dark:hover:bg-[#1e2535]',
                        ].join(' ')}
                    >
                        <BarChart2 className="w-4 h-4" />
                    </button>

                    <button
                        onClick={() => loadAgents(true)}
                        disabled={isRefreshing}
                        title="Refresh"
                        className="p-2 rounded-lg border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-[#1e2535] disabled:opacity-50 transition-colors shadow-sm"
                    >
                        <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                    </button>

                    <div className="flex rounded-lg overflow-hidden border border-slate-200 dark:border-[#1e2535] bg-slate-50 dark:bg-[#161b27] shadow-sm">
                        {(['tree', 'list'] as const).map((mode, i) => (
                            <button
                                key={mode}
                                onClick={() => setViewMode(mode)}
                                className={[
                                    'flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-all duration-150',
                                    i === 0 ? 'border-r border-slate-200 dark:border-[#1e2535]' : '',
                                    viewMode === mode
                                        ? 'bg-white dark:bg-[#1e2535] text-slate-900 dark:text-white shadow-sm'
                                        : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200',
                                ].join(' ')}
                            >
                                {mode === 'tree' ? <LayoutGrid className="w-4 h-4" /> : <List className="w-4 h-4" />}
                                {mode === 'tree' ? 'Tree' : 'List'}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* ── Main + sidebar layout ────────────────────────────── */}
            <div className={`flex flex-1 gap-4 overflow-hidden ${sidebarOpen ? 'flex-row' : ''}`}>

                {/* ── Content area ──────────────────────────────────── */}
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
                            <div className="relative rounded-xl border border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900 p-6 min-h-[500px] overflow-auto">
                                <div
                                    className="absolute inset-0 rounded-xl bg-[radial-gradient(circle,_#cbd5e1_1px,_transparent_1px)] dark:bg-[radial-gradient(circle,_#334155_1px,_transparent_1px)] bg-[length:20px_20px] opacity-60 pointer-events-none"
                                    aria-hidden="true"
                                />
                                <div className="relative z-10">
                                    <AgentTree
                                        agent={headOfCouncil}
                                        agentsMap={agentsMap}
                                        onSpawn={setSpawnParent}
                                        onTerminate={handleTerminate}
                                        onPromote={setPromoteTarget}
                                        draggingAgentId={draggingAgent?.agentium_id ?? null}
                                        dropTargetId={dropTarget}
                                        onDragStart={handleDragStart}
                                        onDragEnd={handleDragEnd}
                                        onDragEnter={handleDragEnter}
                                        onDragLeave={handleDragLeave}
                                        onDrop={handleDrop}
                                    />
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                Head of Council not found in agent list.
                            </div>
                        )

                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {agents.map(agent => {
                                const colorSet = AGENT_TYPE_COLORS[agent.agent_type] ?? AGENT_TYPE_COLORS.task_agent;
                                const label    = AGENT_TYPE_LABELS[agent.agent_type] ?? agent.agent_type;
                                const { light, dark } = colorSet;
                                return (
                                    <div
                                        key={agent.id || agent.agentium_id}
                                        className="rounded-xl border border-slate-200 dark:border-[#1e2535] p-4 bg-white dark:bg-[#0f1117] hover:border-slate-300 dark:hover:border-[#2a3347] hover:shadow-sm transition-all duration-150"
                                    >
                                        <div className="flex items-start justify-between gap-2 mb-3">
                                            <h3 className="text-sm font-semibold text-slate-900 dark:text-gray-100 leading-snug">{agent.name}</h3>
                                            <span className={['inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap flex-shrink-0 border', light.bg, light.text, dark.bg, dark.text, dark.border].join(' ')}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${light.dot} ${dark.dot}`} />
                                                {label}
                                            </span>
                                        </div>
                                        <p className="text-xs text-slate-400 dark:text-slate-600 font-mono truncate">{agent.agentium_id}</p>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* ── Lifecycle sidebar ──────────────────────────────── */}
                {sidebarOpen && (
                    <div className="w-80 flex-shrink-0 overflow-y-auto rounded-xl border border-slate-200 dark:border-[#1e2535] p-5 bg-white dark:bg-[#161b27] shadow-sm dark:shadow-[0_2px_20px_rgba(0,0,0,0.3)]">
                        <LifecycleDashboard
                            key={dashboardKey}
                            onOpenBulkLiquidate={() => setShowBulkLiquidate(true)}
                        />
                    </div>
                )}
            </div>

            {/* ── Modals ──────────────────────────────────────────────── */}
            {spawnParent && (
                <SpawnAgentModal
                    parent={spawnParent}
                    onConfirm={handleSpawn}
                    onClose={() => setSpawnParent(null)}
                />
            )}

            {promoteTarget && (
                <PromoteAgentModal
                    agent={promoteTarget}
                    agents={agents}
                    onConfirm={handlePromoteConfirm}
                    onClose={() => setPromoteTarget(null)}
                />
            )}

            {showBulkLiquidate && (
                <BulkLiquidateModal
                    onClose={() => setShowBulkLiquidate(false)}
                    onSuccess={handleBulkLiquidateSuccess}
                />
            )}

            {pendingReassign && (
                <ReassignModal
                    agent={pendingReassign.agent}
                    newParent={pendingReassign.newParent}
                    validating={validating}
                    validationError={validationError}
                    onConfirm={confirmReassign}
                    onClose={() => setPendingReassign(null)}
                />
            )}
        </div>
    );
};