/**
 * @description Dashboard widget showing real-time channel health metrics
 * from the backend store. Refreshes every 30 seconds.
 * @example
 * ```tsx
 * import { ChannelHealthWidget } from '@/components/dashboard/ChannelHealthWidget';
 *
 * <ChannelHealthWidget />
 * ```
 */
import { WidgetCard } from './WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';
import { useBackendStore } from '@/store/backendStore';
import { HealthIndicator } from '@/components/HealthIndicator';
import { Link } from 'react-router-dom';
import { Radio, AlertTriangle } from 'lucide-react';

export function ChannelHealthWidget() {
  const channelMetrics = useBackendStore((s) => s.channelMetrics);
  const isLoading = useBackendStore((s) => s.isLoadingChannelMetrics);

  const isEmpty = Array.isArray(channelMetrics)
    ? channelMetrics.length === 0
    : (channelMetrics?.channels.length ?? 0) === 0;

  return (
    <WidgetCard
      title="Channel Health"
      icon={Radio}
      aria-label="Channel health"
      action={
        <Link
          to="/channels"
          className="text-sm font-medium text-brand hover:underline"
        >
          View All
        </Link>
      }
    >
      {isLoading ? (
        <div className="space-y-3 p-5">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-lg bg-subtle" />
          ))}
        </div>
      ) : isEmpty ? (
        <EmptyState
          icon={Radio}
          title="No channels configured"
          description="Connect a channel from the Channels page."
          size="sm"
        />
      ) : (
        <div className="p-5">
          <div className="mb-4 grid grid-cols-4 gap-3">
            <div className="p-2 bg-subtle rounded-lg">
              <div className="text-lg font-bold text-green-600 dark:text-green-400">{channelMetrics.summary.healthy}</div>
              <div className="text-xs text-green-700 dark:text-green-400">Healthy</div>
            </div>
            <div className="p-2 bg-subtle rounded-lg">
              <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{channelMetrics.summary.warning}</div>
              <div className="text-xs text-yellow-700 dark:text-yellow-400">Warning</div>
            </div>
            <div className="p-2 bg-subtle rounded-lg">
              <div className="text-lg font-bold text-red-600 dark:text-red-400">{channelMetrics.summary.critical}</div>
              <div className="text-xs text-red-700 dark:text-red-400">Critical</div>
            </div>
            <div className="p-2 bg-subtle rounded-lg">
              <div className="text-lg font-bold text-gray-600 dark:text-gray-400">{channelMetrics.summary.total}</div>
              <div className="text-xs text-gray-700 dark:text-gray-400">Total</div>
            </div>
          </div>

          <ul className="divide-y divide-hairline">
            {channelMetrics.channels.slice(0, 5).map((channel) => (
              <li
                key={channel.channel_id}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-[#0f1117] rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <HealthIndicator status={channel.health_status} size="sm" />
                  <div>
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      {channel.channel_name}
                    </div>
                    <div className="text-xs text-gray-600">
                      {channel.metrics.success_rate.toFixed(0)}% success • {channel.metrics.failed_requests} fails
                    </div>
                  </div>
                </div>
                {channel.metrics.circuit_breaker_state === 'open' && (
                  <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                    <AlertTriangle className="w-3 h-3" /> Circuit Open
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </WidgetCard>
  );
}
