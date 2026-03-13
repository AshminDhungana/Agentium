// src/pages/SovereignDashboard.tsx

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useBackendStore } from '@/store/backendStore';
import {
    Shield,
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
    Wrench,
    DollarSign,
    BookOpen,
    Store,
    Network,
    Users,
    Smartphone,
    Lock,
    Webhook,
    Code,
} from 'lucide-react';
import { hostAccessApi } from '@/services/hostAccessApi';
import { MCPToolRegistry } from '@/components/mcp/MCPToolRegistry';
import { FinancialBurnDashboard } from '@/components/dashboard/FinancialBurnDashboard';
import { SkillsPage } from './SkillsPage';
import ToolMarketplacePage from './ToolMarketplacePage';
import FederationPage from './FederationPage';
import MobilePage from './MobilePage';
import RBACManagementPage from './RBACManagement';
import WebhookManagementPage from './WebhookManagementPage';
import DeveloperPortalPage from './DeveloperPortalPage';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SystemStatus {
    cpu: { usage: number; cores: number; load: number[] };
    memory: { total: number; used: number; free: number; percentage: number };
    disk: { total: number; used: number; free: number; percentage: number };
    uptime: { seconds: number; formatted: string };
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

// ── Tab definitions ───────────────────────────────────────────────────────────

type TabId =
    | 'system'
    | 'mcp-tools'
    | 'financial-burn'
    | 'skills'
    | 'tools-marketplace'
    | 'federation'
    | 'rbac'
    | 'mobile'
    | 'webhooks'
    | 'developer-portal';

interface Tab {
    id: TabId;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    description: string;
    badge?: string;
}

const TABS: Tab[] = [
    {
        id: 'system',
        label: 'System',
        icon: Terminal,
        description: 'Containers, resources, and command history',
    },
    {
        id: 'mcp-tools',
        label: 'MCP Tools',
        icon: Wrench,
        description: 'Constitutional MCP server governance',
        badge: '1.0',
    },
    {
        id: 'financial-burn',
        label: 'Financial',
        icon: DollarSign,
        description: 'Token usage, cost burn rate, and completion stats',
    },
    {
        id: 'skills',
        label: 'Knowledge',
        icon: BookOpen,
        description: 'Search and manage reusable skills and knowledge snippets',
    },
    {
        id: 'tools-marketplace',
        label: 'Marketplace',
        icon: Store,
        description: 'Browse, publish, and manage tools in the marketplace',
    },
    {
        id: 'federation',
        label: 'Federation',
        icon: Network,
        description: 'Peer instances, cross-instance task delegation, and knowledge sharing',
    },
    {
        id: 'rbac',
        label: 'Access Control',
        icon: Lock,
        description: 'Manage user roles, capabilities, and delegations',
    },
    {
        id: 'mobile',
        label: 'Mobile',
        icon: Smartphone,
        description: 'Devices, push notifications, and offline sync settings',
    },
    {
        id: 'webhooks',
        label: 'Webhooks',
        icon: Webhook,
        description: 'Manage outbound event webhook subscriptions and delivery logs',
        badge: 'NEW',
    },
    {
        id: 'developer-portal',
        label: 'Dev Portal',
        icon: Code,
        description: 'API documentation, code samples, and webhook event reference',
        badge: 'NEW',
    },
];

// ── Helper: status badge colours ─────────────────────────────────────────────

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

// ── Main Component ─────────────────────────────────────────────────────────────

export function SovereignDashboard() {
    const { user } = useAuthStore();
    const { status: backendStatus } = useBackendStore();

    const [activeTab, setActiveTab] = useState<TabId>('system');
    const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
    const [containers, setContainers] = useState<Container[]>([]);
    const [commandLogs, setCommandLogs] = useState<CommandLog[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        if (backendStatus.status === 'connected') {
            fetchSystemStatus();
            fetchContainers();
            fetchCommandLogs();

            const ws = hostAccessApi.connectWebSocket((data: any) => {
                if (data.type === 'system_status') setSystemStatus(data.payload);
                else if (data.type === 'container_update') fetchContainers();
                else if (data.type === 'command_log')
                    setCommandLogs((prev) => [data.payload, ...prev]);
            });

            return () => {
                ws.close();
            };
        }
    }, [backendStatus.status]);

    const fetchSystemStatus = async () => {
        try {
            setSystemStatus(await hostAccessApi.getSystemStatus());
        } catch (error) {
            console.error('Failed to fetch system status:', error);
        }
    };

    const fetchContainers = async () => {
        try {
            setContainers(await hostAccessApi.getContainers());
        } catch (error) {
            console.error('Failed to fetch containers:', error);
        }
    };

    const fetchCommandLogs = async () => {
        try {
            setCommandLogs(await hostAccessApi.getCommandHistory(50));
        } catch (error) {
            console.error('Failed to fetch command logs:', error);
        }
    };

    const handleContainerAction = async (
        containerId: string,
        action: 'start' | 'stop' | 'restart' | 'remove',
    ) => {
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

    // ── Access denied ────────────────────────────────────────────────────────

    // Use is_admin as the sovereign gate (matches backend User model)
    if (!user?.is_admin) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6 transition-colors duration-200">
                <div className="text-center">
                    <div className="w-20 h-20 bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-2xl flex items-center justify-center mx-auto mb-5 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
                        <Shield className="w-9 h-9 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Only Sovereign users can access this dashboard.
                    </p>
                </div>
            </div>
        );
    }

    const runningContainers = containers.filter(
        (c) => c.status.toLowerCase() === 'running',
    ).length;

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">

            {/* ── Page Header ─────────────────────────────────────────────── */}
            <div className="mb-6">
                <div className="flex items-center gap-3 mb-1">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                        Sovereign Control Panel
                    </h1>
                    <span className="px-2.5 py-0.5 bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 text-xs font-semibold rounded-full border border-blue-200 dark:border-blue-500/20">
                        ADMIN
                    </span>
                </div>
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                    Full system access and administrative controls.
                </p>
            </div>

            {/* ── Tab navigation ───────────────────────────────────────────── */}
            <div className="mb-6">
                <div className="flex flex-wrap gap-1 p-1 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] w-fit shadow-sm">
                    {TABS.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = activeTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`
                                    flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium
                                    transition-all duration-200
                                    ${isActive
                                        ? 'bg-blue-600 text-white shadow-sm'
                                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
                                    }
                                `}
                            >
                                <Icon className="w-4 h-4" />
                                {tab.label}
                                {tab.badge && (
                                    <span className={`
                                        px-1.5 py-0.5 text-xs rounded-full font-semibold
                                        ${isActive
                                            ? 'bg-white/20 text-white'
                                            : 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400'
                                        }
                                    `}>
                                        {tab.badge}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>
                <p className="mt-2 ml-1 text-xs text-gray-400 dark:text-gray-500">
                    {TABS.find((t) => t.id === activeTab)?.description}
                </p>
            </div>

            {/* ── MCP Tools Tab ────────────────────────────────────────────── */}
            {activeTab === 'mcp-tools' && <MCPToolRegistry />}

            {/* ── Financial & Burn Rate Tab ────────────────────────────────── */}
            {activeTab === 'financial-burn' && <FinancialBurnDashboard />}

            {/* ── Skills / Knowledge Library Tab ───────────────────────────── */}
            {activeTab === 'skills' && <SkillsPage />}

            {/* ── Tool Marketplace Tab ─────────────────────────────────────── */}
            {activeTab === 'tools-marketplace' && <ToolMarketplacePage embedded />}

            {/* ── Federation Tab ───────────────────────────────────────────── */}
            {activeTab === 'federation' && <FederationPage />}

            {/* ── RBAC / Access Control Tab ────────────────────────────────── */}
            {activeTab === 'rbac' && <RBACManagementPage />}

            {/* ── Mobile Tab ───────────────────────────────────────────────── */}
            {activeTab === 'mobile' && <MobilePage />}

            {/* ── Webhooks Tab (Phase 12) ────────────────────────────────────── */}
            {activeTab === 'webhooks' && <WebhookManagementPage />}

            {/* ── Developer Portal Tab (Phase 12) ───────────────────────────── */}
            {activeTab === 'developer-portal' && <DeveloperPortalPage />}

            {/* ── System Control Tab ───────────────────────────────────────── */}
            {activeTab === 'system' && (
                <>
                    {/* System Status Grid */}
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
                                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                                    CPU Usage
                                </p>
                                <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                                    <div
                                        className={`${getResourceBarColor(systemStatus.cpu.usage)} h-1.5 rounded-full transition-all duration-500`}
                                        style={{ width: `${systemStatus.cpu.usage}%` }}
                                    />
                                </div>
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
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
                                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                                    Memory
                                </p>
                                <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                                    <div
                                        className={`${getResourceBarColor(systemStatus.memory.percentage)} h-1.5 rounded-full transition-all duration-500`}
                                        style={{ width: `${systemStatus.memory.percentage}%` }}
                                    />
                                </div>
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                                    {(systemStatus.memory.used / 1024).toFixed(1)} /{' '}
                                    {(systemStatus.memory.total / 1024).toFixed(1)} GB
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
                                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                                    Disk Usage
                                </p>
                                <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5">
                                    <div
                                        className={`${getResourceBarColor(systemStatus.disk.percentage)} h-1.5 rounded-full transition-all duration-500`}
                                        style={{ width: `${systemStatus.disk.percentage}%` }}
                                    />
                                </div>
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                                    {(systemStatus.disk.free / 1024).toFixed(0)} GB free
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
                                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">
                                    System Uptime
                                </p>
                                <p className="text-xs text-gray-400 dark:text-gray-500">
                                    {Math.floor((systemStatus.uptime.seconds % 3600) / 60)} minutes
                                    running
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Container Management */}
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
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                            {runningContainers}/{containers.length} running
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={fetchContainers}
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
                                                <div className="text-xs text-gray-400 dark:text-gray-500 font-mono mt-0.5">
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
                                            <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                                {new Date(container.created).toLocaleDateString()}
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center justify-end gap-1.5">
                                                    <button
                                                        onClick={() =>
                                                            handleContainerAction(container.id, 'start')
                                                        }
                                                        disabled={
                                                            isLoading ||
                                                            container.status.toLowerCase() === 'running'
                                                        }
                                                        className="p-2 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                        title="Start"
                                                    >
                                                        <Play className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button
                                                        onClick={() =>
                                                            handleContainerAction(container.id, 'stop')
                                                        }
                                                        disabled={
                                                            isLoading ||
                                                            container.status.toLowerCase() !== 'running'
                                                        }
                                                        className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                        title="Stop"
                                                    >
                                                        <Square className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button
                                                        onClick={() =>
                                                            handleContainerAction(container.id, 'restart')
                                                        }
                                                        disabled={isLoading}
                                                        className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
                                                        title="Restart"
                                                    >
                                                        <RotateCw className="w-3.5 h-3.5" />
                                                    </button>
                                                    <button
                                                        onClick={() =>
                                                            handleContainerAction(container.id, 'remove')
                                                        }
                                                        disabled={isLoading}
                                                        className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-150"
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
                                        <Terminal className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        No containers found
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Command History */}
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
                                    <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500 ml-7">
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
                                        <CheckCircle className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        No command history
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}