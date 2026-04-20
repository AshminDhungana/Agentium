// src/App.tsx
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useOutlet, useNavigate } from 'react-router-dom';
import { useEffect, useState, useRef, lazy } from 'react';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';
import { useBackendStore } from '@/store/backendStore';
import { GlobalWebSocketProvider } from '@/components/GlobalWebSocketProvider';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MainLayout } from '@/components/layout/MainLayout';
import { FlatMapAuthBackground } from '@/components/FlatMapAuthBackground';
import { LoginPage } from '@/pages/LoginPage';
import { SignupPage } from '@/pages/SignupPage';
import { SovereignRoute } from '@/components/SovereignRoute';
import { AnimatePresence, motion } from 'framer-motion';
import { Shield } from 'lucide-react';
import { modelsApi } from '@/services/models';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Session key ───────────────────────────────────────────────────────────────
// Marks that the model-redirect check has already fired for this login session.
// sessionStorage resets when the tab is closed, and is explicitly cleared on
// every new login / logout (username change detected inside the hook).
const MODEL_REDIRECT_KEY = 'model_redirect_checked';

// ── useModelRedirect ──────────────────────────────────────────────────────────
// Runs once per login session. Uses the existing modelsApi to check whether
// any model configs exist. If none → redirects to /models exactly one time.
// Once the user adds a model the redirect stops for the rest of the session.
// On the next login the check runs fresh.
//
// Enforced by:
//   1. sessionStorage key — survives page refresh within the same tab session.
//   2. Username ref — if user identity changes (different login) the key is
//      cleared and the check re-runs, without touching authStore.
function useModelRedirect() {
    const navigate        = useNavigate();
    const location        = useLocation();
    const isAuthenticated = useAuthStore(s => s.user?.isAuthenticated);
    const username        = useAuthStore(s => s.user?.username ?? null);
    const prevUsernameRef = useRef<string | null>(null);

    useEffect(() => {
        // User logged out — clear the key so next login re-checks.
        if (!isAuthenticated || !username) {
            sessionStorage.removeItem(MODEL_REDIRECT_KEY);
            prevUsernameRef.current = null;
            return;
        }

        // Different user logged in — clear stale key so check re-runs.
        if (prevUsernameRef.current !== username) {
            sessionStorage.removeItem(MODEL_REDIRECT_KEY);
            prevUsernameRef.current = username;
        }

        // Already checked this login session — do nothing.
        if (sessionStorage.getItem(MODEL_REDIRECT_KEY)) return;

        // Already on /models — mark as checked, no redirect needed.
        if (location.pathname === '/models') {
            sessionStorage.setItem(MODEL_REDIRECT_KEY, 'true');
            return;
        }

        let active = true;

        modelsApi.getConfigs()
            .then(configs => {
                if (!active) return;
                // Mark checked regardless of outcome so this never re-fires
                // within the same login session.
                sessionStorage.setItem(MODEL_REDIRECT_KEY, 'true');
                if (configs.length === 0) {
                    navigate('/models', { replace: true });
                }
            })
            .catch(() => {
                // API failed — mark checked so we don't keep retrying and
                // blocking the user.
                if (active) sessionStorage.setItem(MODEL_REDIRECT_KEY, 'true');
            });

        return () => { active = false; };
    // Intentionally only re-runs on auth/identity change, not on navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isAuthenticated, username]);
}

// ── AppWithRedirect ───────────────────────────────────────────────────────────
// Wrapper that runs the model redirect check inside the Router context
// (useNavigate requires being inside <Router>).
function AppWithRedirect() {
    useModelRedirect();
    const { user, isInitialized } = useAuthStore();
    const { startPolling, stopPolling } = useBackendStore();

    useEffect(() => {
        startPolling();
        return () => stopPolling();
    }, [startPolling, stopPolling]);

    if (!isInitialized) {
        return <AppLoader />;
    }

    const isAuthenticated = user?.isAuthenticated === true;

    return (
        <>
            <Toaster
                position="top-right"
                toastOptions={{
                    duration: 4000,
                    className: 'dark:bg-[#161b27] dark:text-white border dark:border-[#1e2535]',
                    style: { background: '#1f2937', color: '#fff' },
                }}
            />

            <GlobalWebSocketProvider>
                <ErrorBoundary variant="page" fallbackHeading="Application Error">
                <Routes>
                    {/* Auth Routes */}
                    <Route element={<AuthLayout />}>
                        <Route
                            path="/login"
                            element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
                        />
                        <Route
                            path="/signup"
                            element={isAuthenticated ? <Navigate to="/" replace /> : <SignupPage />}
                        />
                    </Route>

                    {/* Protected Routes */}
                    <Route
                        path="/"
                        element={
                            isAuthenticated
                                ? <MainLayout />
                                : <Navigate to="/login" replace />
                        }
                    >
                        <Route index element={<Dashboard />} />
                        <Route path="chat" element={<ChatPage />} />
                        <Route path="agents" element={<AgentsPage />} />
                        <Route path="tasks" element={<TasksPage />} />
                        <Route path="monitoring" element={<MonitoringPage />} />
                        <Route path="voting" element={<VotingPage />} />
                        <Route path="constitution" element={<ConstitutionPage />} />
                        <Route path="models" element={<ModelsPage />} />
                        <Route path="channels" element={<ChannelsPage />} />
                        <Route path="message-log" element={<MessageLogPage />} />
                        <Route path="ab-testing" element={<ABTestingPage />} />
                        <Route
                            path="sovereign"
                            element={
                                <SovereignRoute>
                                    <SovereignDashboard />
                                </SovereignRoute>
                            }
                        />
                        <Route path="settings" element={<SettingsPage />} />
                    </Route>

                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
                </ErrorBoundary>
            </GlobalWebSocketProvider>
        </>
    );
}

// ── Lazy-loaded page components ───────────────────────────────────────────────
// Each page chunk is fetched on first visit and cached by the browser thereafter.
// Auth pages (Login/Signup) stay eager since they're needed before JS settles.
const Dashboard        = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const SettingsPage     = lazy(() => import('@/pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
const ChatPage         = lazy(() => import('@/pages/ChatPage').then(m => ({ default: m.ChatPage })));
const ChannelsPage     = lazy(() => import('@/pages/ChannelsPage').then(m => ({ default: m.ChannelsPage })));
const ModelsPage       = lazy(() => import('@/pages/ModelsPage').then(m => ({ default: m.ModelsPage })));
const AgentsPage       = lazy(() => import('@/pages/AgentsPage').then(m => ({ default: m.AgentsPage })));
const TasksPage        = lazy(() => import('@/pages/TasksPage').then(m => ({ default: m.TasksPage })));
const ConstitutionPage = lazy(() => import('@/pages/ConstitutionPage').then(m => ({ default: m.ConstitutionPage })));
const SovereignDashboard = lazy(() => import('@/pages/SovereignDashboard').then(m => ({ default: m.SovereignDashboard })));
const MonitoringPage   = lazy(() => import('@/pages/MonitoringPage').then(m => ({ default: m.MonitoringPage })));
const VotingPage       = lazy(() => import('@/pages/VotingPage').then(m => ({ default: m.VotingPage })));
const MessageLogPage   = lazy(() => import('@/pages/MessageLogPage').then(m => ({ default: m.MessageLogPage })));
const ABTestingPage    = lazy(() => import('@/pages/ABTestingPage').then(m => ({ default: m.ABTestingPage })));

// Full-screen spinner shown while checkAuth() is in-flight on page load
function AppLoader() {
  return (
    <div className="min-h-screen bg-white dark:bg-[#0f1117] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-blue-600 flex items-center justify-center">
          <Shield className="w-6 h-6 text-white" />
        </div>
        <LoadingSpinner size="md" />
      </div>
    </div>
  );
}

// Auth layout — keeps background and header persistent across login/signup.
// Transition timing is aligned with the in-app page transitions (0.22s ease)
// so the whole app feels consistent.
function AuthLayout() {
  const location = useLocation();
  const outlet = useOutlet();
  const isSignup = location.pathname === '/signup';
  const [isDark, setIsDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return document.documentElement.classList.contains('dark');
    }
    return false;
  });

  const toggleTheme = () => {
    const newDark = !isDark;
    setIsDark(newDark);
    if (newDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  };

  return (
    <div className="min-h-screen relative flex flex-col items-center justify-center p-4">
      <FlatMapAuthBackground variant={isSignup ? 'signup' : 'login'} />

      <div className="text-center mb-8 relative z-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 text-white mb-4 transition-transform duration-500 hover:scale-110">
          <button
            onClick={toggleTheme}
            className="
            group relative p-2 rounded-xl
            transition-all duration-300 ease-out
            overflow-hidden
            bg-blue-600 text-white shadow-sm
            hover:bg-zinc-900 hover:text-zinc-100 hover:shadow-lg
            dark:bg-blue-600 dark:text-zinc-900 dark:shadow-none
            dark:hover:bg-white dark:hover:text-zinc-800 dark:hover:shadow-lg
            focus:outline-none focus:ring-2 focus:ring-blue-500/40
            "
            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <Shield className="w-8 h-8 transition-all duration-500 ease-[cubic-bezier(.22,1,.36,1)] rotate-0 scale-100 opacity-100 group-hover:rotate-0 group-hover:scale-0 group-hover:opacity-0 dark:rotate-0 dark:scale-0 dark:opacity-0 dark:group-hover:rotate-0 dark:group-hover:scale-100 dark:group-hover:opacity-100" />
            <Shield className="w-8 h-8 absolute inset-0 m-auto transition-all duration-500 ease-[cubic-bezier(.22,1,.36,1)] rotate-0 scale-0 opacity-0 group-hover:rotate-0 group-hover:scale-100 group-hover:opacity-100 dark:rotate-0 dark:scale-100 dark:opacity-100 dark:group-hover:rotate-0 dark:group-hover:scale-0 dark:group-hover:opacity-0" />
            <span className="pointer-events-none absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100 group-hover:bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.15),transparent_70%)] dark:group-hover:bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.15),transparent_70%)]" />
          </button>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Agentium</h1>
        <p className="text-white">AI Agent Governance System</p>
      </div>

      {/* Auth page transition — aligned with in-app page transition timing.
          Uses a simple fade (no y-shift) since the auth background is static. */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6, scale: 0.995 }}
          animate={{
            opacity: 1,
            y: 0,
            scale: 1,
            transition: { duration: 0.22, ease: [0.25, 0.1, 0.25, 1] },
          }}
          exit={{
            opacity: 0,
            y: -4,
            scale: 0.998,
            transition: { duration: 0.15, ease: [0.25, 0.1, 0.25, 1] },
          }}
          className="w-full max-w-md relative z-10"
        >
          {outlet}
        </motion.div>
      </AnimatePresence>

      <p className="text-center text-sm text-white mt-8 relative z-10">
        Secure AI Governance Platform v1.0.0
      </p>
    </div>
  );
}

export default function App() {
    return (
        <Router>
            <AppWithRedirect />
        </Router>
    );
}