import { VoiceBridgeContainer } from '@/components/voice-bridge';
import { useAuthStore } from '@/store/authStore';

export function VoiceBridgePage() {
  const isAuthenticated = useAuthStore((state) => state.user?.isAuthenticated);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div className="text-center p-8">
          <div className="w-16 h-16 rounded-2xl bg-blue-600/20 flex items-center justify-center mx-auto mb-6">
            <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Voice Bridge</h1>
          <p className="text-gray-400">Please log in to access the voice bridge.</p>
        </div>
      </div>
    );
  }

  return (
    <VoiceBridgeContainer />
  );
}