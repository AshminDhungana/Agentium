// src/pages/RBACManagement.tsx

import { useEffect, useState, useCallback } from 'react';
import {
    Shield,
    Users,
    Key,
    Clock,
    Plus,
    Trash2,
    RefreshCw,
    Loader2,
    UserPlus,
    Search,
    Crown,
    UserCog,
    Eye,
    HandMetal,
    AlertTriangle,
    CheckCircle,
    XCircle,
    ScrollText,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';
import { rbacService, Delegation, RBACUser } from '@/services/rbac';
import { AuditTrailTab } from '@/components/rbac/AuditTrailTab';

// ── Types ─────────────────────────────────────────────────────────────────────

// RBACUser (from services/rbac.ts) now carries created_at — no local alias needed.

interface Capability {
    name: string;
    description: string;
    tier: string;
    /** Whether this capability is valid for delegation (backed by the server). */
    delegatable: boolean;
}

// Reference list — all capabilities displayed in the Capabilities tab.
// The `delegatable` flag marks the four backend-enforced valid capabilities.
// The modal filters to delegatable:true so users can never select a name
// that the server would reject with a 400.
const CAPABILITIES: Capability[] = [
    { name: 'veto',               description: 'Override Council decisions',        tier: '0xxxx', delegatable: true  },
    { name: 'configure_agents',   description: 'Configure agent settings',          tier: '0xxxx', delegatable: true  },
    { name: 'execute_tasks',      description: 'Execute system-level tasks',        tier: '0xxxx', delegatable: true  },
    { name: 'manage_users',       description: 'Manage users and access',           tier: '0xxxx', delegatable: true  },
    { name: 'amendment',          description: 'Propose constitutional amendments', tier: '0xxxx', delegatable: false },
    { name: 'liquidate_any',      description: 'Liquidate any agent',               tier: '0xxxx', delegatable: false },
    { name: 'admin_vector_db',    description: 'Administer vector database',        tier: '0xxxx', delegatable: false },
    { name: 'propose_amendment',  description: 'Propose amendments',                tier: '1xxxx', delegatable: false },
    { name: 'allocate_resources', description: 'Allocate system resources',        tier: '1xxxx', delegatable: false },
    { name: 'audit',              description: 'View audit logs',                   tier: '1xxxx', delegatable: false },
    { name: 'moderate_knowledge', description: 'Moderate knowledge base',           tier: '1xxxx', delegatable: false },
    { name: 'spawn_task_agent',   description: 'Spawn task agents',                tier: '2xxxx', delegatable: false },
    { name: 'delegate_work',      description: 'Delegate work to agents',           tier: '2xxxx', delegatable: false },
    { name: 'request_resources',  description: 'Request resources',                tier: '2xxxx', delegatable: false },
    { name: 'submit_knowledge',   description: 'Submit to knowledge base',         tier: '2xxxx', delegatable: false },
];

/** Capabilities that can actually be sent to the backend delegation endpoint. */
const DELEGATABLE_CAPABILITIES = CAPABILITIES.filter((c) => c.delegatable);

// ── Helpers ───────────────────────────────────────────────────────────────────

const getRoleIcon = (role: string) => {
    switch (role) {
        case 'primary_sovereign':
        case 'sovereign':
            return <Crown className="w-4 h-4 text-yellow-500" />;
        case 'deputy_sovereign':
        case 'council':
            return <Shield className="w-4 h-4 text-purple-500" />;
        case 'lead':
            return <UserCog className="w-4 h-4 text-blue-500" />;
        case 'task':
            return <Users className="w-4 h-4 text-green-500" />;
        default:
            return <Eye className="w-4 h-4 text-gray-500" />;
    }
};

const getRoleClasses = (role: string) => {
    switch (role) {
        case 'primary_sovereign':
        case 'sovereign':
            return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
        case 'deputy_sovereign':
        case 'council':
            return 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20';
        case 'lead':
            return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20';
        case 'task':
            return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20';
        default:
            return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';
    }
};

const getTierClasses = (tier: string) => {
    switch (tier) {
        case '0xxxx':
            return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
        case '1xxxx':
            return 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20';
        case '2xxxx':
            return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20';
        default:
            return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20';
    }
};

const formatDate = (dateString?: string) => {
    if (!dateString) return 'No expiration';
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
};

// ── Access Denied screen (rendered outside the main component so no hooks run) ──

function AccessDenied() {
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
                    Only Sovereign users can manage RBAC settings.
                </p>
            </div>
        </div>
    );
}

// ── Thin public wrapper — auth gate lives here, above all hooks ───────────────

export function RBACManagementPage() {
    const { user } = useAuthStore();

    // Guard fires before any hooks run in the inner component.
    // This prevents unnecessary data fetching for non-admin users.
    if (!user?.is_admin) {
        return <AccessDenied />;
    }

    return <RBACManagementInner />;
}

