import { useState, useEffect } from 'react';
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
    Settings as SettingsIcon
} from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '@/services/api';
import UserManagement from './Usermanagement';

interface PasswordFormData {
    currentPassword: string;
    newPassword: string;
    confirmPassword: string;
}

export function SettingsPage() {
    const { user, changePassword } = useAuthStore();
    const [activeTab, setActiveTab] = useState<'account' | 'users'>('account');
    const [showCurrentPassword, setShowCurrentPassword] = useState(false);
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [passwordStrength, setPasswordStrength] = useState(0);
    const [pendingCount, setPendingCount] = useState(0);

    const {
        register,
        handleSubmit,
        watch,
        reset,
        formState: { errors }
    } = useForm<PasswordFormData>();

    const newPassword = watch('newPassword');

    // Fetch pending users count for badge
    useEffect(() => {
        if (user?.is_admin) {
            fetchPendingCount();
        }
    }, [user?.is_admin]);

    const fetchPendingCount = async () => {
        try {
            const response = await api.get('/api/v1/admin/users/pending');
            setPendingCount(response.data.users?.length || 0);
        } catch (error) {
            console.error('Failed to fetch pending count:', error);
        }
    };

    // Calculate password strength
    const calculatePasswordStrength = (password: string) => {
        if (!password) return 0;
        let strength = 0;
        if (password.length >= 8) strength += 25;
        if (password.length >= 12) strength += 25;
        if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength += 25;
        if (/\d/.test(password)) strength += 12.5;
        if (/[^a-zA-Z0-9]/.test(password)) strength += 12.5;
        return Math.min(strength, 100);
    };

    // Watch password changes for strength indicator
    useEffect(() => {
        if (newPassword) {
            setPasswordStrength(calculatePasswordStrength(newPassword));
        } else {
            setPasswordStrength(0);
        }
    }, [newPassword]);

    const onSubmit = async (data: PasswordFormData) => {
        setIsSubmitting(true);

        try {
            const success = await changePassword(data.currentPassword, data.newPassword);

            if (success) {
                toast.success('Password changed successfully', {
                    icon: '🔒',
                    duration: 3000
                });
                reset();
                setPasswordStrength(0);
            } else {
                // Get error from store - it should now be a string
                const currentError = useAuthStore.getState().error;
                toast.error(currentError || 'Failed to change password');
            }
        } catch (error: any) {
            // This shouldn't happen now, but just in case
            let message = 'Failed to change password';
            if (error?.response?.data?.detail) {
                if (Array.isArray(error.response.data.detail)) {
                    message = error.response.data.detail.map((e: any) => e.msg).join(', ');
                } else {
                    message = String(error.response.data.detail);
                }
            }
            toast.error(message);
        } finally {
            setIsSubmitting(false);
        }
    };

    const getPasswordStrengthColor = () => {
        if (passwordStrength < 40) return 'bg-red-500';
        if (passwordStrength < 70) return 'bg-yellow-500';
        return 'bg-green-500';
    };

    const getPasswordStrengthLabel = () => {
        if (passwordStrength < 40) return 'Weak';
        if (passwordStrength < 70) return 'Moderate';
        return 'Strong';
    };

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center shadow-lg">
                            <SettingsIcon className="w-7 h-7 text-white" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                                Settings
                            </h1>
                            <p className="text-gray-600 dark:text-gray-400 text-sm">
                                Manage your account and system preferences
                            </p>
                        </div>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex gap-2 mb-6">
                    <button
                        onClick={() => setActiveTab('account')}
                        className={`px-6 py-3 rounded-lg font-semibold transition-all ${
                            activeTab === 'account'
                                ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                        }`}
                    >
                        <div className="flex items-center gap-2">
                            <User className="w-5 h-5" />
                            Account Settings
                        </div>
                    </button>
                    
                    {user?.is_admin && (
                        <button
                            onClick={() => setActiveTab('users')}
                            className={`px-6 py-3 rounded-lg font-semibold transition-all ${
                                activeTab === 'users'
                                    ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg'
                                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                            }`}
                        >
                            <div className="flex items-center gap-2">
                                <Users className="w-5 h-5" />
                                User Management
                                {pendingCount > 0 && (
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                        activeTab === 'users' 
                                            ? 'bg-white/20 text-white' 
                                            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                    }`}>
                                        {pendingCount}
                                    </span>
                                )}
                            </div>
                        </button>
                    )}
                </div>

                {/* Account Settings Tab */}
                {activeTab === 'account' && (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Sidebar - Account Overview */}
                        <div className="lg:col-span-1 space-y-6">
                            {/* Account Card */}
                            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
                                <div className="flex flex-col items-center text-center">
                                    {/* Avatar */}
                                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center mb-4 shadow-lg">
                                        <User className="w-10 h-10 text-white" />
                                    </div>
                                    
                                    {/* User Info */}
                                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-1">
                                        {user?.username}
                                    </h2>
                                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                                        <Shield className="w-3 h-3" />
                                        {user?.role}
                                    </span>

                                    {/* Account Status */}
                                    <div className="w-full mt-6 pt-6 border-t border-gray-100 dark:border-gray-700">
                                        <div className="flex items-center justify-between text-sm mb-2">
                                            <span className="text-gray-600 dark:text-gray-400">Account Status</span>
                                            <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400 font-medium">
                                                <CheckCircle2 className="w-4 h-4" />
                                                Active
                                            </span>
                                        </div>
                                        <div className="flex items-center justify-between text-sm">
                                            <span className="text-gray-600 dark:text-gray-400">Last Login</span>
                                            <span className="text-gray-900 dark:text-white font-medium">
                                                Today
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Quick Stats */}
                            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
                                <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                    <Info className="w-4 h-4 text-gray-400" />
                                    Account Info
                                </h3>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">User ID</span>
                                        <span className="text-xs font-mono text-gray-900 dark:text-white">
                                            #{user?.id || '00001'}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">Permissions</span>
                                        <span className="text-xs text-gray-900 dark:text-white">Full Access</span>
                                    </div>
                                    <div className="flex items-center justify-between py-2">
                                        <span className="text-xs text-gray-500 dark:text-gray-400">2FA Status</span>
                                        <span className="text-xs text-gray-500 dark:text-gray-400">Not Enabled</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Main Content - Password Change */}
                        <div className="lg:col-span-2">
                            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                                {/* Card Header */}
                                <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-gray-800 dark:to-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-5">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 flex items-center justify-center shadow-sm">
                                            <Key className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                        </div>
                                        <div>
                                            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                                                Change Password
                                            </h2>
                                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                                Update your security credentials
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Form Content */}
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
                                                        required: 'Current password is required' 
                                                    })}
                                                    className={`w-full px-4 py-3 pr-11 border rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white transition-all ${
                                                        errors.currentPassword
                                                            ? 'border-red-300 dark:border-red-700 focus:ring-red-500 focus:border-red-500'
                                                            : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                                                    }`}
                                                    placeholder="Enter current password"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                                                >
                                                    {showCurrentPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                                </button>
                                            </div>
                                            {errors.currentPassword && (
                                                <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5" />
                                                    {errors.currentPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Divider */}
                                        <div className="relative py-2">
                                            <div className="absolute inset-0 flex items-center">
                                                <div className="w-full border-t border-gray-200 dark:border-gray-700"></div>
                                            </div>
                                            <div className="relative flex justify-center text-xs">
                                                <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
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
                                                            message: 'Password must be at least 6 characters'
                                                        }
                                                    })}
                                                    className={`w-full px-4 py-3 pr-11 border rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white transition-all ${
                                                        errors.newPassword
                                                            ? 'border-red-300 dark:border-red-700 focus:ring-red-500 focus:border-red-500'
                                                            : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                                                    }`}
                                                    placeholder="Enter new password"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => setShowNewPassword(!showNewPassword)}
                                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                                                >
                                                    {showNewPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                                </button>
                                            </div>
                                            
                                            {/* Password Strength Indicator */}
                                            {newPassword && (
                                                <div className="mt-2 space-y-1.5">
                                                    <div className="flex items-center justify-between text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">Password Strength</span>
                                                        <span className={`font-semibold ${
                                                            passwordStrength < 40 ? 'text-red-600 dark:text-red-400' :
                                                            passwordStrength < 70 ? 'text-yellow-600 dark:text-yellow-400' :
                                                            'text-green-600 dark:text-green-400'
                                                        }`}>
                                                            {getPasswordStrengthLabel()}
                                                        </span>
                                                    </div>
                                                    <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                        <div
                                                            className={`h-full ${getPasswordStrengthColor()} transition-all duration-300 rounded-full`}
                                                            style={{ width: `${passwordStrength}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            )}
                                            
                                            {errors.newPassword && (
                                                <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5" />
                                                    {errors.newPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Confirm Password */}
                                        <div>
                                            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                                Confirm New Password
                                            </label>
                                            <input
                                                type="password"
                                                {...register('confirmPassword', {
                                                    required: 'Please confirm your password',
                                                    validate: (value) => value === newPassword || 'Passwords do not match'
                                                })}
                                                className={`w-full px-4 py-3 border rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white transition-all ${
                                                    errors.confirmPassword
                                                        ? 'border-red-300 dark:border-red-700 focus:ring-red-500 focus:border-red-500'
                                                        : 'border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                                                }`}
                                                placeholder="Confirm new password"
                                            />
                                            {errors.confirmPassword && (
                                                <p className="mt-1.5 text-sm text-red-600 dark:text-red-400 flex items-center gap-1.5">
                                                    <AlertTriangle className="w-3.5 h-3.5" />
                                                    {errors.confirmPassword.message}
                                                </p>
                                            )}
                                        </div>

                                        {/* Action Buttons */}
                                        <div className="flex items-center gap-3 pt-4">
                                            <button
                                                type="submit"
                                                disabled={isSubmitting}
                                                className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-all shadow-lg hover:shadow-xl transform hover:scale-[1.02] active:scale-[0.98]"
                                            >
                                                {isSubmitting ? (
                                                    <>
                                                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                        Updating...
                                                    </>
                                                ) : (
                                                    <>
                                                        <Save className="w-5 h-5" />
                                                        Update Password
                                                    </>
                                                )}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    reset();
                                                    setPasswordStrength(0);
                                                }}
                                                className="px-6 py-3 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-lg transition-colors"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    </div>
                                </form>
                            </div>

                            {/* Security Notice */}
                            <div className="mt-6 bg-gradient-to-r from-yellow-50 to-orange-50 dark:from-yellow-900/10 dark:to-orange-900/10 border border-yellow-200 dark:border-yellow-800/30 rounded-lg p-4">
                                <div className="flex gap-3">
                                    <div className="flex-shrink-0">
                                        <div className="w-8 h-8 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
                                            <Shield className="w-4 h-4 text-yellow-600 dark:text-yellow-500" />
                                        </div>
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-semibold text-yellow-900 dark:text-yellow-300 mb-1">
                                            Sovereign Security
                                        </h3>
                                        <p className="text-sm text-yellow-800 dark:text-yellow-400 leading-relaxed">
                                            Your credentials protect the entire Agentium governance system. Use a strong, unique password and store it securely.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* User Management Tab - Import Component */}
                {activeTab === 'users' && user?.is_admin && (
                    <UserManagement />
                )}
            </div>
        </div>
    );
}