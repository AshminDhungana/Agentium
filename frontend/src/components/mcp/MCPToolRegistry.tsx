// src/components/mcp/MCPToolRegistry.tsx
// Phase 6.7 — Constitutional MCP Tool Registry
// Embedded inside SovereignDashboard as a tab panel.

import { useEffect, useState, useCallback } from 'react';
import {
    Plus,
    RefreshCw,
    Shield,
    ShieldCheck,
    ShieldOff,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Clock,
    Activity,
    Eye,
    Zap,
    Server,
    ChevronDown,
    ChevronUp,
    Loader2,
    Hash,
} from 'lucide-react';
import { api } from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface MCPTool {
    id: string;
    name: string;
    description: string;
    server_url: string;
    tier: 'pre_approved' | 'restricted' | 'forbidden';
    constitutional_article: string | null;
    status: 'pending' | 'approved' | 'rejected' | 'revoked' | 'disabled';
    approved_by_council: boolean;
    approval_vote_id: string | null;
    approved_at: string | null;
    approved_by: string | null;
    revoked_at: string | null;
    revoked_by: string | null;
    revocation_reason: string | null;
    capabilities: string[];
    health_status: 'healthy' | 'degraded' | 'down' | 'unknown';
    last_health_check_at: string | null;
    failure_count: number;
    consecutive_failures: number;
    usage_count: number;
    last_used_at: string | null;
    proposed_by: string | null;
    proposed_at: string | null;
    created_at: string | null;
}

