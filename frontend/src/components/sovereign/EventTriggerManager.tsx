// src/components/sovereign/EventTriggerManager.tsx
// Phase 13.6 — Intelligent Event Processing UI
// Integrated as a tab inside SovereignDashboard.tsx

import React, { useState, useEffect, useCallback } from 'react';
import {
    Zap,
    Plus,
    Trash2,
    Play,
    Pause,
    Webhook,
    Activity,
    AlertTriangle,
    BarChart3,
    Globe,
    Clock,
    X,
    Loader2,
    CheckCircle,
    XCircle,
    RefreshCw,
    ChevronDown,
    ChevronRight,
    Copy,
    Eye,
    RotateCcw,
    Search,
    Filter,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface EventTrigger {
    id: string;
    agentium_id: string;
    name: string;
    trigger_type: 'webhook' | 'schedule' | 'threshold' | 'api_poll';
    config: Record<string, any>;
    target_workflow_id: string | null;
    target_agent_id: string | null;
    is_active: boolean;
    last_fired_at: string | null;
    fire_count: number;
    max_fires_per_minute: number;
    pause_duration_seconds: number;
    paused_until: string | null;
    created_at: string;
}

interface EventLog {
    id: string;
    agentium_id: string;
    trigger_id: string;
    event_payload: Record<string, any>;
    status: 'processed' | 'dead_letter' | 'duplicate';
    correlation_id: string | null;
    error: string | null;
    retry_count: number;
    created_at: string;
}

// ── API Helpers ───────────────────────────────────────────────────────────────

const API_BASE = '/api/v1/events';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options?.headers,
        },
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
    }
    return res.json();
}

// ── Trigger Type Config ───────────────────────────────────────────────────────

const TRIGGER_TYPE_META: Record<
    string,
    { label: string; icon: React.ComponentType<{ className?: string }>; color: string; bgColor: string; borderColor: string }
> = {
    webhook: {
        label: 'Webhook',
        icon: Webhook,
        color: 'text-purple-600 dark:text-purple-400',
        bgColor: 'bg-purple-100 dark:bg-purple-500/10',
        borderColor: 'border-purple-200 dark:border-purple-500/20',
    },
    schedule: {
        label: 'Schedule',
        icon: Clock,
        color: 'text-blue-600 dark:text-blue-400',
        bgColor: 'bg-blue-100 dark:bg-blue-500/10',
        borderColor: 'border-blue-200 dark:border-blue-500/20',
    },
    threshold: {
        label: 'Threshold',
        icon: BarChart3,
        color: 'text-amber-600 dark:text-amber-400',
        bgColor: 'bg-amber-100 dark:bg-amber-500/10',
        borderColor: 'border-amber-200 dark:border-amber-500/20',
    },
    api_poll: {
        label: 'API Poll',
        icon: Globe,
        color: 'text-emerald-600 dark:text-emerald-400',
        bgColor: 'bg-emerald-100 dark:bg-emerald-500/10',
        borderColor: 'border-emerald-200 dark:border-emerald-500/20',
    },
};

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
    processed: {
        label: 'Processed',
        cls: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
    },
    dead_letter: {
        label: 'Dead Letter',
        cls: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
    },
    duplicate: {
        label: 'Duplicate',
        cls: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-500/10 dark:text-gray-400 dark:border-gray-500/20',
    },
};

// ── Component ─────────────────────────────────────────────────────────────────