// ── Inner component — all hooks live here, only mounted for admins ────────────

function RBACManagementInner() {
    const { user } = useAuthStore();

    const [users, setUsers] = useState<RBACUser[]>([]);
    const [delegations, setDelegations] = useState<Delegation[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'users' | 'delegations' | 'capabilities' | 'audit'>('users');
    const [searchQuery, setSearchQuery] = useState('');

    // Delegate modal state
    const [showDelegateModal, setShowDelegateModal] = useState(false);
    const [selectedGrantee, setSelectedGrantee] = useState('');
    const [selectedCapabilities, setSelectedCapabilities] = useState<string[]>([]);
    const [delegationReason, setDelegationReason] = useState('');
    const [delegationExpiry, setDelegationExpiry] = useState('');
    const [delegating, setDelegating] = useState(false);

    // Per-row revoke confirmation — stores the delegation ID pending confirmation,
    // or null when no confirmation is in progress.
    const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
    const [revokingId, setRevokingId] = useState<string | null>(null);

    // ── Effects ─────────────────────────────────────────────────────────────

    useEffect(() => {
        fetchData();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // ── Data fetching ────────────────────────────────────────────────────────
    // Wrapped in useCallback so it has a stable identity for useEffect
    // and can be safely passed as a prop if this component is ever split.

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            // Delegations are embedded in each user's active_delegations field
            // from the /roles endpoint — no second API call is needed.
            const resolvedUsers = await rbacService.listUsersWithRoles();
            setUsers(resolvedUsers);
            setDelegations(resolvedUsers.flatMap((u) => u.active_delegations ?? []));
        } catch (error) {
            console.error('Failed to fetch RBAC data:', error);
            toast.error('Failed to load RBAC data');
        } finally {
            setLoading(false);
        }
    }, []);

    // ── Handlers ─────────────────────────────────────────────────────────────

    const handleDelegate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedGrantee || selectedCapabilities.length === 0) return;
        setDelegating(true);
        try {
            await rbacService.delegateCapability(
                selectedGrantee,
                selectedCapabilities,
                delegationReason || undefined,
                delegationExpiry || undefined,
            );
            toast.success('Capability delegated successfully');
            setShowDelegateModal(false);
            setSelectedGrantee('');
            setSelectedCapabilities([]);
            setDelegationReason('');
            setDelegationExpiry('');
            fetchData();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delegate capability');
        } finally {
            setDelegating(false);
        }
    };

    /** Step 1 — show inline confirmation row for this delegation. */
    const requestRevoke = (delegationId: string) => {
        setConfirmRevokeId(delegationId);
    };

    /** Step 2 — user confirmed; execute the revoke. */
    const confirmRevoke = async (delegationId: string) => {
        setConfirmRevokeId(null);
        setRevokingId(delegationId);
        try {
            await rbacService.revokeDelegation(delegationId);
            toast.success('Delegation revoked');
            fetchData();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to revoke delegation');
        } finally {
            setRevokingId(null);
        }
    };

    /** Cancel inline confirmation without taking any action. */
    const cancelRevoke = () => setConfirmRevokeId(null);

    const toggleCapability = (name: string, checked: boolean) => {
        setSelectedCapabilities((prev) =>
            checked ? [...prev, name] : prev.filter((c) => c !== name),
        );
    };

    const filteredUsers = users.filter((u) =>
        u.username.toLowerCase().includes(searchQuery.toLowerCase()),
    );

    // ── Render ───────────────────────────────────────────────────────────────

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ───────────────────────────────────────────── */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        Access Control
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage user roles, capabilities, and delegation.
                    </p>
                </div>

                {/* ── Stats Cards ───────────────────────────────────────────── */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {users.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Users</p>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
                                <Crown className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {users.filter((u) =>
                                    ['sovereign', 'primary_sovereign'].includes(u.effective_role),
                                ).length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Sovereigns</p>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <HandMetal className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {delegations.filter((d) => d.is_active).length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Active Delegations
                        </p>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                <Key className="w-5 h-5 text-green-600 dark:text-green-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {CAPABILITIES.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Capabilities</p>
                    </div>
                </div>

                {/* ── Tabs ──────────────────────────────────────────────────── */}
                <div className="flex gap-2 mb-6">
                    {(
                        [
                            { id: 'users',        label: 'Users & Roles',  icon: Users      },
                            { id: 'delegations',  label: 'Delegations',    icon: HandMetal  },
                            { id: 'capabilities', label: 'Capabilities',   icon: Key        },
                            { id: 'audit',        label: 'Audit Trail',    icon: ScrollText },
                        ] as const
                    ).map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                                activeTab === id
                                    ? 'bg-purple-600 text-white shadow-sm'
                                    : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                            }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </div>

                {/* ── Users Tab ─────────────────────────────────────────────── */}
                {activeTab === 'users' && (
                    <>
                        <div className="flex flex-col sm:flex-row gap-4 mb-6">
                            <div className="relative flex-1">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                                <input
                                    type="text"
                                    placeholder="Search users..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-full pl-11 pr-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                />
                            </div>
                            <button
                                onClick={fetchData}
                                className="px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 flex items-center gap-2"
                            >
                                <RefreshCw className="w-4 h-4" />
                                Refresh
                            </button>
                        </div>

                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            {loading ? (
                                <div className="p-16 text-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-purple-600 dark:text-purple-400 mx-auto mb-4" />
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Loading users...
                                    </p>
                                </div>
                            ) : filteredUsers.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <Users className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Users Found
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        {searchQuery
                                            ? 'Try a different search term'
                                            : 'No users in the system'}
                                    </p>
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full">
                                        <thead className="bg-gray-50 dark:bg-[#0f1117]">
                                            <tr>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                                    User
                                                </th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                                    Role
                                                </th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                                    Active Delegations
                                                </th>
                                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                                    Status
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                            {filteredUsers.map((userItem) => (
                                                <tr
                                                    key={userItem.id}
                                                    className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                                >
                                                    <td className="px-6 py-4">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-9 h-9 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                                                <Users className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                                            </div>
                                                            <div>
                                                                <span className="text-sm font-medium text-gray-900 dark:text-white">
                                                                    {userItem.username}
                                                                </span>
                                                                {userItem.email && (
                                                                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                                                                        {userItem.email}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span
                                                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full border ${getRoleClasses(userItem.effective_role)}`}
                                                        >
                                                            {getRoleIcon(userItem.effective_role)}
                                                            {userItem.effective_role}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span className="text-sm text-gray-600 dark:text-gray-400">
                                                            {userItem.active_delegations?.length || 0}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        <span
                                                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full border ${
                                                                userItem.is_active !== false
                                                                    ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                                    : 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                                                            }`}
                                                        >
                                                            {userItem.is_active !== false ? (
                                                                <>
                                                                    <CheckCircle className="w-3 h-3" />
                                                                    Active
                                                                </>
                                                            ) : (
                                                                'Inactive'
                                                            )}
                                                        </span>
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

                {/* ── Delegations Tab ───────────────────────────────────────── */}
                {activeTab === 'delegations' && (
                    <>
                        <div className="flex justify-end mb-6">
                            <button
                                onClick={() => setShowDelegateModal(true)}
                                className="px-4 py-2.5 bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                            >
                                <UserPlus className="w-4 h-4" />
                                New Delegation
                            </button>
                        </div>

                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            {delegations.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <HandMetal className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Active Delegations
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Create a delegation to grant temporary capabilities
                                    </p>
                                </div>
                            ) : (
                                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                    {delegations.map((delegation) => (
                                        <div
                                            key={delegation.id}
                                            className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                                        <HandMetal className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                            Delegation {delegation.id.substring(0, 8)}
                                                        </p>
                                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                                            {delegation.capabilities.length} capabilities •{' '}
                                                            Expires: {formatDate(delegation.expires_at)}
                                                        </p>
                                                    </div>
                                                </div>

                                                <div className="flex items-center gap-3">
                                                    {delegation.is_emergency && (
                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-red-100 text-red-700 border border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20">
                                                            <AlertTriangle className="w-3 h-3" />
                                                            Emergency
                                                        </span>
                                                    )}
                                                    <span
                                                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium rounded-full border ${
                                                            delegation.is_active
                                                                ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                                : 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                                                        }`}
                                                    >
                                                        {delegation.is_active ? 'Active' : 'Revoked'}
                                                    </span>

                                                    {/* ── Inline revoke confirmation ── */}
                                                    {delegation.is_active && (
                                                        confirmRevokeId === delegation.id ? (
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                                                    Confirm revoke?
                                                                </span>
                                                                <button
                                                                    onClick={() => confirmRevoke(delegation.id)}
                                                                    disabled={revokingId === delegation.id}
                                                                    className="px-2.5 py-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-medium rounded-lg transition-colors duration-150 flex items-center gap-1"
                                                                >
                                                                    {revokingId === delegation.id && (
                                                                        <Loader2 className="w-3 h-3 animate-spin" />
                                                                    )}
                                                                    Yes, revoke
                                                                </button>
                                                                <button
                                                                    onClick={cancelRevoke}
                                                                    className="px-2.5 py-1 border border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors duration-150"
                                                                >
                                                                    Cancel
                                                                </button>
                                                            </div>
                                                        ) : (
                                                            <button
                                                                onClick={() => requestRevoke(delegation.id)}
                                                                disabled={revokingId === delegation.id}
                                                                className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors duration-150 disabled:opacity-50"
                                                                title="Revoke delegation"
                                                            >
                                                                <Trash2 className="w-4 h-4" />
                                                            </button>
                                                        )
                                                    )}
                                                </div>
                                            </div>

                                            <div className="mt-3 flex flex-wrap gap-1">
                                                {delegation.capabilities.map((cap) => (
                                                    <span
                                                        key={cap}
                                                        className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md bg-gray-100 text-gray-700 border border-gray-200 dark:bg-[#0f1117] dark:text-gray-300 dark:border-[#2a3347]"
                                                    >
                                                        {cap}
                                                    </span>
                                                ))}
                                            </div>
                                            {delegation.reason && (
                                                <p className="mt-2 text-xs text-gray-400 dark:text-gray-500 italic">
                                                    Reason: {delegation.reason}
                                                </p>
                                            )}
                                            {delegation.granted_at && (
                                                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                                                    Granted: {formatDate(delegation.granted_at)}
                                                </p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* ── Capabilities Tab ──────────────────────────────────────── */}
                {activeTab === 'capabilities' && (
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                        <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                    <Key className="w-4 h-4 text-green-600 dark:text-green-400" />
                                </div>
                                <div>
                                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Available Capabilities
                                    </h2>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Capabilities that can be delegated to users
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                            {CAPABILITIES.map((cap) => (
                                <div
                                    key={cap.name}
                                    className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                                <Key className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                            </div>
                                            <div>
                                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                    {cap.name}
                                                </p>
                                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                                    {cap.description}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {cap.delegatable && (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700 border border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20">
                                                    <CheckCircle className="w-3 h-3" />
                                                    Delegatable
                                                </span>
                                            )}
                                            <span
                                                className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${getTierClasses(cap.tier)}`}
                                            >
                                                Tier {cap.tier}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Audit Trail Tab ───────────────────────────────────────── */}
                {activeTab === 'audit' && <AuditTrailTab />}
            </div>

            {/* ── Delegate Modal ────────────────────────────────────────────── */}
            {showDelegateModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-lg w-full border border-gray-200 dark:border-[#1e2535]">
                        <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 flex items-center justify-center">
                                    <UserPlus className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                                        New Delegation
                                    </h3>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Grant temporary capabilities to a user
                                    </p>
                                </div>
                            </div>
                        </div>

                        <form onSubmit={handleDelegate} className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Grant To (User)
                                </label>
                                <select
                                    value={selectedGrantee}
                                    onChange={(e) => setSelectedGrantee(e.target.value)}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                    required
                                >
                                    <option value="">Select a user</option>
                                    {users
                                        .filter((u) => u.id !== user?.id)
                                        .map((u) => (
                                            <option key={u.id} value={u.id}>
                                                {u.username}
                                            </option>
                                        ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Capabilities
                                </label>
                                {/* Modal only shows delegatable capabilities — ones the backend accepts. */}
                                <div className="max-h-48 overflow-y-auto border border-gray-200 dark:border-[#1e2535] rounded-lg p-3 space-y-2">
                                    {DELEGATABLE_CAPABILITIES.map((cap) => (
                                        <label
                                            key={cap.name}
                                            className="flex items-center gap-3 cursor-pointer group"
                                        >
                                            <input
                                                type="checkbox"
                                                checked={selectedCapabilities.includes(cap.name)}
                                                onChange={(e) =>
                                                    toggleCapability(cap.name, e.target.checked)
                                                }
                                                className="w-4 h-4 rounded border-gray-300 dark:border-[#2a3347] text-purple-600 focus:ring-purple-500"
                                            />
                                            <div className="flex-1 min-w-0">
                                                <span className="text-sm text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
                                                    {cap.name}
                                                </span>
                                                <span className="text-xs text-gray-400 dark:text-gray-500 ml-2">
                                                    {cap.description}
                                                </span>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Reason
                                    <span className="text-gray-400 dark:text-gray-500 font-normal ml-1">
                                        (Optional)
                                    </span>
                                </label>
                                <input
                                    type="text"
                                    value={delegationReason}
                                    onChange={(e) => setDelegationReason(e.target.value)}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                                    placeholder="Reason for delegation"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Expires
                                    <span className="text-gray-400 dark:text-gray-500 font-normal ml-1">
                                        (Optional)
                                    </span>
                                </label>
                                <input
                                    type="datetime-local"
                                    value={delegationExpiry}
                                    onChange={(e) => setDelegationExpiry(e.target.value)}
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                />
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowDelegateModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={
                                        !selectedGrantee ||
                                        selectedCapabilities.length === 0 ||
                                        delegating
                                    }
                                    className="flex-1 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center justify-center gap-2"
                                >
                                    {delegating && (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    )}
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

export default RBACManagementPage;