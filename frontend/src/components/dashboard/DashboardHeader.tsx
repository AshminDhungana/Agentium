/**
 * @description Welcome title + backend-disconnected warning banner
 * rendered at the top of the Dashboard page.
 * @example
 * ```tsx
 * import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
 *
 * <DashboardHeader />
 * ```
 */

import { AlertTriangle } from 'lucide-react';
import { useBackendStore } from '@/store/backendStore';
import { useAuthStore }    from '@/store/authStore';

export function DashboardHeader() {
    const { user }   = useAuthStore();
    const { status } = useBackendStore();

    return (
        <>
            {/* Welcome text */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                    Welcome, {user?.username}
                </h1>
                <p className="text-gray-600 dark:text-gray-400 text-sm">
                    Oversee your AI governance system from this command center.
                </p>
            </div>

            {/* Backend disconnected warning — identical to the original */}
            {status.status !== 'connected' && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-center gap-3">
                    <AlertTriangle
                        className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0"
                        aria-hidden="true"
                    />
                    <div>
                        <p className="font-medium text-red-900 dark:text-red-300 text-sm">
                            Backend Disconnected
                        </p>
                        <p className="text-sm text-red-700 dark:text-red-400/80">
                            Some features may be unavailable. Please check your backend connection.
                        </p>
                    </div>
                </div>
            )}
        </>
    );
}