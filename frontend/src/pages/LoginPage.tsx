// src/pages/LoginPage.tsx
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { AlertCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import toast from 'react-hot-toast';

export function LoginPage() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    // B13: password visibility toggle
    const [showPassword, setShowPassword] = useState(false);
    const { login, isLoading, error } = useAuthStore();
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const success = await login(username, password);
        if (success) {
            // B8: read from getState() which is synchronous and correct post-await
            // (Zustand set() is synchronous; the store is fully updated before we reach here)
            const user = useAuthStore.getState().user;

            let welcomeMsg = 'Welcome back';
            if (user?.isSovereign) {
                welcomeMsg = 'Welcome, Sovereign';
            } else if (user?.is_admin) {
                welcomeMsg = 'Welcome, Administrator';
            } else if (user?.username) {
                welcomeMsg = `Welcome, ${user.username}`;
            }

            toast.success(welcomeMsg);
            navigate('/');
        }
        // B15: removed toast.error('Invalid credentials') — the inline error
        // banner from the store's `error` state already surfaces this to the
        // user. Showing both a toast AND a banner was a duplicate notification.
    };

    return (
        <>
            {/* Login Card */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8 backdrop-blur-sm">
                <div className="mb-6">
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
                        Welcome Back
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                        Sign in to manage your AI governance system
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                    {/* B14: aria-describedby links the error region to both inputs so
                        screen readers announce the error when either field is focused. */}
                    <div>
                        <label
                            htmlFor="username"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                            Username
                        </label>
                        <input
                            id="username"
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white transition-all"
                            placeholder="Enter username"
                            required
                            autoComplete="username"
                            aria-describedby={error ? 'login-error' : undefined}
                            aria-invalid={!!error}
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="password"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                            Password
                        </label>
                        {/* B13: password visibility toggle wrapper */}
                        <div className="relative">
                            <input
                                id="password"
                                type={showPassword ? 'text' : 'password'}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white transition-all"
                                placeholder="Enter password"
                                required
                                autoComplete="current-password"
                                aria-describedby={error ? 'login-error' : undefined}
                                aria-invalid={!!error}
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword((v) => !v)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                                aria-label={showPassword ? 'Hide password' : 'Show password'}
                            >
                                {showPassword
                                    ? <EyeOff className="w-4 h-4" />
                                    : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    {/* B14: role="alert" ensures screen readers announce this
                        automatically when it appears, without requiring focus. */}
                    {error && (
                        <div
                            id="login-error"
                            role="alert"
                            className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 animate-in fade-in duration-300"
                        >
                            <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                            {error}
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all duration-200 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                                Signing in...
                            </>
                        ) : (
                            'Sign In'
                        )}
                    </button>
                </form>

                <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-sm text-center text-gray-600 dark:text-gray-400">
                        Don't have an account?{' '}
                        <Link
                            to="/signup"
                            className="text-blue-600 dark:text-blue-400 hover:underline font-medium transition-colors"
                        >
                            Request Access
                        </Link>
                    </p>
                </div>

                <div className="mt-4">
                    <p className="text-xs text-center text-gray-500 dark:text-gray-400">
                        Intelligence requires governance
                    </p>
                </div>
            </div>
        </>
    );
}