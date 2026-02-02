import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { useAuthStore } from '@/store/authStore';
import { MainLayout } from '@/components/layout/MainLayout';
import { LoginPage } from '@/pages/LoginPage';
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
import { ProtectedRoute } from '@/components/common/ProtectedRoute'; // New component

export default function App() {
  const { user } = useAuthStore();

  return (
    <Router>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          className: 'dark:bg-gray-800 dark:text-white'
        }}
      />

      <ErrorBoundary>
        <Routes>
          <Route
            path="/login"
            element={!user?.isAuthenticated ? <LoginPage /> : <Navigate to="/" replace />}
          />

          <Route
            path="/"
            element={user?.isAuthenticated ? <MainLayout /> : <Navigate to="/login" replace />}
          >
            <Route index element={<Dashboard />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="constitution" element={<ConstitutionPage />} />
            <Route path="models" element={<ModelsPage />} />
            <Route path="channels" element={<ChannelsPage />} />

            {/* Protected Sovereign Route - Only for admin/sovereign */}
            <Route
              path="sovereign-dashboard"
              element={
                <ProtectedRoute requireSovereign>
                  <SovereignDashboard />
                </ProtectedRoute>
              }
            />

            <Route path="monitoring" element={<MonitoringPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </Router>
  );
}