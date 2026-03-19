import { useState, useEffect, useRef, useCallback } from 'react';
import {
    Users,
    CheckCircle,
    XCircle,
    Trash2,
    Key,
    Shield,
    Clock,
    Loader2,
    UserCheck,
    Mail,
    Calendar,
    AlertCircle,
    Search,
    ChevronDown,
} from 'lucide-react';
import { api } from '@/services/api';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

// C13: Extended User interface to include role fields returned by the
//      updated _user_dict() in admin.py.
interface User {
    id: string;
    username: string;
    email: string;
    is_active: boolean;
    is_admin: boolean;
    is_pending: boolean;
    role?: string;
    is_sovereign?: boolean;
    can_veto?: boolean;
    created_at?: string;
    updated_at?: string;
}

interface UserListResponse {
    users: User[];
    total: number;
}

// D6: Human-readable labels and ordering for the role dropdown.
const ROLE_OPTIONS: { value: string; label: string }[] = [
    { value: 'primary_sovereign', label: 'Primary Sovereign' },
    { value: 'deputy_sovereign',  label: 'Deputy Sovereign' },
    { value: 'observer',          label: 'Observer' },
];

// C7: Props interface — supports both embedded (inside SettingsPage tab) and
//     standalone (direct route) rendering.
interface UserManagementProps {
    /** When true, strips the full-page wrapper so the component fits inside
     *  a parent layout (e.g. the Settings page tab panel). */
    embedded?: boolean;
    /** Called after every successful user fetch with the current pending count.
     *  Used by SettingsPage to update the tab badge without a duplicate API call. */
    onPendingCountChange?: (count: number) => void;
}

