/**
 * ProviderResiliencePanel — Phase 19.3 (Task 18)
 *
 * Live per-provider outbound resilience metrics. Subscribes to the
 * `provider_metrics_update` WebSocket event emitted every 30s by
 * `broadcast_provider_metrics` (backend/celery_app.py) and renders one row
 * per active provider config: requests/min (configured), requests in the last
 * minute (live), current concurrency, 429/rate-limited count, circuit-breaker
 * state, and key health.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { useWebSocketStore } from '../../store/websocketStore';
import {
    Activity,
    Zap,
    AlertTriangle,
    ShieldCheck,
    ShieldAlert,
    Gauge,
} from 'lucide-react';

interface ProviderMetric {
    config_id: string;
    provider: string;
    requests_per_minute: number;
    requests_last_min: number;
    concurrency: number;
    rate_limited_count: number;
    circuit_state: string;
    key_status: string;
}

const PROVIDER_COLORS: Record<string, string> = {
    openai: '#10a37f',
    anthropic: '#d97757',
    groq: '#f55036',
    google: '#4285f4',
    ollama: '#9b59b6',
    local: '#6b7280',
};

function fmt(n: number | undefined, digits = 0): string {
    if (n === undefined || n === null) return '0';
    return digits > 0 ? Number(n).toFixed(digits) : String(n);
}

function CircuitBadge({ state }: { state: string }) {
    const open = state === 'open';
    const cls = open
        ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
        : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
            {open ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
            {open ? 'OPEN' : 'CLOSED'}
        </span>
    );
}

function KeyStatusBadge({ status }: { status: string }) {
    const isHealthy = status === 'healthy';
    const isError = status === 'error';
    const cls = isHealthy
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : isError
            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
            : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${cls}`}>
            {status}
        </span>
    );
}

export const ProviderResiliencePanel: React.FC = () => {
    const [metrics, setMetrics] = useState<ProviderMetric[]>([]);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const lastMessage = useWebSocketStore((s) => s.lastMessage);

    const applyUpdate = useCallback((msg: any) => {
        if (!msg || msg.type !== 'provider_metrics_update') return;
        if (Array.isArray(msg.metrics)) {
            setMetrics(msg.metrics as ProviderMetric[]);
            setLastUpdated(new Date());
        }
    }, []);

    useEffect(() => {
        applyUpdate(lastMessage);
    }, [lastMessage, applyUpdate]);

    return (
        <div className="bg-white dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm overflow-hidden">
            <div className="bg-indigo-50 dark:bg-indigo-950/50 border-b border-indigo-100 dark:border-indigo-900/60 px-6 py-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-gray-900 dark:text-indigo-100 flex items-center gap-2">
                    <Gauge className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    Provider Resilience
                </h2>
                <span className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1">
                    <Activity className="w-3.5 h-3.5" />
                    {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Awaiting data…'}
                </span>
            </div>

            <div className="p-6">
                {metrics.length === 0 ? (
                    <div className="text-center py-10">
                        <div className="w-14 h-14 rounded-full bg-indigo-50 dark:bg-indigo-900/20 flex items-center justify-center mx-auto mb-3 border border-indigo-100 dark:border-indigo-800/40">
                            <Zap className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
                        </div>
                        <p className="text-gray-900 dark:text-white font-medium mb-1">No provider metrics yet</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            Live per-provider resilience numbers will appear here once providers are configured.
                        </p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse min-w-[760px]">
                            <thead>
                                <tr className="border-b border-gray-200 dark:border-[#1e2535] text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-[#161b27]/50">
                                    <th className="p-3 font-semibold rounded-tl-lg">Provider</th>
                                    <th className="p-3 font-semibold">RPM (set)</th>
                                    <th className="p-3 font-semibold">Req / last min</th>
                                    <th className="p-3 font-semibold">Concurrency</th>
                                    <th className="p-3 font-semibold">429s</th>
                                    <th className="p-3 font-semibold">Circuit</th>
                                    <th className="p-3 font-semibold rounded-tr-lg">Key health</th>
                                </tr>
                            </thead>
                            <tbody>
                                {metrics.map((m) => {
                                    const color = PROVIDER_COLORS[m.provider] || '#6b7280';
                                    const rlPct =
                                        m.requests_per_minute > 0
                                            ? Math.min(100, Math.round((m.requests_last_min / m.requests_per_minute) * 100))
                                            : 0;
                                    const nearLimit = rlPct >= 80;
                                    return (
                                        <tr
                                            key={m.config_id}
                                            className="border-b border-gray-100 dark:border-[#1e2535] hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                                        >
                                            <td className="p-3">
                                                <div className="flex items-center gap-2">
                                                    <span
                                                        className="w-2.5 h-2.5 rounded-full"
                                                        style={{ backgroundColor: color }}
                                                    />
                                                    <span className="text-sm font-semibold capitalize text-gray-900 dark:text-white">
                                                        {m.provider}
                                                    </span>
                                                    <span className="text-[10px] font-mono text-gray-400 dark:text-gray-500">
                                                        {m.config_id.slice(0, 8)}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="p-3 text-sm text-gray-700 dark:text-gray-300">
                                                {fmt(m.requests_per_minute)}
                                            </td>
                                            <td className="p-3">
                                                <div className="flex items-center gap-2">
                                                    <span className={`text-sm font-bold ${nearLimit ? 'text-orange-600 dark:text-orange-400' : 'text-gray-900 dark:text-white'}`}>
                                                        {fmt(m.requests_last_min)}
                                                    </span>
                                                    <div className="w-16 h-1.5 rounded-full bg-gray-200 dark:bg-[#1e2535] overflow-hidden">
                                                        <div
                                                            className={`h-full rounded-full ${nearLimit ? 'bg-orange-500' : 'bg-indigo-500'}`}
                                                            style={{ width: `${rlPct}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="p-3 text-sm text-gray-700 dark:text-gray-300">
                                                {fmt(m.concurrency)}
                                            </td>
                                            <td className="p-3">
                                                {m.rate_limited_count > 0 ? (
                                                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-red-600 dark:text-red-400">
                                                        <AlertTriangle className="w-3.5 h-3.5" />
                                                        {fmt(m.rate_limited_count)}
                                                    </span>
                                                ) : (
                                                    <span className="text-sm text-gray-500 dark:text-gray-400">0</span>
                                                )}
                                            </td>
                                            <td className="p-3">
                                                <CircuitBadge state={m.circuit_state} />
                                            </td>
                                            <td className="p-3">
                                                <KeyStatusBadge status={m.key_status} />
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};
