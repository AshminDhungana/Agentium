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
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-6">
      {/* ambient glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background: 'radial-gradient(600px circle at 50% 38%, rgba(59,130,246,0.16), transparent 70%)',
        }}
      />
      {/* faint grid texture for depth */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)',
          backgroundSize: '44px 44px',
        }}
      />

      <div
        role="status"
        aria-live="polite"
        className="relative w-full max-w-sm rounded-3xl border border-white/10 bg-white/[0.03] p-10 text-center shadow-2xl shadow-black/40 backdrop-blur-sm"
      >
        {/* signature element: a voice signal pulsing outward */}
        <div className="relative mx-auto mb-7 flex h-20 w-20 items-center justify-center">
          <span className="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500/20" />
          <span
            className="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-500/10"
            style={{ animationDelay: '0.6s' }}
          />
          <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600/20 ring-1 ring-blue-400/30">
            <svg className="h-7 w-7 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
          </span>
        </div>

        <h1 className="text-xl font-semibold tracking-tight text-white">Voice Bridge</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">
          Sign in to start bridging your call.
        </p>

        {/* small waveform accent, ties back to "voice" without adding marketing flourish */}
        <div aria-hidden="true" className="mx-auto mt-6 flex h-4 items-end justify-center gap-1">
          {[6, 12, 16, 10, 14, 8].map((h, i) => (
            <span
              key={i}
              className="motion-safe:animate-pulse w-1 rounded-full bg-blue-500/40"
              style={{ height: `${h}px`, animationDelay: `${i * 120}ms` }}
            />
          ))}
        </div>

        <a
          href={loginHref}
          className="mt-7 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 active:bg-blue-700"
        >
          Sign in to continue
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
        </a>
      </div>
    </main>
  );
}