import { HealthIndicator } from '@/components/HealthIndicator';
import type { ChannelMetrics, ChannelHealthStatus } from '@/types';

interface ChannelMetricsCardProps {
  metrics: ChannelMetrics;
  healthStatus: ChannelHealthStatus;
}

export function ChannelMetricsCard({ metrics, healthStatus }: ChannelMetricsCardProps) {
  const getHealthColor = () => {
    switch (healthStatus) {
      case 'healthy': return 'text-green-600 dark:text-green-400';
      case 'warning': return 'text-yellow-600 dark:text-yellow-400';
      case 'critical': return 'text-red-600 dark:text-red-400';
    }
  };

  const getHealthBg = () => {
    switch (healthStatus) {
      case 'healthy': return 'bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20';
      case 'warning': return 'bg-yellow-50 dark:bg-yellow-500/10 border-yellow-200 dark:border-yellow-500/20';
      case 'critical': return 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20';
    }
  };

  return (
    <div className={`p-4 rounded-xl border ${getHealthBg()}`}>
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Channel Health</h4>
        <HealthIndicator status={healthStatus} size="sm" />
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics.success_rate.toFixed(1)}%
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400">Success Rate</div>
        </div>
        
        <div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics.failed_requests}
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400">Failures</div>
        </div>
        
        <div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics.rate_limit_hits}
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400">Rate Limits</div>
        </div>
        
        <div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics.consecutive_failures}
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-400">Consecutive Failures</div>
        </div>
      </div>
    </div>
  );
}