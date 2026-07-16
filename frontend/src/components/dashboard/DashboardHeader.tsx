import { useAuthStore } from '@/store/authStore';        // use the path you confirmed
import { useBackendStore } from '@/store/backendStore';  // use the path you confirmed
import { AlertTriangle } from 'lucide-react';

export function DashboardHeader() {
  const user = useAuthStore((s) => s.user);
  const status = useBackendStore((s) => s.status);
  const disconnected = status.status !== 'connected';

  return (
    <header className="mb-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 sm:text-3xl">
        Welcome, {user?.username ?? 'Sovereign'}
      </h1>
      {disconnected && (
        <div
          role="alert"
          aria-label="Backend disconnected"
          className="mt-4 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300"
        >
          <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />
          <span>Backend disconnected — live data is paused. Reconnect to resume real-time updates.</span>
        </div>
      )}
    </header>
  );
}
