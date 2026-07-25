import { Mic, LogIn } from 'lucide-react';
import { VoiceBridgeContainer } from '@/components/voice-bridge';
import { useAuthStore } from '@/store/authStore';

interface VoiceBridgePageProps {
  /**
   * Where "Sign in to continue" sends the user. Point this at your real
   * auth flow — e.g. an authStore action that opens a login modal, or
   * swap the <a> below for your router's <Link> (react-router / next/link)
   * if you want client-side navigation instead of a full page load.
   */
  loginHref?: string;
}

export function VoiceBridgePage({ loginHref = '/login' }: VoiceBridgePageProps) {
  const isAuthenticated = useAuthStore((state) => state.user?.isAuthenticated);

  if (!isAuthenticated) {
    return <VoiceBridgeSignInGate loginHref={loginHref} />;
  }

  return <VoiceBridgeContainer />;
}

function VoiceBridgeSignInGate({ loginHref }: { loginHref: string }) {
  return (
    <div className="h-full bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6">
      <div className="text-center max-w-sm" role="status" aria-live="polite">
        <div className="w-20 h-20 bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6">
          <Mic className="w-10 h-10 text-blue-600 dark:text-blue-400" aria-hidden="true" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">Sign in required</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          Sign in to start bridging your call.
        </p>
        <a
          href={loginHref}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm dark:shadow-blue-900/30"
        >
          <LogIn className="w-4 h-4" aria-hidden="true" />
          Sign in to continue
        </a>
      </div>
    </div>
  );
}