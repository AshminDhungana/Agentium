import React, { useEffect, useReducer, useRef, useCallback, useMemo } from 'react';
import { Agent } from '../types';
import { agentsService, capabilitiesService, lifecycleService } from '../services/agents';
import { AgentTree } from '../components/agents/AgentTree';
import { AgentListView } from '../components/agents/AgentListView';
import { SpawnAgentModal } from '../components/agents/SpawnAgentModal';
import { PromoteAgentModal } from '../components/agents/PromoteAgentModal';
import { TerminateAgentModal } from '../components/agents/TerminateAgentModal';
import { BulkLiquidateModal } from '../components/agents/BulkLiquidateModal';
import { LifecycleDashboard } from '../components/agents/LifecycleDashboard';
import { DragDropProvider } from '../context/DragDropContext';
import { useWebSocketStore } from '@/store/websocketStore';
import { VALID_AGENT_TYPES, AGENT_TYPE_LABELS, AGENT_TYPE_COLORS, isAgentWsEvent } from '../constants/agents';
import {
    LayoutGrid, List, Users, AlertCircle, RefreshCw,
    BarChart2, ChevronLeft, ChevronRight as ChevronRightIcon,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeAgent(raw: unknown): Agent {
    const agent = raw as Record<string, unknown>;
    const rawType = agent.agent_type as string;
    const validType = (VALID_AGENT_TYPES as readonly string[]).includes(rawType) ? rawType : 'task_agent';
    return {
        ...(agent as object),
        subordinates: Array.isArray(agent.subordinates) ? agent.subordinates as string[] : [],
        stats:        (agent.stats as Agent['stats']) || { tasks_completed: 0, tasks_failed: 0 },
        status:       (agent.status as Agent['status']) || 'active',
        name:         (agent.name as string) || 'Unnamed Agent',
        agent_type:   validType as Agent['agent_type'],
        agentium_id:  (agent.agentium_id as string) || (agent.id as string) || 'unknown',
    } as Agent;
}

// ─── Persistent preferences ───────────────────────────────────────────────────

const PREF_VIEW_MODE = 'agentsPage:viewMode';
const PREF_SIDEBAR   = 'agentsPage:sidebarOpen';

function readPref<T>(key: string, fallback: T): T {
    try {
        const v = localStorage.getItem(key);
        return v !== null ? (JSON.parse(v) as T) : fallback;
    } catch { return fallback; }
}
function savePref(key: string, value: unknown) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

// ─── State + reducer ──────────────────────────────────────────────────────────

interface PageState {
    agents:      Agent[];
    isLoading:   boolean;
    isRefreshing: boolean;
    viewMode:    'tree' | 'list';
    sidebarOpen: boolean;
    // modal targets
    spawnParent:       Agent | null;
    promoteTarget:     Agent | null;
    terminateTarget:   Agent | null;
    showBulkLiquidate: boolean;
    // drag-and-drop reassign confirmation
    pendingReassign:  { agent: Agent; newParent: Agent } | null;
    validating:       boolean;
    validationError:  string | null;
}

type PageAction =
    | { type: 'SET_AGENTS';          agents: Agent[] }
    | { type: 'SET_LOADING';         value: boolean }
    | { type: 'SET_REFRESHING';      value: boolean }
    | { type: 'SET_VIEW_MODE';       mode: 'tree' | 'list' }
    | { type: 'TOGGLE_SIDEBAR' }
    | { type: 'SET_SPAWN_PARENT';    agent: Agent | null }
    | { type: 'SET_PROMOTE_TARGET';  agent: Agent | null }
    | { type: 'SET_TERMINATE_TARGET';agent: Agent | null }
    | { type: 'SET_BULK_LIQUIDATE';  show: boolean }
    | { type: 'UPDATE_AGENT_STATUS'; agentiumId: string; status: Agent['status'] }
    | { type: 'PATCH_AGENT';         agentiumId: string; updates: Partial<Agent> }
    | { type: 'SET_PENDING_REASSIGN';payload: { agent: Agent; newParent: Agent } | null }
    | { type: 'SET_VALIDATING';      value: boolean }
    | { type: 'SET_VALIDATION_ERROR';error: string | null };

function reducer(state: PageState, action: PageAction): PageState {
    switch (action.type) {
        case 'SET_AGENTS':
            return { ...state, agents: action.agents, isLoading: false, isRefreshing: false };
        case 'SET_LOADING':
            return { ...state, isLoading: action.value };
        case 'SET_REFRESHING':
            return { ...state, isRefreshing: action.value };
        case 'SET_VIEW_MODE':
            savePref(PREF_VIEW_MODE, action.mode);
            return { ...state, viewMode: action.mode };
        case 'TOGGLE_SIDEBAR': {
            const next = !state.sidebarOpen;
            savePref(PREF_SIDEBAR, next);
            return { ...state, sidebarOpen: next };
        }
        case 'SET_SPAWN_PARENT':      return { ...state, spawnParent:      action.agent };
        case 'SET_PROMOTE_TARGET':    return { ...state, promoteTarget:    action.agent };
        case 'SET_TERMINATE_TARGET':  return { ...state, terminateTarget:  action.agent };
        case 'SET_BULK_LIQUIDATE':    return { ...state, showBulkLiquidate: action.show };
        case 'UPDATE_AGENT_STATUS':
            return {
                ...state,
                agents: state.agents.map(a =>
                    a.agentium_id === action.agentiumId ? { ...a, status: action.status } : a
                ),
            };
        case 'PATCH_AGENT':
            return {
                ...state,
                agents: state.agents.map(a =>
                    a.agentium_id === action.agentiumId ? { ...a, ...action.updates } : a
                ),
            };
        case 'SET_PENDING_REASSIGN':  return { ...state, pendingReassign: action.payload };
        case 'SET_VALIDATING':        return { ...state, validating: action.value };
        case 'SET_VALIDATION_ERROR':  return { ...state, validationError: action.error };
        default:                      return state;
    }
}

// ─── Reassign modal (inline — small enough to stay here) ─────────────────────

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
                    <LoadingSpinner size="xs" />
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
    const [state, dispatch] = useReducer(reducer, {
        agents:            [],
        isLoading:         true,
        isRefreshing:      false,
        viewMode:          readPref<'tree' | 'list'>(PREF_VIEW_MODE, 'tree'),
        sidebarOpen:       readPref<boolean>(PREF_SIDEBAR, false),
        spawnParent:       null,
        promoteTarget:     null,
        terminateTarget:   null,
        showBulkLiquidate: false,
        pendingReassign:   null,
        validating:        false,
        validationError:   null,
    });

    const {
        agents, isLoading, isRefreshing, viewMode, sidebarOpen,
        spawnParent, promoteTarget, terminateTarget, showBulkLiquidate,
        pendingReassign, validating, validationError,
    } = state;

    // ── Lifecycle sidebar refresh token ───────────────────────────────────────
    const [dashboardKey, setDashboardKey] = React.useState(0);

    // ── WebSocket ─────────────────────────────────────────────────────────────
    const lastMessage = useWebSocketStore(s => s.lastMessage);
    const prevMsgRef  = useRef<typeof lastMessage>(null);

    const fetchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // ─────────────────────────────────────────────────────────────────────────
    // Data loading
    // ─────────────────────────────────────────────────────────────────────────

    const loadAgents = useCallback(async (silent = false) => {
        if (!silent) dispatch({ type: 'SET_LOADING', value: true });
        else         dispatch({ type: 'SET_REFRESHING', value: true });

        try {
            const data = await agentsService.getAgents();
            dispatch({ type: 'SET_AGENTS', agents: (data || []).map(normalizeAgent) });
        } catch (err) {
            console.error('Failed to load agents:', err);
            if (!silent) showToast.error('Failed to load agents');
            dispatch({ type: 'SET_LOADING',    value: false });
            dispatch({ type: 'SET_REFRESHING', value: false });
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        agentsService.getAgents()
            .then(data => {
                if (!cancelled) dispatch({ type: 'SET_AGENTS', agents: (data || []).map(normalizeAgent) });
            })
            .catch(err => {
                if (!cancelled) {
                    console.error('Failed to load agents:', err);
                    showToast.error('Failed to load agents');
                    dispatch({ type: 'SET_LOADING', value: false });
                }
            });
        return () => { cancelled = true; };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // ─────────────────────────────────────────────────────────────────────────
    // Real-time updates via WebSocket
    // ─────────────────────────────────────────────────────────────────────────

    const debouncedSilentFetch = useCallback(() => {
        if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
        fetchDebounceRef.current = setTimeout(() => {
            loadAgents(true);
            fetchDebounceRef.current = null;
        }, 250);
    }, [loadAgents]);

    useEffect(() => {
        if (!lastMessage || lastMessage === prevMsgRef.current) return;
        prevMsgRef.current = lastMessage;

        const { type, content, metadata } = lastMessage;
        const contentStr = typeof content === 'string' ? content : '';

        if (type === 'agent_spawned' || type === 'agent_promoted') {
            debouncedSilentFetch();
            return;
        }

        if (type === 'agent_liquidated') {
            const agentId = (lastMessage.agent_id as string) ?? metadata?.agent_id as string;
            if (agentId) {
                dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: agentId, status: 'terminated' });
            }
            debouncedSilentFetch();
            return;
        }

        if (type === 'agent_status_changed') {
            const agentId   = (lastMessage.agent_id as string) ?? metadata?.agent_id as string;
            const newStatus = lastMessage.new_status as Agent['status'];
            if (agentId && newStatus) {
                dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: agentId, status: newStatus });
            }
            return;
        }

        if (type === 'system' && isAgentWsEvent(type, contentStr)) {
            debouncedSilentFetch();
            return;
        }

        if (metadata?.agent_id) {
            const agentId = metadata.agent_id as string;

            const statusMatch = contentStr.match(/^agent_status:(\w+):/);
            if (statusMatch) {
                const newStatus = statusMatch[1] as Agent['status'];
                dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: agentId, status: newStatus });
                return;
            }

            if (contentStr.startsWith('agent_spawned') || contentStr.startsWith('agent_promoted')) {
                debouncedSilentFetch();
                return;
            }

            if (contentStr.startsWith('agent_terminated') || contentStr.startsWith('agent_liquidated')) {
                dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: agentId, status: 'terminated' });
                debouncedSilentFetch();
                return;
            }
        }
    }, [lastMessage, debouncedSilentFetch]);

    // Cleanup debounce on unmount
    useEffect(() => () => {
        if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
    }, []);

    // ─────────────────────────────────────────────────────────────────────────
    // Derived data
    // ─────────────────────────────────────────────────────────────────────────

    const agentsMap = useMemo(() => {
        const map = new Map<string, Agent>();
        agents.forEach(a => { if (a?.agentium_id) map.set(a.agentium_id, a); });
        return map;
    }, [agents]);

    const headOfCouncil = useMemo(
        () => agents.find(a => a.agent_type === 'head_of_council'),
        [agents],
    );

    const tierCounts = useMemo(() => {
        const counts = { head: 0, council: 0, lead: 0, task: 0 };
        agents.forEach(a => {
            if (a.status === 'terminated') return;
            const prefix = (a.agentium_id ?? a.id ?? '')[0];
            if (prefix === '0') counts.head++;
            else if (prefix === '1') counts.council++;
            else if (prefix === '2') counts.lead++;
            else if (prefix === '3') counts.task++;
        });
        return counts;
    }, [agents]);

    // ─────────────────────────────────────────────────────────────────────────
    // Spawn
    // ─────────────────────────────────────────────────────────────────────────

    const handleSpawn = async (
        name: string,
        childType: 'council_member' | 'lead_agent' | 'task_agent',
    ) => {
        if (!spawnParent) return;

        const placeholderId = `pending-${Date.now()}`;
        const placeholder   = normalizeAgent({
            id: placeholderId, agentium_id: placeholderId, name,
            agent_type: childType, status: 'initializing',
            subordinates: [], stats: { tasks_completed: 0, tasks_failed: 0 },
            constitution_version: '', is_terminated: false, parent: spawnParent.agentium_id,
        });

        dispatch({
            type: 'SET_AGENTS',
            agents: [
                ...agents.map(a =>
                    a.agentium_id === spawnParent.agentium_id
                        ? { ...a, subordinates: [...a.subordinates, placeholderId] }
                        : a
                ),
                placeholder,
            ],
        });

        try {
            await agentsService.spawnAgent(spawnParent.agentium_id, {
                child_type:         childType,
                name,
                description:        `${childType.replace(/_/g, ' ')} spawned via UI: ${name}`,
                parent_agentium_id: spawnParent.agentium_id,
            });
            showToast.success('Agent spawned successfully');
            await loadAgents(true);
        } catch (err) {
            dispatch({
                type: 'SET_AGENTS',
                agents: agents
                    .filter(a => a.agentium_id !== placeholderId)
                    .map(a =>
                        a.agentium_id === spawnParent.agentium_id
                            ? { ...a, subordinates: a.subordinates.filter(id => id !== placeholderId) }
                            : a
                    ),
            });
            throw err;
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Terminate
    // ─────────────────────────────────────────────────────────────────────────

    const handleTerminate = useCallback((agent: Agent) => {
        dispatch({ type: 'SET_TERMINATE_TARGET', agent });
    }, []);

    const handleTerminateConfirm = async (reason: string, authorizedById: string) => {
        if (!terminateTarget) return;

        dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: terminateTarget.agentium_id, status: 'terminating' });

        try {
            await agentsService.terminateAgent(terminateTarget.agentium_id, reason, authorizedById);
            showToast.success(`${terminateTarget.name} terminated`);
            dispatch({ type: 'SET_TERMINATE_TARGET', agent: null });
            await loadAgents(true);
            setDashboardKey(k => k + 1);
        } catch (err: unknown) {
            dispatch({ type: 'UPDATE_AGENT_STATUS', agentiumId: terminateTarget.agentium_id, status: 'active' });
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            throw new Error(detail || 'Termination failed');
        }
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Promote
    // ─────────────────────────────────────────────────────────────────────────

    const handlePromoteConfirm = async (promotedByAgentiumId: string, reason: string) => {
        if (!promoteTarget) return;
        await lifecycleService.promoteAgent({
            task_agentium_id:        promoteTarget.agentium_id,
            promoted_by_agentium_id: promotedByAgentiumId,
            reason,
        });
        showToast.success(`${promoteTarget.name} promoted to Lead Agent`);
        dispatch({ type: 'SET_PROMOTE_TARGET', agent: null });
        await loadAgents(true);
        setDashboardKey(k => k + 1);
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Bulk liquidate
    // ─────────────────────────────────────────────────────────────────────────

    const handleBulkLiquidateSuccess = async (count: number) => {
        showToast.success(`${count} idle agent${count !== 1 ? 's' : ''} liquidated`);
        await loadAgents(true);
        setDashboardKey(k => k + 1);
    };

    // ─────────────────────────────────────────────────────────────────────────
    // Drag-and-drop reassign
    // ─────────────────────────────────────────────────────────────────────────

    const handleDropCommit = useCallback(async (draggingAgent: Agent, newParentId: string) => {
        const newParent = agentsMap.get(newParentId);
        if (!newParent) return;

        dispatch({ type: 'SET_PENDING_REASSIGN', payload: { agent: draggingAgent, newParent } });
        dispatch({ type: 'SET_VALIDATING',        value: true });
        dispatch({ type: 'SET_VALIDATION_ERROR',  error: null });

        try {
            const result = await capabilitiesService.validateReassignment(
                draggingAgent.agentium_id, newParentId,
            );
            dispatch({ type: 'SET_VALIDATION_ERROR', error: result.valid ? null : (result.reason ?? 'Invalid reassignment') });
        } catch {
            dispatch({ type: 'SET_VALIDATION_ERROR', error: 'Could not validate capabilities.' });
        } finally {
            dispatch({ type: 'SET_VALIDATING', value: false });
        }
    }, [agentsMap]);

    const confirmReassign = async () => {
        if (!pendingReassign) return;
        const { agent, newParent } = pendingReassign;
        dispatch({ type: 'SET_PENDING_REASSIGN', payload: null });

        const oldParent = agents.find(a => a.subordinates.includes(agent.agentium_id));
        dispatch({
            type: 'SET_AGENTS',
            agents: agents.map(a => {
                if (oldParent && a.agentium_id === oldParent.agentium_id)
                    return { ...a, subordinates: a.subordinates.filter(id => id !== agent.agentium_id) };
                if (a.agentium_id === newParent.agentium_id)
                    return { ...a, subordinates: [...a.subordinates, agent.agentium_id] };
                return a;
            }),
        });

        try {
            await agentsService.reassignAgent(agent.agentium_id, {
                new_parent_id: newParent.agentium_id,
                reason:        'Manual reassignment via drag-and-drop',
            });
            showToast.success(`${agent.name} moved under ${newParent.name}`);
            await loadAgents(true);
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            showToast.error(detail || 'Reassignment failed');
            await loadAgents(true);
        }
    };

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
                    </p>

                    {!isLoading && agents.length > 0 && (
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                            {([
                                ['head',    'Head',    'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'],
                                ['council', 'Council', 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300'],
                                ['lead',    'Lead',    'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'],
                                ['task',    'Task',    'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300'],
                            ] as const).map(([key, label, cls]) => (
                                tierCounts[key] > 0 && (
                                    <span key={key} className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
                                        {label}: {tierCounts[key]}
                                    </span>
                                )
                            ))}
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {/* Lifecycle sidebar toggle */}
                    <button
                        onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
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
                                onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode })}
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
            {/*
             * flex-1 + overflow-hidden here is critical.
             * The tree uses a virtualizer that needs a concrete scroll container height.
             * overflow-hidden on this row prevents the page itself from scrolling and
             * ensures the inner virtualizer div gets h-full resolved to a real pixel value.
             */}
            <div className={`flex flex-1 gap-4 overflow-hidden ${sidebarOpen ? 'flex-row' : ''}`}>

                {/* ── Content area ──────────────────────────────────── */}
                {/*
                 * overflow-hidden (not overflow-auto) — the virtualizer manages its own
                 * scroll internally. Setting overflow-auto here competes with it and
                 * breaks the scroll container height calculation.
                 */}
                <div className="flex-1 overflow-hidden rounded-xl border border-slate-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] shadow-sm dark:shadow-[0_2px_20px_rgba(0,0,0,0.3)] transition-colors duration-200">

                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center h-40 gap-3 text-slate-400 dark:text-slate-500">
                            <LoadingSpinner size="md" label="Loading agents…" />
                        </div>

                    ) : agents.length === 0 ? (
                            <div className="max-w-md mx-auto pt-10">
                                <EmptyState
                                    illustration="agents"
                                    icon={Users}
                                    title="No agents yet"
                                    description="Your AI workforce hasn't been initialized yet. Spawn the Head of Council to begin building your agent hierarchy."
                                />
                            </div>

                    ) : viewMode === 'tree' ? (
                        headOfCouncil ? (
                            /*
                             * Tree wrapper:
                             *
                             * BEFORE: min-h-[500px] overflow-auto p-6
                             *   - min-h grows with content → parent never clips → page scrolls
                             *   - overflow-auto competes with the virtualizer's own scroll container
                             *   - p-6 padding is inside the scroll area, causing the virtualizer
                             *     to miscalculate available height
                             *
                             * AFTER: h-full overflow-hidden p-4
                             *   - h-full resolves to the flex-1 parent's computed height (fixed)
                             *   - overflow-hidden lets the virtualizer's own scroll container
                             *     be the only scrollable element
                             *   - Dot-grid bg is still there via the absolute overlay
                             */
                            <div className="relative h-full overflow-hidden bg-slate-50 dark:bg-slate-900">
                                {/* Dot-grid background decoration */}
                                <div
                                    className="absolute inset-0 bg-[radial-gradient(circle,_#cbd5e1_1px,_transparent_1px)] dark:bg-[radial-gradient(circle,_#334155_1px,_transparent_1px)] bg-[length:20px_20px] opacity-60 pointer-events-none rounded-xl"
                                    aria-hidden="true"
                                />
                                {/* Tree content — p-4 applied here, inside the scroll area */}
                                <div className="relative z-10 h-full p-4">
                                    <DragDropProvider onDropCommit={handleDropCommit}>
                                        <AgentTree
                                            agent={headOfCouncil}
                                            agentsMap={agentsMap}
                                            onSpawn={a => dispatch({ type: 'SET_SPAWN_PARENT', agent: a })}
                                            onTerminate={handleTerminate}
                                            onPromote={a => dispatch({ type: 'SET_PROMOTE_TARGET', agent: a })}
                                        />
                                    </DragDropProvider>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm p-6">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                Head of Council not found in agent list.
                            </div>
                        )

                    ) : (
                        // List view — its own scroll, so overflow-auto is correct here
                        <div className="h-full overflow-auto p-6">
                            <AgentListView
                                agents={agents}
                                onSpawn={a => dispatch({ type: 'SET_SPAWN_PARENT', agent: a })}
                                onTerminate={handleTerminate}
                                onPromote={a => dispatch({ type: 'SET_PROMOTE_TARGET', agent: a })}
                            />
                        </div>
                    )}
                </div>

                {/* ── Lifecycle sidebar ──────────────────────────────── */}
                {sidebarOpen && (
                    <div className="w-80 flex-shrink-0 overflow-y-auto rounded-xl border border-slate-200 dark:border-[#1e2535] p-5 bg-white dark:bg-[#161b27] shadow-sm dark:shadow-[0_2px_20px_rgba(0,0,0,0.3)]">
                        <LifecycleDashboard
                            key={dashboardKey}
                            onOpenBulkLiquidate={() => dispatch({ type: 'SET_BULK_LIQUIDATE', show: true })}
                        />
                    </div>
                )}
            </div>

            {/* ── Modals ──────────────────────────────────────────────── */}
            {spawnParent && (
                <SpawnAgentModal
                    parent={spawnParent}
                    onConfirm={handleSpawn}
                    onClose={() => dispatch({ type: 'SET_SPAWN_PARENT', agent: null })}
                />
            )}

            {promoteTarget && (
                <PromoteAgentModal
                    agent={promoteTarget}
                    agents={agents}
                    onConfirm={handlePromoteConfirm}
                    onClose={() => dispatch({ type: 'SET_PROMOTE_TARGET', agent: null })}
                />
            )}

            {terminateTarget && (
                <TerminateAgentModal
                    agent={terminateTarget}
                    agents={agents}
                    onConfirm={handleTerminateConfirm}
                    onClose={() => dispatch({ type: 'SET_TERMINATE_TARGET', agent: null })}
                />
            )}

            {showBulkLiquidate && (
                <BulkLiquidateModal
                    onClose={() => dispatch({ type: 'SET_BULK_LIQUIDATE', show: false })}
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
                    onClose={() => dispatch({ type: 'SET_PENDING_REASSIGN', payload: null })}
                />
            )}
        </div>
    );
};