import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { Shield, Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
    children: React.ReactNode;
    requireSovereign?: boolean;
}

/**
 * Route guard that waits for the auth store to finish initialising
 * before making any redirect decisions.
 *
 * D4: Previously only checked user?.isAuthenticated, which could render
 * stale persisted state while checkAuth() was still resolving on page load
 * (hard refresh, direct URL entry). This caused a flash-of-wrong-content
 * where protected routes briefly rendered or redirected before the server
 * had validated the token.
 *
 * The fix: also check isInitialized. While false (checkAuth in-flight),
 * render a spinner — the same AppLoader shown in App.tsx. Once
 * isInitialized is true the normal auth/sovereign checks proceed.
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
    children,
    requireSovereign = false,
}) => {
    const { user, isInitialized } = useAuthStore();

    // D4: Wait for checkAuth() to finish before making routing decisions.
    // Without this check, a hard refresh renders with stale persisted state
    // before the server has verified the token, causing incorrect redirects.
    if (!isInitialized) {
        return (
            <div className="min-h-screen bg-gray-900 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-12 h-12 rounded-2xl bg-blue-600 flex items-center justify-center">
                        <Shield className="w-6 h-6 text-white" />
                    </div>
                    <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
                </div>
            </div>
        );
    }

    if (!user?.isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (requireSovereign && user.role !== 'admin' && user.username !== 'sovereign') {
        return (
            <div className="flex items-center justify-center h-full bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
                <div className="text-center p-8 bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] max-w-sm w-full">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 mb-5">
                        <Shield className="w-7 h-7 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Only the Sovereign can access this area.
                    </p>
                </div>
            </div>
        );
    }

    return <>{children}</>;
};