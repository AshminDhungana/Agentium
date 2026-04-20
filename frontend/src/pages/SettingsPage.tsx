import { useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useForm } from 'react-hook-form';
import {
    Lock,
    Shield,
    Save,
    Eye,
    EyeOff,
    User,
    Key,
    CheckCircle2,
    AlertTriangle,
    Info,
    Users,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import UserManagement from './Usermanagement';
// C14: password strength logic extracted into a reusable hook
import { usePasswordStrength } from '@/hooks/usePasswordStrength';

interface PasswordFormData {
    currentPassword: string;
    newPassword: string;
    confirmPassword: string;
}

// C11: Human-readable labels for each RBAC role returned by the backend.
const ROLE_PERMISSION_LABELS: Record<string, string> = {
    primary_sovereign: 'Full Access',
    deputy_sovereign:  'Elevated Access',
    observer:          'Read Only',
    sovereign:         'Full Access',   // backdoor sovereign fallback
    admin:             'Full Access',   // legacy alias
    user:              'Standard',      // legacy alias
};

export function SettingsPage() {
    const { user, changePassword } = useAuthStore();
    const [activeTab, setActiveTab] = useState<'account' | 'users'>('account');

    // C8: individual show/hide states for all three password fields
    const [showCurrentPassword, setShowCurrentPassword] = useState(false);
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    const [isSubmitting, setIsSubmitting] = useState(false);

    // C5: pendingCount is now driven by a callback from UserManagement instead
    //     of a duplicate API call made here. Starts at 0; UserManagement sets
    //     it after its own initial fetch completes.
    const [pendingCount, setPendingCount] = useState(0);

    const {
        register,
        handleSubmit,
        watch,
        reset,
        formState: { errors },
    } = useForm<PasswordFormData>();

    const newPassword = watch('newPassword');

    // C14: Derived from the watched field — no extra state or effect needed.
    const {
        strength: passwordStrength,
        color: strengthColor,
        label: strengthLabel,
        textColor: strengthTextColor,
    } = usePasswordStrength(newPassword ?? '');

    // C11: Derive permission label from the actual role instead of hardcoding.
    const permissionLabel =
        ROLE_PERMISSION_LABELS[user?.role ?? ''] ?? 'Standard';

    // D3: last_login_at is now properly typed on the User interface in authStore.ts
    //     (no `as any` cast needed). Falls back to 'N/A' when the backend does not
    //     yet include the field in the verify/login response.
    const lastLoginDisplay = (() => {
        const raw = user?.last_login_at;
        if (!raw) return 'N/A';
        return new Date(raw).toLocaleDateString('en-US', {
            month: 'short',
            day:   'numeric',
            year:  'numeric',
        });
    })();

    const onSubmit = async (data: PasswordFormData) => {
        setIsSubmitting(true);
        try {
            const success = await changePassword(data.currentPassword, data.newPassword);
            if (success) {
                showToast.success('Password changed successfully');
                reset();
            } else {
                const currentError = useAuthStore.getState().error;
                showToast.error(currentError || 'Failed to change password');
            }
        } catch (error: any) {
            let message = 'Failed to change password';
            if (error?.response?.data?.detail) {
                message = Array.isArray(error.response.data.detail)
                    ? error.response.data.detail.map((e: any) => e.msg).join(', ')
                    : String(error.response.data.detail);
            }
            showToast.error(message);
        } finally {
            setIsSubmitting(false);
        }
    };

    /* ── Shared input class builder ── */
    const inputClass = (hasError: boolean) =>
        `w-full px-4 py-3 border rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 outline-none transition-all duration-150 ${
            hasError
                ? 'border-red-300 dark:border-red-500/50 focus:ring-2 focus:ring-red-500/30 focus:border-red-500'
                : 'border-gray-300 dark:border-[#1e2535] focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 dark:focus:border-blue-500/70'
        }`;

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ─────────────────────────────────────────── */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        Settings
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Manage your account and system preferences.
                    </p>
                </div>

                {/* ── Tabs ─────────────────────────────────────────────────── */}
                <div className="flex gap-2 mb-6">
                    <button
                        onClick={() => setActiveTab('account')}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 ${
                            activeTab === 'account'
                                ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
                                : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:text-gray-900 dark:hover:text-gray-200'
                        }`}
                    >
                        <User className="w-4 h-4" />
                        Account Settings
                    </button>

                    {user?.is_admin && (
                        <button
                            onClick={() => setActiveTab('users')}
                            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 ${
                                activeTab === 'users'
                                    ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
                                    : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:text-gray-900 dark:hover:text-gray-200'
                            }`}
                        >
                            <Users className="w-4 h-4" />
                            User Management
                            {pendingCount > 0 && (
                                <span className={`px-1.5 py-0.5 rounded-full text-xs font-bold leading-none ${
                                    activeTab === 'users'
                                        ? 'bg-white/20 text-white'
                                        : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400'
                                }`}>
                                    {pendingCount}
                                </span>
                            )}
                        </button>
                    )}
                </div>

                {/* ── Account Settings Tab ─────────────────────────────────── */}
                {/* C6: Both tab panels are kept mounted; visibility is toggled  */}
                {/*     with Tailwind's `hidden` class so UserManagement never   */}
                {/*     re-mounts (and re-fetches) when switching tabs.           */}
                <div className={activeTab === 'account' ? 'block' : 'hidden'}>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                        {/* Sidebar */}
                        <div className="lg:col-span-1 space-y-5">

                            {/* Account Card */}
                            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                                <div className="flex flex-col items-center text-center">
                                    {/* Avatar */}
                                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center mb-4 shadow-lg">
                                        <User className="w-10 h-10 text-white" />
                                    </div>

                                    {/* User Info */}
                                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                                        {user?.username}
                                    </h2>
                                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20">
                                        <Shield className="w-3 h-3" />
                                        {user?.role}
                                    </span>

                                    {/* Account status */}
                                    <div className="w-full mt-6 pt-5 border-t border-gray-100 dark:border-[#1e2535]">
                                        <div className="flex items-center justify-between text-sm mb-3">
                                            <span className="text-gray-500 dark:text-gray-400">Account Status</span>
                                            <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 font-medium text-xs">
                                                <CheckCircle2 className="w-3.5 h-3.5" />
                                                Active
                                            </span>
                                        </div>
                                        {/* D3: last_login_at is now typed — no `as any` cast */}
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-gray-500 dark:text-gray-400">Last Login</span>
                                            <span className="text-gray-900 dark:text-gray-100 font-medium text-xs">
                                                {lastLoginDisplay}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Account Info */}
                            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                    <Info className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                                    Account Info
                                </h3>
                                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                    <div className="flex items-center justify-between py-2.5">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">User ID</span>
                                        <span className="text-xs font-mono text-gray-900 dark:text-gray-100">
                                            #{user?.id || '—'}
                                        </span>
                                    </div>
                                    {/* C11: Derived from actual role instead of hardcoded "Full Access" */}
                                    <div className="flex items-center justify-between py-2.5">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">Permissions</span>
                                        <span className="text-xs text-gray-900 dark:text-gray-100">
                                            {permissionLabel}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between py-2.5">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">2FA Status</span>
                                        <span className="text-xs text-gray-400 dark:text-gray-500">Not Enabled</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Main content — Password change */}
                        <div className="lg:col-span-2">
                            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">

                                {/* Card header */}
                                <div className="bg-gray-50 dark:bg-[#0f1117] border-b border-gray-200 dark:border-[#1e2535] px-6 py-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 flex items-center justify-center">
                                            <Key className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                        </div>
                                        <div>
                                            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                                Change Password
                                            </h2>
                                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                                Update your security credentials
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Form */}
                                <form onSubmit={handleSubmit(onSubmit)} className="p-6">
                                    <div className="space-y-5">

                                        {/* Current Password */}
                                        <div>
                                            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                                Current Password
                                            </label>
                                            <div className="relative">
                                                <input
                                                    type={showCurrentPassword ? 'text' : 'password'}
                                                    {...register('currentPassword', {
                                                        required: 'Current password is required',
                                                    })}
                                                    className={`${inputClass(!!errors.currentPassword)} pr-11`}
                                                    placeholder="Enter current password"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150"
                                                    aria-label={showCurrentPassword ? 'Hide password' : 'Show password'}
                                                >
                                                    {showCurrentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                </button>
                                            </div>
                                            {errors.currentPassword && (
                                                <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                                                    {errors.currentPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Divider */}
                                        <div className="relative py-1">
                                            <div className="absolute inset-0 flex items-center">
                                                <div className="w-full border-t border-gray-200 dark:border-[#1e2535]" />
                                            </div>
                                            <div className="relative flex justify-center">
                                                <span className="px-3 bg-white dark:bg-[#161b27] text-xs text-gray-400 dark:text-gray-500">
                                                    New Password
                                                </span>
                                            </div>
                                        </div>

                                        {/* New Password */}
                                        <div>
                                            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                                New Password
                                            </label>
                                            <div className="relative">
                                                <input
                                                    type={showNewPassword ? 'text' : 'password'}
                                                    {...register('newPassword', {
                                                        required: 'New password is required',
                                                        minLength: {
                                                            value: 8,
                                                            message: 'Password must be at least 8 characters',
                                                        },
                                                    })}
                                                    className={`${inputClass(!!errors.newPassword)} pr-11`}
                                                    placeholder="Enter new password"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => setShowNewPassword(!showNewPassword)}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150"
                                                    aria-label={showNewPassword ? 'Hide password' : 'Show password'}
                                                >
                                                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                </button>
                                            </div>

                                            {/* C14: Password Strength Indicator */}
                                            {newPassword && (
                                                <div className="mt-2.5 space-y-1.5">
                                                    <div className="flex items-center justify-between text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">Password Strength</span>
                                                        <span className={`font-semibold ${strengthTextColor}`}>
                                                            {strengthLabel}
                                                        </span>
                                                    </div>
                                                    <div className="h-1.5 bg-gray-200 dark:bg-[#1e2535] rounded-full overflow-hidden">
                                                        <div
                                                            className={`h-full ${strengthColor} transition-all duration-300 rounded-full`}
                                                            style={{ width: `${passwordStrength}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                            {errors.newPassword && (
                                                <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                                                    {errors.newPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Confirm Password */}
                                        <div>
                                            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                                Confirm New Password
                                            </label>
                                            <div className="relative">
                                                <input
                                                    type={showConfirmPassword ? 'text' : 'password'}
                                                    {...register('confirmPassword', {
                                                        required: 'Please confirm your password',
                                                        validate: (value) =>
                                                            value === newPassword || 'Passwords do not match',
                                                    })}
                                                    className={`${inputClass(!!errors.confirmPassword)} pr-11`}
                                                    placeholder="Confirm new password"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors duration-150"
                                                    aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                                                >
                                                    {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                </button>
                                            </div>
                                            {errors.confirmPassword && (
                                                <p className="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                                                    {errors.confirmPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Action Buttons */}
                                        <div className="flex items-center gap-3 pt-2">
                                            <button
                                                type="submit"
                                                disabled={isSubmitting}
                                                className="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors duration-150 shadow-sm"
                                            >
                                                {isSubmitting ? (
                                                    <>
                                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        Updating…
                                                    </>
                                                ) : (
                                                    <>
                                                        <Save className="w-4 h-4" />
                                                        Update Password
                                                    </>
                                                )}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => reset()}
                                                className="px-6 py-2.5 border border-gray-300 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-[#0f1117] hover:border-gray-400 dark:hover:border-[#2a3347] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg transition-all duration-150"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    </div>
                                </form>
                            </div>

                            {/* Security Notice */}
                            <div className="mt-5 p-4 bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl flex gap-3 transition-colors duration-200">
                                <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <Shield className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-yellow-900 dark:text-yellow-300 mb-1">
                                        Sovereign Security
                                    </h3>
                                    <p className="text-sm text-yellow-800 dark:text-yellow-400/80 leading-relaxed">
                                        Your credentials protect the entire Agentium governance system. Use a strong, unique password and store it securely.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── User Management Tab ─────────────────────────────────── */}
                {/* C6: Always mounted when user is admin so switching back to  */}
                {/*     this tab does not trigger a full remount + refetch.      */}
                {/* C7: embedded prop strips the standalone page wrapper so     */}
                {/*     UserManagement fits inside the settings layout.          */}
                {/* C5: onPendingCountChange callback keeps the tab badge count  */}
                {/*     in sync without a duplicate /pending API call here.      */}
                {user?.is_admin && (
                    <div className={activeTab === 'users' ? 'block' : 'hidden'}>
                        <UserManagement
                            embedded
                            onPendingCountChange={setPendingCount}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}