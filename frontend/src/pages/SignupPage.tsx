// src/pages/SignupPage.tsx
import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { AlertCircle, Loader2, CheckCircle, ArrowLeft, Eye, EyeOff } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import toast from 'react-hot-toast';

export function SignupPage() {
    const [username, setUsername]               = useState('');
    const [email, setEmail]                     = useState('');
    const [password, setPassword]               = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading]             = useState(false);
    const [error, setError]                     = useState('');
    const [success, setSuccess]                 = useState(false);
    // B13: separate visibility toggles for each password field
    const [showPassword, setShowPassword]               = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    // B7: store the redirect timer so we can cancel it on unmount
    const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const { signup } = useAuthStore(); // B5: use store instead of raw api.post
    const navigate = useNavigate();

    // B7: clear the timer if the component unmounts before it fires
    useEffect(() => {
        return () => {
            if (redirectTimerRef.current !== null) {
                clearTimeout(redirectTimerRef.current);
            }
        };
    }, []);

    // B10: real-time password-match feedback — only shown once the user has
    //      started typing in the confirm field, avoiding premature red state.
    const passwordsDoNotMatch =
        confirmPassword.length > 0 && password !== confirmPassword;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        // --- Client-side validation ---

        if (username.trim().length < 3) {
            setError('Username must be at least 3 characters long');
            return;
        }

        // B9/B11: removed the redundant custom email regex — the browser's
        //         native `type="email"` validation already enforces RFC-compliant
        //         format and is more accurate. The regex would never fire because
        //         the browser blocks form submission first.

        if (password.length < 8) {
            setError('Password must be at least 8 characters long');
            return;
        }

        if (password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        setIsLoading(true);

        try {
            // B5: delegate to authStore.signup() instead of calling api.post
            //     directly. All auth API calls now flow through a single layer.
            const result = await signup(username, email, password);

            if (result.success) {
                setSuccess(true);
                toast.success('Signup request submitted! Awaiting admin approval.', {
                    duration: 4000,
                    icon: '✅',
                });
                // B7: store ref so the cleanup effect can cancel this
                redirectTimerRef.current = setTimeout(() => navigate('/login'), 3000);
            } else {
                setError(result.message);
                toast.error(result.message, { duration: 4000 });
            }
        } catch {
            // authStore.signup() absorbs errors and returns them in result.message,
            // so this catch is a safety net for truly unexpected throws.
            const msg = 'An unexpected error occurred. Please try again.';
            setError(msg);
            toast.error(msg, { duration: 4000 });
        } finally {
            setIsLoading(false);
        }
    };

    if (success) {
        return (
            <>
                {/* Success Card */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8 text-center backdrop-blur-sm">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 mb-4">
                        <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                        Request Submitted!
                    </h2>
                    <p className="text-gray-600 dark:text-gray-400 mb-6">
                        Your signup request has been sent to the admin for approval.
                        You will be able to login once approved.
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-500">
                        Redirecting to login page...
                    </p>
                </div>
            </>
        );
    }

    return (
        <>
            {/* Signup Card */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8 backdrop-blur-sm">
                <div className="mb-6">
                    <Link
                        to="/login"
                        className="inline-flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4 transition-colors"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Login
                    </Link>

                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
                        Create Account
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                        Request access to the governance system
                    </p>
                </div>

                {/* B14: noValidate lets us control all validation messaging
                         ourselves while still using semantic <input> types. */}
                <form onSubmit={handleSubmit} className="space-y-4" noValidate>

                    {/* Username */}
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
                            placeholder="Choose a username"
                            required
                            autoComplete="username"
                            minLength={3}
                            maxLength={50}
                            aria-describedby={error ? 'signup-error' : undefined}
                            aria-invalid={!!error}
                        />
                    </div>

                    {/* Email */}
                    <div>
                        <label
                            htmlFor="email"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                            Email Address
                        </label>
                        <input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white transition-all"
                            placeholder="your.email@example.com"
                            required
                            autoComplete="email"
                        />
                    </div>

                    {/* Password */}
                    <div>
                        <label
                            htmlFor="password"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                            Password
                        </label>
                        {/* B13: password visibility toggle */}
                        <div className="relative">
                            <input
                                id="password"
                                type={showPassword ? 'text' : 'password'}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white transition-all"
                                placeholder="Choose a password"
                                required
                                autoComplete="new-password"
                                minLength={8}
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
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            Minimum 8 characters
                        </p>
                    </div>

                    {/* Confirm Password */}
                    <div>
                        <label
                            htmlFor="confirmPassword"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                            Confirm Password
                        </label>
                        {/* B13: separate toggle for confirm field */}
                        <div className="relative">
                            <input
                                id="confirmPassword"
                                type={showConfirmPassword ? 'text' : 'password'}
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className={`w-full px-3 py-2 pr-10 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-white transition-all ${
                                    // B10: real-time visual cue on the confirm field border
                                    passwordsDoNotMatch
                                        ? 'border-red-400 dark:border-red-500'
                                        : 'border-gray-300 dark:border-gray-600'
                                }`}
                                placeholder="Confirm your password"
                                required
                                autoComplete="new-password"
                                minLength={8}
                                aria-describedby={
                                    passwordsDoNotMatch
                                        ? 'password-match-hint'
                                        : error
                                        ? 'signup-error'
                                        : undefined
                                }
                                aria-invalid={passwordsDoNotMatch || !!error}
                            />
                            <button
                                type="button"
                                onClick={() => setShowConfirmPassword((v) => !v)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                                aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                            >
                                {showConfirmPassword
                                    ? <EyeOff className="w-4 h-4" />
                                    : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                        {/* B10: inline real-time mismatch hint */}
                        {passwordsDoNotMatch && (
                            <p
                                id="password-match-hint"
                                className="text-xs text-red-500 dark:text-red-400 mt-1"
                                role="status"
                            >
                                Passwords do not match
                            </p>
                        )}
                    </div>

                    {/* B14: role="alert" surfaces submit-time errors to screen readers */}
                    {error && (
                        <div
                            id="signup-error"
                            role="alert"
                            className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg animate-in fade-in duration-300"
                        >
                            <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                            {error}
                        </div>
                    )}

                    <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg">
                        <p className="text-xs text-blue-800 dark:text-blue-300">
                            ℹ️ Your account will be pending until approved by an administrator.
                            You'll be able to login once approved.
                        </p>
                    </div>

                    <button
                        type="submit"
                        disabled={isLoading || passwordsDoNotMatch}
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-all duration-200 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                                Submitting Request...
                            </>
                        ) : (
                            'Create Account'
                        )}
                    </button>
                </form>

                <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-sm text-center text-gray-600 dark:text-gray-400">
                        Already have an account?{' '}
                        <Link
                            to="/login"
                            className="text-blue-600 dark:text-blue-400 hover:underline font-medium transition-colors"
                        >
                            Sign In
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