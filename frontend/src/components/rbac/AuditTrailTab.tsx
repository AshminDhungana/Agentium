// src/components/rbac/AuditTrailTab.tsx

import { useCallback, useEffect, useState } from 'react';
import {
    Activity,
    ArrowUpCircle,
    ChevronLeft,
    ChevronRight,
    Loader2,
    Search,
    Shield,
    XCircle,
} from 'lucide-react';
import { auditService, AuditLog } from '@/services/audit';

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

// ── Helpers ───────────────────────────────────────────────────────────────────

const getLevelClasses = (level: string) => {
    switch (level.toLowerCase()) {
        case 'emergency':
            return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20';
        case 'warning':
            return 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20';
        case 'info':
            return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20';
        default:
            return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';
    }
};

const getActionClasses = (action: string) => {
    switch (action) {
        case 'privilege_escalation':
            return 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20';
        case 'privilege_revocation':
            return 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-500/10 dark:text-orange-400 dark:border-orange-500/20';
        default:
            return 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';
    }
};

const getActionLabel = (action: string) => {
    switch (action) {
        case 'privilege_escalation':  return 'Escalation';
        case 'privilege_revocation':  return 'Revocation';
        default:                      return action;
    }
};

const formatTimestamp = (ts: string) =>
    new Date(ts).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });

const truncateId = (id: string) =>
    id.length > 12 ? `${id.substring(0, 12)}…` : id;

// ── Component ─────────────────────────────────────────────────────────────────

