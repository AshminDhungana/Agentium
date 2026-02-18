// src/App.tsx
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';
import { useBackendStore } from '@/store/backendStore';
import { MainLayout } from '@/components/layout/MainLayout';
import { FlatMapAuthBackground } from '@/components/FlatMapAuthBackground';
import { LoginPage } from '@/pages/LoginPage';
import { SignupPage } from '@/pages/SignupPage';
import { Dashboard } from '@/pages/Dashboard';
import { SettingsPage } from '@/pages/SettingsPage';
import { ChatPage } from '@/pages/ChatPage';
import { ChannelsPage } from '@/pages/ChannelsPage';
import { ModelsPage } from '@/pages/ModelsPage';
import { AgentsPage } from '@/pages/AgentsPage';
import { TasksPage } from '@/pages/TasksPage';
import { MonitoringPage } from '@/pages/MonitoringPage';
import { ConstitutionPage } from '@/pages/ConstitutionPage';
import { SovereignDashboard } from '@/pages/SovereignDashboard';
import { SovereignRoute } from '@/components/SovereignRoute';
import { AnimatePresence, motion } from 'framer-motion';
import { Shield, Loader2 } from 'lucide-react';

// Full-screen spinner shown while checkAuth() is in-flight on page load
function AppLoader() {
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

// Auth layout — keeps background and header persistent across login/signup
function AuthLayout() {
  const location = useLocation();
  const isSignup = location.pathname === '/signup';

  return (
    <div className="min-h-screen relative flex flex-col items-center justify-center p-4">
      <FlatMapAuthBackground variant={isSignup ? 'signup' : 'login'} />

      <div className="text-center mb-8 relative z-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 text-white mb-4 transition-transform duration-500 hover:scale-110">
          <Shield className="w-8 h-8" />
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Agentium</h1>
        <p className="text-white">AI Agent Governance System</p>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -15 }}
          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
          className="w-full max-w-md relative z-10"
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>

      <p className="text-center text-sm text-white mt-8 relative z-10">
        Secure AI Governance Platform v1.0.0
      </p>
    </div>
  );
}

export default function App() {
  const { user, isInitialized, isLoading } = useAuthStore();
  const { startPolling, stopPolling } = useBackendStore();

  // NOTE: We no longer call checkAuth() here.
  // It is now triggered automatically inside authStore via onRehydrateStorage,
  // which fires before any React component renders — eliminating the race condition.

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  // Block the entire app until checkAuth() has finished at least once.
  // This prevents ANY routing decision from being made before we know
  // whether the user's token is valid, which was the root cause of the
  // "refresh → redirect to login" bug.
  if (!isInitialized) {
    return <AppLoader />;
  }

  const isAuthenticated = user?.isAuthenticated === true;

  return (
    <Router>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          className: 'dark:bg-gray-800 dark:text-white',
          style: { background: '#1f2937', color: '#fff' },
        }}
      />

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
            isLoading ? (
              // isLoading covers background re-verification (e.g. after login form submit)
              <AppLoader />
            ) : isAuthenticated ? (
              <MainLayout />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="monitoring" element={<MonitoringPage />} />
          <Route path="constitution" element={<ConstitutionPage />} />
          <Route path="models" element={<ModelsPage />} />
          <Route path="channels" element={<ChannelsPage />} />
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
    </Router>
  );
}