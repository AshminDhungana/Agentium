// ─── SystemHealth ────────────────────────────────────────────────────────────
// System Status panel — extracted verbatim from Dashboard.tsx bottom row.
// No behaviour changes; only moved to its own file.

import { Shield } from 'lucide-react';
import { useBackendStore } from '@/store/backendStore';

export function SystemHealth() {
    const { status } = useBackendStore();
    const isConnected = status.status === 'connected';

    return (
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

            {/* Header */}
            <div className="flex items-center gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                    <Shield className="w-4 h-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />
                </div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                    System Status
                </h2>
            </div>

            {/* Status rows — identical to original */}
            <div className="space-y-0 divide-y divide-gray-100 dark:divide-[#1e2535]">

                <div className="flex items-center justify-between py-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Backend Status</span>
                    <span
                        className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                            isConnected
                                ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
                        }`}
                        role="status"
                        aria-label={`Backend is ${isConnected ? 'healthy' : 'disconnected'}`}
                    >
                        {isConnected ? 'Healthy' : 'Disconnected'}
                    </span>
                </div>

                <div className="flex items-center justify-between py-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400">API Latency</span>
                    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {status.latency ? `${status.latency}ms` : 'N/A'}
                    </span>
                </div>

                <div className="flex items-center justify-between py-3">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Constitution Version</span>
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/20">
                        v1.0.0
                    </span>
                </div>

            </div>
        </div>
    );
}