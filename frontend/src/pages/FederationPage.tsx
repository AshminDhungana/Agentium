// src/pages/FederationPage.tsx

import { useEffect, useState } from 'react';
import {
    Globe,
    Plus,
    RefreshCw,
    Shield,
    AlertTriangle,
    CheckCircle,
    Send,
    Search,
    Activity,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { useAuthStore } from '@/store/authStore';
import {
    federationService,
} from '@/services/federation';
import type {
    PeerInstance,
    FederatedTask,
    TrustLevel,
    RegisterPeerRequest,
    DelegateTaskRequest,
} from '@/services/federation';
import { getFedTaskStatusColors } from '@/utils/statusColors';
import { PeerTable } from '@/components/federation/PeerTable';
import { AddPeerModal } from '@/components/federation/AddPeerModal';
import { DelegateTaskModal } from '@/components/federation/DelegateTaskModal';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Module-scope helpers (not recreated on every render) ──────────────────────

/**
 * Format a delegated_at / completed_at ISO string into a readable locale string.
 * Used in the Tasks tab. For last_heartbeat_at use federationService.formatHeartbeat().
 */
function formatDate(dateString?: string | null): string {
    if (!dateString) return '—';
    try {
        return new Date(dateString).toLocaleString('en-US', {
            year:   'numeric',
            month:  'short',
            day:    'numeric',
            hour:   '2-digit',
            minute: '2-digit',
        });
    } catch {
        return dateString;
    }
}

// ── Component ──────────────────────────────────────────────────────────────────

export function FederationPage() {
    const { user } = useAuthStore();

    // ── Data state ────────────────────────────────────────────────────────────
    const [peers, setPeers]   = useState<PeerInstance[]>([]);
    const [tasks, setTasks]   = useState<FederatedTask[]>([]);

    // ── Granular loading flags ────────────────────────────────────────────────
    const [peersLoading, setPeersLoading] = useState(true);
    const [tasksLoading, setTasksLoading] = useState(true);
    const [submitting,   setSubmitting]   = useState(false);

    // ── UI state ──────────────────────────────────────────────────────────────
    const [activeTab,               setActiveTab]               = useState<'peers' | 'tasks'>('peers');
    const [showAddPeerModal,        setShowAddPeerModal]        = useState(false);
    const [showDelegateTaskModal,   setShowDelegateTaskModal]   = useState(false);
    const [searchQuery,             setSearchQuery]             = useState('');
    /** ID of the peer currently in inline-delete-confirm state. null = none. */
    const [deletingPeerId,          setDeletingPeerId]          = useState<string | null>(null);

    // ── Bootstrap ─────────────────────────────────────────────────────────────

    useEffect(() => {
        void fetchPeers();
        void fetchTasks();
    }, []);

    // ── Data fetching ─────────────────────────────────────────────────────────

    const fetchPeers = async () => {
        setPeersLoading(true);
        try {
            const data = await federationService.listPeers();
            setPeers(data);
        } catch (error: unknown) {
            console.error('Failed to fetch peers:', error);
            showToast.error(error instanceof Error ? error.message : 'Failed to load peers');
        } finally {
            setPeersLoading(false);
        }
    };

    const fetchTasks = async () => {
        setTasksLoading(true);
        try {
            const data = await federationService.listFederatedTasks();
            setTasks(data);
        } catch (error: unknown) {
            console.error('Failed to fetch tasks:', error);
            showToast.error(error instanceof Error ? error.message : 'Failed to load tasks');
        } finally {
            setTasksLoading(false);
        }
    };

    // ── Handlers ──────────────────────────────────────────────────────────────

    /** Called by AddPeerModal with validated form data. */
    const handleAddPeer = async (data: RegisterPeerRequest) => {
        setSubmitting(true);
        try {
            await federationService.registerPeer(data);
            showToast.success(`Peer "${data.name}" registered successfully`);
            setShowAddPeerModal(false);
            await fetchPeers();
        } catch (error: unknown) {
            showToast.error(error instanceof Error ? error.message : 'Failed to register peer');
        } finally {
            setSubmitting(false);
        }
    };

    /** Called by PeerTable when the user confirms inline deletion. */
    const handleDeletePeer = async (peerId: string) => {
        const peerName = peers.find(p => p.id === peerId)?.name ?? peerId;
        setSubmitting(true);
        try {
            await federationService.deletePeer(peerId);
            showToast.success(`Peer "${peerName}" removed successfully`);
            setDeletingPeerId(null);
            await fetchPeers();
        } catch (error: unknown) {
            showToast.error(error instanceof Error ? error.message : 'Failed to remove peer');
        } finally {
            setSubmitting(false);
        }
    };

    /** Called by PeerTable when the trust-level select changes. */
    const handleUpdateTrust = async (peerId: string, trustLevel: TrustLevel) => {
        const peerName = peers.find(p => p.id === peerId)?.name ?? peerId;
        try {
            await federationService.updatePeerTrust(peerId, trustLevel);
            showToast.success(`Trust level for "${peerName}" updated to ${trustLevel}`);
            // Refresh to get the authoritative DB value
            await fetchPeers();
        } catch (error: unknown) {
            showToast.error(error instanceof Error ? error.message : 'Failed to update trust level');
            // Re-fetch to revert optimistic UI if any
            await fetchPeers();
        }
    };

    /** Called by DelegateTaskModal with validated + JSON-parsed form data. */
    const handleDelegateTask = async (data: DelegateTaskRequest) => {
        setSubmitting(true);
        try {
            const result = await federationService.delegateTask(data);
            showToast.success(`Task delegated successfully (ID: ${result.id})`);
            setShowDelegateTaskModal(false);
            await fetchTasks();
        } catch (error: unknown) {
            showToast.error(error instanceof Error ? error.message : 'Failed to delegate task');
        } finally {
            setSubmitting(false);
        }
    };

    // ── Derived data ──────────────────────────────────────────────────────────

    const peerStats = federationService.getPeerStats(peers);
    const taskStats = federationService.getTaskStats(tasks);

    const filteredPeers = peers.filter(peer =>
        peer.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        peer.base_url.toLowerCase().includes(searchQuery.toLowerCase())
    );

    // ── Access gate ───────────────────────────────────────────────────────────

    if (!user?.isSovereign) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6 transition-colors duration-200">
                <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] border border-gray-200 dark:border-[#1e2535] p-8 text-center max-w-md">
                    <div className="w-16 h-16 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mx-auto mb-5">
                        <Shield className="w-8 h-8 text-red-600 dark:text-red-400" aria-hidden="true" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Only Sovereign users can manage federation settings.
                    </p>
                </div>
            </div>
        );
    }

    // ── Render ─────────────────────────────────────────────────────────────────

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ───────────────────────────────────────────── */}
                <div className="mb-8">
                    <div className="flex items-center gap-3 mb-1">
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                            Federation
                        </h1>
                        <span className="px-2.5 py-0.5 bg-indigo-100 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 text-xs font-semibold rounded-full border border-indigo-200 dark:border-indigo-500/20">
                            New
                        </span>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage peer instances and cross-instance task delegation.
                    </p>
                </div>

                {/* ── Stats Cards ───────────────────────────────────────────── */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">

                    {/* Total Peers */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center">
                                <Globe className="w-5 h-5 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {peersLoading ? '—' : peerStats.total}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Peers</p>
                    </div>

                    {/* Active Peers */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" aria-hidden="true" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {peersLoading ? '—' : peerStats.active}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active</p>
                    </div>

                    {/* Suspended Peers — operationally important to surface */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                                <AlertTriangle className="w-5 h-5 text-orange-600 dark:text-orange-400" aria-hidden="true" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {peersLoading ? '—' : peerStats.suspended}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Suspended</p>
                    </div>

                    {/* Delegated Tasks */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <Send className="w-5 h-5 text-blue-600 dark:text-blue-400" aria-hidden="true" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {tasksLoading ? '—' : tasks.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Delegated Tasks</p>
                    </div>
                </div>

                {/* ── Tabs ──────────────────────────────────────────────────── */}
                <div className="flex gap-2 mb-6" role="tablist" aria-label="Federation sections">
                    <button
                        role="tab"
                        aria-selected={activeTab === 'peers'}
                        onClick={() => setActiveTab('peers')}
                        className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                            activeTab === 'peers'
                                ? 'bg-indigo-600 text-white shadow-sm'
                                : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                        }`}
                    >
                        <Globe className="w-4 h-4" aria-hidden="true" />
                        Peer Instances
                        {!peersLoading && peerStats.total > 0 && (
                            <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                                activeTab === 'peers'
                                    ? 'bg-white/20 text-white'
                                    : 'bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                            }`}>
                                {peerStats.total}
                            </span>
                        )}
                    </button>
                    <button
                        role="tab"
                        aria-selected={activeTab === 'tasks'}
                        onClick={() => setActiveTab('tasks')}
                        className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                            activeTab === 'tasks'
                                ? 'bg-indigo-600 text-white shadow-sm'
                                : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                        }`}
                    >
                        <Activity className="w-4 h-4" aria-hidden="true" />
                        Delegated Tasks
                        {!tasksLoading && tasks.length > 0 && (
                            <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                                activeTab === 'tasks'
                                    ? 'bg-white/20 text-white'
                                    : 'bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                            }`}>
                                {tasks.length}
                            </span>
                        )}
                    </button>
                </div>

                {/* ── Peers Tab ──────────────────────────────────────────────── */}
                {activeTab === 'peers' && (
                    <>
                        {/* Toolbar */}
                        <div className="flex flex-col sm:flex-row gap-4 mb-6">
                            <div className="relative flex-1">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                                <input
                                    type="search"
                                    placeholder="Search peers by name or URL…"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    aria-label="Search peers"
                                    className="w-full pl-11 pr-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                />
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => void fetchPeers()}
                                    disabled={peersLoading}
                                    aria-label="Refresh peer list"
                                    className="px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {peersLoading
                                        ? <LoadingSpinner size="sm" />
                                        : <RefreshCw className="w-4 h-4" aria-hidden="true" />
                                    }
                                    Refresh
                                </button>
                                <button
                                    onClick={() => setShowAddPeerModal(true)}
                                    aria-label="Add new peer instance"
                                    className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                                >
                                    <Plus className="w-4 h-4" aria-hidden="true" />
                                    Add Peer
                                </button>
                            </div>
                        </div>

                        {/* Peers Table (extracted component) */}
                        <PeerTable
                            peers={filteredPeers}
                            isLoading={peersLoading}
                            hasSearch={searchQuery.length > 0}
                            deletingPeerId={deletingPeerId}
                            onDeleteRequest={setDeletingPeerId}
                            onDeleteConfirm={handleDeletePeer}
                            onDeleteCancel={() => setDeletingPeerId(null)}
                            onTrustChange={handleUpdateTrust}
                        />
                    </>
                )}

                {/* ── Tasks Tab ──────────────────────────────────────────────── */}
                {activeTab === 'tasks' && (
                    <>
                        {/* Toolbar */}
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex gap-4 text-sm text-gray-500 dark:text-gray-400">
                                {!tasksLoading && tasks.length > 0 && (
                                    <>
                                        <span>
                                            <span className="font-semibold text-gray-900 dark:text-white">{taskStats.outgoing}</span> outgoing
                                        </span>
                                        <span>
                                            <span className="font-semibold text-gray-900 dark:text-white">{taskStats.incoming}</span> incoming
                                        </span>
                                        <span>
                                            <span className="font-semibold text-green-600 dark:text-green-400">{taskStats.completed}</span> completed
                                        </span>
                                        {taskStats.failed > 0 && (
                                            <span>
                                                <span className="font-semibold text-red-600 dark:text-red-400">{taskStats.failed}</span> failed
                                            </span>
                                        )}
                                    </>
                                )}
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => void fetchTasks()}
                                    disabled={tasksLoading}
                                    aria-label="Refresh tasks"
                                    className="px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {tasksLoading
                                        ? <LoadingSpinner size="sm" />
                                        : <RefreshCw className="w-4 h-4" aria-hidden="true" />
                                    }
                                    Refresh
                                </button>
                                <button
                                    onClick={() => setShowDelegateTaskModal(true)}
                                    disabled={peerStats.active === 0}
                                    aria-label="Delegate a task to a peer"
                                    title={peerStats.active === 0 ? 'No active peers available' : undefined}
                                    className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                                >
                                    <Send className="w-4 h-4" aria-hidden="true" />
                                    Delegate Task
                                </button>
                            </div>
                        </div>

                        {/* Tasks List */}
                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            {tasksLoading ? (
                                <div className="p-16 text-center">
                                    <LoadingSpinner size="lg" />
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Loading tasks…</p>
                                </div>
                            ) : tasks.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <Activity className="w-6 h-6 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Delegated Tasks
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Delegate tasks to peer instances to distribute workload.
                                    </p>
                                </div>
                            ) : (
                                <div
                                    className="divide-y divide-gray-100 dark:divide-[#1e2535]"
                                    aria-label="Federated task list"
                                >
                                    {tasks.map((task) => {
                                        const statusColors = getFedTaskStatusColors(task.status);
                                        const isOutgoing   = task.direction === 'outgoing';

                                        return (
                                            <div
                                                key={task.id}
                                                className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                            >
                                                <div className="flex items-start justify-between gap-4">
                                                    <div className="flex items-start gap-3 min-w-0">
                                                        <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                                                            isOutgoing
                                                                ? 'bg-blue-100 dark:bg-blue-500/10'
                                                                : 'bg-green-100 dark:bg-green-500/10'
                                                        }`}>
                                                            <Send className={`w-4 h-4 ${
                                                                isOutgoing
                                                                    ? 'text-blue-600 dark:text-blue-400'
                                                                    : 'text-green-600 dark:text-green-400'
                                                            }`} aria-hidden="true" />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                                                Task{' '}
                                                                <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                                                                    {task.original_task_id}
                                                                </span>
                                                            </p>
                                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                                                {isOutgoing ? '↑ Outgoing' : '↓ Incoming'}
                                                                {' · '}
                                                                {formatDate(task.delegated_at)}
                                                                {task.completed_at && (
                                                                    <> · completed {formatDate(task.completed_at)}</>
                                                                )}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border flex-shrink-0 ${statusColors.badge}`}>
                                                        {statusColors.label}
                                                    </span>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>

            {/* ── Modals ──────────────────────────────────────────────────────── */}

            {showAddPeerModal && (
                <AddPeerModal
                    isSubmitting={submitting}
                    onClose={() => setShowAddPeerModal(false)}
                    onSubmit={handleAddPeer}
                />
            )}

            {showDelegateTaskModal && (
                <DelegateTaskModal
                    peers={peers}
                    isSubmitting={submitting}
                    onClose={() => setShowDelegateTaskModal(false)}
                    onSubmit={handleDelegateTask}
                />
            )}
        </div>
    );
}

export default FederationPage;