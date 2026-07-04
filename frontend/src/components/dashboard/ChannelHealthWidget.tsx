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
import { useEffect } from 'react';
import { useBackendStore } from '@/store/backendStore';
import { HealthIndicator } from '@/components/HealthIndicator';
import { Link } from 'react-router-dom';
import { Radio, AlertTriangle } from 'lucide-react';

export function ChannelHealthWidget() {
  const { channelMetrics, isLoadingChannelMetrics, fetchChannelMetrics } = useBackendStore();

  useEffect(() => {
    fetchChannelMetrics();
    const interval = setInterval(fetchChannelMetrics, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchChannelMetrics]);

  if (isLoadingChannelMetrics && !channelMetrics) {
    return (
      <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535]">
        <div className="animate-pulse h-4 bg-gray-200 dark:bg-[#1e2535] rounded w-1/3 mb-4"></div>
        <div className="space-y-2">
          {[1,2,3].map(i => (
            <div key={i} className="h-8 bg-gray-100 dark:bg-[#0f1117] rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
            <Radio className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">
            Channel Health
          </h2>
        </div>
        <Link 
          to="/channels" 
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          View All
        </Link>
      </div>

      {channelMetrics?.summary && (
        <div className="grid grid-cols-4 gap-2 mb-4 text-center">
          <div className="p-2 bg-green-50 dark:bg-green-500/10 rounded-lg">
            <div className="text-lg font-bold text-green-600 dark:text-green-400">{channelMetrics.summary.healthy}</div>
            <div className="text-xs text-green-700 dark:text-green-400">Healthy</div>
          </div>
          <div className="p-2 bg-yellow-50 dark:bg-yellow-500/10 rounded-lg">
            <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{channelMetrics.summary.warning}</div>
            <div className="text-xs text-yellow-700 dark:text-yellow-400">Warning</div>
          </div>
          <div className="p-2 bg-red-50 dark:bg-red-500/10 rounded-lg">
            <div className="text-lg font-bold text-red-600 dark:text-red-400">{channelMetrics.summary.critical}</div>
            <div className="text-xs text-red-700 dark:text-red-400">Critical</div>
          </div>
          <div className="p-2 bg-gray-50 dark:bg-gray-500/10 rounded-lg">
            <div className="text-lg font-bold text-gray-600 dark:text-gray-400">{channelMetrics.summary.total}</div>
            <div className="text-xs text-gray-700 dark:text-gray-400">Total</div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {channelMetrics?.channels.slice(0, 5).map((channel) => (
          <div 
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
          </div>
        ))}
        
        {(channelMetrics?.channels.length || 0) === 0 && (
          <div className="text-center py-4 text-sm text-gray-600">
            No channels configured
          </div>
        )}
      </div>
    </div>
  );
}