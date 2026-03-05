// src/pages/FederationPage.tsx

import { useEffect, useState } from 'react';
import {
    Globe,
    Plus,
    Trash2,
    RefreshCw,
    Link2,
    Shield,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Clock,
    Send,
    Settings,
    Loader2,
    ExternalLink,
    Search,
    Activity,
} from 'lucide-react';
import { api } from '@/services/api';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Peer {
    id: string;
    name: string;
    base_url: string;
    status: string;
    trust_level: string;
    last_heartbeat_at?: string;
    capabilities_shared?: string[];
}

interface FederatedTask {
    id: string;
    original_task_id: string;
    local_task_id?: string;
    status: string;
    direction: 'outgoing' | 'incoming';
    created_at: string;
}

// ── Component ───────────────────────────────────────────────────────────────

export function FederationPage() {
    const { user } = useAuthStore();

    // State
    const [peers, setPeers] = useState<Peer[]>([]);
    const [tasks, setTasks] = useState<FederatedTask[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'peers' | 'tasks'>('peers');
    const [showAddPeerModal, setShowAddPeerModal] = useState(false);
    const [showDelegateTaskModal, setShowDelegateTaskModal] = useState(false);

    // Add peer form state
    const [newPeer, setNewPeer] = useState({
        name: '',
        base_url: '',
        shared_secret: '',
        trust_level: 'limited',
        capabilities: '',
    });

    // Delegate task form state
    const [delegateForm, setDelegateForm] = useState({
        target_peer_id: '',
        original_task_id: '',
        payload: '',
    });

    const [searchQuery, setSearchQuery] = useState('');

    // ── Effects ─────────────────────────────────────────────────────────────

    useEffect(() => {
        fetchPeers();
        fetchTasks();
    }, []);

    // ── Data fetching ────────────────────────────────────────────────────

    const fetchPeers = async () => {
        try {
            const response = await api.get('/api/v1/federation/peers');
            setPeers(response.data);
        } catch (error: any) {
            console.error('Failed to fetch peers:', error);
            toast.error('Failed to load peers');
        }
    };

    const fetchTasks = async () => {
        setLoading(true);
        try {
            // For now, we'll fetch from existing endpoints
            // This is a placeholder - actual implementation would need backend support
            setTasks([]);
        } catch (error: any) {
            console.error('Failed to fetch tasks:', error);
        } finally {
            setLoading(false);
        }
    };

    // ── Handlers ─────────────────────────────────────────────────────────

    const handleAddPeer = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const response = await api.post('/api/v1/federation/peers', {
                name: newPeer.name,
                base_url: newPeer.base_url,
                shared_secret: newPeer.shared_secret,
                trust_level: newPeer.trust_level,
                capabilities: newPeer.capabilities.split(',').map(c => c.trim()).filter(Boolean),
            });
            toast.success(`Peer "${newPeer.name}" registered successfully`);
            setShowAddPeerModal(false);
            setNewPeer({ name: '', base_url: '', shared_secret: '', trust_level: 'limited', capabilities: '' });
            fetchPeers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to register peer');
        }
    };

    const handleDeletePeer = async (peerId: string, peerName: string) => {
        if (!confirm(`Are you sure you want to remove peer "${peerName}"?`)) return;
        try {
            await api.delete(`/api/v1/federation/peers/${peerId}`);
            toast.success('Peer removed successfully');
            fetchPeers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to remove peer');
        }
    };

    const handleDelegateTask = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const response = await api.post('/api/v1/federation/tasks/delegate', {
                target_peer_id: delegateForm.target_peer_id,
                original_task_id: delegateForm.original_task_id,
                payload: JSON.parse(delegateForm.payload || '{}'),
            });
            toast.success('Task delegated successfully');
            setShowDelegateTaskModal(false);
            setDelegateForm({ target_peer_id: '', original_task_id: '', payload: '' });
            fetchTasks();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delegate task');
        }
    };

    // ── Helpers ─────────────────────────────────────────────────────────

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'active':
                return <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />;
            case 'suspended':
                return <AlertTriangle className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />;
            case 'inactive':
                return <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />;
            default:
                return <Clock className="w-4 h-4 text-gray-400" />;
        }
    };

    const getStatusClasses = (status: string) => {
        switch (status) {
            case 'active':
                return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20';
            case 'suspended':
                return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
            case 'inactive':
                return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20';
            default:
                return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';
        }
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return 'Never';
        return new Date(dateString).toLocaleString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    };

    const filteredPeers = peers.filter(peer =>
        peer.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        peer.base_url.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const activePeersCount = peers.filter(p => p.status === 'active').length;

    // ── Access Check ───────────────────────────────────────────────────

    if (!user?.isSovereign) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6 transition-colors duration-200">
                <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] border border-gray-200 dark:border-[#1e2535] p-8 text-center max-w-md">
                    <div className="w-16 h-16 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mx-auto mb-5">
                        <Shield className="w-8 h-8 text-red-600 dark:text-red-400" />
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

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ─────────────────────────────────────────────── */}
                <div className="mb-8">
                    <div className="flex items-center gap-3 mb-1">
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                            Federation
                        </h1>
                        <span className="px-2.5 py-0.5 bg-indigo-100 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 text-xs font-semibold rounded-full border border-indigo-200 dark:border-indigo-500/20">
                            PHASE 11.2
                        </span>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage peer instances and cross-instance task delegation.
                    </p>
                </div>

                {/* ── Stats Cards ───────────────────────────────────────────── */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center">
                                <Globe className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {peers.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Peers</p>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {activePeersCount}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Peers</p>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <Send className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {tasks.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Delegated Tasks</p>
                    </div>
                </div>

                {/* ── Tabs ───────────────────────────────────────────────────── */}
                <div className="flex gap-2 mb-6">
                    <button
                        onClick={() => setActiveTab('peers')}
                        className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                            activeTab === 'peers'
                                ? 'bg-indigo-600 text-white shadow-sm'
                                : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                        }`}
                    >
                        <Globe className="w-4 h-4" />
                        Peer Instances
                    </button>
                    <button
                        onClick={() => setActiveTab('tasks')}
                        className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                            activeTab === 'tasks'
                                ? 'bg-indigo-600 text-white shadow-sm'
                                : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                        }`}
                    >
                        <Activity className="w-4 h-4" />
                        Delegated Tasks
                    </button>
                </div>

                {/* ── Peers Tab ───────────────────────────────────────────────── */}
                {activeTab === 'peers' && (
                    <>
                        {/* Toolbar */}
                        <div className="flex flex-col sm:flex-row gap-4 mb-6">
                            <div className="relative flex-1">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                                <input
                                    type="text"
                                    placeholder="Search peers by name or URL..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-full pl-11 pr-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                />
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={fetchPeers}
                                    className="px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 flex items-center gap-2"
                                >
                                    <RefreshCw className="w-4 h-4" />
                                    Refresh
                                </button>
                                <button
                                    onClick={() => setShowAddPeerModal(true)}
                                    className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                                >
                                    <Plus className="w-4 h-4" />
                                    Add Peer
                                </button>
                            </div>
                        </div>

                        {/* Peers Table */}
                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            {filteredPeers.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <Globe className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        {searchQuery ? 'No Peers Found' : 'No Peer Instances'}
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        {searchQuery ? 'Try a different search term' : 'Add a peer instance to start federation'}
                                    </p>
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full">
                                        <thead className="bg-gray-50 dark:bg-[#0f1117]">
                                            <tr>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Peer</th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">URL</th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Trust Level</th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Last Heartbeat</th>
                                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                            {filteredPeers.map((peer) => (
                                                <tr key={peer.id} className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150">
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-9 h-9 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center">
                                                                <Globe className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                                                            </div>
                                                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                                                                {peer.name}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-xs font-mono text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] px-2 py-0.5 rounded-md">
                                                                {peer.base_url}
                                                            </span>
                                                            <a
                                                                href={peer.base_url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400"
                                                            >
                                                                <ExternalLink className="w-3.5 h-3.5" />
                                                            </a>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${
                                                            peer.trust_level === 'full'
                                                                ? 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20'
                                                                : peer.trust_level === 'limited'
                                                                ? 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20'
                                                                : 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                                                        }`}>
                                                            {peer.trust_level}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full border ${getStatusClasses(peer.status)}`}>
                                                            {getStatusIcon(peer.status)}
                                                            {peer.status}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4 text-xs text-gray-500 dark:text-gray-400">
                                                        {formatDate(peer.last_heartbeat_at)}
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center justify-end gap-1.5">
                                                            <button
                                                                onClick={() => handleDeletePeer(peer.id, peer.name)}
                                                                className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors duration-150"
                                                                title="Remove peer"
                                                            >
                                                                <Trash2 className="w-3.5 h-3.5" />
                                                            </button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* ── Tasks Tab ───────────────────────────────────────────────── */}
                {activeTab === 'tasks' && (
                    <>
                        <div className="flex justify-end mb-6">
                            <button
                                onClick={() => setShowDelegateTaskModal(true)}
                                disabled={activePeersCount === 0}
                                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                            >
                                <Send className="w-4 h-4" />
                                Delegate Task
                            </button>
                        </div>

                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            {loading ? (
                                <div className="p-16 text-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400 mx-auto mb-4" />
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Loading tasks...</p>
                                </div>
                            ) : tasks.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <Activity className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Delegated Tasks
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Delegate tasks to peer instances to distribute workload.
                                    </p>
                                </div>
                            ) : (
                                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                    {tasks.map((task) => (
                                        <div key={task.id} className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150">
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                                                        task.direction === 'outgoing'
                                                            ? 'bg-blue-100 dark:bg-blue-500/10'
                                                            : 'bg-green-100 dark:bg-green-500/10'
                                                    }`}>
                                                        <Send className={`w-4 h-4 ${
                                                            task.direction === 'outgoing'
                                                                ? 'text-blue-600 dark:text-blue-400'
                                                                : 'text-green-600 dark:text-green-400'
                                                        }`} />
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                            Task {task.original_task_id}
                                                        </p>
                                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                                            {task.direction === 'outgoing' ? 'Outgoing' : 'Incoming'} • {formatDate(task.created_at)}
                                                        </p>
                                                    </div>
                                                </div>
                                                <span className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${
                                                    task.status === 'completed'
                                                        ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                        : task.status === 'pending'
                                                        ? 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20'
                                                        : 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                                                }`}>
                                                    {task.status}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>

            {/* ── Add Peer Modal ─────────────────────────────────────────────── */}
            {showAddPeerModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-lg w-full border border-gray-200 dark:border-[#1e2535]">
                        <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 flex items-center justify-center">
                                    <Plus className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Add Peer Instance
                                    </h3>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Register a new Agentium peer
                                    </p>
                                </div>
                            </div>
                        </div>

                        <form onSubmit={handleAddPeer} className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Peer Name
                                </label>
                                <input
                                    type="text"
                                    value={newPeer.name}
                                    onChange={(e) => setNewPeer({ ...newPeer, name: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="Engineering Dept"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Base URL
                                </label>
                                <input
                                    type="url"
                                    value={newPeer.base_url}
                                    onChange={(e) => setNewPeer({ ...newPeer, base_url: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="https://agentium-dept.company.com"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Shared Secret
                                </label>
                                <input
                                    type="password"
                                    value={newPeer.shared_secret}
                                    onChange={(e) => setNewPeer({ ...newPeer, shared_secret: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="Enter shared secret"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Trust Level
                                </label>
                                <select aria-label="Trust Level"
                                    value={newPeer.trust_level}
                                    onChange={(e) => setNewPeer({ ...newPeer, trust_level: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                >
                                    <option value="limited">Limited</option>
                                    <option value="full">Full</option>
                                    <option value="read_only">Read Only</option>
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Capabilities (comma-separated)
                                </label>
                                <input
                                    type="text"
                                    value={newPeer.capabilities}
                                    onChange={(e) => setNewPeer({ ...newPeer, capabilities: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="task_delegation, knowledge_sharing"
                                />
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowAddPeerModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                                >
                                    Add Peer
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Delegate Task Modal ─────────────────────────────────────────── */}
            {showDelegateTaskModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-lg w-full border border-gray-200 dark:border-[#1e2535]">
                        <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center">
                                    <Send className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Delegate Task
                                    </h3>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Send a task to a peer instance
                                    </p>
                                </div>
                            </div>
                        </div>

                        <form onSubmit={handleDelegateTask} className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Target Peer
                                </label>
                                <select aria-label="Target Peer"
                                    value={delegateForm.target_peer_id}
                                    onChange={(e) => setDelegateForm({ ...delegateForm, target_peer_id: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                    required
                                >
                                    <option value="">Select a peer</option>
                                    {peers.filter(p => p.status === 'active').map(peer => (
                                        <option key={peer.id} value={peer.id}>{peer.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Original Task ID
                                </label>
                                <input
                                    type="text"
                                    value={delegateForm.original_task_id}
                                    onChange={(e) => setDelegateForm({ ...delegateForm, original_task_id: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="local-task-123"
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Payload (JSON)
                                </label>
                                <textarea
                                    value={delegateForm.payload}
                                    onChange={(e) => setDelegateForm({ ...delegateForm, payload: e.target.value })}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150 font-mono"
                                    placeholder='{"task": "analyze data", "priority": "high"}'
                                    rows={4}
                                />
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowDelegateTaskModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                                >
                                    Delegate
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

export default FederationPage;