export function AuditTrailTab() {
    const [logs, setLogs]               = useState<AuditLog[]>([]);
    const [total, setTotal]             = useState(0);
    const [page, setPage]               = useState(0);
    const [search, setSearch]           = useState('');
    const [activeSearch, setActiveSearch] = useState('');
    const [loading, setLoading]         = useState(true);
    const [expandedId, setExpandedId]   = useState<string | null>(null);

    // Debounce search — resets to page 0 on new query
    useEffect(() => {
        const t = setTimeout(() => {
            setActiveSearch(search);
            setPage(0);
        }, 350);
        return () => clearTimeout(t);
    }, [search]);

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        try {
            const result = await auditService.getEscalations(
                page * PAGE_SIZE,
                PAGE_SIZE,
                activeSearch || undefined,
            );
            setLogs(result.data);
            setTotal(result.total);
        } catch (err) {
            console.error('Failed to fetch audit logs:', err);
        } finally {
            setLoading(false);
        }
    }, [page, activeSearch]);

    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    const totalPages = Math.ceil(total / PAGE_SIZE);
    const toggleExpanded = (id: string) =>
        setExpandedId((prev) => (prev === id ? null : id));

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">

            {/* ── Panel Header ──────────────────────────────────────────────── */}
            <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                            <Activity className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                        </div>
                        <div>
                            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                Privilege Escalation Log
                            </h2>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                {loading ? 'Loading…' : `${total.toLocaleString()} event${total !== 1 ? 's' : ''} recorded`}
                            </p>
                        </div>
                    </div>

                    <div className="relative w-full sm:w-80">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
                        <input
                            type="text"
                            placeholder="Search actor, target, or description…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                        />
                    </div>
                </div>
            </div>

            {/* ── Body ──────────────────────────────────────────────────────── */}
            {loading ? (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
                </div>
            ) : logs.length === 0 ? (
                <div className="p-16 text-center">
                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                        <Shield className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                    </div>
                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                        No Escalation Events
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        {search
                            ? 'No events match your search query.'
                            : 'No privilege escalations have been recorded yet.'}
                    </p>
                </div>
            ) : (
                <>
                    {/* ── Table ─────────────────────────────────────────────── */}
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-gray-100 dark:border-[#1e2535] bg-gray-50 dark:bg-[#0f1117]">
                                    {['Timestamp', 'Actor', 'Action', 'Target', 'Level', 'Description'].map(
                                        (col) => (
                                            <th
                                                key={col}
                                                className="px-6 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                                            >
                                                {col}
                                            </th>
                                        ),
                                    )}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                {logs.map((log) => (
                                    <>
                                        {/* ── Main row ── */}
                                        <tr
                                            key={log.id}
                                            onClick={() => toggleExpanded(log.id)}
                                            className="hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150 cursor-pointer"
                                        >
                                            {/* Timestamp */}
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                                                    {formatTimestamp(log.timestamp)}
                                                </span>
                                            </td>

                                            {/* Actor */}
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-2">
                                                    <div className="w-7 h-7 rounded-md bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center flex-shrink-0">
                                                        <ArrowUpCircle className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                                                    </div>
                                                    <div>
                                                        <p className="text-xs font-medium text-gray-900 dark:text-white font-mono">
                                                            {truncateId(log.actor.id)}
                                                        </p>
                                                        <p className="text-xs text-gray-400 dark:text-gray-500">
                                                            {log.actor.type}
                                                        </p>
                                                    </div>
                                                </div>
                                            </td>

                                            {/* Action */}
                                            <td className="px-6 py-4">
                                                <span
                                                    className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${getActionClasses(log.action)}`}
                                                >
                                                    {getActionLabel(log.action)}
                                                </span>
                                            </td>

                                            {/* Target */}
                                            <td className="px-6 py-4">
                                                {log.target ? (
                                                    <div>
                                                        <p className="text-xs font-medium text-gray-900 dark:text-white font-mono">
                                                            {truncateId(log.target.id)}
                                                        </p>
                                                        <p className="text-xs text-gray-400 dark:text-gray-500">
                                                            {log.target.type}
                                                        </p>
                                                    </div>
                                                ) : (
                                                    <span className="text-gray-400 dark:text-gray-500 text-xs">—</span>
                                                )}
                                            </td>

                                            {/* Level */}
                                            <td className="px-6 py-4">
                                                <span
                                                    className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${getLevelClasses(log.level)}`}
                                                >
                                                    {log.level}
                                                </span>
                                            </td>

                                            {/* Description */}
                                            <td className="px-6 py-4 max-w-xs">
                                                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                    {log.description}
                                                </p>
                                            </td>
                                        </tr>

                                        {/* ── Expanded detail row ── */}
                                        {expandedId === log.id && (
                                            <tr key={`${log.id}-detail`}>
                                                <td
                                                    colSpan={6}
                                                    className="px-6 py-5 bg-gray-50 dark:bg-[#0f1117] border-b border-gray-100 dark:border-[#1e2535]"
                                                >
                                                    <div className="space-y-4">
                                                        <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
                                                            Event Details
                                                        </p>

                                                        {/* Full description */}
                                                        <p className="text-sm text-gray-600 dark:text-gray-400">
                                                            {log.description}
                                                        </p>

                                                        {/* Result */}
                                                        {log.result && (
                                                            <div className="flex items-center gap-2">
                                                                {log.result.success ? (
                                                                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-600 dark:text-green-400">
                                                                        <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                                                                        Succeeded
                                                                    </span>
                                                                ) : (
                                                                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-600 dark:text-red-400">
                                                                        <XCircle className="w-3 h-3" />
                                                                        Failed
                                                                        {log.result.error && `: ${log.result.error}`}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}

                                                        {/* Metadata */}
                                                        {log.metadata && (
                                                            <div className="space-y-2">
                                                                {/* Delegated capabilities */}
                                                                {Array.isArray(log.metadata?.capabilities) &&
                                                                    log.metadata.capabilities.length > 0 && (
                                                                        <div>
                                                                            <p className="text-xs font-medium text-gray-500 dark:text-gray-500 mb-1">
                                                                                Capabilities
                                                                            </p>
                                                                            <div className="flex flex-wrap gap-1">
                                                                                {log.metadata.capabilities.map(
                                                                                    (cap: string) => (
                                                                                        <span
                                                                                            key={cap}
                                                                                            className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md bg-white dark:bg-[#161b27] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347]"
                                                                                        >
                                                                                            {cap}
                                                                                        </span>
                                                                                    ),
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    )}

                                                                {/* Reason */}
                                                                {log.metadata?.reason && (
                                                                    <p className="text-xs text-gray-500 dark:text-gray-400 italic">
                                                                        Reason: {log.metadata.reason}
                                                                    </p>
                                                                )}

                                                                {/* Expiry */}
                                                                {log.metadata?.expires_at && (
                                                                    <p className="text-xs text-gray-500 dark:text-gray-400">
                                                                        Expires:{' '}
                                                                        {formatTimestamp(log.metadata.expires_at)}
                                                                    </p>
                                                                )}

                                                                {/* Delegation ID */}
                                                                {log.metadata?.delegation_id && (
                                                                    <p className="text-xs font-mono text-gray-400 dark:text-gray-500">
                                                                        Delegation ID: {log.metadata.delegation_id}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        )}

                                                        {/* Event ID */}
                                                        <p className="text-xs font-mono text-gray-400 dark:text-gray-500 pt-1 border-t border-gray-200 dark:border-[#2a3347]">
                                                            Event ID: {log.id}
                                                        </p>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* ── Pagination ────────────────────────────────────────── */}
                    {totalPages > 1 && (
                        <div className="px-6 py-4 border-t border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                Showing {page * PAGE_SIZE + 1}–
                                {Math.min((page + 1) * PAGE_SIZE, total)} of{' '}
                                {total.toLocaleString()} events
                            </p>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                                    disabled={page === 0}
                                    className="p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-[#1e2535] disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
                                    aria-label="Previous page"
                                >
                                    <ChevronLeft className="w-4 h-4" />
                                </button>
                                <span className="text-xs text-gray-600 dark:text-gray-400 min-w-[80px] text-center">
                                    Page {page + 1} of {totalPages}
                                </span>
                                <button
                                    onClick={() =>
                                        setPage((p) => Math.min(totalPages - 1, p + 1))
                                    }
                                    disabled={page >= totalPages - 1}
                                    className="p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-[#1e2535] disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
                                    aria-label="Next page"
                                >
                                    <ChevronRight className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}