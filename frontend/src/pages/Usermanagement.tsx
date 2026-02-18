import { useState, useEffect } from 'react';
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
} from 'lucide-react';
import { api } from '@/services/api';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

interface User {
    id: number;
    username: string;
    email: string;
    is_active: boolean;
    is_admin: boolean;
    is_pending: boolean;
    created_at?: string;
    updated_at?: string;
}

interface UserListResponse {
    users: User[];
    total: number;
}

export default function UserManagement() {
    const { user: currentUser } = useAuthStore();
    const [pendingUsers, setPendingUsers] = useState<User[]>([]);
    const [approvedUsers, setApprovedUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'pending' | 'approved'>('pending');
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [selectedUser, setSelectedUser] = useState<User | null>(null);
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [searchQuery, setSearchQuery] = useState('');

    useEffect(() => {
        fetchUsers();
    }, []);

    /* ── Access denied ── */
    if (!currentUser?.is_admin) {
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
            setPendingUsers(pendingRes.data.users || []);
            setApprovedUsers(approvedRes.data.users || []);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to fetch users');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (userId: number, username: string) => {
        try {
            await api.post(`/api/v1/admin/users/${userId}/approve`);
            toast.success(`${username} approved successfully`, { icon: '✅', duration: 3000 });
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to approve user');
        }
    };

    const handleReject = async (userId: number, username: string) => {
        if (!confirm(`Are you sure you want to reject ${username}'s signup request?`)) return;
        try {
            await api.post(`/api/v1/admin/users/${userId}/reject`);
            toast.success(`${username}'s request rejected`, { icon: '❌', duration: 3000 });
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to reject user');
        }
    };

    const handleDelete = async (userId: number, username: string) => {
        if (!confirm(`Delete user "${username}"? This action cannot be undone.`)) return;
        if (userId === currentUser.id) {
            toast.error('You cannot delete your own account');
            return;
        }
        try {
            await api.delete(`/api/v1/admin/users/${userId}`);
            toast.success(`${username} deleted successfully`);
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to delete user');
        }
    };

    const handleChangePassword = async () => {
        if (!selectedUser || !newPassword) return;
        if (newPassword !== confirmPassword) { toast.error('Passwords do not match'); return; }
        if (newPassword.length < 8) { toast.error('Password must be at least 8 characters'); return; }
        try {
            await api.post(`/api/v1/admin/users/${selectedUser.id}/change-password`, {
                new_password: newPassword,
            });
            toast.success(`Password changed for ${selectedUser.username}`, { icon: '🔐', duration: 3000 });
            setShowPasswordModal(false);
            setSelectedUser(null);
            setNewPassword('');
            setConfirmPassword('');
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to change password');
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
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center transition-colors duration-200">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading users…</span>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ──────────────────────────────────────────── */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        User Management
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage user approvals and permissions.
                    </p>
                </div>

                {/* ── Stats Cards ──────────────────────────────────────────── */}
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

                {/* ── Tabs ────────────────────────────────────────────────── */}
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

                {/* ── Pending Users Tab ────────────────────────────────────── */}
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

                                            <div className="flex gap-2 flex-shrink-0">
                                                <button
                                                    onClick={() => handleApprove(user.id, user.username)}
                                                    className="px-3 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                >
                                                    <CheckCircle className="w-3.5 h-3.5" />
                                                    Approve
                                                </button>
                                                <button
                                                    onClick={() => handleReject(user.id, user.username)}
                                                    className="px-3 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                >
                                                    <XCircle className="w-3.5 h-3.5" />
                                                    Reject
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Approved Users Tab ───────────────────────────────────── */}
                {activeTab === 'approved' && (
                    <>
                        {/* Search bar */}
                        <div className="mb-5">
                            <div className="relative">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                                <input
                                    type="text"
                                    placeholder="Search users by name or email…"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
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
                                                            <Shield className={`w-5 h-5 text-purple-600 dark:text-purple-400`} />
                                                        ) : (
                                                            <Users className={`w-5 h-5 text-blue-600 dark:text-blue-400`} />
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

                                                <div className="flex gap-2 flex-shrink-0">
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
                                                    <button
                                                        onClick={() => handleDelete(user.id, user.username)}
                                                        disabled={user.id === currentUser.id}
                                                        className="px-3 py-2 bg-red-600 hover:bg-red-700 dark:hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                        title={user.id === currentUser.id ? 'Cannot delete your own account' : ''}
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                        Delete
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>

            {/* ── Password Change Modal ─────────────────────────────────── */}
            {showPasswordModal && selectedUser && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-md w-full border border-gray-200 dark:border-[#1e2535]">

                        {/* Modal header */}
                        <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center">
                                    <Key className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
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
                                <input
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
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
                                    onChange={(e) => setConfirmPassword(e.target.value)}
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
                                onClick={closePasswordModal}
                                className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleChangePassword}
                                disabled={!newPassword || newPassword !== confirmPassword || newPassword.length < 8}
                                className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                            >
                                Change Password
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
