import { useState, useRef, useEffect } from 'react';
import {
    Users,
    CheckCircle,
    XCircle,
    Trash2,
    Key,
    Shield,
    Clock,
    UserCheck,
    Mail,
    Calendar,
    AlertCircle,
    Search,
    ChevronDown,
    RefreshCw,
    CheckCircle2,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { useAuthStore } from '@/store/authStore';
import { useUserManagement, ROLE_OPTIONS, type User } from '@/hooks/useUserManagement';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Props ─────────────────────────────────────────────────────────────────────

interface UserManagementProps {
    /** Strip the full-page wrapper so the component fits inside a parent layout. */
    embedded?: boolean;
    /** Notify parent of the current pending count to update a tab badge. */
    onPendingCountChange?: (count: number) => void;
}

// ── Main component ────────────────────────────────────────────────────────────

export default function UserManagement({
    embedded = false,
    onPendingCountChange,
}: UserManagementProps) {
    const { user: currentUser } = useAuthStore();
    const [activeTab, setActiveTab] = useState<'pending' | 'approved'>('pending');

    // Password modal local state — open/selected/passwords live here because
    // they are purely UI concerns; the submit action is delegated to the hook.
    const [showPasswordModal,  setShowPasswordModal]  = useState(false);
    const [selectedUser,       setSelectedUser]       = useState<User | null>(null);
    const [newPassword,        setNewPassword]        = useState('');
    const [confirmPassword,    setConfirmPassword]    = useState('');
    const modalFirstInputRef = useRef<HTMLInputElement>(null);

    // ── Data / actions from hook ──────────────────────────────────────────────
    const {
        pendingUsers,
        filteredApprovedUsers,
        approvedUsers,
        loading,
        error,
        changingRole,
        isChangingPassword,
        roleChangeSuccess,
        confirmingReject,
        confirmingDelete,
        rawSearch,
        searchQuery,
        setRawSearch,
        clearSearch,
        fetchUsers,
        handleApprove,
        handleReject,
        handleDelete,
        handleRoleChange,
        handleChangePassword,
        toggleConfirmReject,
        toggleConfirmDelete,
    } = useUserManagement(onPendingCountChange);

    // Focus first input when modal opens
    useEffect(() => {
        if (showPasswordModal) {
            const id = setTimeout(() => modalFirstInputRef.current?.focus(), 50);
            return () => clearTimeout(id);
        }
    }, [showPasswordModal]);

    // ── Guards ────────────────────────────────────────────────────────────────

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

    if (loading) {
        return (
            <div className="flex items-center justify-center py-24">
                <div className="flex flex-col items-center gap-3">
                    <LoadingSpinner size="lg" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading users…</span>
                </div>
            </div>
        );
    }

    // Error state with retry — shown after initial load fails
    if (error && !loading && pendingUsers.length === 0 && approvedUsers.length === 0) {
        return (
            <div className="flex items-center justify-center py-16">
                <div className="text-center">
                    <div className="w-14 h-14 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mx-auto mb-4">
                        <AlertCircle className="w-7 h-7 text-red-500 dark:text-red-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                        Failed to load users
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 max-w-xs">
                        {error}
                    </p>
                    <button
                        onClick={fetchUsers}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Try Again
                    </button>
                </div>
            </div>
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    const formatDate = (dateString?: string) => {
        if (!dateString) return 'N/A';
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    };

    const openPasswordModal = (user: User) => {
        setSelectedUser(user);
        setNewPassword('');
        setConfirmPassword('');
        setShowPasswordModal(true);
    };

    const closePasswordModal = () => {
        setShowPasswordModal(false);
        setSelectedUser(null);
        setNewPassword('');
        setConfirmPassword('');
    };

    const onPasswordSubmit = async () => {
        if (!selectedUser) return;
        const ok = await handleChangePassword(selectedUser.id, selectedUser.username, newPassword);
        if (ok) closePasswordModal();
    };

    // ── Shared content (embedded + standalone) ─────────────────────────────────

    const content = (
        <>
            {/* Header — standalone only */}
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

            {/* ── Stats Cards ─────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <StatCard
                    icon={<Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />}
                    iconBg="bg-yellow-100 dark:bg-yellow-500/10"
                    value={pendingUsers.length}
                    label="Pending Approvals"
                />
                <StatCard
                    icon={<UserCheck className="w-5 h-5 text-green-600 dark:text-green-400" />}
                    iconBg="bg-green-100 dark:bg-green-500/10"
                    value={approvedUsers.filter(u => u.is_active).length}
                    label="Active Users"
                />
                <StatCard
                    icon={<Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />}
                    iconBg="bg-blue-100 dark:bg-blue-500/10"
                    value={approvedUsers.length}
                    label="Total Users"
                />
            </div>

            {/* ── Tabs ────────────────────────────────────────────────────── */}
            <div className="flex gap-2 mb-6">
                <TabButton
                    active={activeTab === 'pending'}
                    onClick={() => setActiveTab('pending')}
                    icon={<Clock className="w-4 h-4" />}
                    label="Pending Approvals"
                    badge={pendingUsers.length > 0 ? pendingUsers.length : undefined}
                    isActiveTab={activeTab === 'pending'}
                />
                <TabButton
                    active={activeTab === 'approved'}
                    onClick={() => setActiveTab('approved')}
                    icon={<UserCheck className="w-4 h-4" />}
                    label="Approved Users"
                />
            </div>

            {/* ── Pending tab ─────────────────────────────────────────────── */}
            {activeTab === 'pending' && (
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden">
                    {pendingUsers.length === 0 ? (
                        <EmptyState
                            icon={<Clock className="w-6 h-6 text-gray-400 dark:text-gray-500" />}
                            title="No Pending Approvals"
                            description="All signup requests have been processed."
                        />
                    ) : (
                        <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                            {pendingUsers.map((user) => (
                                <div
                                    key={user.id}
                                    className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                >
                                    <div className="flex items-center justify-between gap-4">
                                        <UserInfo user={user} formatDate={formatDate} pending />

                                        <div className="flex gap-2 flex-shrink-0">
                                            <button
                                                onClick={() => handleApprove(user.id, user.username)}
                                                className="px-3 py-2 bg-green-600 hover:bg-green-700 dark:hover:bg-green-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                            >
                                                <CheckCircle className="w-3.5 h-3.5" />
                                                Approve
                                            </button>

                                            {confirmingReject.has(user.id) ? (
                                                <div className="flex gap-1.5">
                                                    <button
                                                        onClick={() => handleReject(user.id, user.username)}
                                                        className="px-3 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors duration-150 shadow-sm"
                                                    >
                                                        Confirm
                                                    </button>
                                                    <button
                                                        onClick={() => toggleConfirmReject(user.id)}
                                                        className="px-3 py-2 border border-gray-300 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors duration-150"
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    onClick={() => toggleConfirmReject(user.id)}
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

            {/* ── Approved tab ────────────────────────────────────────────── */}
            {activeTab === 'approved' && (
                <>
                    {/* Search bar with clear button */}
                    <div className="mb-5">
                        <div className="relative">
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
                            <input
                                type="text"
                                placeholder="Search users by name or email…"
                                value={rawSearch}
                                onChange={(e) => setRawSearch(e.target.value)}
                                className="w-full pl-11 pr-10 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            />
                            {rawSearch && (
                                <button
                                    onClick={clearSearch}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                                    aria-label="Clear search"
                                >
                                    <XCircle className="w-4 h-4" />
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden">
                        {filteredApprovedUsers.length === 0 ? (
                            <EmptyState
                                icon={<Users className="w-6 h-6 text-gray-400 dark:text-gray-500" />}
                                title={searchQuery ? 'No Users Found' : 'No Approved Users'}
                                description={
                                    searchQuery
                                        ? 'Try a different search term'
                                        : 'Approve pending users to get started'
                                }
                                action={
                                    searchQuery
                                        ? <button
                                            onClick={clearSearch}
                                            className="mt-3 text-sm text-blue-600 dark:text-blue-400 hover:underline"
                                          >
                                              Clear search
                                          </button>
                                        : undefined
                                }
                            />
                        ) : (
                            <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                {filteredApprovedUsers.map((user) => (
                                    <div
                                        key={user.id}
                                        className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                    >
                                        <div className="flex items-center justify-between gap-4">
                                            <UserInfo user={user} formatDate={formatDate} />

                                            <div className="flex items-center gap-2 flex-shrink-0">
                                                {/* Role dropdown with optimistic update + success indicator */}
                                                <div className="flex items-center gap-1.5">
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
                                                            aria-label={`Role for ${user.username}`}
                                                        >
                                                            {ROLE_OPTIONS.map((opt) => (
                                                                <option key={opt.value} value={opt.value}>
                                                                    {opt.label}
                                                                </option>
                                                            ))}
                                                        </select>
                                                        {changingRole === user.id ? (
                                                            <LoadingSpinner size="xs" />
                                                        ) : (
                                                            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
                                                        )}
                                                    </div>
                                                    {/* 2 s success checkmark after role change */}
                                                    {roleChangeSuccess === user.id && (
                                                        <CheckCircle2
                                                            className="w-4 h-4 text-green-500 flex-shrink-0"
                                                            aria-label="Role updated"
                                                        />
                                                    )}
                                                </div>

                                                <button
                                                    onClick={() => openPasswordModal(user)}
                                                    className="px-3 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors duration-150 shadow-sm"
                                                >
                                                    <Key className="w-3.5 h-3.5" />
                                                    Password
                                                </button>

                                                {/* Inline delete confirmation */}
                                                {confirmingDelete.has(user.id) ? (
                                                    <div className="flex gap-1.5">
                                                        <button
                                                            onClick={() => handleDelete(user.id, user.username)}
                                                            className="px-3 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors duration-150 shadow-sm"
                                                        >
                                                            Confirm
                                                        </button>
                                                        <button
                                                            onClick={() => toggleConfirmDelete(user.id)}
                                                            className="px-3 py-2 border border-gray-300 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors duration-150"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        onClick={() => toggleConfirmDelete(user.id)}
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

    // Render mode
    if (embedded) {
        return (
            <>
                {content}
                {showPasswordModal && selectedUser && (
                    <PasswordModal
                        selectedUser={selectedUser}
                        newPassword={newPassword}
                        confirmPassword={confirmPassword}
                        isSubmitting={isChangingPassword}
                        onNewPasswordChange={setNewPassword}
                        onConfirmPasswordChange={setConfirmPassword}
                        onSubmit={onPasswordSubmit}
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
                    isSubmitting={isChangingPassword}
                    onNewPasswordChange={setNewPassword}
                    onConfirmPasswordChange={setConfirmPassword}
                    onSubmit={onPasswordSubmit}
                    onClose={closePasswordModal}
                    firstInputRef={modalFirstInputRef}
                />
            )}
        </div>
    );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
    icon, iconBg, value, label,
}: {
    icon: React.ReactNode;
    iconBg: string;
    value: number;
    label: string;
}) {
    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
            <div className="flex items-center justify-between mb-4">
                <div className={`w-11 h-11 rounded-lg flex items-center justify-center ${iconBg}`}>
                    {icon}
                </div>
                <span className="text-2xl font-bold text-gray-900 dark:text-white">{value}</span>
            </div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</p>
        </div>
    );
}

function TabButton({
    active, onClick, icon, label, badge, isActiveTab,
}: {
    active: boolean;
    onClick: () => void;
    icon: React.ReactNode;
    label: string;
    badge?: number;
    isActiveTab?: boolean;
}) {
    return (
        <button
            onClick={onClick}
            className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                active
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
            }`}
        >
            {icon}
            {label}
            {badge !== undefined && (
                <span className={`px-1.5 py-0.5 rounded-full text-xs font-bold ${
                    isActiveTab
                        ? 'bg-white/20 text-white'
                        : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400'
                }`}>
                    {badge}
                </span>
            )}
        </button>
    );
}

function UserInfo({
    user, formatDate, pending = false,
}: {
    user: User;
    formatDate: (d?: string) => string;
    pending?: boolean;
}) {
    return (
        <div className="flex items-center gap-4 flex-1 min-w-0">
            <div className={`w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0 border ${
                pending
                    ? 'bg-yellow-100 dark:bg-yellow-500/10 border-yellow-200 dark:border-yellow-500/20'
                    : user.is_admin
                        ? 'bg-purple-100 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20'
                        : 'bg-blue-100 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20'
            }`}>
                {user.is_admin && !pending ? (
                    <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                ) : (
                    <Users className={`w-5 h-5 ${
                        pending
                            ? 'text-yellow-600 dark:text-yellow-400'
                            : 'text-blue-600 dark:text-blue-400'
                    }`} />
                )}
            </div>

            <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                        {user.username}
                    </h3>
                    {pending && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700 border border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20 shrink-0">
                            Pending
                        </span>
                    )}
                    {!pending && user.is_admin && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 border border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20 shrink-0">
                            <Shield className="w-3 h-3" />
                            Admin
                        </span>
                    )}
                    {!pending && (
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border shrink-0 ${
                            user.is_active
                                ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                : 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]'
                        }`}>
                            {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                    )}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <span className="flex items-center gap-1.5">
                        <Mail className="w-3.5 h-3.5" />
                        {user.email}
                    </span>
                    <span className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        {pending ? formatDate(user.created_at) : `Joined ${formatDate(user.created_at)}`}
                    </span>
                </div>
            </div>
        </div>
    );
}

function EmptyState({
    icon, title, description, action,
}: {
    icon: React.ReactNode;
    title: string;
    description: string;
    action?: React.ReactNode;
}) {
    return (
        <div className="p-16 text-center">
            <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                {icon}
            </div>
            <p className="text-gray-900 dark:text-white font-medium mb-1">{title}</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
            {action}
        </div>
    );
}

// ── Password Modal ─────────────────────────────────────────────────────────────

interface PasswordModalProps {
    selectedUser: Pick<User, 'id' | 'username'>;
    newPassword: string;
    confirmPassword: string;
    isSubmitting: boolean;
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
    isSubmitting,
    onNewPasswordChange,
    onConfirmPasswordChange,
    onSubmit,
    onClose,
    firstInputRef,
}: PasswordModalProps) {
    const canSubmit =
        !!newPassword &&
        newPassword === confirmPassword &&
        newPassword.length >= 8 &&
        !isSubmitting;

    return (
        <div
            className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-modal-title"
            onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
        >
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-md w-full border border-gray-200 dark:border-[#1e2535]">

                {/* Header with close button */}
                <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                    <div className="flex items-center justify-between">
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
                        {/* Explicit close button with aria-label for screen readers */}
                        <button
                            onClick={onClose}
                            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors rounded-lg p-1 hover:bg-gray-100 dark:hover:bg-[#1e2535]"
                            aria-label="Close password change dialog"
                        >
                            <XCircle className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            New Password
                        </label>
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

                {/* Footer */}
                <div className="flex gap-3 px-6 pb-6">
                    <button
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] disabled:opacity-40 transition-all duration-150"
                    >
                        Cancel
                    </button>
                    {/* Submit button with loading state to prevent duplicate submissions */}
                    <button
                        onClick={onSubmit}
                        disabled={!canSubmit}
                        className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center justify-center gap-2"
                    >
                        {isSubmitting ? (
                            <>
                                <LoadingSpinner size="sm" />
                                Updating…
                            </>
                        ) : (
                            'Change Password'
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}