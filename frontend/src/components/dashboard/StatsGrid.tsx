/**
 * @description Renders the four top-level KPI stat cards on the Dashboard.
 * Delegates to StatCard for consistent styling, skeletons, and ARIA labels.
 * @example
 * ```tsx
 * import { StatsGrid } from '@/components/dashboard/StatsGrid';
 *
 * <StatsGrid stats={stats} isLoading={false} />
 * ```
 * @param {DashboardStats} props.stats - Current dashboard statistics.
 * @param {boolean} props.isLoading - When true each card renders an animated loading skeleton.
 */

import { Users, CheckCircle, AlertTriangle, Activity } from 'lucide-react';
import { StatCard } from '@/components/ui/StatCard';
import type { DashboardStats } from '@/types/dashboard';

interface StatsGridProps {
    stats:     DashboardStats;
    /** When true each card renders an animated loading skeleton. */
    isLoading: boolean;
}

export function StatsGrid({ stats, isLoading }: StatsGridProps) {
    const cards = [
        {
            title: 'Total Agents',
            value: stats.totalAgents,
            icon:  Users,
            color: 'blue'   as const,
            link:  '/agents',
        },
        {
            title: 'Active Agents',
            value: stats.activeAgents,
            icon:  Activity,
            color: 'green'  as const,
            link:  '/agents',
        },
        {
            title: 'Pending Tasks',
            value: stats.pendingTasks,
            icon:  AlertTriangle,
            color: 'yellow' as const,
            link:  '/tasks',
        },
        {
            title: 'Completed Tasks',
            value: stats.completedTasks,
            icon:  CheckCircle,
            color: 'purple' as const,
            link:  '/tasks',
        },
    ];

    return (
        <div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8"
            role="region"
            aria-label="System statistics"
        >
            {cards.map(card => (
                <StatCard
                    key={card.title}
                    title={card.title}
                    value={card.value}
                    icon={card.icon}
                    color={card.color}
                    link={card.link}
                    isLoading={isLoading}
                />
            ))}
        </div>
    );
}