interface AuditEntry {
    agent_id: string;
    timestamp: string;
    input_hash: string;
    success: boolean;
    error?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const TIER_META = {
    pre_approved: {
        label: 'Pre-Approved',
        icon: ShieldCheck,
        bg: 'bg-green-100 dark:bg-green-500/10',
        text: 'text-green-700 dark:text-green-400',
        border: 'border-green-200 dark:border-green-500/20',
        dot: 'bg-green-500',
    },
    restricted: {
        label: 'Restricted',
        icon: Shield,
        bg: 'bg-yellow-100 dark:bg-yellow-500/10',
        text: 'text-yellow-700 dark:text-yellow-400',
        border: 'border-yellow-200 dark:border-yellow-500/20',
        dot: 'bg-yellow-500',
    },
    forbidden: {
        label: 'Forbidden',
        icon: ShieldOff,
        bg: 'bg-red-100 dark:bg-red-500/10',
        text: 'text-red-700 dark:text-red-400',
        border: 'border-red-200 dark:border-red-500/20',
        dot: 'bg-red-500',
    },
};

const STATUS_META: Record<string, { label: string; icon: any; cls: string }> = {
    pending:  { label: 'Pending',  icon: Clock,        cls: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20' },
    approved: { label: 'Approved', icon: CheckCircle,  cls: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20' },
    rejected: { label: 'Rejected', icon: XCircle,      cls: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20' },
    revoked:  { label: 'Revoked',  icon: ShieldOff,    cls: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20' },
    disabled: { label: 'Disabled', icon: AlertTriangle, cls: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-700/30 dark:text-gray-400 dark:border-gray-600/30' },
};

const HEALTH_META: Record<string, { cls: string; dot: string }> = {
    healthy:  { cls: 'text-green-600 dark:text-green-400',  dot: 'bg-green-500 animate-pulse' },
    degraded: { cls: 'text-yellow-600 dark:text-yellow-400', dot: 'bg-yellow-500 animate-pulse' },
    down:     { cls: 'text-red-600 dark:text-red-400',      dot: 'bg-red-500' },
    unknown:  { cls: 'text-gray-500 dark:text-gray-400',    dot: 'bg-gray-400' },
};

function fmtDate(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
}

// ── Propose Modal ─────────────────────────────────────────────────────────────

interface ProposeModalProps {
    onClose: () => void;
    onProposed: () => void;
}

function ProposeModal({ onClose, onProposed }: ProposeModalProps) {
    const [form, setForm] = useState({
        name: '',
        description: '',
        server_url: '',
        tier: 'restricted',
        constitutional_article: '',
        capabilities: '',
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }));

    const handleSubmit = async () => {
        setLoading(true);
        setError(null);
        try {
            await api.post('/api/v1/mcp-tools', {
                ...form,
                capabilities: form.capabilities
                    ? form.capabilities.split(',').map(s => s.trim()).filter(Boolean)
                    : [],
                constitutional_article: form.constitutional_article || null,
            });
            onProposed();
            onClose();
        } catch (e: any) {
            setError(e.response?.data?.detail || 'Failed to propose MCP server.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-2xl w-full max-w-lg">
                {/* Header */}
                <div className="p-6 border-b border-gray-100 dark:border-[#1e2535] flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <Plus className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                        <h3 className="text-base font-semibold text-gray-900 dark:text-white">Propose MCP Server</h3>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Creates a pending proposal for Council vote</p>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6 space-y-4">
                    {error && (
                        <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-sm text-red-700 dark:text-red-400">
                            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                            {error}
                        </div>
                    )}

                    <Field label="Name" required>
                        <input
                            className={inputCls}
                            placeholder="e.g. Weather API"
                            value={form.name}
                            onChange={e => set('name', e.target.value)}
                        />
                    </Field>

                    <Field label="Description" required>
                        <textarea
                            className={`${inputCls} resize-none`}
                            rows={2}
                            placeholder="What does this MCP server do?"
                            value={form.description}
                            onChange={e => set('description', e.target.value)}
                        />
                    </Field>

                    <Field label="Server URL / Command" required>
                        <input
                            className={inputCls}
                            placeholder="https://mcp.example.com or /usr/bin/mcp-server"
                            value={form.server_url}
                            onChange={e => set('server_url', e.target.value)}
                        />
                    </Field>

                    <Field label="Constitutional Tier" required>
                        <select
                            aria-label="Constitutional Tier"
                            className={inputCls}
                            value={form.tier}
                            onChange={e => set('tier', e.target.value)}
                        >
                            <option value="pre_approved">Pre-Approved — safe read-only APIs</option>
                            <option value="restricted">Restricted — destructive / side-effectful</option>
                            <option value="forbidden">Forbidden — constitutionally banned</option>
                        </select>
                    </Field>

                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Constitution Article">
                            <input
                                className={inputCls}
                                placeholder="e.g. Article 7.2"
                                value={form.constitutional_article}
                                onChange={e => set('constitutional_article', e.target.value)}
                            />
                        </Field>
                        <Field label="Capabilities (comma-separated)">
                            <input
                                className={inputCls}
                                placeholder="search, fetch, write"
                                value={form.capabilities}
                                onChange={e => set('capabilities', e.target.value)}
                            />
                        </Field>
                    </div>
                </div>

                {/* Footer */}
                <div className="p-6 border-t border-gray-100 dark:border-[#1e2535] flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={loading || !form.name || !form.description || !form.server_url}
                        className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                        Submit Proposal
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Audit Log Drawer ──────────────────────────────────────────────────────────

function AuditDrawer({ tool, onClose }: { tool: MCPTool; onClose: () => void }) {
    const [entries, setEntries] = useState<AuditEntry[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get(`/api/v1/mcp-tools/${tool.id}/audit?limit=100`)
            .then(r => setEntries(r.data.entries || []))
            .catch(() => setEntries([]))
            .finally(() => setLoading(false));
    }, [tool.id]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
                <div className="p-5 border-b border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                            <Activity className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Audit Log — {tool.name}</h3>
                            <p className="text-xs text-gray-400 dark:text-gray-500">Last 100 invocations</p>
                        </div>
                    </div>
                    <button 
                        onClick={onClose} 
                        className="p-2 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg transition-colors"
                        title="Close"
                        aria-label="Close audit log"
                    >
                        <XCircle className="w-4 h-4 text-gray-400" />
                    </button>
                </div>
                <div className="overflow-y-auto flex-1 divide-y divide-gray-100 dark:divide-[#1e2535]">
                    {loading && (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                        </div>
                    )}
                    {!loading && entries.length === 0 && (
                        <div className="text-center py-12 text-sm text-gray-400">No invocations recorded yet.</div>
                    )}
                    {!loading && entries.map((e, i) => (
                        <div key={i} className="p-4 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors">
                            <div className="flex items-center gap-3 mb-1">
                                {e.success
                                    ? <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
                                    : <XCircle    className="w-4 h-4 text-red-500 shrink-0" />
                                }
                                <span className="text-sm font-mono text-gray-800 dark:text-gray-200">{e.agent_id}</span>
                                <span className="ml-auto text-xs text-gray-400">{fmtDate(e.timestamp)}</span>
                            </div>
                            <div className="ml-7 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                                <Hash className="w-3 h-3" />
                                <code className="font-mono">{e.input_hash}</code>
                                {e.error && <span className="text-red-500 truncate ml-2">— {e.error}</span>}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// ── Tool Row / Card ───────────────────────────────────────────────────────────

function ToolCard({ tool, onRefresh }: { tool: MCPTool; onRefresh: () => void }) {
    const [expanded, setExpanded] = useState(false);
    const [showAudit, setShowAudit] = useState(false);
    const [healthLoading, setHealthLoading] = useState(false);
    const [approving, setApproving] = useState(false);
    const [revoking, setRevoking] = useState(false);
    const [revokeReason, setRevokeReason] = useState('');
    const [showRevokeInput, setShowRevokeInput] = useState(false);

    const tier = TIER_META[tool.tier] || TIER_META.restricted;
    const statusMeta = STATUS_META[tool.status] || STATUS_META.pending;
    const health = HEALTH_META[tool.health_status] || HEALTH_META.unknown;
    const TierIcon = tier.icon;

    const pingHealth = async () => {
        setHealthLoading(true);
        try {
            await api.get(`/api/v1/mcp-tools/${tool.id}/health`);
            onRefresh();
        } finally {
            setHealthLoading(false);
        }
    };

    const approve = async () => {
        setApproving(true);
        try {
            await api.post(`/api/v1/mcp-tools/${tool.id}/approve`, {
                approved_by: '00001',
                vote_id: null,
            });
            onRefresh();
        } finally {
            setApproving(false);
        }
    };

    const revoke = async () => {
        if (!revokeReason.trim()) return;
        setRevoking(true);
        try {
            await api.post(`/api/v1/mcp-tools/${tool.id}/revoke`, {
                revoked_by: '00001',
                reason: revokeReason,
            });
            setShowRevokeInput(false);
            setRevokeReason('');
            onRefresh();
        } finally {
            setRevoking(false);
        }
    };

    return (
        <>
            {showAudit && <AuditDrawer tool={tool} onClose={() => setShowAudit(false)} />}

            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 overflow-hidden">
                {/* ── Summary row ── */}
                <div className="p-5">
                    <div className="flex items-start gap-4">
                        {/* Tier icon */}
                        <div className={`w-10 h-10 rounded-lg ${tier.bg} flex items-center justify-center shrink-0 mt-0.5`}>
                            <TierIcon className={`w-5 h-5 ${tier.text}`} />
                        </div>

                        {/* Main info */}
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                                <span className="text-sm font-semibold text-gray-900 dark:text-white truncate">{tool.name}</span>

                                {/* Tier badge */}
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${tier.bg} ${tier.text} ${tier.border}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${tier.dot}`} />
                                    {tier.label}
                                </span>

                                {/* Status badge */}
                                <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${statusMeta.cls}`}>
                                    {tool.status}
                                </span>
                            </div>

                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate mb-2">{tool.description}</p>

                            <div className="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
                                <span className="font-mono truncate max-w-[220px]">{tool.server_url}</span>
                                <span className="flex items-center gap-1">
                                    <span className={`w-1.5 h-1.5 rounded-full ${health.dot}`} />
                                    <span className={health.cls}>{tool.health_status}</span>
                                </span>
                                <span className="flex items-center gap-1">
                                    <Zap className="w-3 h-3" />
                                    {tool.usage_count} uses
                                </span>
                                {tool.constitutional_article && (
                                    <span className="text-blue-500 dark:text-blue-400">{tool.constitutional_article}</span>
                                )}
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1.5 shrink-0">
                            <button
                                onClick={pingHealth}
                                disabled={healthLoading}
                                title="Check health"
                                className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-colors disabled:opacity-40"
                            >
                                {healthLoading
                                    ? <Loader2 className="w-4 h-4 animate-spin" />
                                    : <Activity className="w-4 h-4" />
                                }
                            </button>
                            <button
                                onClick={() => setShowAudit(true)}
                                title="View audit log"
                                className="p-2 text-gray-400 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10 rounded-lg transition-colors"
                            >
                                <Eye className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setExpanded(v => !v)}
                                className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg transition-colors"
                                title={expanded ? "Collapse details" : "Expand details"}
                                aria-label={expanded ? "Collapse details" : "Expand details"}
                            >
                                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                </div>

                {/* ── Expanded detail ── */}
                {expanded && (
                    <div className="px-5 pb-5 border-t border-gray-100 dark:border-[#1e2535] pt-4 space-y-4">
                        {/* Stats grid */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <Stat label="Total Uses" value={tool.usage_count.toString()} />
                            <Stat label="Failures" value={tool.failure_count.toString()} warn={tool.failure_count > 0} />
                            <Stat label="Consecutive Failures" value={tool.consecutive_failures.toString()} warn={tool.consecutive_failures > 0} />
                            <Stat label="Last Used" value={tool.last_used_at ? new Date(tool.last_used_at).toLocaleDateString() : '—'} />
                        </div>

                        {/* Capabilities */}
                        {tool.capabilities.length > 0 && (
                            <div>
                                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Capabilities</p>
                                <div className="flex flex-wrap gap-1.5">
                                    {tool.capabilities.map(cap => (
                                        <span key={cap} className="px-2 py-0.5 text-xs font-mono bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] text-gray-600 dark:text-gray-300 rounded-md">
                                            {cap}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Metadata */}
                        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                            <MetaRow label="Proposed by" value={tool.proposed_by || '—'} />
                            <MetaRow label="Proposed at" value={fmtDate(tool.proposed_at)} />
                            {tool.approved_by && <MetaRow label="Approved by" value={tool.approved_by} />}
                            {tool.approved_at && <MetaRow label="Approved at" value={fmtDate(tool.approved_at)} />}
                            {tool.revoked_by && <MetaRow label="Revoked by" value={tool.revoked_by} />}
                            {tool.revocation_reason && <MetaRow label="Revocation reason" value={tool.revocation_reason} />}
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-2 flex-wrap pt-1">
                            {tool.status === 'pending' && tool.tier !== 'forbidden' && (
                                <button
                                    onClick={approve}
                                    disabled={approving}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors disabled:opacity-40"
                                >
                                    {approving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                                    Approve (Council)
                                </button>
                            )}

                            {(tool.status === 'approved') && (
                                <>
                                    {!showRevokeInput ? (
                                        <button
                                            onClick={() => setShowRevokeInput(true)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                                        >
                                            <ShieldOff className="w-3 h-3" />
                                            Emergency Revoke
                                        </button>
                                    ) : (
                                        <div className="flex items-center gap-2 w-full">
                                            <input
                                                autoFocus
                                                className={`${inputCls} flex-1 text-xs py-1.5`}
                                                placeholder="Revocation reason (required)"
                                                value={revokeReason}
                                                onChange={e => setRevokeReason(e.target.value)}
                                                onKeyDown={e => e.key === 'Enter' && revoke()}
                                            />
                                            <button
                                                onClick={revoke}
                                                disabled={revoking || !revokeReason.trim()}
                                                className="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded-lg disabled:opacity-40 flex items-center gap-1"
                                            >
                                                {revoking && <Loader2 className="w-3 h-3 animate-spin" />}
                                                Confirm
                                            </button>
                                            <button
                                                onClick={() => { setShowRevokeInput(false); setRevokeReason(''); }}
                                                className="px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-white/5 rounded-lg"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </>
    );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

const inputCls =
    'w-full px-3 py-2 text-sm bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-colors';

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
                {label}{required && <span className="text-red-500 ml-0.5">*</span>}
            </label>
            {children}
        </div>
    );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
    return (
        <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
            <p className={`text-lg font-bold mt-0.5 ${warn && value !== '0' ? 'text-red-500 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>
                {value}
            </p>
        </div>
    );
}

function MetaRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex gap-1">
            <span className="font-medium text-gray-400 dark:text-gray-500 shrink-0">{label}:</span>
            <span className="truncate text-gray-600 dark:text-gray-300">{value}</span>
        </div>
    );
}

// ── Filters bar ───────────────────────────────────────────────────────────────

type FilterStatus = 'all' | 'pending' | 'approved' | 'revoked' | 'disabled';
type FilterTier   = 'all' | 'pre_approved' | 'restricted' | 'forbidden';

// ── Main component ────────────────────────────────────────────────────────────

export function MCPToolRegistry() {
    const [tools, setTools] = useState<MCPTool[]>([]);
    const [loading, setLoading] = useState(true);
    const [showPropose, setShowPropose] = useState(false);
    const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
    const [tierFilter, setTierFilter] = useState<FilterTier>('all');
    const [search, setSearch] = useState('');

    const fetchTools = useCallback(async () => {
        setLoading(true);
        try {
            const params: Record<string, string> = {};
            if (statusFilter !== 'all') params.status = statusFilter;
            if (tierFilter !== 'all') params.tier = tierFilter;

            const res = await api.get('/api/v1/mcp-tools', { params });
            setTools(res.data.tools || []);
        } catch {
            setTools([]);
        } finally {
            setLoading(false);
        }
    }, [statusFilter, tierFilter]);

    useEffect(() => { fetchTools(); }, [fetchTools]);

    const filtered = tools.filter(t =>
        !search ||
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.description.toLowerCase().includes(search.toLowerCase()) ||
        t.server_url.toLowerCase().includes(search.toLowerCase())
    );

    // Summary counts
    const counts = {
        total:    tools.length,
        approved: tools.filter(t => t.status === 'approved').length,
        pending:  tools.filter(t => t.status === 'pending').length,
        revoked:  tools.filter(t => t.status === 'revoked' || t.status === 'disabled').length,
        healthy:  tools.filter(t => t.health_status === 'healthy').length,
    };

    return (
        <>
            {showPropose && (
                <ProposeModal
                    onClose={() => setShowPropose(false)}
                    onProposed={fetchTools}
                />
            )}

            <div className="space-y-6">

                {/* ── Summary cards ── */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <SummaryCard label="Total Tools"   value={counts.total}    color="blue"   />
                    <SummaryCard label="Approved"      value={counts.approved} color="green"  />
                    <SummaryCard label="Pending Vote"  value={counts.pending}  color="yellow" />
                    <SummaryCard label="Revoked / Off" value={counts.revoked}  color="red"    />
                </div>

                {/* ── Toolbar ── */}
                <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 flex flex-wrap items-center gap-3">
                    {/* Search */}
                    <input
                        className={`${inputCls} max-w-xs`}
                        placeholder="Search tools…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />

                    {/* Status filter */}
                    <select aria-label="Status filter"
                        className={`${inputCls} w-auto`}
                        value={statusFilter}
                        onChange={e => setStatusFilter(e.target.value as FilterStatus)}
                    >
                        <option value="all">All statuses</option>
                        <option value="pending">Pending</option>
                        <option value="approved">Approved</option>
                        <option value="revoked">Revoked</option>
                        <option value="disabled">Disabled</option>
                    </select>

                    {/* Tier filter */}
                    <select aria-label="Tier filter"
                        className={`${inputCls} w-auto`}
                        value={tierFilter}
                        onChange={e => setTierFilter(e.target.value as FilterTier)}
                    >
                        <option value="all">All tiers</option>
                        <option value="pre_approved">Pre-Approved</option>
                        <option value="restricted">Restricted</option>
                        <option value="forbidden">Forbidden</option>
                    </select>

                    <div className="ml-auto flex items-center gap-2">
                        <button
                            onClick={fetchTools}
                            className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-colors"
                            title="Refresh"
                        >
                            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        </button>
                        <button
                            onClick={() => setShowPropose(true)}
                            className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg transition-colors shadow-sm"
                        >
                            <Plus className="w-4 h-4" />
                            Propose Server
                        </button>
                    </div>
                </div>

                {/* ── Tool list ── */}
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="text-center py-20">
                        <div className="w-14 h-14 bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-xl flex items-center justify-center mx-auto mb-3">
                            <Server className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                            {search || statusFilter !== 'all' || tierFilter !== 'all'
                                ? 'No tools match your filters.'
                                : 'No MCP tools registered yet. Propose the first one!'}
                        </p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {filtered.map(tool => (
                            <ToolCard key={tool.id} tool={tool} onRefresh={fetchTools} />
                        ))}
                    </div>
                )}
            </div>
        </>
    );
}

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
    const colors: Record<string, string> = {
        blue:   'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400',
        green:  'bg-green-100 dark:bg-green-500/10 text-green-600 dark:text-green-400',
        yellow: 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
        red:    'bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-400',
    };
    return (
        <div className={`rounded-xl border border-gray-200 dark:border-[#1e2535] p-4 ${colors[color].split(' ').slice(0, 2).join(' ')} bg-opacity-40`}>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
            <p className={`text-2xl font-bold ${colors[color].split(' ').slice(2).join(' ')}`}>{value}</p>
        </div>
    );
}