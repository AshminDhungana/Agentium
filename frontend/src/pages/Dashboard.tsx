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
    ChevronRight,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import BudgetControl from '@/components/BudgetControl';
import { api } from '@/services/api';

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
    const [isLoadingStats, setIsLoadingStats] = useState(false);

    useEffect(() => {
        if (status.status === 'connected') {
            fetchStats();
        } else {
            setStats({ totalAgents: 0, activeAgents: 0, pendingTasks: 0, completedTasks: 0 });
        }
    }, [status]);

    const fetchStats = async () => {
        setIsLoadingStats(true);
        try {
            const [agentsRes, tasksRes] = await Promise.allSettled([
                api.get('/api/v1/agents'),
                api.get('/api/v1/tasks/'),
            ]);

            let totalAgents = 0;
            let activeAgents = 0;
            if (agentsRes.status === 'fulfilled') {
                const agents: any[] = Array.isArray(agentsRes.value.data)
                    ? agentsRes.value.data
                    : agentsRes.value.data?.agents ?? [];
                totalAgents = agents.length;
                activeAgents = agents.filter(
                    (a: any) => a.status === 'active' || a.status === 'working'
                ).length;
            }

            let pendingTasks = 0;
            let completedTasks = 0;
            if (tasksRes.status === 'fulfilled') {
                const tasks: any[] = Array.isArray(tasksRes.value.data)
                    ? tasksRes.value.data
                    : tasksRes.value.data?.tasks ?? [];
                pendingTasks = tasks.filter(
                    (t: any) => t.status === 'pending' || t.status === 'deliberating'
                ).length;
                completedTasks = tasks.filter(
                    (t: any) => t.status === 'completed'
                ).length;
            }

            setStats({ totalAgents, activeAgents, pendingTasks, completedTasks });
        } catch (err) {
            console.error('Failed to fetch dashboard stats:', err);
        } finally {
            setIsLoadingStats(false);
        }
    };

    const colorClasses = {
        blue: {
            bg:       'bg-blue-100 dark:bg-blue-500/10',
            text:     'text-blue-600 dark:text-blue-400',
            border:   'dark:border-blue-500/15',
        },
        green: {
            bg:       'bg-green-100 dark:bg-green-500/10',
            text:     'text-green-600 dark:text-green-400',
            border:   'dark:border-green-500/15',
        },
        yellow: {
            bg:       'bg-yellow-100 dark:bg-yellow-500/10',
            text:     'text-yellow-600 dark:text-yellow-400',
            border:   'dark:border-yellow-500/15',
        },
        purple: {
            bg:       'bg-purple-100 dark:bg-purple-500/10',
            text:     'text-purple-600 dark:text-purple-400',
            border:   'dark:border-purple-500/15',
        },
    };

    const statCards = [
        { title: 'Total Agents',    value: stats.totalAgents,    icon: Users,        color: 'blue',   link: '/agents' },
        { title: 'Active Agents',   value: stats.activeAgents,   icon: Activity,     color: 'green',  link: '/agents' },
        { title: 'Pending Tasks',   value: stats.pendingTasks,   icon: AlertTriangle,color: 'yellow', link: '/tasks'  },
        { title: 'Completed Tasks', value: stats.completedTasks, icon: CheckCircle,  color: 'purple', link: '/tasks'  },
    ];

    return (
        <div className="h-full bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">

            {/* ── Welcome Header ─────────────────────────────────────────── */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                    Welcome, {user?.username}
                </h1>
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                    Oversee your AI governance system from this command center.
                </p>
            </div>

            {/* ── Connection Warning ─────────────────────────────────────── */}
            {status.status !== 'connected' && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
                    <div>
                        <p className="font-medium text-red-900 dark:text-red-300 text-sm">
                            Backend Disconnected
                        </p>
                        <p className="text-sm text-red-700 dark:text-red-400/80">
                            Some features may be unavailable. Please check your backend connection.
                        </p>
                    </div>
                </div>
            )}

            {/* ── Stats Grid ─────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
                {statCards.map((stat) => {
                    const c = colorClasses[stat.color as keyof typeof colorClasses];
                    return (
                        <Link
                            key={stat.title}
                            to={stat.link}
                            className="group bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150"
                        >
                            <div className="flex items-center justify-between mb-4">
                                <div className={`w-11 h-11 rounded-lg ${c.bg} flex items-center justify-center transition-colors duration-200`}>
                                    <stat.icon className={`w-5 h-5 ${c.text}`} />
                                </div>
                                <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                    {isLoadingStats ? (
                                        <span className="inline-block w-7 h-6 rounded bg-gray-200 dark:bg-[#1e2535] animate-pulse" />
                                    ) : (
                                        stat.value
                                    )}
                                </span>
                            </div>
                            <p className="text-sm font-medium text-gray-500 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-300 transition-colors duration-150">
                                {stat.title}
                            </p>
                        </Link>
                    );
                })}
            </div>

            {/* ── Budget Control Panel ───────────────────────────────────── */}
            <div className="mb-8">
                <BudgetControl />
            </div>

            {/* ── Bottom Panels ──────────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* System Status */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-5">
                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Shield className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        </div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                            System Status
                        </h2>
                    </div>

                    <div className="space-y-0 divide-y divide-gray-100 dark:divide-[#1e2535]">
                        <div className="flex items-center justify-between py-3">
                            <span className="text-sm text-gray-500 dark:text-gray-400">Backend Status</span>
                            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                                status.status === 'connected'
                                    ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                    : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
                            }`}>
                                {status.status === 'connected' ? 'Healthy' : 'Disconnected'}
                            </span>
                        </div>

                        <div className="flex items-center justify-between py-3">
                            <span className="text-sm text-gray-500 dark:text-gray-400">API Latency</span>
                            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                {status.latency ? `${status.latency}ms` : 'N/A'}
                            </span>
                        </div>

                        <div className="flex items-center justify-between py-3">
                            <span className="text-sm text-gray-500 dark:text-gray-400">Constitution Version</span>
                            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/20">
                                v1.0.0
                            </span>
                        </div>
                    </div>
                </div>

                {/* Quick Actions */}
                <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-5">
                        <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <Cpu className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                        </div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                            Quick Actions
                        </h2>
                    </div>

                    <div className="space-y-2">
                        <Link
                            to="/agents"
                            className="group flex items-center justify-between w-full px-4 py-3.5 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-transparent hover:bg-gray-50 dark:hover:bg-[#0f1117] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                        >
                            <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Manage Agents</p>
                                <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">View and spawn new agents</p>
                            </div>
                            <ChevronRight className="w-4 h-4 text-gray-400 dark:text-gray-600 group-hover:text-gray-600 dark:group-hover:text-gray-400 transition-colors duration-150 flex-shrink-0" />
                        </Link>

                        <Link
                            to="/models"
                            className="group flex items-center justify-between w-full px-4 py-3.5 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-transparent hover:bg-gray-50 dark:hover:bg-[#0f1117] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                        >
                            <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Configure AI Models</p>
                                <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">Set up API keys and providers</p>
                            </div>
                            <ChevronRight className="w-4 h-4 text-gray-400 dark:text-gray-600 group-hover:text-gray-600 dark:group-hover:text-gray-400 transition-colors duration-150 flex-shrink-0" />
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
