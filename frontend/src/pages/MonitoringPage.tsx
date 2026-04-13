/**
 * MonitoringPage — updated with:
 */

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { monitoringService } from '../services/monitoring';
import { MonitoringDashboard, ViolationReport, AgentHealthReport } from '../types';
import { useWebSocketStore } from '../store/websocketStore';
import { ErrorState } from '@/components/ui/ErrorState';
import {
    Activity,
    ShieldCheck,
    AlertTriangle,
    Loader2,
    RefreshCw,
    Clock,
    Cpu,
    Zap,
    CheckCircle,
    ChevronDown,
    Filter,
    XCircle,
    HeartPulse,
    RotateCcw,
    ShieldAlert,
    Wrench
} from 'lucide-react';

const KNOWN_MONITOR_IDS  = ['00001', '00002', '00003'];
const REFRESH_INTERVAL_MS = 30_000;

type Tab = 'dashboard' | 'violations' | 'recovery' | 'operations' | 'sla' | 'incidents' | 'chaos' | 'slow_queries';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function HealthRing({ score }: { score: number }) {
    const color      = score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444';
    const r          = 20;
    const circ       = 2 * Math.PI * r;
    const dashOffset = circ * (1 - score / 100);
    return (
        <svg width="52" height="52" className="rotate-[-90deg]">
            <circle cx="26" cy="26" r={r} stroke="#e5e7eb" strokeWidth="4" fill="none" className="dark:stroke-gray-700" />
            <circle
                cx="26" cy="26" r={r}
                stroke={color} strokeWidth="4" fill="none"
                strokeDasharray={circ}
                strokeDashoffset={dashOffset}
                strokeLinecap="round"
                style={{ transition: 'stroke-dashoffset 0.6s ease' }}
            />
        </svg>
    );
}

function SeverityBadge({ severity }: { severity: string }) {
    const cls =
        severity === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' :
        severity === 'major'    ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300' :
        severity === 'moderate' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300' :
                                  'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
            {severity}
        </span>
    );
}

function StatusBadge({ status }: { status: string }) {
    const cls =
        status === 'open'     ? 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400' :
        status === 'resolved' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                                'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
            {status}
        </span>
    );
}

// ─── Violations Tab ───────────────────────────────────────────────────────────

interface ViolationsTabProps {
    initialViolations: ViolationReport[];
}