export default function UserManagement({
    embedded = false,
    onPendingCountChange,
}: UserManagementProps) {
    const { user: currentUser } = useAuthStore();
    const [pendingUsers, setPendingUsers] = useState<User[]>([]);
    const [approvedUsers, setApprovedUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'pending' | 'approved'>('pending');

    // Password modal state
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [selectedUser, setSelectedUser] = useState<User | null>(null);
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');

    // C9: Inline confirmation states replace window.confirm() for both
    //     reject (pending users) and delete (approved users).
    const [confirmingReject, setConfirmingReject] = useState<string | null>(null);
    const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);

    // D6: Track which user's role is being updated (for per-row loading state).
    const [changingRole, setChangingRole] = useState<string | null>(null);

    // C10: Separate raw input from the debounced search query so each keystroke
    //      does not immediately re-filter a potentially large user list.
    const [rawSearch, setRawSearch] = useState('');
    const [searchQuery, setSearchQuery] = useState('');

    // C15: Ref to the first focusable element inside the modal for focus management.
    const modalFirstInputRef = useRef<HTMLInputElement>(null);

    // ── C10: 150 ms debounce on the search input ────────────────────────────
    useEffect(() => {
        const id = setTimeout(() => setSearchQuery(rawSearch), 150);
        return () => clearTimeout(id);
    }, [rawSearch]);

    // ── C15: Focus the first input when the password modal opens ───────────
    useEffect(() => {
        if (showPasswordModal) {
            // Small timeout ensures the element is in the DOM before focusing
            const id = setTimeout(() => modalFirstInputRef.current?.focus(), 50);
            return () => clearTimeout(id);
        }
    }, [showPasswordModal]);

    useEffect(() => {
        fetchUsers();
    }, []);

    /* ── Access denied ── */
    if (!currentUser?.is_admin) {
        return (
            <div className="flex items-center justify-center p-6">
                <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] border border-gray-200 dark:border-[#1e2535] p-8 text-center max-w-md">
                    <div className="w-16 h-16 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mx-auto mb-5">
                        <Shield className="w-8 h-8 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Admin privileges required to access user management.
                    </p>
                </div>
            </div>
        );
    }

    const fetchUsers = async () => {
        setLoading(true);
        try {
            const [pendingRes, approvedRes] = await Promise.all([
                api.get<UserListResponse>('/api/v1/admin/users/pending'),
                api.get<UserListResponse>('/api/v1/admin/users'),
            ]);
            const pending = pendingRes.data.users || [];
            setPendingUsers(pending);
            setApprovedUsers(approvedRes.data.users || []);
            // C5: Notify parent (SettingsPage) of the current pending count so
            //     it can update the tab badge without a duplicate API call.
            onPendingCountChange?.(pending.length);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to fetch users');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (userId: string, username: string) => {
        try {
            await api.post(`/api/v1/admin/users/${userId}/approve`);
            toast.success(`${username} approved successfully`, { icon: '✅', duration: 3000 });
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to approve user');
        }
    };

    // C9: Reject no longer uses window.confirm — the inline button pair handles
    //     confirmation. setConfirmingReject is cleared after the action.
    const handleReject = async (userId: string, username: string) => {
        try {
            await api.post(`/api/v1/admin/users/${userId}/reject`);
            toast.success(`${username}'s request rejected`, { icon: '❌', duration: 3000 });
            setConfirmingReject(null);
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to reject user');
            setConfirmingReject(null);
        }
    };

    // C9: Delete no longer uses window.confirm — same inline confirmation pattern.
    const handleDelete = async (userId: string, username: string) => {
        if (currentUser?.id && userId === currentUser.id) {
            toast.error('You cannot delete your own account');
            return;
        }
        try {
            await api.delete(`/api/v1/admin/users/${userId}`);
            toast.success(`${username} deleted successfully`);
            setConfirmingDelete(null);
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delete user');
            setConfirmingDelete(null);
        }
    };

    const handleChangePassword = async () => {
        if (!selectedUser || !newPassword) return;
        if (newPassword !== confirmPassword) { toast.error('Passwords do not match'); return; }
        if (newPassword.length < 8) { toast.error('Password must be at least 8 characters'); return; }
        try {
            // C2 (admin.py): body is now JSON { new_password } not a query param
            await api.post(`/api/v1/admin/users/${selectedUser.id}/change-password`, {
                new_password: newPassword,
            });
            toast.success(`Password changed for ${selectedUser.username}`, { icon: '🔐', duration: 3000 });
            closePasswordModal();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to change password');
        }
    };

    // D6: Role change handler — calls the new POST /admin/users/{id}/role endpoint.
    const handleRoleChange = async (userId: string, username: string, newRole: string) => {
        setChangingRole(userId);
        try {
            await api.post(`/api/v1/admin/users/${userId}/role`, { new_role: newRole });
            toast.success(`Role updated for ${username}`, { icon: '🛡️', duration: 3000 });
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to update role');
        } finally {
            setChangingRole(null);
        }
    };

    const closePasswordModal = () => {
        setShowPasswordModal(false);
        setSelectedUser(null);
        setNewPassword('');
        setConfirmPassword('');
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return 'N/A';
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    };

    const filteredApprovedUsers = approvedUsers.filter(
        (user) =>
            user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
            user.email.toLowerCase().includes(searchQuery.toLowerCase())
    );

    /* ── Loading ── */
    if (loading) {
        return (
            <div className="flex items-center justify-center py-24">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading users…</span>
                </div>
            </div>
        );
    }

    // ── Main content (shared between embedded and standalone) ───────────────
    const content = (
        <>
            {/* C7: Header only shown in standalone mode */}
            {!embedded && (
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        User Management
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage user approvals and permissions.
                    </p>
                </div>
            )}

            {/* ── Stats Cards ──────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                {/* Pending Approvals */}
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
                            <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                        </div>
                        <span className="text-2xl font-bold text-gray-900 dark:text-white">
                            {pendingUsers.length}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Pending Approvals</p>
                </div>

                {/* Active Users */}
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                            <UserCheck className="w-5 h-5 text-green-600 dark:text-green-400" />
                        </div>
                        <span className="text-2xl font-bold text-gray-900 dark:text-white">
                            {approvedUsers.filter((u) => u.is_active).length}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Users</p>
                </div>

                {/* Total Users */}
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                    <div className="flex items-center justify-between mb-4">
                        <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <span className="text-2xl font-bold text-gray-900 dark:text-white">
                            {approvedUsers.length}
                        </span>
                    </div>
                    <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Users</p>
                </div>
            </div>

            {/* ── Tabs ────────────────────────────────────────────────────── */}
            <div className="flex gap-2 mb-6">
                <button
                    onClick={() => setActiveTab('pending')}
                    className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                        activeTab === 'pending'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                    }`}
                >
                    <Clock className="w-4 h-4" />
                    Pending Approvals
                    {pendingUsers.length > 0 && (
                        <span className={`px-1.5 py-0.5 rounded-full text-xs font-bold ${
                            activeTab === 'pending'
                                ? 'bg-white/20 text-white'
                                : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                        }`}>
                            {pendingUsers.length}
                        </span>
                    )}
                </button>

                <button
                    onClick={() => setActiveTab('approved')}
                    className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                        activeTab === 'approved'
                            ? 'bg-blue-600 text-white shadow-sm'
                            : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                    }`}
                >
                    <UserCheck className="w-4 h-4" />
                    Approved Users
                </button>
            </div>

            {/* ── Pending Users Tab ────────────────────────────────────────── */}
            {activeTab === 'pending' && (
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                    {pendingUsers.length === 0 ? (
                        <div className="p-16 text-center">
                            <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                <Clock className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                            </div>
                            <p className="text-gray-900 dark:text-white font-medium mb-1">
                                No Pending Approvals
                            </p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                All signup requests have been processed.
                            </p>
                        </div>
                    ) : (
                        <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                            {pendingUsers.map((user) => (
                                <div
                                    key={user.id}
                                    className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                >
                                    <div className="flex items-center justify-between gap-4">
                                        <div className="flex items-center gap-4 flex-1 min-w-0">
                                            {/* Avatar */}
                                            <div className="w-11 h-11 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 flex items-center justify-center flex-shrink-0">
                                                <Users className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                                            </div>

                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                                        {user.username}
                                                    </h3>
                                                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700 border border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20 shrink-0">
                                                        Pending
                                                    </span>
                                                </div>
                                                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                                                    <span className="flex items-center gap-1.5">
                                                        <Mail className="w-3.5 h-3.5" />
                                                        {user.email}
                                                    </span>
                                                    <span className="flex items-center gap-1.5">
                                                        <Calendar className="w-3.5 h-3.5" />
                                                        {formatDate(user.created_at)}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* C9: Inline reject confirmation replaces window.confirm() */}
                                        <div className="flex gap-2 flex-shrink-0">
                                            <button
                                                onClick={() => handleApprove(user.id, user.username)}
                                                className="px-3 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                            >
                                                <CheckCircle className="w-3.5 h-3.5" />
                                                Approve
                                            </button>

                                            {confirmingReject === user.id ? (
                                                <div className="flex gap-1.5">
                                                    <button
                                                        onClick={() => handleReject(user.id, user.username)}
                                                        className="px-3 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors duration-150 shadow-sm"
                                                    >
                                                        Confirm
                                                    </button>
                                                    <button
                                                        onClick={() => setConfirmingReject(null)}
                                                        className="px-3 py-2 border border-gray-300 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors duration-150"
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    onClick={() => setConfirmingReject(user.id)}
                                                    className="px-3 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                >
                                                    <XCircle className="w-3.5 h-3.5" />
                                                    Reject
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── Approved Users Tab ───────────────────────────────────────── */}
            {activeTab === 'approved' && (
                <>
                    {/* C10: Search input writes to rawSearch; searchQuery is debounced */}
                    <div className="mb-5">
                        <div className="relative">
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                            <input
                                type="text"
                                placeholder="Search users by name or email…"
                                value={rawSearch}
                                onChange={(e) => setRawSearch(e.target.value)}
                                className="w-full pl-11 pr-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            />
                        </div>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                        {filteredApprovedUsers.length === 0 ? (
                            <div className="p-16 text-center">
                                <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                    <Users className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                </div>
                                <p className="text-gray-900 dark:text-white font-medium mb-1">
                                    {searchQuery ? 'No Users Found' : 'No Approved Users'}
                                </p>
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                    {searchQuery
                                        ? 'Try a different search term'
                                        : 'Approve pending users to get started'}
                                </p>
                            </div>
                        ) : (
                            <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                {filteredApprovedUsers.map((user) => (
                                    <div
                                        key={user.id}
                                        className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                    >
                                        <div className="flex items-center justify-between gap-4">
                                            <div className="flex items-center gap-4 flex-1 min-w-0">
                                                {/* Avatar */}
                                                <div className={`w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                                                    user.is_admin
                                                        ? 'bg-purple-100 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20'
                                                        : 'bg-blue-100 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20'
                                                }`}>
                                                    {user.is_admin ? (
                                                        <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                                    ) : (
                                                        <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                                    )}
                                                </div>

                                                <div className="flex-1 min-w-0">
                                                    <div className="flex flex-wrap items-center gap-2 mb-1">
                                                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                                            {user.username}
                                                        </h3>
                                                        {user.is_admin && (
                                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 border border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20 shrink-0">
                                                                <Shield className="w-3 h-3" />
                                                                Admin
                                                            </span>
                                                        )}
                                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border shrink-0 ${
                                                            user.is_active
                                                                ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                                : 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                                                        }`}>
                                                            {user.is_active ? 'Active' : 'Inactive'}
                                                        </span>
                                                    </div>
                                                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                                                        <span className="flex items-center gap-1.5">
                                                            <Mail className="w-3.5 h-3.5" />
                                                            {user.email}
                                                        </span>
                                                        <span className="flex items-center gap-1.5">
                                                            <Calendar className="w-3.5 h-3.5" />
                                                            Joined {formatDate(user.created_at)}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2 flex-shrink-0">
                                                {/* D6: Role dropdown — disabled for own account and while saving */}
                                                <div className="relative">
                                                    <select
                                                        value={user.role ?? 'observer'}
                                                        onChange={(e) =>
                                                            handleRoleChange(user.id, user.username, e.target.value)
                                                        }
                                                        disabled={
                                                            changingRole === user.id ||
                                                            user.id === currentUser?.id
                                                        }
                                                        className="appearance-none pl-3 pr-7 py-2 border border-gray-200 dark:border-[#1e2535] rounded-lg text-xs font-medium bg-white dark:bg-[#0f1117] text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150 cursor-pointer"
                                                        title="Change user role"
                                                    >
                                                        {ROLE_OPTIONS.map((opt) => (
                                                            <option key={opt.value} value={opt.value}>
                                                                {opt.label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    {changingRole === user.id ? (
                                                        <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 animate-spin text-blue-500 pointer-events-none" />
                                                    ) : (
                                                        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                                                    )}
                                                </div>

                                                <button
                                                    onClick={() => {
                                                        setSelectedUser(user);
                                                        setShowPasswordModal(true);
                                                    }}
                                                    className="px-3 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                >
                                                    <Key className="w-3.5 h-3.5" />
                                                    Password
                                                </button>

                                                {/* C9: Inline delete confirmation */}
                                                {confirmingDelete === user.id ? (
                                                    <div className="flex gap-1.5">
                                                        <button
                                                            onClick={() => handleDelete(user.id, user.username)}
                                                            className="px-3 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors duration-150 shadow-sm"
                                                        >
                                                            Confirm
                                                        </button>
                                                        <button
                                                            onClick={() => setConfirmingDelete(null)}
                                                            className="px-3 py-2 border border-gray-300 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors duration-150"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        onClick={() => setConfirmingDelete(user.id)}
                                                        disabled={user.id === currentUser?.id}
                                                        className="px-3 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                        title={user.id === currentUser?.id ? 'Cannot delete your own account' : ''}
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                        Delete
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </>
    );

    // C7: Standalone mode wraps content in the full-page shell.
    //     Embedded mode returns content directly without the outer layout.
    if (embedded) {
        return (
            <>
                {content}
                {/* C15: Password modal rendered outside the scrolling content area */}
                {showPasswordModal && selectedUser && (
                    <PasswordModal
                        selectedUser={selectedUser}
                        newPassword={newPassword}
                        confirmPassword={confirmPassword}
                        onNewPasswordChange={setNewPassword}
                        onConfirmPasswordChange={setConfirmPassword}
                        onSubmit={handleChangePassword}
                        onClose={closePasswordModal}
                        firstInputRef={modalFirstInputRef}
                    />
                )}
            </>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">
                {content}
            </div>

            {showPasswordModal && selectedUser && (
                <PasswordModal
                    selectedUser={selectedUser}
                    newPassword={newPassword}
                    confirmPassword={confirmPassword}
                    onNewPasswordChange={setNewPassword}
                    onConfirmPasswordChange={setConfirmPassword}
                    onSubmit={handleChangePassword}
                    onClose={closePasswordModal}
                    firstInputRef={modalFirstInputRef}
                />
            )}
        </div>
    );
}


// ── Password Change Modal (extracted for reuse between embedded/standalone) ──

interface PasswordModalProps {
    selectedUser: { username: string };
    newPassword: string;
    confirmPassword: string;
    onNewPasswordChange: (v: string) => void;
    onConfirmPasswordChange: (v: string) => void;
    onSubmit: () => void;
    onClose: () => void;
    firstInputRef: React.RefObject<HTMLInputElement>;
}

function PasswordModal({
    selectedUser,
    newPassword,
    confirmPassword,
    onNewPasswordChange,
    onConfirmPasswordChange,
    onSubmit,
    onClose,
    firstInputRef,
}: PasswordModalProps) {
    // C15: Close on Escape key; aria-modal + role="dialog" for screen readers.
    return (
        <div
            className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-modal-title"
            onKeyDown={(e) => {
                if (e.key === 'Escape') onClose();
            }}
        >
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-md w-full border border-gray-200 dark:border-[#1e2535]">

                {/* Modal header */}
                <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center">
                            <Key className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h3
                                id="password-modal-title"
                                className="text-base font-semibold text-gray-900 dark:text-white"
                            >
                                Change Password
                            </h3>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                for {selectedUser.username}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Modal body */}
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            New Password
                        </label>
                        {/* C15: ref for focus-on-open */}
                        <input
                            ref={firstInputRef}
                            type="password"
                            value={newPassword}
                            onChange={(e) => onNewPasswordChange(e.target.value)}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="Enter new password"
                            minLength={8}
                        />
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                            Minimum 8 characters
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Confirm Password
                        </label>
                        <input
                            type="password"
                            value={confirmPassword}
                            onChange={(e) => onConfirmPasswordChange(e.target.value)}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="Confirm new password"
                            minLength={8}
                        />
                    </div>

                    {newPassword && confirmPassword && newPassword !== confirmPassword && (
                        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 p-3 rounded-lg">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            Passwords do not match
                        </div>
                    )}
                </div>

                {/* Modal footer */}
                <div className="flex gap-3 px-6 pb-6">
                    <button
                        onClick={onClose}
                        className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onSubmit}
                        disabled={!newPassword || newPassword !== confirmPassword || newPassword.length < 8}
                        className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                    >
                        Change Password
                    </button>
                </div>
            </div>
        </div>
    );
}