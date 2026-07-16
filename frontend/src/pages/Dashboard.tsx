import { useBackendStore } from '@/store/backendStore';
import { useDashboardData } from '@/hooks/useDashboardData';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { DashboardSkeleton } from '@/components/ui/DashboardSkeleton';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { StatsGrid } from '@/components/dashboard/StatsGrid';
import { ProviderAnalytics } from '@/components/dashboard/ProviderAnalytics';
import { FinancialBurnDashboard } from '@/components/dashboard/FinancialBurnDashboard';
import { RecentTasks } from '@/components/dashboard/RecentTasks';
import { AgentsList } from '@/components/dashboard/AgentsList';
import { SystemHealth } from '@/components/dashboard/SystemHealth';
import { QuickActions } from '@/components/dashboard/QuickActions';
import { ChannelHealthWidget } from '@/components/dashboard/ChannelHealthWidget';

export default function Dashboard() {
  const status = useBackendStore((s) => s.status);
  const {
    stats, recentTasks, activeAgentsList,
    isAgentsLoading, isTasksLoading, isAgentsError, isTasksError,
    refetchAgents, refetchTasks,
  } = useDashboardData();
  const statsLoading = status.status !== 'connected' || isAgentsLoading || isTasksLoading;

  if (status.status !== 'connected') {
    return (
      <div className="h-full overflow-y-auto bg-canvas p-6 transition-colors duration-200">
        <DashboardHeader />
        <div className="mt-6"><DashboardSkeleton /></div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-canvas p-4 transition-colors duration-200 sm:p-6">
      <DashboardHeader />
      <div className="mt-6">
        <ErrorBoundary variant="widget" fallbackHeading="Stats Error">
          <StatsGrid stats={stats} isLoading={statsLoading} />
        </ErrorBoundary>
      </div>
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <ErrorBoundary variant="widget" fallbackHeading="Analytics Error"><ProviderAnalytics /></ErrorBoundary>
          <ErrorBoundary variant="widget" fallbackHeading="Budget Error"><FinancialBurnDashboard /></ErrorBoundary>
          <ErrorBoundary variant="widget" fallbackHeading="Tasks Error">
            <RecentTasks tasks={recentTasks} isLoading={isTasksLoading} isError={isTasksError} onRetry={refetchTasks} />
          </ErrorBoundary>
          <ErrorBoundary variant="widget" fallbackHeading="Agents Error">
            <AgentsList agents={activeAgentsList} isLoading={isAgentsLoading} isError={isAgentsError} onRetry={refetchAgents} />
          </ErrorBoundary>
        </div>
        <div className="flex flex-col gap-6">
          <ErrorBoundary variant="widget" fallbackHeading="Health Error"><SystemHealth /></ErrorBoundary>
          <ErrorBoundary variant="widget" fallbackHeading="Quick Actions Error"><QuickActions /></ErrorBoundary>
          <ErrorBoundary variant="widget" fallbackHeading="Channels Error"><ChannelHealthWidget /></ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
