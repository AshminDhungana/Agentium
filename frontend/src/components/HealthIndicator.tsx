import { useEffect } from 'react';
import { useBackendStore } from '@/store/backendStore';

type HealthStatus = 'connected' | 'connecting' | 'disconnected' | 'healthy' | 'warning' | 'critical';

interface HealthIndicatorProps {
  showTooltip?: boolean;
  status?: HealthStatus;  // Optional - if not provided, uses backend status
  label?: string;         // Optional custom label
  size?: 'sm' | 'md' | 'lg';
}

export function HealthIndicator({ 
  showTooltip = true, 
  status: propStatus,
  label: propLabel,
  size = 'md'
}: HealthIndicatorProps) {
  const { status: backendStatus, startPolling, stopPolling } = useBackendStore();

  // Only poll if using backend status
  useEffect(() => {
    if (!propStatus) {
      startPolling();
      return () => stopPolling();
    }
  }, [startPolling, stopPolling, propStatus]);

  const status = propStatus || backendStatus.status;
  
  const getStatusColor = () => {
    switch (status) {
      case 'connected':
      case 'healthy':      return 'bg-green-500';
      case 'connecting':   return 'bg-yellow-500 animate-pulse';
      case 'disconnected':
      case 'critical':     return 'bg-red-500';
      case 'warning':      return 'bg-yellow-500';
    }
  };

  const getTooltipText = () => {
    if (propLabel) return propLabel;
    switch (status) {
      case 'connected':    return `Connected`;
      case 'healthy':      return 'Healthy';
      case 'warning':      return 'Warning';
      case 'critical':     return 'Critical';
      case 'connecting':   return 'Connecting…';
      case 'disconnected': return 'Disconnected';
    }
  };

  const sizeClasses = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4'
  };

  return (
    <div className="relative group">
      <div
        className={`${sizeClasses[size]} rounded-full ${getStatusColor()} transition-all duration-300`}
        role="img"
        aria-label={getTooltipText()}
      />
      {showTooltip && (
        <div className="absolute right-0 top-full mt-2 px-2.5 py-1 bg-gray-900 dark:bg-[#0f1117] dark:border dark:border-[#1e2535] text-white text-xs rounded-lg whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50 shadow-lg">
          {getTooltipText()}
        </div>
      )}
    </div>
  );
}