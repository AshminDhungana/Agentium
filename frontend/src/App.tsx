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
import { Shield } from 'lucide-react';

// Auth layout that keeps background and header persistent
function AuthLayout() {
  const location = useLocation();
  const isSignup = location.pathname === '/signup';

  return (
    <div className="min-h-screen relative flex flex-col items-center justify-center p-4">
      {/* Background persists across auth pages */}
      <FlatMapAuthBackground variant={isSignup ? 'signup' : 'login'} />
      
      {/* Static Header - doesn't animate */}
      <div className="text-center mb-8 relative z-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 text-white mb-4 transition-transform duration-500 hover:scale-110">
          <Shield className="w-8 h-8" />
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">Agentium</h1>
        <p className="text-white">AI Agent Governance System</p>
      </div>

      {/* Animated content switch - only the form card */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -15 }}
          transition={{ 
            duration: 0.25, 
            ease: [0.4, 0, 0.2, 1]
          }}
          className="w-full max-w-md relative z-10"
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>

      {/* Static Footer - doesn't animate */}
      <p className="text-center text-sm text-white mt-8 relative z-10">
        Secure AI Governance Platform v1.0.0
      </p>
    </div>
  );
}

export default function App() {
  const { user, checkAuth } = useAuthStore();
  const { startPolling, stopPolling } = useBackendStore();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  return (
    <Router>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          className: 'dark:bg-gray-800 dark:text-white',
          style: {
            background: '#1f2937',
            color: '#fff',
          },
        }}
      />

      <Routes>
        {/* Auth Routes - Shared layout with persistent background */}
        <Route element={<AuthLayout />}>
          <Route
            path="/login"
            element={!user?.isAuthenticated ? <LoginPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/signup"
            element={!user?.isAuthenticated ? <SignupPage /> : <Navigate to="/" replace />}
          />
        </Route>

        {/* Protected Routes */}
        <Route
          path="/"
          element={
            user?.isAuthenticated ? (
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
