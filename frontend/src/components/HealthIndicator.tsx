import { useEffect } from 'react';
import { useBackendStore } from '@/store/backendStore';

interface HealthIndicatorProps {
    showTooltip?: boolean;
}

export function HealthIndicator({ showTooltip = true }: HealthIndicatorProps) {
    const { status, startPolling, stopPolling } = useBackendStore();

    useEffect(() => {
        startPolling();
        return () => stopPolling();
    }, [startPolling, stopPolling]);

    const getStatusColor = () => {
        switch (status.status) {
            case 'connected':
                return 'bg-green-500';
            case 'connecting':
                return 'bg-yellow-500 animate-pulse';
            case 'disconnected':
                return 'bg-red-500';
        }
    };

    const getTooltipText = () => {
        switch (status.status) {
            case 'connected':
                return `Connected${status.latency ? ` (${status.latency}ms)` : ''}`;
            case 'connecting':
                return 'Connecting...';
            case 'disconnected':
                return 'Disconnected';
        }
    };

    return (
        <div className="relative group">
            <div
                className={`w-3 h-3 rounded-full ${getStatusColor()} transition-all duration-300`}
                aria-label={getTooltipText()}
            />
            {showTooltip && (
                <div className="absolute right-0 top-full mt-2 px-2 py-1 bg-gray-900 text-white text-xs rounded whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
                    {getTooltipText()}
                </div>
            )}
        </div>
    );
}