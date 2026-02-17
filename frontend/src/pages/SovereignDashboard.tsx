import { useEffect, useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useBackendStore } from '@/store/backendStore';
import {
    Shield,
    Server,
    Activity,
    AlertTriangle,
    Terminal,
    Play,
    Square,
    RotateCw,
    Trash2,
    CheckCircle,
    XCircle,
    Clock,
    Cpu,
    Database,
    HardDrive,
    Zap
} from 'lucide-react';
import { hostAccessApi } from '@/services/hostAccessApi';

interface SystemStatus {
    cpu: {
        usage: number;
        cores: number;
        load: number[];
    };
    memory: {
        total: number;
        used: number;
        free: number;
        percentage: number;
    };
    disk: {
        total: number;
        used: number;
        free: number;
        percentage: number;
    };
    uptime: {
        seconds: number;
        formatted: string;
    };
}

interface Container {
    id: string;
    name: string;
    status: string;
    image: string;
    created: string;
}

interface CommandLog {
    id: string;
    command: string;
    status: 'pending' | 'approved' | 'rejected' | 'executed';
    timestamp: Date;
    executor?: string;
}

export function SovereignDashboard() {
    const { user } = useAuthStore();
    const { status: backendStatus } = useBackendStore();
    const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
    const [containers, setContainers] = useState<Container[]>([]);
    const [commandLogs, setCommandLogs] = useState<CommandLog[]>([]);
    const [selectedContainer, setSelectedContainer] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (backendStatus.status === 'connected') {
            fetchSystemStatus();
            fetchContainers();
            fetchCommandLogs();

            const ws = hostAccessApi.connectWebSocket((data) => {
                if (data.type === 'system_status') {
                    setSystemStatus(data.payload);
                } else if (data.type === 'container_update') {
                    fetchContainers();
                } else if (data.type === 'command_log') {
                    setCommandLogs(prev => [data.payload, ...prev]);
                }
            });

            return () => {
                ws.close();
            };
        }
    }, [backendStatus.status]);

    const fetchSystemStatus = async () => {
        try {
            const data = await hostAccessApi.getSystemStatus();
            setSystemStatus(data);
        } catch (error) {
            console.error('Failed to fetch system status:', error);
        }
    };

    const fetchContainers = async () => {
        try {
            const data = await hostAccessApi.getContainers();
            setContainers(data);
        } catch (error) {
            console.error('Failed to fetch containers:', error);
        }
    };

    const fetchCommandLogs = async () => {
        try {
            const data = await hostAccessApi.getCommandHistory(50);
            setCommandLogs(data);
        } catch (error) {
            console.error('Failed to fetch command logs:', error);
        }
    };

    const handleContainerAction = async (containerId: string, action: 'start' | 'stop' | 'restart' | 'remove') => {
        setIsLoading(true);
        try {
            await hostAccessApi.manageContainer(containerId, action);
            await fetchContainers();
        } catch (error) {
            console.error(`Failed to ${action} container:`, error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleExecuteCommand = async (command: string, params: Record<string, any> = {}) => {
        try {
            await hostAccessApi.executeSovereignCommand(command, params);
            await fetchCommandLogs();
        } catch (error) {
            console.error('Failed to execute command:', error);
        }
    };

    const getStatusColor = (status: string) => {
        switch (status.toLowerCase()) {
            case 'running':
                return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
            case 'stopped':
            case 'exited':
                return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
            case 'paused':
                return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
            default:
                return 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400';
        }
    };

    const getCommandStatusIcon = (status: string) => {
        switch (status) {
            case 'approved':
            case 'executed':
                return <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />;
            case 'rejected':
                return <XCircle className="w-4 h-4 text-red-600 dark:text-red-400" />;
            case 'pending':
                return <Clock className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />;
            default:
                return null;
        }
    };

    const getResourceColor = (value: number) => {
        if (value >= 90) return 'bg-red-600';
        if (value >= 75) return 'bg-yellow-600';
        if (value >= 50) return 'bg-blue-600';
        return 'bg-green-600';
    };

    const colorClasses = {
        blue: {
            bg: 'bg-blue-100 dark:bg-blue-900/30',
            text: 'text-blue-600 dark:text-blue-400'
        },
        green: {
            bg: 'bg-green-100 dark:bg-green-900/30',
            text: 'text-green-600 dark:text-green-400'
        },
        purple: {
            bg: 'bg-purple-100 dark:bg-purple-900/30',
            text: 'text-purple-600 dark:text-purple-400'
        },
        orange: {
            bg: 'bg-orange-100 dark:bg-orange-900/30',
            text: 'text-orange-600 dark:text-orange-400'
        }
    };

    if (!user?.isSovereign) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
                <div className="text-center">
                    <Shield className="w-16 h-16 text-red-600 dark:text-red-400 mx-auto mb-4" />
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-gray-600 dark:text-gray-400">
                        Only Sovereign users can access this dashboard.
                    </p>
                </div>
            </div>
        );
    }

    const runningContainers = containers.filter(c => c.status.toLowerCase() === 'running').length;

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                        Sovereign Control Panel
                    </h1>
                    <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-xs font-semibold rounded-full">
                        ADMIN
                    </span>
                </div>
                <p className="text-gray-600 dark:text-gray-400">
                    Full system access and administrative controls
                </p>
            </div>

            {/* System Status Grid */}
            {systemStatus && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    {/* CPU */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${colorClasses.blue.bg} flex items-center justify-center`}>
                                <Cpu className={`w-6 h-6 ${colorClasses.blue.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.cpu.usage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            CPU Usage
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div
                                className={`${getResourceColor(systemStatus.cpu.usage)} h-2 rounded-full transition-all`}
                                style={{ width: `${systemStatus.cpu.usage}%` }}
                            />
                        </div>
                    </div>

                    {/* Memory */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${colorClasses.purple.bg} flex items-center justify-center`}>
                                <Server className={`w-6 h-6 ${colorClasses.purple.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.memory.percentage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            Memory
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div
                                className={`${getResourceColor(systemStatus.memory.percentage)} h-2 rounded-full transition-all`}
                                style={{ width: `${systemStatus.memory.percentage}%` }}
                            />
                        </div>
                    </div>

                    {/* Disk */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${colorClasses.green.bg} flex items-center justify-center`}>
                                <HardDrive className={`w-6 h-6 ${colorClasses.green.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {systemStatus.disk.percentage.toFixed(1)}%
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            Disk Usage
                        </p>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div
                                className={`${getResourceColor(systemStatus.disk.percentage)} h-2 rounded-full transition-all`}
                                style={{ width: `${systemStatus.disk.percentage}%` }}
                            />
                        </div>
                    </div>

                    {/* Uptime */}
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${colorClasses.orange.bg} flex items-center justify-center`}>
                                <Zap className={`w-6 h-6 ${colorClasses.orange.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {Math.floor(systemStatus.uptime.seconds / 3600)}h
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-3">
                            System Uptime
                        </p>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            {Math.floor((systemStatus.uptime.seconds % 3600) / 60)} minutes running
                        </div>
                    </div>
                </div>
            )}

            {/* Container Management */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 mb-6">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Terminal className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                                Container Management
                            </h2>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                                ({runningContainers}/{containers.length} running)
                            </span>
                        </div>
                        <button
                            onClick={fetchContainers}
                            className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2"
                        >
                            <RotateCw className="w-4 h-4" />
                            Refresh
                        </button>
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full">
                        <thead className="bg-gray-50 dark:bg-gray-900/50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Container
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Image
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Created
                                </th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {containers.map((container) => (
                                <tr key={container.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                                            {container.name}
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                                            {container.id.substring(0, 12)}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(container.status)}`}>
                                            {container.status}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400 font-mono">
                                        {container.image}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-400">
                                        {new Date(container.created).toLocaleDateString()}
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center justify-end gap-2">
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'start')}
                                                disabled={isLoading || container.status === 'running'}
                                                className="p-2 text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/30 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                                title="Start"
                                            >
                                                <Play className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'stop')}
                                                disabled={isLoading || container.status !== 'running'}
                                                className="p-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                                title="Stop"
                                            >
                                                <Square className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'restart')}
                                                disabled={isLoading}
                                                className="p-2 text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/30 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                                title="Restart"
                                            >
                                                <RotateCw className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleContainerAction(container.id, 'remove')}
                                                disabled={isLoading}
                                                className="p-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/30 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                                title="Remove"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {containers.length === 0 && (
                        <div className="text-center py-12">
                            <Terminal className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                            <p className="text-gray-500 dark:text-gray-400">No containers found</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Command History */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3">
                        <Activity className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                            Command History
                        </h2>
                    </div>
                </div>

                <div className="divide-y divide-gray-200 dark:divide-gray-700 max-h-[500px] overflow-y-auto">
                    {commandLogs.slice(0, 10).map((log) => (
                        <div key={log.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                            <div className="flex items-center gap-3 mb-2">
                                {getCommandStatusIcon(log.status)}
                                <code className="text-sm font-mono text-gray-900 dark:text-white bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                                    {log.command}
                                </code>
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                                    log.status === 'executed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                    log.status === 'rejected' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                                    'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                }`}>
                                    {log.status}
                                </span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 ml-7">
                                <span>{new Date(log.timestamp).toLocaleString()}</span>
                                {log.executor && <span>Executor: {log.executor}</span>}
                            </div>
                        </div>
                    ))}
                    {commandLogs.length === 0 && (
                        <div className="text-center py-12">
                            <CheckCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                            <p className="text-gray-500 dark:text-gray-400">No command history</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}