function ViolationsTab({ initialViolations }: ViolationsTabProps) {
    const [violations,       setViolations]       = useState<ViolationReport[]>(initialViolations);
    const [filterStatus,     setFilterStatus]     = useState<string>('');
    const [filterSeverity,   setFilterSeverity]   = useState<string>('');
    const [isLoading,        setIsLoading]        = useState(false);
    const [resolvingId,      setResolvingId]      = useState<string | null>(null);
    const [resolveModal,     setResolveModal]     = useState<{ id: string; open: boolean }>({ id: '', open: false });
    const [resolutionNotes,  setResolutionNotes]  = useState('');
    const [resolveError,     setResolveError]     = useState<string | null>(null);
    const [fetchError,       setFetchError]       = useState<string | null>(null);

    // AbortController ref so filter changes cancel in-flight requests
    const abortRef = useRef<AbortController | null>(null);

    const fetchViolations = useCallback(async () => {
        // Cancel any in-flight request from a previous filter change
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setIsLoading(true);
        setFetchError(null);
        try {
            const data = await monitoringService.getViolations({
                status:   filterStatus   || undefined,
                severity: filterSeverity || undefined,
            });
            if (!controller.signal.aborted) {
                setViolations(data);
            }
        } catch (err: any) {
            if (!controller.signal.aborted) {
                console.error('Failed to fetch violations:', err);
                setFetchError(err?.response?.data?.detail || 'Could not load violations');
            }
        } finally {
            if (!controller.signal.aborted) {
                setIsLoading(false);
            }
        }
    }, [filterStatus, filterSeverity]);

    useEffect(() => {
        fetchViolations();
        return () => abortRef.current?.abort();
    }, [fetchViolations]);

    const openResolveModal = (id: string) => {
        setResolutionNotes('');
        setResolveError(null);
        setResolveModal({ id, open: true });
    };

    const handleResolve = async () => {
        if (!resolutionNotes.trim()) {
            setResolveError('Resolution notes are required.');
            return;
        }
        setResolvingId(resolveModal.id);
        try {
            await monitoringService.resolveViolation(resolveModal.id, resolutionNotes);
            setResolveModal({ id: '', open: false });
            // Optimistically update status
            setViolations(prev =>
                prev.map(v =>
                    v.id === resolveModal.id ? { ...v, status: 'resolved' } : v
                )
            );
        } catch (err: any) {
            setResolveError(err.response?.data?.detail || 'Failed to resolve violation.');
        } finally {
            setResolvingId(null);
        }
    };

    return (
        <div>
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3 mb-6">
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <Filter className="w-4 h-4" />
                    <span className="font-medium">Filters:</span>
                </div>

                <select
                    aria-label="Filter status"
                    value={filterStatus}
                    onChange={e => setFilterStatus(e.target.value)}
                    className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="">All statuses</option>
                    <option value="open">Open</option>
                    <option value="resolved">Resolved</option>
                    <option value="dismissed">Dismissed</option>
                </select>

                <select
                    aria-label="Filter severity"
                    value={filterSeverity}
                    onChange={e => setFilterSeverity(e.target.value)}
                    className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="">All severities</option>
                    <option value="critical">Critical</option>
                    <option value="major">Major</option>
                    <option value="moderate">Moderate</option>
                    <option value="minor">Minor</option>
                </select>

                {(filterStatus || filterSeverity) && (
                    <button
                        onClick={() => { setFilterStatus(''); setFilterSeverity(''); }}
                        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    >
                        <XCircle className="w-3.5 h-3.5" /> Clear
                    </button>
                )}

                {isLoading && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
            </div>

            {/* Error state for filter fetch failures */}
            {fetchError && (
                <ErrorState message={fetchError} onRetry={fetchViolations} />
            )}

            {/* Table */}
            {!fetchError && violations.length === 0 ? (
                <div className="text-center py-16">
                    <div className="w-14 h-14 rounded-full bg-green-50 dark:bg-green-900/20 flex items-center justify-center mx-auto mb-3 border border-green-100 dark:border-green-800/40">
                        <ShieldCheck className="w-7 h-7 text-green-500 dark:text-green-400" />
                    </div>
                    <p className="text-gray-900 dark:text-white font-medium mb-1">No violations found</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Try adjusting filters or check back later</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {violations.map((v: ViolationReport) => (
                        <div
                            key={v.id}
                            className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 shadow-sm"
                        >
                            <div className="flex items-start justify-between gap-4">
                                <div className="flex-1 min-w-0">
                                    <div className="flex flex-wrap items-center gap-2 mb-2">
                                        <SeverityBadge severity={v.severity} />
                                        <StatusBadge   status={v.status}   />
                                        <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{v.type}</span>
                                    </div>
                                    <p className="text-sm text-gray-900 dark:text-gray-100 mb-2">{v.description}</p>
                                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
                                        <span>Reporter: <span className="font-mono text-gray-600 dark:text-gray-300">{v.reporter}</span></span>
                                        <span>Violator: <span className="font-mono text-gray-600 dark:text-gray-300">{v.violator}</span></span>
                                        {v.created_at && <span>{new Date(v.created_at).toLocaleString()}</span>}
                                    </div>
                                </div>

                                {v.status === 'open' && (
                                    <button
                                        onClick={() => openResolveModal(v.id)}
                                        disabled={resolvingId === v.id}
                                        className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800/60 hover:bg-green-100 dark:hover:bg-green-900/50 transition-colors disabled:opacity-50"
                                    >
                                        {resolvingId === v.id
                                            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                            : <CheckCircle className="w-3.5 h-3.5" />
                                        }
                                        Resolve
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Resolve Modal */}
            {resolveModal.open && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
                    <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 w-full max-w-md p-6">
                        <h3 className="text-base font-bold text-gray-900 dark:text-white mb-1">Resolve Violation</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                            Provide resolution notes before marking this violation as resolved.
                        </p>
                        <textarea
                            value={resolutionNotes}
                            onChange={e => { setResolutionNotes(e.target.value); setResolveError(null); }}
                            placeholder="Describe how the violation was addressed..."
                            rows={4}
                            className="w-full text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-green-500 resize-none"
                        />
                        {resolveError && (
                            <p className="text-xs text-red-600 dark:text-red-400 mt-2">{resolveError}</p>
                        )}
                        <div className="flex justify-end gap-3 mt-4">
                            <button
                                onClick={() => setResolveModal({ id: '', open: false })}
                                className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleResolve}
                                disabled={!!resolvingId}
                                className="px-4 py-2 rounded-lg text-sm font-semibold bg-green-600 hover:bg-green-700 text-white transition-colors disabled:opacity-50 flex items-center gap-2"
                            >
                                {resolvingId ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                                Confirm Resolve
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Recovery Tab ─────────────────────────────────────────────────────────────

function RecoveryTab() {
    const [status, setStatus] = useState<any>(null);
    const [events, setEvents] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRollingBack, setIsRollingBack] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        setIsLoading(true);
        try {
            const [st, evs] = await Promise.all([
                monitoringService.getSelfHealingStatus(),
                monitoringService.getSelfHealingEvents(50, 7)
            ]);
            setStatus(st);
            setEvents(evs);
        } catch (err) {
            console.error('Failed to load recovery data', err);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const handleRollback = async (eventId: string, checkpointId: string) => {
        if (!confirm(`Are you sure you want to rollback to checkpoint ${checkpointId}? This will terminate active agent operations and reset state.`)) return;
        
        setIsRollingBack(eventId);
        try {
            await monitoringService.rollbackFromCheckpoint(checkpointId);
            alert(`Successfully rolled back to checkpoint ${checkpointId}`);
            loadData();
        } catch (err: any) {
            alert(err?.response?.data?.detail || 'Rollback failed');
        } finally {
            setIsRollingBack(null);
        }
    };

    if (isLoading) {
        return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;
    }

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* System Status Banner */}
            <div className={`rounded-xl border p-6 shadow-sm ${status?.system_mode === 'degraded' ? 'bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800/50' : 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800/50'}`}>
                <div className="flex items-start gap-4">
                    <div className={`p-3 rounded-lg flex-shrink-0 ${status?.system_mode === 'degraded' ? 'bg-orange-100 dark:bg-orange-900/50' : 'bg-green-100 dark:bg-green-900/50'}`}>
                        {status?.system_mode === 'degraded' ? <ShieldAlert className="w-6 h-6 text-orange-600 dark:text-orange-400" /> : <ShieldCheck className="w-6 h-6 text-green-600 dark:text-green-400" />}
                    </div>
                    <div>
                        <h3 className={`text-lg font-bold ${status?.system_mode === 'degraded' ? 'text-orange-900 dark:text-orange-300' : 'text-green-900 dark:text-green-300'}`}>
                            System Mode: {status?.system_mode === 'degraded' ? 'DEGRADED' : 'NORMAL'}
                        </h3>
                        {status?.system_mode === 'degraded' && (
                             <p className="text-sm text-orange-800 dark:text-orange-400 mt-1">
                                Degraded since {status.degraded_since ? new Date(status.degraded_since).toLocaleString() : 'recently'}. Reason: {status.reason}. Active circuit breakers: {status.active_circuit_breakers}. Non-critical tasks are paused.
                             </p>
                        )}
                        {status?.system_mode !== 'degraded' && (
                            <p className="text-sm text-green-800 dark:text-green-400 mt-1">
                                All self-healing systems are active and operating normally. Automated recovery, degradation mode, and critical path protection are engaged.
                            </p>
                        )}
                    </div>
                </div>
            </div>

            {/* Events Feed */}
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4 flex items-center justify-between bg-gray-50 dark:bg-gray-800/50">
                    <h2 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        <HeartPulse className="w-5 h-5 text-rose-500" />
                        Self-Healing Activity Log
                    </h2>
                    <button onClick={loadData} className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50 transition">
                        <RefreshCw className="w-3.5 h-3.5" /> Refresh
                    </button>
                </div>
                <div className="p-6">
                    {events.length === 0 ? (
                        <div className="text-center py-12">
                            <Wrench className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
                            <p className="text-gray-900 dark:text-white font-medium mb-1">No events recorded</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">Self-healing actions will appear here when triggered.</p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {events.map((ev: any) => (
                                <div key={ev.id} className="flex gap-4 border-l-2 border-indigo-200 dark:border-indigo-800/60 pl-4 py-2 relative group hover:border-indigo-400 dark:hover:border-indigo-500 transition-colors">
                                    <div className="absolute w-2.5 h-2.5 rounded-full bg-indigo-500 dark:bg-indigo-400 -left-[6px] top-3" />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-3 mb-1">
                                            <span className="text-sm font-bold text-gray-900 dark:text-white">{ev.action}</span>
                                            <span className="text-xs font-medium text-gray-400 dark:text-gray-500">{new Date(ev.created_at).toLocaleString()}</span>
                                            {ev.level === 'critical' || ev.level === 'error' ? (
                                                <span className="bg-red-100 text-red-700 text-[10px] px-2 py-0.5 rounded-full uppercase font-bold dark:bg-red-900/30 dark:text-red-400 border border-red-200 dark:border-red-800/40">Error</span>
                                            ) : null}
                                        </div>
                                        <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed mb-1">{ev.description}</p>
                                        
                                        {/* Rollback Button for crashed agents that were checkpointed before crash */}
                                        {ev.action === 'agent_crashed' && ev.after_state?.checkpoint_id && (
                                            <div className="mt-3">
                                                <button
                                                    onClick={() => handleRollback(ev.id, ev.after_state.checkpoint_id)}
                                                    disabled={!!isRollingBack}
                                                    className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 transition"
                                                >
                                                    {isRollingBack === ev.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5 text-rose-500" />}
                                                    Debug: Rollback to Checkpoint
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── Operations Tab ─────────────────────────────────────────────────────────────

function OperationsTab() {
    const [data, setData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(true);

    const loadData = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await monitoringService.getAggregatedMetrics();
            setData(res);
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    if (isLoading) {
        return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;
    }

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="flex items-center justify-between mb-2">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">Aggregated System Metrics</h2>
                <button onClick={loadData} className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50">
                    <RefreshCw className="w-3.5 h-3.5" /> Refresh
                </button>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                {[
                    { title: "Agents", pct: data?.agents?.health_pct || 0 },
                    { title: "Tasks", pct: data?.tasks?.health_pct || 0 },
                    { title: "Workflows", pct: data?.workflows?.health_pct || 0 },
                    { title: "Events", pct: data?.events?.health_pct || 0 },
                    { title: "Budget", pct: data?.budget?.health_pct || 0 },
                ].map((item, i) => (
                    <div key={i} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 shadow-sm flex flex-col items-center">
                        <HealthRing score={item.pct} />
                        <div className={`text-lg font-bold mt-2 ${item.pct >= 90 ? 'text-green-600 dark:text-green-400' : item.pct >= 70 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'}`}>
                            {item.pct}%
                        </div>
                        <div className="text-sm text-gray-500 dark:text-gray-400 font-medium">{item.title} Health</div>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                    <div className="bg-blue-50 dark:bg-blue-950/50 border-b border-blue-100 dark:border-blue-900/60 px-6 py-4">
                        <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                            <Activity className="w-4 h-4 text-blue-500" />
                            Live Telemetry Summary
                        </h3>
                    </div>
                    <div className="p-6">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                <p className="text-xs text-gray-500 dark:text-gray-400">Scaling Actions (24h)</p>
                                <p className="text-xl font-bold dark:text-white">{data?.scaling_events_24h ?? 0}</p>
                            </div>
                            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                <p className="text-xs text-gray-500 dark:text-gray-400">Total Tasks (24h)</p>
                                <p className="text-xl font-bold dark:text-white">{data?.tasks?.total_24h ?? 0}</p>
                            </div>
                            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                <p className="text-xs text-gray-500 dark:text-gray-400">Budget Spent ($)</p>
                                <p className="text-xl font-bold text-indigo-600 dark:text-indigo-400">${data?.budget?.cost_used_usd?.toFixed(2) ?? '0.00'}</p>
                            </div>
                            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                <p className="text-xs text-gray-500 dark:text-gray-400">Capacity Forecast (24h)</p>
                                <p className="text-xl font-bold text-purple-600 dark:text-purple-400">
                                    {(data?.capacity_forecast?.next_24h !== undefined ? Math.round(data.capacity_forecast.next_24h) : 'N/A')}
                                </p>
                            </div>
                            <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                                <p className="text-xs text-gray-500 dark:text-gray-400">Frontend Errors (24h)</p>
                                <p className="text-xl font-bold text-red-600 dark:text-red-400">{data?.frontend_errors_24h ?? 0}</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                    <div className="bg-orange-50 dark:bg-orange-950/50 border-b border-orange-100 dark:border-orange-900/60 px-6 py-4">
                        <h3 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-orange-500" />
                            Active Anomalies
                        </h3>
                    </div>
                    <div className="p-6">
                        {data?.active_anomalies > 0 ? (
                            <div className="flex items-center gap-4 bg-orange-100/50 dark:bg-orange-900/30 rounded-lg p-4 border border-orange-200 dark:border-orange-800/50">
                                <ShieldAlert className="w-8 h-8 text-orange-500" />
                                <div>
                                    <h4 className="font-bold text-orange-900 dark:text-orange-300">{data.active_anomalies} Anomaly Detected</h4>
                                    <p className="text-sm text-orange-800 dark:text-orange-400">Check the Violations tab for details on anomalies waiting for remediation.</p>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-6">
                                <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
                                <p className="text-gray-900 dark:text-white font-medium">No Anomalies Detected</p>
                                <p className="text-sm text-gray-500 dark:text-gray-400">System operating within historical baseline limits.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── SLA Tab ──────────────────────────────────────────────────────────────────

function SLATab() {
    const [data, setData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(true);

    const loadData = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await monitoringService.getSLAMetrics();
            setData(res);
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;

    const items = Object.entries(data?.sla_by_priority || {});

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {items.map(([priority, v]: [string, any]) => {
                    const pct = v.compliance_pct;
                    const isBreach = pct < 80;
                    return (
                        <div key={priority} className={`bg-white dark:bg-gray-900 rounded-xl border p-6 shadow-sm ${isBreach ? 'border-red-300 dark:border-red-800' : 'border-gray-200 dark:border-gray-800'}`}>
                            <div className="flex items-center gap-3 mb-2">
                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: priority === 'critical' || priority === 'sovereign' ? '#ef4444' : priority === 'high' ? '#f97316' : '#3b82f6' }} />
                                <h3 className="font-bold uppercase text-gray-900 dark:text-white">{priority} Priority</h3>
                            </div>
                            <div className={`text-4xl font-bold my-4 ${pct >= 95 ? 'text-green-600' : pct >= 80 ? 'text-yellow-600' : 'text-red-600'}`}>
                                {pct}%
                            </div>
                            <p className="text-sm text-gray-500 dark:text-gray-400">
                                {v.met} / {v.total} tasks met SLA target (30 day)
                            </p>
                            {v.breached > 0 && (
                                <p className="text-xs text-red-500 mt-2 font-medium">{v.breached} tasks breached</p>
                            )}
                        </div>
                    );
                })}
            </div>
            {items.length === 0 && (
                <div className="text-center py-12">
                    <p className="text-gray-500 dark:text-gray-400">No SLA data available.</p>
                </div>
            )}
        </div>
    );
}

// ─── Incidents Tab ────────────────────────────────────────────────────────────

function IncidentsTab() {
    const [logs, setLogs] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const loadData = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await monitoringService.getIncidentLog(50);
            setLogs(res);
        } catch (e) {
            console.error(e);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    const handleRollback = async (auditId: string) => {
        if (!confirm('Revert this auto-remediated action via AuditLog?')) return;
        try {
            await monitoringService.rollbackAction(auditId);
            alert('Revert logged successfully.');
            loadData();
        } catch (err: any) {
            alert(err?.response?.data?.detail || 'Revert failed.');
        }
    };

    if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;

    return (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <Wrench className="w-5 h-5 text-indigo-500" />
                    Auto-Remediated Incidents
                </h2>
                <button onClick={loadData} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-400">
                    Refresh
                </button>
            </div>
            <div className="p-6">
                {logs.length === 0 ? (
                    <div className="text-center py-12">
                        <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
                        <p className="text-gray-900 dark:text-white font-medium">No Auto-Remediations</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">The zero-touch ops engine has not needed to intervene.</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {logs.map((log: any) => (
                            <div key={log.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-800 text-sm">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="font-bold text-gray-900 dark:text-white">{log.description}</div>
                                    <button
                                        onClick={() => handleRollback(log.id)}
                                        className="text-xs px-2 py-1 bg-red-100 text-red-700 hover:bg-red-200 rounded dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
                                    >
                                        Revert
                                    </button>
                                </div>
                                <div className="text-xs text-gray-500 mt-2 font-mono break-all bg-white dark:bg-gray-900 p-2 rounded border border-gray-200 dark:border-gray-700">
                                    {JSON.stringify(log.after_state)}
                                </div>
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                                    {new Date(log.created_at).toLocaleString()}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Chaos Engineering Tab ────────────────────────────────────────────────────

function ChaosTab() {
    const [isLoading, setIsLoading] = useState(false);
    const [result, setResult] = useState<any>(null);

    const handleChaos = async (type: string) => {
        if (!confirm(`Are you sure you want to inject ${type} failure into the live system?`)) return;
        setIsLoading(true);
        setResult(null);
        try {
            const res = await monitoringService.injectChaosTest(type);
            setResult({ success: true, data: res });
        } catch (e: any) {
            setResult({ success: false, error: e?.response?.data?.detail || e.message });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-red-200 dark:border-red-900/50 shadow-sm p-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
            <h2 className="text-xl font-bold text-red-600 dark:text-red-400 mb-2 flex items-center gap-2">
                <ShieldAlert /> Chaos Engineering Lab
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                Warning: These tests inject real failures into the live system to verify automated response mechanisms. All actions are audit-logged.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <h3 className="font-bold text-gray-900 dark:text-white mb-1">Agent Crash</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 h-10">Suspends a random non-persistent idle task agent.</p>
                    <button onClick={() => handleChaos('agent_crash')} disabled={isLoading} className="w-full bg-red-600 hover:bg-red-700 text-white rounded text-sm py-1.5 font-bold disabled:opacity-50">
                        Inject Crash
                    </button>
                </div>
                <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <h3 className="font-bold text-gray-900 dark:text-white mb-1">API Timeout</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 h-10">Simulates LLM API timeouts for 60 seconds.</p>
                    <button onClick={() => handleChaos('api_timeout')} disabled={isLoading} className="w-full bg-red-600 hover:bg-red-700 text-white rounded text-sm py-1.5 font-bold disabled:opacity-50">
                        Inject Timeout
                    </button>
                </div>
                <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <h3 className="font-bold text-gray-900 dark:text-white mb-1">DB Connection Loss</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 h-10">Simulates DB failure for diagnostic routines.</p>
                    <button onClick={() => handleChaos('db_connection_loss')} disabled={isLoading} className="w-full bg-red-600 hover:bg-red-700 text-white rounded text-sm py-1.5 font-bold disabled:opacity-50">
                        Inject DB Failure
                    </button>
                </div>
            </div>

            {result && (
                <div className={`p-4 rounded-lg border ${result.success ? 'bg-green-50 border-green-200 text-green-900 dark:bg-green-900/30 dark:border-green-800/50 dark:text-green-100' : 'bg-red-50 border-red-200 text-red-900 dark:bg-red-900/30 dark:border-red-800/50 dark:text-red-100'}`}>
                    <h4 className="font-bold mb-1">{result.success ? 'Test Injected Successfully' : 'Injection Failed'}</h4>
                    <pre className="text-xs font-mono overflow-auto opacity-80 whitespace-pre-wrap">
                        {JSON.stringify(result.data || result.error, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
}

// ─── Slow Queries Tab ─────────────────────────────────────────────────────────

function SlowQueriesTab() {
    const [queries, setQueries] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const res = await monitoringService.getSlowQueries(20);
            setQueries(res.slow_queries || []);
        } catch (e: any) {
            setError(e?.response?.data?.detail || 'Failed to load slow queries');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>;

    return (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="border-b border-gray-200 dark:border-gray-800 px-6 py-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <Clock className="w-5 h-5 text-purple-500" />
                    Slow Queries
                </h2>
                <div className="flex gap-2 text-gray-500">
                    <a href="https://www.postgresql.org/docs/current/using-explain.html" target="_blank" rel="noreferrer" className="text-xs font-semibold px-3 py-1.5 dark:text-gray-300 hover:text-gray-900 border border-gray-200 rounded-lg shrink-0">EXPLAIN Docs</a>
                    <button onClick={loadData} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-400">
                        Refresh
                    </button>
                </div>
            </div>
            
            <div className="p-6">
                {error && <ErrorState message={error} onRetry={loadData} />}
                
                {!error && queries.length === 0 ? (
                    <div className="text-center py-12">
                        <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
                        <p className="text-gray-900 dark:text-white font-medium">No Slow Queries</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">All database queries are running efficiently.</p>
                    </div>
                ) : (
                    !error && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-gray-200 dark:border-gray-800 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50">
                                        <th className="p-3 font-semibold rounded-tl-lg">Query Preview</th>
                                        <th className="p-3 font-semibold">Avg Duration (ms)</th>
                                        <th className="p-3 font-semibold">Calls</th>
                                        <th className="p-3 font-semibold">Rows/Call</th>
                                        <th className="p-3 font-semibold rounded-tr-lg">Last Seen</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {queries.map((q, idx) => (
                                        <tr key={idx} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                            <td className="p-3 font-mono text-xs max-w-sm overflow-hidden text-ellipsis whitespace-nowrap text-gray-800 dark:text-gray-200" title={q.query_preview}>
                                                {q.query_preview}
                                            </td>
                                            <td className="p-3 text-sm text-gray-600 dark:text-gray-300">
                                                <span className={`font-semibold ${q.avg_duration_ms > 1000 ? 'text-red-500' : 'text-yellow-600 dark:text-yellow-500'}`}>
                                                    {Number(q.avg_duration_ms).toFixed(2)}
                                                </span>
                                            </td>
                                            <td className="p-3 text-sm text-gray-600 dark:text-gray-300">{q.call_count}</td>
                                            <td className="p-3 text-sm text-gray-600 dark:text-gray-300">{Number(q.rows_per_call).toFixed(1)}</td>
                                            <td className="p-3 text-xs text-gray-500 dark:text-gray-400">
                                                {q.last_seen ? new Date(q.last_seen).toLocaleString() : '—'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )
                )}
            </div>
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export const MonitoringPage: React.FC = () => {
    const [monitorId,    setMonitorId]    = useState(KNOWN_MONITOR_IDS[0]);
    const [dashboard,    setDashboard]    = useState<MonitoringDashboard | null>(null);
    const [isLoading,    setIsLoading]    = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [error,        setError]        = useState<string | null>(null);
    const [lastUpdated,  setLastUpdated]  = useState<Date | null>(null);
    const [activeTab,    setActiveTab]    = useState<Tab>('dashboard');
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // WebSocket: refresh on violation or health events
    const lastMessage = useWebSocketStore(s => s.lastMessage);
    useEffect(() => {
        if (!lastMessage) return;
        const data = lastMessage as any;
        if (
            data.event === 'violation_detected' ||
            data.event === 'health_report'      ||
            data.type  === 'monitoring_update'
        ) {
            loadDashboard(true);
        }
    }, [lastMessage]); // eslint-disable-line react-hooks/exhaustive-deps

    const loadDashboard = useCallback(async (silent = false) => {
        if (!silent) setIsLoading(true);
        else         setIsRefreshing(true);

        try {
            setError(null);
            const data = await monitoringService.getDashboard(monitorId);
            setDashboard(data);
            setLastUpdated(new Date());
        } catch (err: any) {
            console.error('Monitoring error:', err);
            setError(err.response?.data?.detail || 'Monitoring endpoint not available');
            if (!silent) {
                // Provide safe defaults so the page doesn't stay blank
                setDashboard({
                    system_health:           100,
                    active_alerts:           0,
                    agent_health_breakdown:  {},
                    latest_health_reports:   [],
                    recent_violations:       [],
                });
            }
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    }, [monitorId]);

    // ── Interval management with visibility pausing ────────────────────────
    // [FIX] Stop polling when the tab goes to the background so we don't
    // burn network/CPU while the user isn't looking.  Resume and trigger an
    // immediate refresh when the tab becomes visible again so data is fresh.
    const startInterval = useCallback(() => {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = setInterval(() => loadDashboard(true), REFRESH_INTERVAL_MS);
    }, [loadDashboard]);

    const stopInterval = useCallback(() => {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
    }, []);

    useEffect(() => {
        loadDashboard();
        startInterval();

        const handleVisibilityChange = () => {
            if (document.visibilityState === 'hidden') {
                stopInterval();
            } else {
                // Tab became visible — refresh immediately then restart the clock
                loadDashboard(true);
                startInterval();
            }
        };

        document.addEventListener('visibilitychange', handleVisibilityChange);

        return () => {
            stopInterval();
            document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
    }, [loadDashboard, startInterval, stopInterval]);

    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading metrics...</span>
                </div>
            </div>
        );
    }

    const systemHealth   = dashboard?.system_health           ?? 100;
    const activeAlerts   = dashboard?.active_alerts           ?? 0;
    const healthReports  = dashboard?.latest_health_reports   ?? [];
    const violations     = dashboard?.recent_violations       ?? [];
    const healthBreakdown = dashboard?.agent_health_breakdown ?? {};

    const healthColor =
        systemHealth >= 90 ? 'text-green-600 dark:text-green-400' :
        systemHealth >= 70 ? 'text-yellow-600 dark:text-yellow-400' :
                             'text-red-600 dark:text-red-400';

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-6 transition-colors duration-200">
            <div className="max-w-7xl mx-auto">

                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="mb-8 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center shadow-lg">
                            <Activity className="w-7 h-7 text-white" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                                System Monitoring
                            </h1>
                            <p className="text-gray-500 dark:text-gray-400 text-sm">
                                Real-time oversight of agent operations
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        {/* Monitor selector */}
                        <div className="relative flex items-center">
                            <label className="text-xs text-gray-500 dark:text-gray-400 mr-2 hidden sm:block">Monitor:</label>
                            <div className="relative">
                                <select
                                    aria-label="Monitor ID"
                                    value={monitorId}
                                    onChange={e => setMonitorId(e.target.value)}
                                    className="appearance-none text-sm border border-gray-200 dark:border-gray-700 rounded-lg pl-3 pr-8 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                                >
                                    {KNOWN_MONITOR_IDS.map(id => (
                                        <option key={id} value={id}>#{id}</option>
                                    ))}
                                </select>
                                <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                            </div>
                        </div>

                        {lastUpdated && (
                            <span className="hidden sm:flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                                <Clock className="w-3 h-3" />
                                Updated {lastUpdated.toLocaleTimeString()}
                            </span>
                        )}
                        <button
                            onClick={() => loadDashboard(true)}
                            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition-colors"
                            title="Refresh now"
                            aria-label="Refresh monitoring data"
                        >
                            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>

                {/* ── Error Notice ────────────────────────────────────────── */}
                {error && (
                    <div className="mb-6 bg-yellow-50 dark:bg-yellow-950/40 border border-yellow-200 dark:border-yellow-800/60 rounded-lg p-4">
                        <div className="flex gap-3">
                            <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <h3 className="text-sm font-semibold text-yellow-900 dark:text-yellow-300 mb-1">
                                    Monitoring System Notice
                                </h3>
                                <p className="text-sm text-yellow-800 dark:text-yellow-400">
                                    {error}. Displaying cached or default values.
                                </p>
                                <button
                                    onClick={() => loadDashboard()}
                                    className="mt-2 text-xs text-yellow-700 dark:text-yellow-400 underline hover:no-underline"
                                >
                                    Retry
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Tabs ────────────────────────────────────────────────── */}
                <div className="flex gap-1 mb-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-1 w-fit shadow-sm max-w-full overflow-x-auto">
                    {(['operations', 'dashboard', 'violations', 'recovery', 'sla', 'incidents', 'chaos', 'slow_queries'] as Tab[]).map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-3 py-2 rounded-lg text-sm font-medium capitalize transition-colors whitespace-nowrap ${
                                activeTab === tab
                                    ? 'bg-blue-600 text-white shadow-sm'
                                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                        >
                            {tab === 'violations' && activeAlerts > 0 ? (
                                <span className="flex items-center gap-2">
                                    Violations
                                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500 text-white">{activeAlerts}</span>
                                </span>
                            ) : (
                                tab.charAt(0).toUpperCase() + tab.slice(1)
                            )}
                        </button>
                    ))}
                </div>

                {/* ══ Dashboard Tab ══════════════════════════════════════════ */}
                {activeTab === 'dashboard' && (
                    <>
                        {/* Stats Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">

                            {/* System Health */}
                            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm flex items-center gap-4">
                                <div className="relative flex-shrink-0">
                                    <HealthRing score={systemHealth} />
                                    <span className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${healthColor}`}>
                                        {systemHealth}%
                                    </span>
                                </div>
                                <div>
                                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-0.5">System Health</p>
                                    <p className={`text-2xl font-bold ${healthColor}`}>{systemHealth}%</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        {systemHealth >= 90 ? 'Fully Operational' : systemHealth >= 70 ? 'Degraded' : 'Critical'}
                                    </p>
                                </div>
                            </div>

                            {/* Active Alerts */}
                            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Active Alerts</p>
                                        <p className={`text-3xl font-bold ${activeAlerts > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>
                                            {activeAlerts}
                                        </p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                            {activeAlerts === 0 ? 'No issues detected' : `${activeAlerts} requiring attention`}
                                        </p>
                                    </div>
                                    <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${activeAlerts > 0 ? 'bg-red-100 dark:bg-red-900/30' : 'bg-gray-100 dark:bg-gray-800'}`}>
                                        <AlertTriangle className={`w-6 h-6 ${activeAlerts > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'}`} />
                                    </div>
                                </div>
                            </div>

                            {/* Agents Reporting */}
                            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Agents Reporting</p>
                                        <p className="text-3xl font-bold text-gray-900 dark:text-white">
                                            {healthReports.length}
                                        </p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                            {healthReports.filter((r: AgentHealthReport) => r.health_score >= 90).length} healthy
                                        </p>
                                    </div>
                                    <div className="w-12 h-12 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                                        <Cpu className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Agent Health Breakdown */}
                        {Object.keys(healthBreakdown).length > 0 && (
                            <div className="mb-8">
                                <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
                                    Agent Tier Health
                                </h2>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    {Object.entries(healthBreakdown).map(([tier, score]) => (
                                        <div key={tier} className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-3 flex items-center gap-3">
                                            <div className={`w-8 h-8 rounded-md flex items-center justify-center ${
                                                (score as number) >= 90 ? 'bg-green-100 dark:bg-green-900/30' : 'bg-yellow-100 dark:bg-yellow-900/30'
                                            }`}>
                                                <Zap className={`w-4 h-4 ${(score as number) >= 90 ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`} />
                                            </div>
                                            <div>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{tier}</p>
                                                <p className={`text-sm font-bold ${(score as number) >= 90 ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                                                    {score}%
                                                </p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Panels Row */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                            {/* Recent Violations (summary) */}
                            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                                <div className="bg-yellow-50 dark:bg-yellow-950/50 border-b border-yellow-100 dark:border-yellow-900/60 px-6 py-4 flex items-center justify-between">
                                    <h2 className="text-base font-bold text-gray-900 dark:text-yellow-100 flex items-center gap-2">
                                        <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                                        Recent Violations
                                    </h2>
                                    <div className="flex items-center gap-2">
                                        {violations.length > 0 && (
                                            <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-200 dark:bg-yellow-800/60 text-yellow-800 dark:text-yellow-300 font-medium">
                                                {violations.length}
                                            </span>
                                        )}
                                        <button
                                            onClick={() => setActiveTab('violations')}
                                            className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium"
                                        >
                                            View all →
                                        </button>
                                    </div>
                                </div>

                                <div className="p-6">
                                    {violations.length > 0 ? (
                                        <div className="space-y-3 max-h-80 overflow-y-auto">
                                            {violations.map((v: ViolationReport) => (
                                                <div
                                                    key={v.id}
                                                    className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
                                                >
                                                    <div className="flex items-start justify-between gap-4">
                                                        <div className="flex-1">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <SeverityBadge severity={v.severity} />
                                                                <StatusBadge   status={v.status}   />
                                                            </div>
                                                            <p className="text-sm text-gray-900 dark:text-gray-100">{v.description}</p>
                                                            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                                                {v.created_at ? new Date(v.created_at).toLocaleString() : '—'}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-10">
                                            <div className="w-14 h-14 rounded-full bg-green-50 dark:bg-green-900/20 flex items-center justify-center mx-auto mb-3 border border-green-100 dark:border-green-800/40">
                                                <ShieldCheck className="w-7 h-7 text-green-500 dark:text-green-400" />
                                            </div>
                                            <p className="text-gray-900 dark:text-white font-medium mb-1">No Violations Detected</p>
                                            <p className="text-sm text-gray-500 dark:text-gray-400">All agents operating within guidelines</p>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Agent Health Reports */}
                            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                                <div className="bg-blue-50 dark:bg-blue-950/50 border-b border-blue-100 dark:border-blue-900/60 px-6 py-4 flex items-center justify-between">
                                    <h2 className="text-base font-bold text-gray-900 dark:text-blue-100 flex items-center gap-2">
                                        <Activity className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                        Agent Health Reports
                                    </h2>
                                    {healthReports.length > 0 && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-200 dark:bg-blue-800/60 text-blue-800 dark:text-blue-300 font-medium">
                                            {healthReports.length}
                                        </span>
                                    )}
                                </div>

                                <div className="p-6">
                                    {healthReports.length > 0 ? (
                                        <div className="space-y-3 max-h-80 overflow-y-auto">
                                            {healthReports.map((report: AgentHealthReport) => {
                                                const isHealthy = report.health_score > 90;
                                                return (
                                                    <div
                                                        key={report.id}
                                                        className="flex items-center gap-4 bg-gray-50 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700"
                                                    >
                                                        <div className="relative flex-shrink-0">
                                                            <HealthRing score={report.health_score} />
                                                            <span className={`absolute inset-0 flex items-center justify-center text-[10px] font-bold ${isHealthy ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                                                                {report.health_score}
                                                            </span>
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                                                Agent #{report.subject}
                                                            </p>
                                                            <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">{report.status}</p>
                                                        </div>
                                                        <div className="text-right flex-shrink-0">
                                                            <div className="text-xs text-gray-500 dark:text-gray-400">Success Rate</div>
                                                            <div className={`text-sm font-bold ${isHealthy ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                                                                {report.metrics.success_rate}%
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    ) : (
                                        <div className="text-center py-10">
                                            <div className="w-14 h-14 rounded-full bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center mx-auto mb-3 border border-blue-100 dark:border-blue-800/40">
                                                <CheckCircle className="w-7 h-7 text-blue-400 dark:text-blue-500" />
                                            </div>
                                            <p className="text-gray-900 dark:text-white font-medium mb-1">No Health Reports</p>
                                            <p className="text-sm text-gray-500 dark:text-gray-400">Agent monitoring will appear here</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </>
                )}

                {/* ══ Violations Tab ═════════════════════════════════════════ */}
                {activeTab === 'violations' && (
                    <ViolationsTab initialViolations={violations} />
                )}

                {/* ══ Recovery Tab ═══════════════════════════════════════════ */}
                {activeTab === 'recovery' && (
                    <RecoveryTab />
                )}

                {/* ══ Operations Tab ═════════════════════════════════════════ */}
                {activeTab === 'operations' && (
                    <OperationsTab />
                )}

                {/* ══ SLA Tab ════════════════════════════════════════════════ */}
                {activeTab === 'sla' && (
                    <SLATab />
                )}

                {/* ══ Incidents Tab ══════════════════════════════════════════ */}
                {activeTab === 'incidents' && (
                    <IncidentsTab />
                )}

                {/* ══ Chaos Tab ══════════════════════════════════════════════ */}
                {activeTab === 'chaos' && (
                    <ChaosTab />
                )}

                {/* ══ Slow Queries Tab ══════════════════════════════════════════════ */}
                {activeTab === 'slow_queries' && (
                    <SlowQueriesTab />
                )}

            </div>
        </div>
    );
};