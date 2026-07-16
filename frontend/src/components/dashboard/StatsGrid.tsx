import { Users, Cpu, Clock, CheckCircle2, Activity } from 'lucide-react';
import { WidgetCard } from './WidgetCard';
import { StatCard, type StatCardProps } from '@/components/ui/StatCard';
import type { DashboardStats } from '@/types/dashboard';

interface StatsGridProps {
  stats: DashboardStats;
  isLoading: boolean;
}

export function StatsGrid({ stats, isLoading }: StatsGridProps) {
  const items: StatCardProps[] = [
    { title: 'Total Agents', value: stats.totalAgents, icon: Users, color: 'blue', isLoading },
    { title: 'Active Agents', value: stats.activeAgents, icon: Cpu, color: 'green', isLoading },
    { title: 'Pending Tasks', value: stats.pendingTasks, icon: Clock, color: 'yellow', isLoading },
    { title: 'Completed Tasks', value: stats.completedTasks, icon: CheckCircle2, color: 'purple', isLoading },
  ];
  return (
    <WidgetCard title="System Statistics" icon={Activity} aria-label="System statistics">
      <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <StatCard key={it.title} {...it} />
        ))}
      </div>
    </WidgetCard>
  );
}
