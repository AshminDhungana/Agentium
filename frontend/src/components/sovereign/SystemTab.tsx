/**
 * @description System health tab for the Sovereign Dashboard.
 * Displays CPU, memory, disk usage, and service status.
 * Purely presentational; data-fetching is handled by useSystemTab.
 * @example
 * ```tsx
 * import { SystemTab } from '@/components/sovereign/SystemTab';
 *
 * <SystemTab />
 * ```
 */
// System tab panel extracted from SovereignDashboard.
// All data-fetching and WebSocket logic lives in useSystemTab — this
// component is purely presentational.

import {
    Server,
    Activity,
    Terminal,
    Play,
    Square,
    RotateCw,
    Trash2,
    CheckCircle,
    XCircle,
    Clock,
    Cpu,
    HardDrive,
    Zap,
    AlertCircle,
} from 'lucide-react';
import { useSystemTab } from '@/hooks/useSystemTab';

// ── Constants ─────────────────────────────────────────────────────────────────

// Backend returns bytes; divide by 1 GiB (1024^3) to display correct GB values.
const BYTES_PER_GB = 1_073_741_824;

// ── Helpers ───────────────────────────────────────────────────────────────────

const getContainerStatusClasses = (status: string) => {
    switch (status.toLowerCase()) {
        case 'running':
            return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20';
        case 'stopped':
        case 'exited':
            return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20';
        case 'paused':
            return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
        default:
            return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';
    }
};

const getCommandStatusIcon = (status: string) => {
    switch (status) {
        case 'approved':
        case 'executed':
            return <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400 shrink-0" />;
        case 'rejected':
            return <XCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />;
        case 'pending':
            return <Clock className="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />;
        default:
            return null;
    }
};

const getCommandStatusClasses = (status: string) => {
    switch (status) {
        case 'executed':
            return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20';
        case 'rejected':
            return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20';
        default:
            return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
    }
};

const getResourceBarColor = (value: number) => {
    if (value >= 90) return 'bg-red-500';
    if (value >= 75) return 'bg-yellow-500 dark:bg-yellow-400';
    if (value >= 50) return 'bg-blue-500 dark:bg-blue-400';
    return 'bg-green-500 dark:bg-green-400';
};

// ── Component ─────────────────────────────────────────────────────────────────

