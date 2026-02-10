import { useEffect, useState } from 'react';
import { useBackendStore } from '@/store/backendStore';
import { useAuthStore } from '@/store/authStore';
import {
    Users,
    CheckCircle,
    AlertTriangle,
    Activity,
    Shield,
    Cpu,
    Coins,
    DollarSign
} from 'lucide-react';
import { Link } from 'react-router-dom';
import BudgetControl from '@/components/BudgetControl';

interface Stats {
    totalAgents: number;
    activeAgents: number;
    pendingTasks: number;
    completedTasks: number;
}

export function Dashboard() {
    const { user } = useAuthStore();
    const { status } = useBackendStore();
    const [stats, setStats] = useState<Stats>({
        totalAgents: 0,
        activeAgents: 0,
        pendingTasks: 0,
        completedTasks: 0
    });

    // Fetch stats from backend
    useEffect(() => {
        if (status.status === 'connected') {
            // TODO: Replace with actual API calls
            // Mock data for now
            setStats({
                totalAgents: 5,
                activeAgents: 4,
                pendingTasks: 3,
                completedTasks: 12
            });
        }
    }, [status]);
    const colorClasses = {
        blue: {
            bg: 'bg-blue-100 dark:bg-blue-900/30',
            text: 'text-blue-600 dark:text-blue-400'
        },
        green: {
            bg: 'bg-green-100 dark:bg-green-900/30',
            text: 'text-green-600 dark:text-green-400'
        },
        yellow: {
            bg: 'bg-yellow-100 dark:bg-yellow-900/30',
            text: 'text-yellow-600 dark:text-yellow-400'
        },
        purple: {
            bg: 'bg-purple-100 dark:bg-purple-900/30',
            text: 'text-purple-600 dark:text-purple-400'
        }
    };

    const statCards = [
        {
            title: 'Total Agents',
            value: stats.totalAgents,
            icon: Users,
            color: 'blue',
            link: '/agents'
        },
        {
            title: 'Active Agents',
            value: stats.activeAgents,
            icon: Activity,
            color: 'green',
            link: '/agents'
        },
        {
            title: 'Pending Tasks',
            value: stats.pendingTasks,
            icon: AlertTriangle,
            color: 'yellow',
            link: '/tasks'
        },
        {
            title: 'Completed Tasks',
            value: stats.completedTasks,
            icon: CheckCircle,
            color: 'purple',
            link: '/tasks'
        }
    ];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
            {/* Welcome Header */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                    Welcome, {user?.username}
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                    Oversee your AI governance system from this command center.
                </p>
            </div>

            {/* Connection Warning */}
            {status.status !== 'connected' && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                    <div>
                        <p className="font-medium text-red-900 dark:text-red-300">
                            Backend Disconnected
                        </p>
                        <p className="text-sm text-red-700 dark:text-red-400">
                            Some features may be unavailable. Please check your backend connection.
                        </p>
                    </div>
                </div>
            )}

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                {statCards.map((stat) => (
                    <Link
                        key={stat.title}
                        to={stat.link}
                        className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-lg transition-shadow"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${colorClasses[stat.color].bg} flex items-center justify-center`}>
                                <stat.icon className={`w-6 h-6 ${colorClasses[stat.color].text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {stat.value}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                            {stat.title}
                        </p>
                    </Link>
                ))}
            </div>

            {/* NEW: Budget Control Panel - Full Width */}
            <div className="mb-8">
                <BudgetControl />
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* System Status */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3 mb-4">
                        <Shield className="w-5 h-5 text-blue-600" />
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                            System Status
                        </h2>
                    </div>

                    <div className="space-y-3">
                        <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Backend Status</span>
                            <span className={`text-sm font-medium px-2 py-1 rounded-full ${status.status === 'connected'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                }`}>
                                {status.status === 'connected' ? 'Healthy' : 'Disconnected'}
                            </span>
                        </div>

                        <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700">
                            <span className="text-sm text-gray-600 dark:text-gray-400">API Latency</span>
                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                                {status.latency ? `${status.latency}ms` : 'N/A'}
                            </span>
                        </div>

                        <div className="flex items-center justify-between py-2">
                            <span className="text-sm text-gray-600 dark:text-gray-400">Constitution Version</span>
                            <span className="text-sm font-medium text-gray-900 dark:text-white">v1.0.0</span>
                        </div>
                    </div>
                </div>

                {/* Quick Actions */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-3 mb-4">
                        <Cpu className="w-5 h-5 text-purple-600" />
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                            Quick Actions
                        </h2>
                    </div>

                    <div className="space-y-3">
                        <Link
                            to="/agents"
                            className="block w-full text-left px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                        >
                            <p className="font-medium text-gray-900 dark:text-white">Manage Agents</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">View and spawn new agents</p>
                        </Link>

                        <Link
                            to="/models"
                            className="block w-full text-left px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                        >
                            <p className="font-medium text-gray-900 dark:text-white">Configure AI Models</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">Set up API keys and providers</p>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}