export const EventTriggerManager: React.FC = () => {
    // ── State ────────────────────────────────────────────────────────────────
    const [triggers, setTriggers] = useState<EventTrigger[]>([]);
    const [logs, setLogs] = useState<EventLog[]>([]);
    const [deadLetters, setDeadLetters] = useState<EventLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeSubTab, setActiveSubTab] = useState<'triggers' | 'logs' | 'dead-letters'>('triggers');
    const [showCreate, setShowCreate] = useState(false);
    const [expandedTrigger, setExpandedTrigger] = useState<string | null>(null);
    const [logFilter, setLogFilter] = useState<string>('');
    const [logStatusFilter, setLogStatusFilter] = useState<string>('');
    const [retrying, setRetrying] = useState<string | null>(null);

    // Form state
    const [formName, setFormName] = useState('');
    const [formType, setFormType] = useState<'webhook' | 'threshold' | 'api_poll' | 'schedule'>('webhook');
    const [formConfig, setFormConfig] = useState<Record<string, any>>({});
    const [formWorkflowId, setFormWorkflowId] = useState('');

    // ── Data loading ─────────────────────────────────────────────────────────
    const loadTriggers = useCallback(async () => {
        try {
            const data = await apiFetch<EventTrigger[]>('/triggers');
            setTriggers(data);
        } catch (err) {
            console.error('Failed to load triggers:', err);
        }
    }, []);

    const loadLogs = useCallback(async () => {
        try {
            let path = '/logs?limit=100';
            if (logStatusFilter) path += `&status=${logStatusFilter}`;
            const data = await apiFetch<EventLog[]>(path);
            setLogs(data);
        } catch (err) {
            console.error('Failed to load logs:', err);
        }
    }, [logStatusFilter]);

    const loadDeadLetters = useCallback(async () => {
        try {
            const data = await apiFetch<EventLog[]>('/dead-letters?limit=50');
            setDeadLetters(data);
        } catch (err) {
            console.error('Failed to load dead letters:', err);
        }
    }, []);

    useEffect(() => {
        setLoading(true);
        Promise.all([loadTriggers(), loadLogs(), loadDeadLetters()]).finally(() =>
            setLoading(false),
        );
    }, [loadTriggers, loadLogs, loadDeadLetters]);

    // ── Trigger actions ──────────────────────────────────────────────────────
    const handleCreate = async () => {
        if (!formName || !formType) return;
        try {
            await apiFetch<EventTrigger>('/triggers', {
                method: 'POST',
                body: JSON.stringify({
                    name: formName,
                    trigger_type: formType,
                    config: formConfig,
                    target_workflow_id: formWorkflowId || null,
                }),
            });
            setShowCreate(false);
            setFormName('');
            setFormType('webhook');
            setFormConfig({});
            setFormWorkflowId('');
            await loadTriggers();
        } catch (err) {
            console.error('Failed to create trigger:', err);
        }
    };

    const handleToggle = async (trigger: EventTrigger) => {
        try {
            await apiFetch(`/triggers/${trigger.id}`, {
                method: 'PUT',
                body: JSON.stringify({ is_active: !trigger.is_active }),
            });
            await loadTriggers();
        } catch (err) {
            console.error('Toggle failed:', err);
        }
    };

    const handleDelete = async (id: string) => {
        if (!window.confirm('Deactivate this event trigger?')) return;
        try {
            await apiFetch(`/triggers/${id}`, { method: 'DELETE' });
            await loadTriggers();
        } catch (err) {
            console.error('Delete failed:', err);
        }
    };

    const handleRetry = async (logId: string) => {
        setRetrying(logId);
        try {
            await apiFetch(`/dead-letters/${logId}/retry`, { method: 'POST' });
            await loadDeadLetters();
        } catch (err) {
            console.error('Retry failed:', err);
        } finally {
            setRetrying(null);
        }
    };

    // ── Dynamic config fields based on trigger type ──────────────────────────
    const renderConfigFields = () => {
        switch (formType) {
            case 'webhook':
                return (
                    <div className="space-y-3">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                HMAC Secret (auto-generated if empty)
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                placeholder="Leave empty to auto-generate"
                                value={formConfig.hmac_secret || ''}
                                onChange={(e) => setFormConfig({ ...formConfig, hmac_secret: e.target.value })}
                            />
                        </div>
                    </div>
                );
            case 'threshold':
                return (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Metric Key
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                placeholder="e.g. pending_tasks"
                                value={formConfig.metric || ''}
                                onChange={(e) => setFormConfig({ ...formConfig, metric: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Operator
                            </label>
                            <select
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-amber-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                title="Select comparison operator"
                                value={formConfig.operator || 'gt'}
                                onChange={(e) => setFormConfig({ ...formConfig, operator: e.target.value })}
                            >
                                <option value="gt">&gt; Greater Than</option>
                                <option value="gte">≥ Greater or Equal</option>
                                <option value="lt">&lt; Less Than</option>
                                <option value="lte">≤ Less or Equal</option>
                                <option value="eq">= Equal</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Value
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                type="number"
                                placeholder="10"
                                value={formConfig.value ?? ''}
                                onChange={(e) => setFormConfig({ ...formConfig, value: parseFloat(e.target.value) })}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Cooldown (seconds)
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                type="number"
                                placeholder="60"
                                value={formConfig.cooldown_seconds ?? ''}
                                onChange={(e) =>
                                    setFormConfig({ ...formConfig, cooldown_seconds: parseInt(e.target.value) })
                                }
                            />
                        </div>
                    </div>
                );
            case 'api_poll':
                return (
                    <div className="space-y-3">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                URL to Poll
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                type="url"
                                placeholder="https://api.example.com/status"
                                value={formConfig.url || ''}
                                onChange={(e) => setFormConfig({ ...formConfig, url: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Poll Interval (seconds)
                            </label>
                            <input
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                type="number"
                                placeholder="60"
                                value={formConfig.poll_interval_seconds ?? ''}
                                onChange={(e) =>
                                    setFormConfig({ ...formConfig, poll_interval_seconds: parseInt(e.target.value) })
                                }
                            />
                        </div>
                    </div>
                );
            case 'schedule':
                return (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            Cron Expression
                        </label>
                        <input
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm font-mono transition-colors duration-150 outline-none"
                            placeholder="*/5 * * * *"
                            value={formConfig.cron_expression || ''}
                            onChange={(e) => setFormConfig({ ...formConfig, cron_expression: e.target.value })}
                        />
                        <p className="text-xs text-gray-400 mt-1">e.g., "*/5 * * * *" for every 5 minutes</p>
                    </div>
                );
        }
    };

    // ── Loading ──────────────────────────────────────────────────────────────
    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center p-16">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400 mb-4" />
                <p className="text-sm text-gray-500 dark:text-gray-400">Loading event processing…</p>
            </div>
        );
    }

    // ── Render ───────────────────────────────────────────────────────────────
    return (
        <div className="space-y-6">
            {/* ── Header ──────────────────────────────────────────────────── */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <div className="flex items-center gap-3 mb-1">
                        <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-purple-600 dark:from-indigo-400 dark:to-purple-400">
                            Intelligent Event Processing
                        </h2>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Automatically react to webhooks, threshold breaches, and external API changes.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => {
                            loadTriggers();
                            loadLogs();
                            loadDeadLetters();
                        }}
                        className="px-3 py-2 text-sm font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                    >
                        <RefreshCw className="w-4 h-4" /> Refresh
                    </button>
                </div>
            </div>

            {/* ── KPI Cards ───────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    {
                        label: 'Active Triggers',
                        value: triggers.filter((t) => t.is_active).length,
                        total: triggers.length,
                        icon: Zap,
                        color: 'text-indigo-600 dark:text-indigo-400',
                        bg: 'bg-indigo-100 dark:bg-indigo-500/10',
                        border: 'border-indigo-200 dark:border-indigo-500/20',
                    },
                    {
                        label: 'Total Events',
                        value: triggers.reduce((sum, t) => sum + t.fire_count, 0),
                        icon: Activity,
                        color: 'text-green-600 dark:text-green-400',
                        bg: 'bg-green-100 dark:bg-green-500/10',
                        border: 'border-green-200 dark:border-green-500/20',
                    },
                    {
                        label: 'Dead Letters',
                        value: deadLetters.length,
                        icon: AlertTriangle,
                        color: 'text-red-600 dark:text-red-400',
                        bg: 'bg-red-100 dark:bg-red-500/10',
                        border: 'border-red-200 dark:border-red-500/20',
                    },
                    {
                        label: 'Webhooks',
                        value: triggers.filter((t) => t.trigger_type === 'webhook').length,
                        icon: Webhook,
                        color: 'text-purple-600 dark:text-purple-400',
                        bg: 'bg-purple-100 dark:bg-purple-500/10',
                        border: 'border-purple-200 dark:border-purple-500/20',
                    },
                ].map((kpi) => {
                    const Icon = kpi.icon;
                    return (
                        <div
                            key={kpi.label}
                            className={`${kpi.bg} border ${kpi.border} rounded-xl p-4 transition-all duration-200 hover:shadow-md`}
                        >
                            <div className="flex items-center gap-2 mb-2">
                                <Icon className={`w-5 h-5 ${kpi.color}`} />
                                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    {kpi.label}
                                </span>
                            </div>
                            <p className={`text-2xl font-bold ${kpi.color}`}>
                                {kpi.value}
                                {kpi.total !== undefined && (
                                    <span className="text-sm font-normal text-gray-400 dark:text-gray-500">
                                        {' '}/ {kpi.total}
                                    </span>
                                )}
                            </p>
                        </div>
                    );
                })}
            </div>

            {/* ── Sub-tabs ────────────────────────────────────────────────── */}
            <div className="flex gap-1 p-1 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] w-fit">
                {(['triggers', 'logs', 'dead-letters'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveSubTab(tab)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                            activeSubTab === tab
                                ? 'bg-indigo-600 text-white shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
                        }`}
                    >
                        {tab === 'triggers' && 'Triggers'}
                        {tab === 'logs' && `Event Log`}
                        {tab === 'dead-letters' && `Dead Letters (${deadLetters.length})`}
                    </button>
                ))}
            </div>

            {/* ═════════ TRIGGERS TAB ═════════ */}
            {activeSubTab === 'triggers' && (
                <div className="space-y-4">
                    {/* New Trigger button */}
                    <div className="flex items-center justify-between">
                        <button
                            onClick={() => setShowCreate(!showCreate)}
                            className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm ${
                                showCreate
                                    ? 'bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347]'
                                    : 'bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 text-white'
                            }`}
                        >
                            {showCreate ? (
                                <>
                                    <X className="w-4 h-4" /> Cancel
                                </>
                            ) : (
                                <>
                                    <Plus className="w-4 h-4" /> New Trigger
                                </>
                            )}
                        </button>
                        <span className="text-gray-500 dark:text-gray-400 text-sm">
                            {triggers.length} trigger{triggers.length !== 1 ? 's' : ''}
                        </span>
                    </div>

                    {/* Creation form */}
                    {showCreate && (
                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-indigo-200 dark:border-indigo-500/20 shadow-sm p-6 transition-colors duration-200 space-y-4">
                            <h3 className="text-lg font-semibold text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
                                <Zap className="w-5 h-5" /> New Event Trigger
                            </h3>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Trigger Name
                                    </label>
                                    <input
                                        className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                        placeholder="e.g., High CPU Alert"
                                        value={formName}
                                        onChange={(e) => setFormName(e.target.value)}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Trigger Type
                                    </label>
                                    <div className="flex gap-2 flex-wrap">
                                        {Object.entries(TRIGGER_TYPE_META).map(([key, meta]) => {
                                            const Icon = meta.icon;
                                            const isSelected = formType === key;
                                            return (
                                                <button
                                                    key={key}
                                                    onClick={() => {
                                                        setFormType(key as any);
                                                        setFormConfig({});
                                                    }}
                                                    className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-all duration-150 ${
                                                        isSelected
                                                            ? `${meta.bgColor} ${meta.color} ${meta.borderColor} ring-2 ring-offset-1 ring-offset-transparent`
                                                            : 'bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-[#2a3347] hover:bg-gray-200 dark:hover:bg-[#2a3347]'
                                                    }`}
                                                >
                                                    <Icon className="w-4 h-4" />
                                                    {meta.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>

                            {/* Type-specific fields */}
                            <div>{renderConfigFields()}</div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Target Workflow ID (optional)
                                </label>
                                <input
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                                    placeholder="Leave empty if no workflow target"
                                    value={formWorkflowId}
                                    onChange={(e) => setFormWorkflowId(e.target.value)}
                                />
                            </div>

                            <button
                                onClick={handleCreate}
                                disabled={!formName}
                                className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center gap-2"
                            >
                                <Plus className="w-4 h-4" /> Create Trigger
                            </button>
                        </div>
                    )}

                    {/* Triggers list */}
                    {triggers.length === 0 && !showCreate ? (
                        <div className="text-center py-16 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
                            <div className="w-14 h-14 bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 rounded-xl flex items-center justify-center mx-auto mb-4">
                                <Zap className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                            </div>
                            <p className="text-gray-900 dark:text-white font-medium mb-1">
                                No event triggers configured
                            </p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                Create a trigger to automate reactions to webhooks, thresholds, or API changes.
                            </p>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-3">
                            {triggers.map((trigger) => {
                                const meta = TRIGGER_TYPE_META[trigger.trigger_type] || TRIGGER_TYPE_META.webhook;
                                const Icon = meta.icon;
                                const isPaused =
                                    trigger.paused_until && new Date(trigger.paused_until) > new Date();
                                const isExpanded = expandedTrigger === trigger.id;

                                return (
                                    <div
                                        key={trigger.id}
                                        className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 overflow-hidden"
                                    >
                                        <div className="p-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                                            <div className="flex items-start gap-3">
                                                <div
                                                    className={`w-10 h-10 ${meta.bgColor} border ${meta.borderColor} rounded-lg flex items-center justify-center shrink-0`}
                                                >
                                                    <Icon className={`w-5 h-5 ${meta.color}`} />
                                                </div>
                                                <div>
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <span className="font-semibold text-gray-900 dark:text-white">
                                                            {trigger.name}
                                                        </span>
                                                        <span
                                                            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${
                                                                trigger.is_active && !isPaused
                                                                    ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                                    : isPaused
                                                                    ? 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'
                                                                    : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
                                                            }`}
                                                        >
                                                            {isPaused ? 'Rate-Limited' : trigger.is_active ? 'Active' : 'Inactive'}
                                                        </span>
                                                        <span
                                                            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${meta.bgColor} ${meta.color} ${meta.borderColor}`}
                                                        >
                                                            {meta.label}
                                                        </span>
                                                    </div>
                                                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                                        Fired {trigger.fire_count} time{trigger.fire_count !== 1 ? 's' : ''}
                                                        {trigger.last_fired_at && (
                                                            <> · Last: {new Date(trigger.last_fired_at).toLocaleString()}</>
                                                        )}
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2 shrink-0">
                                                <button
                                                    onClick={() =>
                                                        setExpandedTrigger(isExpanded ? null : trigger.id)
                                                    }
                                                    className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                                                >
                                                    <Eye className="w-3.5 h-3.5" />
                                                    {isExpanded ? 'Hide' : 'Details'}
                                                </button>
                                                <button
                                                    onClick={() => handleToggle(trigger)}
                                                    className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                                                >
                                                    {trigger.is_active ? (
                                                        <>
                                                            <Pause className="w-3.5 h-3.5" /> Pause
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Play className="w-3.5 h-3.5" /> Resume
                                                        </>
                                                    )}
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(trigger.id)}
                                                    className="px-3 py-1.5 text-xs font-medium bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:hover:bg-red-500/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20 rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" /> Delete
                                                </button>
                                            </div>
                                        </div>

                                        {/* Expanded config details */}
                                        {isExpanded && (
                                            <div className="border-t border-gray-100 dark:border-[#1e2535] bg-gray-50 dark:bg-[#0f1117] p-5 space-y-3">
                                                <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                                                    Configuration
                                                </div>
                                                <pre className="text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-[#161b27] p-4 rounded-lg border border-gray-200 dark:border-[#1e2535] overflow-x-auto font-mono">
                                                    {JSON.stringify(trigger.config, null, 2)}
                                                </pre>

                                                {trigger.trigger_type === 'webhook' && (
                                                    <div className="mt-3">
                                                        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                                            Webhook URL:
                                                        </p>
                                                        <div className="flex items-center gap-2 bg-white dark:bg-[#161b27] p-2 rounded-lg border border-gray-200 dark:border-[#1e2535]">
                                                            <code className="text-xs text-indigo-600 dark:text-indigo-400 font-mono break-all">
                                                                {`${window.location.origin}/api/v1/events/webhook/${trigger.id}`}
                                                            </code>
                                                            <button
                                                                onClick={() =>
                                                                    navigator.clipboard.writeText(
                                                                        `${window.location.origin}/api/v1/events/webhook/${trigger.id}`,
                                                                    )
                                                                }
                                                                className="shrink-0 p-1 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded transition-colors"
                                                                title="Copy URL"
                                                            >
                                                                <Copy className="w-3.5 h-3.5 text-gray-400" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}

                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                                                    <div className="text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">ID:</span>{' '}
                                                        <span className="font-mono text-gray-700 dark:text-gray-300">{trigger.agentium_id}</span>
                                                    </div>
                                                    <div className="text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">Max fires/min:</span>{' '}
                                                        <span className="text-gray-700 dark:text-gray-300">{trigger.max_fires_per_minute}</span>
                                                    </div>
                                                    <div className="text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">Pause duration:</span>{' '}
                                                        <span className="text-gray-700 dark:text-gray-300">{trigger.pause_duration_seconds}s</span>
                                                    </div>
                                                    <div className="text-xs">
                                                        <span className="text-gray-500 dark:text-gray-400">Created:</span>{' '}
                                                        <span className="text-gray-700 dark:text-gray-300">
                                                            {new Date(trigger.created_at).toLocaleDateString()}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* ═════════ LOGS TAB ═════════ */}
            {activeSubTab === 'logs' && (
                <div className="space-y-4">
                    {/* Filters */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-2 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-lg px-3 py-2">
                            <Filter className="w-4 h-4 text-gray-400" />
                            <select
                                className="bg-transparent text-sm text-gray-700 dark:text-gray-300 outline-none"
                                title="Filter by event log status"
                                value={logStatusFilter}
                                onChange={(e) => {
                                    setLogStatusFilter(e.target.value);
                                }}
                            >
                                <option value="">All Statuses</option>
                                <option value="processed">Processed</option>
                                <option value="dead_letter">Dead Letter</option>
                                <option value="duplicate">Duplicate</option>
                            </select>
                        </div>
                        <button
                            onClick={loadLogs}
                            className="px-3 py-2 text-sm font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                        >
                            <RefreshCw className="w-3.5 h-3.5" /> Apply
                        </button>
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                            {logs.length} log entries
                        </span>
                    </div>

                    {logs.length === 0 ? (
                        <div className="text-center py-12 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                            <p className="text-gray-500 dark:text-gray-400 text-sm">No event logs found.</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {logs.map((log) => {
                                const badge = STATUS_BADGE[log.status] || STATUS_BADGE.processed;
                                const triggerName =
                                    triggers.find((t) => t.id === log.trigger_id)?.name || log.trigger_id.slice(0, 8);
                                return (
                                    <div
                                        key={log.id}
                                        className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-white dark:bg-[#161b27] rounded-lg border border-gray-200 dark:border-[#1e2535] text-sm gap-3 hover:border-gray-300 dark:hover:border-[#2a3347] transition-colors duration-150"
                                    >
                                        <div className="flex items-center gap-3 flex-wrap">
                                            <span
                                                className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${badge.cls}`}
                                            >
                                                {badge.label}
                                            </span>
                                            <span className="font-medium text-gray-700 dark:text-gray-300">
                                                {triggerName}
                                            </span>
                                            {log.correlation_id && (
                                                <span className="font-mono text-xs text-gray-400 dark:text-gray-500">
                                                    {log.correlation_id.slice(0, 8)}…
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                                            {log.error && (
                                                <span className="text-red-500 dark:text-red-400 max-w-[200px] truncate" title={log.error}>
                                                    {log.error}
                                                </span>
                                            )}
                                            <span>{new Date(log.created_at).toLocaleString()}</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {/* ═════════ DEAD LETTERS TAB ═════════ */}
            {activeSubTab === 'dead-letters' && (
                <div className="space-y-4">
                    {deadLetters.length === 0 ? (
                        <div className="text-center py-12 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                            <div className="w-12 h-12 bg-green-100 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-xl flex items-center justify-center mx-auto mb-3">
                                <CheckCircle className="w-6 h-6 text-green-600 dark:text-green-400" />
                            </div>
                            <p className="text-gray-900 dark:text-white font-medium">No dead letters</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                All events are processing successfully.
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {deadLetters.map((log) => {
                                const triggerName =
                                    triggers.find((t) => t.id === log.trigger_id)?.name || 'Unknown';
                                return (
                                    <div
                                        key={log.id}
                                        className="p-4 bg-white dark:bg-[#161b27] rounded-lg border border-red-200 dark:border-red-500/20 text-sm space-y-2"
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <XCircle className="w-4 h-4 text-red-500 dark:text-red-400" />
                                                <span className="font-medium text-gray-900 dark:text-white">
                                                    {triggerName}
                                                </span>
                                                <span className="text-xs text-gray-400 dark:text-gray-500">
                                                    Retries: {log.retry_count}
                                                </span>
                                            </div>
                                            <button
                                                onClick={() => handleRetry(log.id)}
                                                disabled={retrying === log.id}
                                                className="px-3 py-1.5 text-xs font-medium bg-amber-50 hover:bg-amber-100 dark:bg-amber-500/10 dark:hover:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/20 rounded-lg transition-colors duration-150 flex items-center gap-1.5 disabled:opacity-50"
                                            >
                                                {retrying === log.id ? (
                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                ) : (
                                                    <RotateCcw className="w-3.5 h-3.5" />
                                                )}
                                                Retry
                                            </button>
                                        </div>
                                        {log.error && (
                                            <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/5 p-2 rounded border border-red-100 dark:border-red-500/10">
                                                {log.error}
                                            </p>
                                        )}
                                        <p className="text-xs text-gray-400 dark:text-gray-500">
                                            {new Date(log.created_at).toLocaleString()}
                                        </p>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default EventTriggerManager;