export function SystemTab() {
    const {
        systemStatus,
        containers,
        commandLogs,
        isLoading,
        error,
        refresh,
        handleContainerAction,
        clearError,
    } = useSystemTab();

    const runningContainers = containers.filter(
        (c) => c.status.toLowerCase() === 'running',
    ).length;

    return (
        <>
            {/* ── Error banner (C1) ──────────────────────────────────────── */}
            {error && (
                <div className="flex items-center gap-3 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl mb-6">
                    <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
                    <span className="text-sm text-red-600 dark:text-red-400 flex-1">{error}</span>
                    <button
                        onClick={() => { clearError(); refresh(); }}
                        className="text-xs font-medium text-red-600 dark:text-red-400 underline underline-offset-2 hover:no-underline shrink-0"
                    >
                        Retry
                    </button>
                </div>
            )}

            {/* ── System Status Grid ─────────────────────────────────────── */}
            {systemStatus && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">

                    {/* CPU */}
                    <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <Cpu className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.cpu.usage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            CPU Usage
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                            <div
                                className={`${getResourceBarColor(systemStatus.cpu.usage)} h-1.5 rounded-full transition-all duration-500`}
                                style={{ width: `${systemStatus.cpu.usage}%` }}
                            />
                        </div>
                        <p className="text-xs text-gray-600 dark:text-gray-500 mt-2">
                            {systemStatus.cpu.cores} cores
                        </p>
                    </div>

                    {/* Memory */}
                    <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                <Server className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.memory.percentage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            Memory
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                            <div
                                className={`${getResourceBarColor(systemStatus.memory.percentage)} h-1.5 rounded-full transition-all duration-500`}
                                style={{ width: `${systemStatus.memory.percentage}%` }}
                            />
                        </div>
                        <p className="text-xs text-gray-600 dark:text-gray-500 mt-2">
                            {(systemStatus.memory.used / BYTES_PER_GB).toFixed(1)} /{' '}
                            {(systemStatus.memory.total / BYTES_PER_GB).toFixed(1)} GB
                        </p>
                    </div>

                    {/* Disk */}
                    <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-green-100 dark:bg-green-500/10 flex items-center justify-center">
                                <HardDrive className="w-5 h-5 text-green-600 dark:text-green-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.disk.percentage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            Disk Usage
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                            <div
                                className={`${getResourceBarColor(systemStatus.disk.percentage)} h-1.5 rounded-full transition-all duration-500`}
                                style={{ width: `${systemStatus.disk.percentage}%` }}
                            />
                        </div>
                        <p className="text-xs text-gray-600 dark:text-gray-500 mt-2">
                            {(systemStatus.disk.free / BYTES_PER_GB).toFixed(1)} GB free
                        </p>
                    </div>

                    {/* Uptime */}
                    <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                                <Zap className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {Math.floor(systemStatus.uptime.seconds / 3600)}h
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            System Uptime
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-500">
                            {Math.floor((systemStatus.uptime.seconds % 3600) / 60)} minutes running
                        </p>
                    </div>
                </div>
            )}

            {/* ── Container Management ───────────────────────────────────── */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] mb-6 transition-colors duration-200">
                <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <Terminal className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                            </div>
                            <div>
                                <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                    Container Management
                                </h2>
                                <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                                    {runningContainers}/{containers.length} running
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={refresh}
                            className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg transition-colors duration-150 flex items-center gap-2 shadow-sm"
                        >
                            <RotateCw className="w-3.5 h-3.5" />
                            Refresh
                        </button>
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-[#0f1117]">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                                    Container
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                                    Image
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                                    Created
                                </th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wider">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                            {containers.map((container) => (
                                <tr
                                    key={container.id}
                                    className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                >
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                                            {container.name}
                                        </div>
                                        <div className="text-xs text-gray-600 dark:text-gray-500 font-mono mt-0.5">
                                            {container.id.substring(0, 12)}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span
                                            className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${getContainerStatusClasses(container.status)}`}
                                        >
                                            {container.status}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="text-xs font-mono text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] px-2 py-0.5 rounded-md">
                                            {container.image}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                                        {new Date(container.created).toLocaleDateString()}
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center justify-end gap-1.5">
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'start')}
                                                disabled={isLoading || container.status.toLowerCase() === 'running'}
                                                className="p-2 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                aria-label={`Start ${container.name}`}
                                                title="Start"
                                            >
                                                <Play className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'stop')}
                                                disabled={isLoading || container.status.toLowerCase() !== 'running'}
                                                className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                aria-label={`Stop ${container.name}`}
                                                title="Stop"
                                            >
                                                <Square className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'restart')}
                                                disabled={isLoading}
                                                className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                aria-label={`Restart ${container.name}`}
                                                title="Restart"
                                            >
                                                <RotateCw className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'remove')}
                                                disabled={isLoading}
                                                className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                aria-label={`Remove ${container.name}`}
                                                title="Remove"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {containers.length === 0 && (
                        <div className="text-center py-16">
                            <div className="w-14 h-14 bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-xl flex items-center justify-center mx-auto mb-3">
                                <Terminal className="w-6 h-6 text-gray-600 dark:text-gray-500" />
                            </div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                No containers found
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Command History ────────────────────────────────────────── */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <Activity className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                        </div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                            Command History
                        </h2>
                    </div>
                </div>

                <div className="divide-y divide-gray-100 dark:divide-[#1e2535] max-h-[500px] overflow-y-auto">
                    {commandLogs.slice(0, 10).map((log) => (
                        <div
                            key={log.id}
                            className="p-4 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                        >
                            <div className="flex items-center gap-3 mb-1.5">
                                {getCommandStatusIcon(log.status)}
                                <code className="text-sm font-mono text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] px-2 py-0.5 rounded-md flex-1 truncate">
                                    {log.command}
                                </code>
                                <span
                                    className={`text-xs font-medium px-2 py-0.5 rounded-full border shrink-0 ${getCommandStatusClasses(log.status)}`}
                                >
                                    {log.status}
                                </span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-500 ml-7">
                                <span>{new Date(log.timestamp).toLocaleString()}</span>
                                {log.executor && (
                                    <span>
                                        via{' '}
                                        <span className="text-gray-600 dark:text-gray-400">
                                            {log.executor}
                                        </span>
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}

                    {commandLogs.length === 0 && (
                        <div className="text-center py-16">
                            <div className="w-14 h-14 bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-xl flex items-center justify-center mx-auto mb-3">
                                <CheckCircle className="w-6 h-6 text-gray-600 dark:text-gray-500" />
                            </div>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                No command history
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}