import { useEffect } from 'react';
import { useBackendStore } from '@/store/backendStore';
import { Wifi, WifiOff, Loader2 } from 'lucide-react';

interface ConnectionStatusProps {
    compact?: boolean;
}

export function ConnectionStatus({ compact = false }: ConnectionStatusProps) {
    const { status, startPolling, stopPolling } = useBackendStore();

    useEffect(() => {
        startPolling();
        return () => stopPolling();
    }, [startPolling, stopPolling]);

    const getStatusColor = () => {
        switch (status.status) {
            case 'connected':    return 'bg-green-500';
            case 'connecting':   return 'bg-yellow-500';
            case 'disconnected': return 'bg-red-500';
        }
    };

    const getStatusIcon = () => {
        switch (status.status) {
            case 'connected':    return <Wifi className="w-4 h-4" />;
            case 'connecting':   return <Loader2 className="w-4 h-4 animate-spin" />;
            case 'disconnected': return <WifiOff className="w-4 h-4" />;
        }
    };

    const tooltipText =
        status.status === 'connected' && status.latency
            ? `Connected (${status.latency}ms)`
            : status.status;

    /* ── Compact mode — dot only with tooltip ── */
    if (compact) {
        return (
            <div className="relative group">
                <div className={`w-3 h-3 rounded-full ${getStatusColor()} ${status.status === 'connecting' ? 'animate-pulse' : ''} transition-colors duration-300`} />
                <div className="absolute right-0 top-full mt-2 px-2.5 py-1 bg-gray-900 dark:bg-[#0f1117] dark:border dark:border-[#1e2535] text-white text-xs rounded-lg whitespace-nowrap opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50 shadow-lg">
                    {tooltipText}
                </div>
            </div>
        );
    }

    /* ── Full mode ── */
    return (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-[#1e2535] border border-transparent dark:border-[#2a3347] text-sm transition-colors duration-200">
            <div className={`w-2 h-2 rounded-full ${getStatusColor()} ${status.status === 'connecting' ? 'animate-pulse' : ''} transition-colors duration-300`} />
            <span className={`${status.status === 'connected' ? 'text-gray-600 dark:text-gray-300' : status.status === 'disconnected' ? 'text-red-600 dark:text-red-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                {getStatusIcon()}
            </span>
            <span className="capitalize hidden sm:inline text-gray-600 dark:text-gray-300 text-xs font-medium">
                {status.status}
            </span>
            {status.latency && (
                <span className="text-xs text-gray-400 dark:text-gray-500 hidden md:inline">
                    ({status.latency}ms)
                </span>
            )}
        </div>
    );
}
