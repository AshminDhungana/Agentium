// src/pages/SovereignDashboard.tsx

import { useState, useRef, useEffect } from 'react';
import { useAuthStore } from '@/store/authStore';
import {
    Shield,
    Terminal,
    Wrench,
    DollarSign,
    BookOpen,
    Store,
    Network,
    Smartphone,
    Lock,
    Webhook,
    Code,
    TrendingUp,
    Sparkles,
    Zap,
} from 'lucide-react';
import { SystemTab } from '@/components/sovereign/SystemTab';
import { MCPToolRegistry } from '@/components/mcp/MCPToolRegistry';
import { FinancialBurnDashboard } from '@/components/dashboard/FinancialBurnDashboard';
import { SkillsPage } from './SkillsPage';
import ToolMarketplacePage from './ToolMarketplacePage';
import FederationPage from './FederationPage';
import MobilePage from './MobilePage';
import RBACManagementPage from './RBACManagement';
import WebhookManagementPage from './WebhookManagementPage';
import DeveloperPortalPage from './DeveloperPortalPage';
import { ScalingDashboard } from './ScalingDashboard';
import { LearningImpactDashboard } from './LearningImpactDashboard';
import { EventTriggerManager } from '@/components/sovereign/EventTriggerManager';

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
    | 'developer-portal'
    | 'scaling'
    | 'improve'
    | 'events';

interface Tab {
    id: TabId;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    description: string;
    badge?: string;
}

const TABS: Tab[] = [
    // ── Monitor ──────────────────────────────────────────────────────────────
    {
        id: 'system',
        label: 'System',
        icon: Terminal,
        description: 'Containers, resources, and command history',
    },
    {
        id: 'financial-burn',
        label: 'Financial',
        icon: DollarSign,
        description: 'Token usage, cost burn rate, and completion stats',
    },
    {
        id: 'scaling',
        label: 'Auto-Scaling',
        icon: TrendingUp,
        description: 'Predictive agent capacity scaling and manual overrides',
    },
    // ── Configure ─────────────────────────────────────────────────────────────
    {
        id: 'mcp-tools',
        label: 'MCP Tools',
        icon: Wrench,
        description: 'Constitutional MCP server governance',
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
    // ── Secure ────────────────────────────────────────────────────────────────
    {
        id: 'rbac',
        label: 'Access Control',
        icon: Lock,
        description: 'Manage user roles, capabilities, and delegations',
    },
    {
        id: 'federation',
        label: 'Federation',
        icon: Network,
        description: 'Peer instances, cross-instance task delegation, and knowledge sharing',
    },
    // ── Integrate ─────────────────────────────────────────────────────────────
    {
        id: 'webhooks',
        label: 'Webhooks',
        icon: Webhook,
        description: 'Manage outbound event webhook subscriptions and delivery logs',
    },
    {
        id: 'developer-portal',
        label: 'Dev Portal',
        icon: Code,
        description: 'API documentation, code samples, and webhook event reference',
    },
    {
        id: 'mobile',
        label: 'Mobile',
        icon: Smartphone,
        description: 'Devices, push notifications, and offline sync settings',
    },
    // ── Automate ──────────────────────────────────────────────────────────────
    {
        id: 'events',
        label: 'Events',
        icon: Zap,
        description: 'Intelligent event processing — webhooks, thresholds, API polling, and dead-letter management',
    },
    // ── Optimize ──────────────────────────────────────────────────────────────
    {
        id: 'improve',
        label: 'Self-Improvement',
        icon: Sparkles,
        description: 'Learning patterns and task optimization telemetry',
    },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function SovereignDashboard() {
    const { user } = useAuthStore();
    const [activeTab, setActiveTab] = useState<TabId>('system');
    const tabNavRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const el = tabNavRef.current;
        if (!el) return;
        const onWheel = (e: WheelEvent) => {
            if (e.deltaY === 0) return;
            e.preventDefault();
            el.scrollLeft += e.deltaY;
        };
        el.addEventListener('wheel', onWheel, { passive: false });
        return () => el.removeEventListener('wheel', onWheel);
    }, []);

    // ── Access denied ────────────────────────────────────────────────────────
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
                <div
                    ref={tabNavRef}
                    className="w-fit max-w-full overflow-x-auto rounded-xl border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] shadow-sm [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-gray-300 dark:[&::-webkit-scrollbar-thumb]:bg-[#2a3347] [&::-webkit-scrollbar-thumb]:rounded-full"
                >
                    <div className="flex gap-1 p-1 min-w-max">
                        {TABS.map((tab) => {
                            const Icon = tab.icon;
                            const isActive = activeTab === tab.id;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`
                                        flex items-center gap-2 px-3.5 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap
                                        transition-all duration-200
                                        ${isActive
                                            ? 'bg-blue-600 text-white shadow-sm'
                                            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
                                        }
                                    `}
                                >
                                    <Icon className="w-4 h-4 shrink-0" />
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
                </div>
                <p className="mt-2 ml-1 text-xs text-gray-400 dark:text-gray-500">
                    {TABS.find((t) => t.id === activeTab)?.description}
                </p>
            </div>

            {/* ── Tab content ──────────────────────────────────────────────── */}
            <div>
                {activeTab === 'system'           && <SystemTab />}
                {activeTab === 'mcp-tools'        && <MCPToolRegistry />}
                {activeTab === 'financial-burn'   && <FinancialBurnDashboard />}
                {activeTab === 'skills'           && <SkillsPage />}
                {activeTab === 'tools-marketplace'&& <ToolMarketplacePage embedded />}
                {activeTab === 'federation'       && <FederationPage />}
                {activeTab === 'rbac'             && <RBACManagementPage />}
                {activeTab === 'mobile'           && <MobilePage />}
                {activeTab === 'webhooks'         && <WebhookManagementPage />}
                {activeTab === 'developer-portal' && <DeveloperPortalPage />}
                {activeTab === 'scaling'          && <ScalingDashboard />}
                {activeTab === 'improve'          && <LearningImpactDashboard />}
                {activeTab === 'events'           && <EventTriggerManager />}
            </div>
        </div>
    );
}