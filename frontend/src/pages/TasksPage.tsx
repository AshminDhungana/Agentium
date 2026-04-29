import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
    Task,
    UserPreference,
    Subtask,
    CritiqueReview,
    CriticAgentStats,
    CriticStatsResponse,
} from '../types';
import { tasksService, criticsService, CreateTaskRequest, UpdateTaskRequest } from '../services/tasks';
import { preferencesService, PREFERENCE_CATEGORIES, DATA_TYPE_LABELS, formatPreferenceValue, parsePreferenceValue } from '../services/preferences';
import { TaskCard } from '../components/tasks/TaskCard';
import { CreateTaskModal } from '../components/tasks/CreateTaskModal';
import { CheckpointImportModal } from '../components/checkpoints/CheckpointImportModal';
import {
    Plus,
    Filter,
    CheckCircle,
    Clock,
    AlertTriangle,
    ListTodo,
    RefreshCw,
    ShieldCheck,
    ShieldX,
    ShieldAlert,
    TrendingUp,
    Activity,
    Code2,
    FileText,
    GitBranch,
    ChevronUp,
    ChevronDown,
    ChevronRight,
    Minus,
    Users,
    Cpu,
    CornerDownRight,
    AlertCircle,
    ArrowDown,
    Zap,
    CheckSquare,
    RotateCcw,
    Info,
    Hash,
    Calendar,
    Timer,
    Milestone,
    Settings,
    SlidersHorizontal,
    Trash2,
    Edit3,
    Save,
    X,
    History,
    Sparkles,
    Database,
    GitCompareArrows,
    Upload,
    Brain,
    Network,
    Monitor,
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { EmptyState } from '@/components/ui/EmptyState';
import { CheckpointTimeline } from '../components/checkpoints/CheckpointTimeline';
import { BranchDiffView } from '../components/checkpoints/BranchDiffView';
import { AutoDelegationPanel } from '../components/tasks/AutoDelegationPanel';
import { WorkflowAutomationPanel } from '../components/workflows/WorkflowAutomationPanel';
import { BrowserSessionsList } from '../components/tasks/BrowserSessionsList';
import { BrowserTaskViewer } from '../components/tasks/BrowserTaskViewer';

// ─── Local-only type (UI state, not suitable for shared types/index.ts) ────────

interface SubtaskWithReviews extends Subtask {
    reviews: CritiqueReview[];
    reviewsLoaded: boolean;
    reviewsLoading: boolean;
}

// ─── FIX 14: Tab-level error boundary ─────────────────────────────────────────
// Prevents a runtime error in one tab from blanking the entire page.

class TabErrorBoundary extends React.Component<
    { children: React.ReactNode; tabName: string },
    { hasError: boolean; errorMessage: string }
> {
    state = { hasError: false, errorMessage: '' };

    static getDerivedStateFromError(error: Error) {
        return { hasError: true, errorMessage: error.message };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error(`[TabErrorBoundary:${this.props.tabName}]`, error, info);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
                    <div className="w-12 h-12 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center">
                        <AlertCircle className="w-6 h-6 text-red-500 dark:text-red-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                        Something went wrong in the {this.props.tabName} tab
                    </p>
                    {this.state.errorMessage && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 max-w-sm font-mono">
                            {this.state.errorMessage}
                        </p>
                    )}
                    <button
                        onClick={() => this.setState({ hasError: false, errorMessage: '' })}
                        className="mt-1 px-4 py-2 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
                    >
                        Retry
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUS_FILTERS = [
    { value: '',             label: 'All',          color: 'gray'   },
    { value: 'pending',      label: 'Pending',      color: 'yellow' },
    { value: 'deliberating', label: 'Deliberating', color: 'purple' },
    { value: 'in_progress',  label: 'In Progress',  color: 'blue'   },
    { value: 'retrying',     label: 'Retrying',     color: 'amber'  },
    { value: 'completed',    label: 'Completed',    color: 'green'  },
    { value: 'failed',       label: 'Failed',       color: 'red'    },
    { value: 'escalated',    label: 'Escalated',    color: 'crimson'},
];

const FILTER_COLORS: Record<string, string> = {
    gray:    'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-300 dark:border-[#2a3347]',
    yellow:  'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
    purple:  'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20',
    blue:    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20',
    green:   'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
    red:     'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
    amber:   'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20',
    crimson: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-900/30',
};

const FILTER_ACTIVE: Record<string, string> = {
    gray:    'bg-gray-600 text-white border-gray-600 dark:bg-gray-500 dark:border-gray-500',
    yellow:  'bg-yellow-500 text-white border-yellow-500',
    purple:  'bg-purple-600 text-white border-purple-600',
    blue:    'bg-blue-600 text-white border-blue-600',
    green:   'bg-green-600 text-white border-green-600',
    red:     'bg-red-600 text-white border-red-600',
    amber:   'bg-amber-500 text-white border-amber-500',
    crimson: 'bg-red-700 text-white border-red-700',
};

const CRITIC_META: Record<string, {
    label: string;
    id: string;
    icon: React.ElementType;
    accent: string;
    accentDark: string;
    bg: string;
    bgDark: string;
    border: string;
    borderDark: string;
    badge: string;
    bar: string;
}> = {
    code: {
        label: 'Code Critic',
        id: '7xxxx',
        icon: Code2,
        accent: 'text-violet-600',
        accentDark: 'dark:text-violet-400',
        bg: 'bg-violet-50',
        bgDark: 'dark:bg-violet-500/10',
        border: 'border-violet-200',
        borderDark: 'dark:border-violet-500/20',
        badge: 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300',
        bar: 'bg-violet-500',
    },
    output: {
        label: 'Output Critic',
        id: '8xxxx',
        icon: FileText,
        accent: 'text-sky-600',
        accentDark: 'dark:text-sky-400',
        bg: 'bg-sky-50',
        bgDark: 'dark:bg-sky-500/10',
        border: 'border-sky-200',
        borderDark: 'dark:border-sky-500/20',
        badge: 'bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300',
        bar: 'bg-sky-500',
    },
    plan: {
        label: 'Plan Critic',
        id: '9xxxx',
        icon: GitBranch,
        accent: 'text-teal-600',
        accentDark: 'dark:text-teal-400',
        bg: 'bg-teal-50',
        bgDark: 'dark:bg-teal-500/10',
        border: 'border-teal-200',
        borderDark: 'dark:border-teal-500/20',
        badge: 'bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300',
        bar: 'bg-teal-500',
    },
};

const SUBTASK_STATUS_CONFIG: Record<string, {
    border: string;
    dot: string;
    badge: string;
    label: string;
}> = {
    pending:      { border: 'border-l-gray-300 dark:border-l-gray-600',     dot: 'bg-gray-400',               badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/20 dark:text-gray-400',       label: 'Pending' },
    in_progress:  { border: 'border-l-blue-400 dark:border-l-blue-500',     dot: 'bg-blue-400 animate-pulse', badge: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',       label: 'In Progress' },
    deliberating: { border: 'border-l-purple-400 dark:border-l-purple-500', dot: 'bg-purple-400',             badge: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400', label: 'Deliberating' },
    retrying:     { border: 'border-l-amber-400 dark:border-l-amber-500',   dot: 'bg-amber-400',              badge: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400',     label: 'Retrying' },
    completed:    { border: 'border-l-green-400 dark:border-l-green-500',   dot: 'bg-green-400',              badge: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',     label: 'Completed' },
    failed:       { border: 'border-l-red-400 dark:border-l-red-500',       dot: 'bg-red-400',                badge: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',             label: 'Failed' },
    escalated:    { border: 'border-l-orange-400 dark:border-l-orange-500', dot: 'bg-orange-400',             badge: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400', label: 'Escalated' },
    stopped:      { border: 'border-l-gray-400 dark:border-l-gray-500',     dot: 'bg-gray-500',               badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/20 dark:text-gray-400',         label: 'Stopped' },
};

// ─── FIX 1: Module-scope statics (no longer recreated on every render) ─────────

/** Priority options used in the inline edit dropdown of MainTaskCard. */
const PRIORITY_OPTIONS_LIST = ['low', 'normal', 'high', 'critical', 'sovereign'] as const;

/** Status → badge class map for MainTaskCard (was recreated inside component body). */
const TASK_STATUS_COLOR: Record<string, string> = {
    pending:      'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400',
    in_progress:  'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
    deliberating: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400',
    retrying:     'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
    completed:    'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',
    failed:       'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
    escalated:    'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400',
};

/** Priority → text class map for MainTaskCard (was recreated inside component body). */
const TASK_PRIORITY_COLOR: Record<string, string> = {
    sovereign: 'text-indigo-600 dark:text-indigo-400',
    critical:  'text-red-600 dark:text-red-400',
    high:      'text-orange-600 dark:text-orange-400',
    urgent:    'text-orange-600 dark:text-orange-400',
    normal:    'text-gray-500 dark:text-gray-400',
    low:       'text-gray-400 dark:text-gray-500',
};

/** VerdictBadge config map (was recreated inside VerdictBadge on every render). */
const VERDICT_CONFIG: Record<string, { icon: React.ElementType; cls: string; label: string }> = {
    pass:     { icon: ShieldCheck, cls: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',   label: 'Pass' },
    reject:   { icon: ShieldX,     cls: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',           label: 'Reject' },
    escalate: { icon: ShieldAlert, cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',   label: 'Escalate' },
};

/** Verdict → dot color map for CriticSummaryDots (was recreated inside the component). */
const VERDICT_DOT_COLOR: Record<string, string> = {
    pass:     'bg-green-400 dark:bg-green-500',
    reject:   'bg-red-400 dark:bg-red-500',
    escalate: 'bg-amber-400 dark:bg-amber-500',
};

/**
 * FIX 4: Full, static Tailwind class strings for data-type badges.
 * Replaces the `bg-${color}-100 text-${color}-700` interpolation pattern
 * which Tailwind's build-time purge cannot detect and therefore strips in
 * production. Keys match the `color` values in DATA_TYPE_LABELS.
 */
const DATA_TYPE_BADGE_CLASSES: Record<string, string> = {
    blue:   'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
    green:  'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
    cyan:   'bg-cyan-100 text-cyan-700 dark:bg-cyan-500/20 dark:text-cyan-400',
    purple: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400',
    orange: 'bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400',
    pink:   'bg-pink-100 text-pink-700 dark:bg-pink-500/20 dark:text-pink-400',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const fmtMs = (ms: number) =>
    ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;

const fmtDate = (iso: string) =>
    new Date(iso).toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });

const isProblematic = (status: string) =>
    ['failed', 'escalated', 'retrying'].includes(status);

const getSubtaskStatusCfg = (status: string) =>
    SUBTASK_STATUS_CONFIG[status] ?? SUBTASK_STATUS_CONFIG.pending;

// ─── Shared Sub-components ────────────────────────────────────────────────────

// FIX 1: VerdictBadge now reads from module-scope VERDICT_CONFIG
const VerdictBadge: React.FC<{ verdict: string; size?: 'sm' | 'xs' }> = ({ verdict, size = 'sm' }) => {
    const cfg = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.pass;
    const Icon = cfg.icon;
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-semibold ${size === 'xs' ? 'text-[10px]' : 'text-xs'} ${cfg.cls}`}>
            <Icon className={size === 'xs' ? 'w-2.5 h-2.5' : 'w-3 h-3'} />
            {cfg.label}
        </span>
    );
};

const MiniBar: React.FC<{ value: number; color: string }> = ({ value, color }) => (
    <div className="h-1.5 w-full rounded-full bg-gray-100 dark:bg-[#1e2535] overflow-hidden">
        <div
            className={`h-full rounded-full transition-all duration-700 ${color}`}
            style={{ width: `${Math.min(100, value)}%` }}
        />
    </div>
);

const DeltaChip: React.FC<{ value: number }> = ({ value }) => {
    if (value === 0) return <span className="text-xs text-gray-400 flex items-center gap-0.5"><Minus className="w-3 h-3" />—</span>;
    const up = value > 0;
    return (
        <span className={`text-xs flex items-center gap-0.5 font-medium ${up ? 'text-green-500' : 'text-red-400'}`}>
            {up ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {Math.abs(value).toFixed(1)}%
        </span>
    );
};

// ─── Critic Summary Dots ──────────────────────────────────────────────────────

// FIX 1: CriticSummaryDots now reads from module-scope VERDICT_DOT_COLOR
const CriticSummaryDots: React.FC<{ reviews: CritiqueReview[] }> = ({ reviews }) => {
    if (reviews.length === 0) {
        return <span className="text-xs text-gray-300 dark:text-gray-600 italic">No reviews</span>;
    }

    const latest: Record<string, string> = {};
    [...reviews]
        .sort((a, b) => new Date(a.reviewed_at).getTime() - new Date(b.reviewed_at).getTime())
        .forEach(r => { latest[r.critic_type] = r.verdict; });

    return (
        <div className="flex items-center gap-1.5">
            {Object.entries(latest).map(([type, verdict]) => {
                const meta = CRITIC_META[type];
                return (
                    <div key={type} className="relative group flex items-center">
                        <span className={`w-2 h-2 rounded-full inline-block ${VERDICT_DOT_COLOR[verdict] ?? 'bg-gray-300'}`} />
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:flex flex-col items-center z-20 pointer-events-none">
                            <div className="bg-gray-900 dark:bg-[#1e2535] text-white text-[10px] rounded px-2 py-1 whitespace-nowrap shadow-lg">
                                {meta?.label ?? type}: {verdict}
                            </div>
                            <div className="w-1.5 h-1.5 bg-gray-900 dark:bg-[#1e2535] rotate-45 -mt-0.5" />
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

// ─── Inline Critic Review Panel ───────────────────────────────────────────────

const CriticReviewPanel: React.FC<{
    reviews: CritiqueReview[];
    loading: boolean;
}> = ({ reviews, loading }) => {
    const [expandedSuggestions, setExpandedSuggestions] = useState<Set<string>>(new Set());

    if (loading) {
        return (
            <div className="flex items-center justify-center py-6 gap-2 text-gray-400">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span className="text-xs">Loading critic reviews…</span>
            </div>
        );
    }

    if (reviews.length === 0) {
        return (
            <div className="flex items-center justify-center py-6 gap-2 text-gray-400 dark:text-gray-500">
                <ShieldCheck className="w-4 h-4" />
                <span className="text-xs">No critic reviews yet for this subtask.</span>
            </div>
        );
    }

    const grouped: Record<string, CritiqueReview[]> = {};
    reviews.forEach(r => {
        if (!grouped[r.critic_type]) grouped[r.critic_type] = [];
        grouped[r.critic_type].push(r);
    });
    Object.values(grouped).forEach(g =>
        g.sort((a, b) => new Date(b.reviewed_at).getTime() - new Date(a.reviewed_at).getTime())
    );

    const allPass = Object.values(grouped).every(g => g[0]?.verdict === 'pass');

    if (allPass) {
        return (
            <div className="flex items-center gap-3 py-4 px-5">
                <div className="w-8 h-8 rounded-full bg-green-100 dark:bg-green-500/10 flex items-center justify-center flex-shrink-0">
                    <CheckSquare className="w-4 h-4 text-green-600 dark:text-green-400" />
                </div>
                <div>
                    <p className="text-sm font-medium text-green-700 dark:text-green-400">All checks passed</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {Object.keys(grouped).length} critic{Object.keys(grouped).length !== 1 ? 's' : ''} approved this output
                    </p>
                </div>
                <div className="ml-auto flex gap-2 flex-wrap">
                    {Object.entries(grouped).map(([type]) => {
                        const meta = CRITIC_META[type];
                        if (!meta) return null;
                        const Icon = meta.icon;
                        return (
                            <div key={type} className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium ${meta.badge}`}>
                                <Icon className="w-3 h-3" />
                                {meta.label.split(' ')[0]}
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    }

    return (
        <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
            {Object.entries(grouped).map(([type, typeReviews]) => {
                const latest = typeReviews[0];
                const meta = CRITIC_META[type] ?? CRITIC_META.output;
                const Icon = meta.icon;
                const hasSuggestions = !!latest.suggestions;
                const suggestionsOpen = expandedSuggestions.has(latest.id);

                return (
                    <div key={type} className="px-5 py-4">
                        <div className="flex items-start gap-3">
                            <div className={`w-8 h-8 rounded-lg ${meta.bg} ${meta.bgDark} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                                <Icon className={`w-4 h-4 ${meta.accent} ${meta.accentDark}`} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-sm font-semibold text-gray-900 dark:text-white">{meta.label}</span>
                                    <VerdictBadge verdict={latest.verdict} />
                                    <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                                        retry {latest.retry_count}/{latest.max_retries}
                                    </span>
                                    {latest.model_used && (
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${meta.badge}`}>
                                            {latest.model_used.split(':')[1] ?? latest.model_used}
                                        </span>
                                    )}
                                    <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto whitespace-nowrap">
                                        {fmtDate(latest.reviewed_at)} · {fmtMs(latest.review_duration_ms)}
                                    </span>
                                </div>

                                {latest.rejection_reason && (
                                    <div className="mt-2 flex items-start gap-2">
                                        <AlertCircle className="w-3.5 h-3.5 text-red-400 dark:text-red-500 flex-shrink-0 mt-0.5" />
                                        <p className="text-xs text-red-700 dark:text-red-400 leading-relaxed">
                                            {latest.rejection_reason}
                                        </p>
                                    </div>
                                )}

                                {hasSuggestions && (
                                    <div className="mt-2">
                                        <button
                                            onClick={() => setExpandedSuggestions(prev => {
                                                const next = new Set(prev);
                                                if (next.has(latest.id)) next.delete(latest.id);
                                                else next.add(latest.id);
                                                return next;
                                            })}
                                            className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                                        >
                                            <ChevronRight className={`w-3 h-3 transition-transform ${suggestionsOpen ? 'rotate-90' : ''}`} />
                                            <Zap className="w-3 h-3 text-amber-500" />
                                            Improvement hints
                                        </button>
                                        {suggestionsOpen && (
                                            <div className="mt-2 pl-5 pr-2 py-2 bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 rounded-lg">
                                                <p className="text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                                                    {latest.suggestions}
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {typeReviews.length > 1 && (
                                    <p className="mt-1.5 text-[10px] text-gray-400 dark:text-gray-500 font-mono">
                                        + {typeReviews.length - 1} earlier review{typeReviews.length - 1 !== 1 ? 's' : ''}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

// ─── Subtask Row ──────────────────────────────────────────────────────────────

const SubtaskRow: React.FC<{
    subtask: SubtaskWithReviews;
    index: number;
    isExpanded: boolean;
    onToggle: () => void;
    onLoadReviews: () => void;
    subtaskRef?: React.RefObject<HTMLDivElement>;
}> = ({ subtask, index, isExpanded, onToggle, onLoadReviews, subtaskRef }) => {
    const cfg = getSubtaskStatusCfg(subtask.status);
    const hasProblem = isProblematic(subtask.status);

    const handleToggle = () => {
        onToggle();
        if (!subtask.reviewsLoaded && !subtask.reviewsLoading) {
            onLoadReviews();
        }
    };

    return (
        <div
            ref={subtaskRef}
            className={`
                border-l-[3px] ${cfg.border}
                ${hasProblem ? 'bg-red-50/30 dark:bg-red-500/[0.03]' : 'bg-white dark:bg-[#161b27]'}
                transition-colors duration-200
            `}
        >
            <button
                onClick={handleToggle}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-[#1e2535]/50 transition-colors duration-150 text-left group"
            >
                <span className="text-[10px] font-mono text-gray-300 dark:text-gray-600 w-5 flex-shrink-0 text-right select-none">
                    {String(index + 1).padStart(2, '0')}
                </span>
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                <span className="flex-1 text-sm font-medium text-gray-800 dark:text-gray-200 truncate min-w-0">
                    {subtask.title}
                </span>
                {subtask.agentium_id && (
                    <span className="hidden sm:block text-[10px] font-mono text-gray-300 dark:text-gray-600 flex-shrink-0">
                        {subtask.agentium_id}
                    </span>
                )}
                <div className="flex-shrink-0">
                    <CriticSummaryDots reviews={subtask.reviews} />
                </div>
                <span className={`hidden md:inline-flex flex-shrink-0 items-center px-2 py-0.5 rounded text-[10px] font-semibold ${cfg.badge}`}>
                    {cfg.label}
                </span>
                {hasProblem && (
                    <AlertCircle className="w-3.5 h-3.5 text-red-400 dark:text-red-500 flex-shrink-0" />
                )}
                <ChevronDown
                    className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 group-hover:text-gray-600 dark:group-hover:text-gray-300 ${isExpanded ? 'rotate-180' : ''}`}
                />
            </button>

            {isExpanded && (
                <div className="border-t border-gray-100 dark:border-[#1e2535] bg-gray-50/50 dark:bg-[#0f1117]/50">
                    <div className="px-5 pt-3 pb-2 flex items-center gap-4 flex-wrap border-b border-gray-100 dark:border-[#1e2535]">
                        <span className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">
                            Critic Reviews
                        </span>
                        {subtask.error_info && subtask.error_info.error_count > 0 && (
                            <div className="flex items-center gap-1.5">
                                <RotateCcw className="w-3 h-3 text-amber-500" />
                                <span className="text-xs text-amber-600 dark:text-amber-400">
                                    {subtask.error_info.retry_count}/{subtask.error_info.max_retries} retries
                                </span>
                            </div>
                        )}
                        {subtask.progress !== undefined && (
                            <div className="flex items-center gap-1.5">
                                <Timer className="w-3 h-3 text-gray-400" />
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                    {subtask.progress}% complete
                                </span>
                            </div>
                        )}
                        {subtask.error_info?.last_error && (
                            <span className="text-xs text-red-500 dark:text-red-400 truncate max-w-xs" title={subtask.error_info.last_error}>
                                ✕ {subtask.error_info.last_error}
                            </span>
                        )}
                    </div>
                    <CriticReviewPanel reviews={subtask.reviews} loading={subtask.reviewsLoading} />
                </div>
            )}
        </div>
    );
};

// ─── Task Subtask Accordion ───────────────────────────────────────────────────

// FIX 5: Uses tasksService.getTaskSubtasks() and criticsService.getTaskReviews()
//        instead of calling api.get() directly.
const TaskSubtaskAccordion: React.FC<{ task: Task }> = ({ task }) => {
    const [subtasks, setSubtasks] = useState<SubtaskWithReviews[]>([]);
    const [loading, setLoading]   = useState(true);
    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    // FIX 6: useRef<Map> keeps refs stable across renders — createRef is only
    // called once per unique subtask id, not on every render cycle.
    const subtaskRefs = useRef<Map<string, React.RefObject<HTMLDivElement>>>(new Map());

    const getOrCreateRef = (id: string): React.RefObject<HTMLDivElement> => {
        if (!subtaskRefs.current.has(id)) {
            subtaskRefs.current.set(id, React.createRef<HTMLDivElement>());
        }
        return subtaskRefs.current.get(id)!;
    };

    // FIX 5: hoisted so it can be referenced in useEffect without closure issues
    const loadReviewsForSubtask = useCallback(async (subtaskId: string) => {
        setSubtasks(prev => prev.map(s =>
            s.id === subtaskId ? { ...s, reviewsLoading: true } : s
        ));
        try {
            // FIX 5: use service layer instead of api.get()
            const data = await criticsService.getTaskReviews(subtaskId);
            const reviews: CritiqueReview[] = data.reviews ?? [];
            setSubtasks(prev => prev.map(s =>
                s.id === subtaskId ? { ...s, reviews, reviewsLoaded: true, reviewsLoading: false } : s
            ));
        } catch {
            setSubtasks(prev => prev.map(s =>
                s.id === subtaskId ? { ...s, reviewsLoading: false } : s
            ));
        }
    }, []);

    useEffect(() => {
        // FIX 5: use service layer instead of api.get()
        tasksService.getTaskSubtasks(task.id)
            .then(data => {
                const raw: Subtask[] = data.subtasks ?? [];
                const withReviews: SubtaskWithReviews[] = raw.map(s => ({
                    ...s,
                    reviews: [],
                    reviewsLoaded: false,
                    reviewsLoading: false,
                }));
                setSubtasks(withReviews);

                const autoExpand = new Set<string>(
                    raw.filter(s => isProblematic(s.status)).map(s => s.id)
                );
                setExpanded(autoExpand);
                autoExpand.forEach(id => loadReviewsForSubtask(id));
            })
            .catch(() => showToast.error('Failed to load subtasks'))
            .finally(() => setLoading(false));
    }, [task.id, loadReviewsForSubtask]);

    const toggleSubtask = (id: string) => {
        setExpanded(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const jumpToFirstIssue = () => {
        const first = subtasks.find(s => isProblematic(s.status));
        if (first) {
            subtaskRefs.current.get(first.id)?.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    };

    if (loading) {
        return (
            <div className="flex items-center gap-2 px-5 py-4 text-gray-400 dark:text-gray-500">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span className="text-xs">Loading subtasks…</span>
            </div>
        );
    }

    if (subtasks.length === 0) {
        return (
            <div className="flex items-center gap-2 px-5 py-4 text-gray-400 dark:text-gray-500">
                <CornerDownRight className="w-3.5 h-3.5" />
                <span className="text-xs italic">No subtasks have been generated yet.</span>
            </div>
        );
    }

    const problemCount = subtasks.filter(s => isProblematic(s.status)).length;
    const passCount    = subtasks.filter(s => s.status === 'completed').length;

    return (
        <div>
            <div className="px-5 py-2.5 bg-gray-50 dark:bg-[#0f1117] border-b border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                        Subtasks
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                        {subtasks.length} total
                    </span>
                    {passCount > 0 && (
                        <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                            {passCount} passing
                        </span>
                    )}
                    {problemCount > 0 && (
                        <span className="inline-flex items-center gap-1 text-xs text-red-500 dark:text-red-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                            {problemCount} need attention
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setExpanded(new Set(subtasks.map(s => s.id)))}
                        className="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors px-2 py-0.5 rounded hover:bg-gray-100 dark:hover:bg-[#1e2535]"
                    >
                        Expand all
                    </button>
                    <span className="text-gray-200 dark:text-gray-700">·</span>
                    <button
                        onClick={() => setExpanded(new Set())}
                        className="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors px-2 py-0.5 rounded hover:bg-gray-100 dark:hover:bg-[#1e2535]"
                    >
                        Collapse all
                    </button>
                </div>
            </div>

            <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                {subtasks.map((subtask, i) => (
                    <SubtaskRow
                        key={subtask.id}
                        subtask={subtask}
                        index={i}
                        isExpanded={expanded.has(subtask.id)}
                        onToggle={() => toggleSubtask(subtask.id)}
                        onLoadReviews={() => loadReviewsForSubtask(subtask.id)}
                        subtaskRef={getOrCreateRef(subtask.id)}
                    />
                ))}
            </div>

            {problemCount > 0 && (
                <div className="sticky bottom-4 mx-4 mt-2 mb-1 z-10">
                    <button
                        onClick={jumpToFirstIssue}
                        className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/20 transition-all duration-150 group"
                    >
                        <div className="flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            <span className="text-sm font-medium">
                                {problemCount} subtask{problemCount !== 1 ? 's' : ''} need{problemCount === 1 ? 's' : ''} attention
                            </span>
                        </div>
                        <div className="flex items-center gap-1.5 text-red-200 group-hover:text-white transition-colors">
                            <span className="text-xs font-medium">Jump to first</span>
                            <ArrowDown className="w-3.5 h-3.5" />
                        </div>
                    </button>
                </div>
            )}
        </div>
    );
};

// ─── Main Task Card ───────────────────────────────────────────────────────────

// FIX 2: React.memo prevents re-renders when sibling tasks update
const MainTaskCard: React.FC<{ task: Task; onUpdated?: (updated: Task) => void; onViewLive?: (task: Task) => void }> = React.memo(({ task, onUpdated, onViewLive }) => {
    const [subtasksOpen, setSubtasksOpen]         = useState(false);
    const [governanceOpen, setGovernanceOpen]     = useState(false);
    const [isEditing, setIsEditing]               = useState(false);
    const [isSaving, setIsSaving]                 = useState(false);
    const [editTitle, setEditTitle]               = useState(task.title);
    const [editDescription, setEditDescription]   = useState(task.description ?? '');
    // FIX 8: task.priority is typed in the Task interface — no as any needed
    const [editPriority, setEditPriority]         = useState(task.priority ?? 'normal');
    const [editStatus, setEditStatus]             = useState(task.status);
    const [allowedTransitions, setAllowedTransitions] = useState<string[] | null>(null);
    const [transitionsLoading, setTransitionsLoading] = useState(false);

    // FIX 1: PRIORITY_OPTIONS_LIST is now at module scope — no recreation per render

    const openEdit = async () => {
        setEditTitle(task.title);
        setEditDescription(task.description ?? '');
        setEditPriority(task.priority ?? 'normal');
        setEditStatus(task.status);
        setIsEditing(true);
        setTransitionsLoading(true);
        try {
            const res = await tasksService.getAllowedTransitions(task.id);
            setAllowedTransitions([task.status, ...res.allowed_transitions]);
        } catch {
            setAllowedTransitions(null);
        } finally {
            setTransitionsLoading(false);
        }
    };

    const cancelEdit = () => {
        setIsEditing(false);
        setAllowedTransitions(null);
    };

    const saveEdit = async () => {
        setIsSaving(true);
        try {
            const payload: UpdateTaskRequest = {};
            if (editTitle !== task.title)                       payload.title = editTitle;
            if (editDescription !== (task.description ?? ''))  payload.description = editDescription;
            if (editPriority !== (task.priority ?? 'normal'))  payload.priority = editPriority;
            if (editStatus !== task.status)                    payload.status = editStatus;

            if (Object.keys(payload).length === 0) { cancelEdit(); return; }

            const updated = await tasksService.updateTask(task.id, payload);
            onUpdated?.(updated);
            setIsEditing(false);
            showToast.success('Task updated');
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail ?? 'Failed to update task');
        } finally {
            setIsSaving(false);
        }
    };

    // FIX 1+8: These maps are now at module scope (TASK_STATUS_COLOR,
    // TASK_PRIORITY_COLOR) — removed from component body.
    // FIX 8: All (task as any) casts removed — fields exist on Task type.
    const gov       = task.governance;
    const agents    = task.assigned_agents;
    const errorInfo = task.error_info;
    const progress  = task.progress ?? 0;

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">

            {/* ── Main task header ──────────────────────────────────────── */}
            <div className="px-6 pt-5 pb-4 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <ListTodo className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>

                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                            {/* FIX 8: task.agentium_id is optional string — no as any */}
                            {task.agentium_id && (
                                <span className="text-xs font-mono text-gray-400 dark:text-gray-500">
                                    {task.agentium_id}
                                </span>
                            )}
                            {isEditing ? (
                                <select
                                    value={editStatus}
                                    onChange={e => setEditStatus(e.target.value)}
                                    disabled={transitionsLoading}
                                    className="text-xs font-semibold rounded-full px-2.5 py-0.5 border border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-400"
                                >
                                    {(allowedTransitions ?? [task.status]).map(s => (
                                        <option key={s} value={s}>{s.replace('_', ' ')}</option>
                                    ))}
                                </select>
                            ) : (
                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${TASK_STATUS_COLOR[task.status] ?? TASK_STATUS_COLOR.pending}`}>
                                    {task.status.replace('_', ' ')}
                                </span>
                            )}
                            {isEditing ? (
                                <select
                                    value={editPriority}
                                    onChange={e => setEditPriority(e.target.value)}
                                    className="text-xs font-semibold uppercase rounded px-2 py-0.5 border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#1e2535] text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-400"
                                >
                                    {/* FIX 1: use module-scope constant */}
                                    {PRIORITY_OPTIONS_LIST.map(p => (
                                        <option key={p} value={p}>{p}</option>
                                    ))}
                                </select>
                            ) : (
                                // FIX 8: task.priority typed — no as any
                                <span className={`text-xs font-semibold uppercase tracking-wide ${TASK_PRIORITY_COLOR[task.priority ?? 'normal'] ?? TASK_PRIORITY_COLOR.normal}`}>
                                    {task.priority ?? 'normal'}
                                </span>
                            )}
                        </div>
                        {isEditing ? (
                            <input
                                type="text"
                                value={editTitle}
                                onChange={e => setEditTitle(e.target.value)}
                                className="w-full text-base font-semibold text-gray-900 dark:text-white bg-gray-50 dark:bg-[#1e2535] border border-blue-300 dark:border-blue-600 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400 mb-2"
                            />
                        ) : (
                            <h3 className="text-base font-semibold text-gray-900 dark:text-white leading-snug">
                                {task.title}
                            </h3>
                        )}
                        {isEditing ? (
                            <textarea
                                value={editDescription}
                                onChange={e => setEditDescription(e.target.value)}
                                rows={2}
                                className="w-full text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-[#1e2535] border border-blue-300 dark:border-blue-600 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                            />
                        ) : (
                            task.description && (
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                                    {task.description}
                                </p>
                            )
                        )}
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                        {isEditing ? (
                            <>
                                <button
                                    onClick={saveEdit}
                                    disabled={isSaving}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
                                >
                                    <Save className="w-3.5 h-3.5" />
                                    {isSaving ? 'Saving…' : 'Save'}
                                </button>
                                <button
                                    onClick={cancelEdit}
                                    disabled={isSaving}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors disabled:opacity-50"
                                >
                                    <X className="w-3.5 h-3.5" />
                                    Cancel
                                </button>
                            </>
                        ) : (
                            <>
                                <button
                                    onClick={openEdit}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                                    title="Edit task"
                                >
                                    <Edit3 className="w-3.5 h-3.5" />
                                    Edit
                                </button>
                                {errorInfo && (
                                    <button
                                        onClick={() =>
                                            tasksService.retryTask(task.id)
                                                .then(() => showToast.success('Task queued for retry'))
                                                .catch(() => showToast.error('Retry failed'))
                                        }
                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-500/20 transition-colors"
                                    >
                                        <RotateCcw className="w-3.5 h-3.5" />
                                        Retry
                                    </button>
                                )}
                                {['in_progress', 'pending', 'retrying'].includes(task.status) && (
                                    <button
                                        onClick={() =>
                                            tasksService.escalateTask(task.id, 'Manual escalation')
                                                .then(() => showToast.success('Task escalated'))
                                                .catch(() => showToast.error('Escalation failed'))
                                        }
                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-500/20 transition-colors"
                                    >
                                        <ShieldAlert className="w-3.5 h-3.5" />
                                        Escalate
                                    </button>
                                )}
                                {task.task_type === 'browser' && (task.status === 'in_progress' || task.status === 'executing') && onViewLive && (
                                    <button
                                        onClick={() => onViewLive(task)}
                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400 border border-violet-200 dark:border-violet-500/20 hover:bg-violet-200 dark:hover:bg-violet-500/25 transition-colors duration-150"
                                        title="Watch agent interact with browser live"
                                    >
                                        <Monitor className="w-3.5 h-3.5" />
                                        View Live
                                    </button>
                                )}
                            </>
                        )}
                    </div>
                </div>

                {progress > 0 && (
                    <div className="mt-4">
                        <div className="flex items-center justify-between mb-1.5">
                            <span className="text-xs text-gray-400 dark:text-gray-500">Overall progress</span>
                            <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">{progress}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-gray-100 dark:bg-[#1e2535] overflow-hidden">
                            <div
                                className="h-full rounded-full bg-blue-500 transition-all duration-700"
                                style={{ width: `${Math.min(100, progress)}%` }}
                            />
                        </div>
                    </div>
                )}

                {agents && (
                    <div className="mt-4 flex items-center gap-3 flex-wrap">
                        <Users className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                        {agents.head && (
                            <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                                <span className="font-medium text-gray-700 dark:text-gray-300">Head:</span>
                                <span className="font-mono bg-gray-100 dark:bg-[#1e2535] px-1.5 py-0.5 rounded text-[10px]">{agents.head}</span>
                            </span>
                        )}
                        {agents.lead && (
                            <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                                <span className="font-medium text-gray-700 dark:text-gray-300">Lead:</span>
                                <span className="font-mono bg-gray-100 dark:bg-[#1e2535] px-1.5 py-0.5 rounded text-[10px]">{agents.lead}</span>
                            </span>
                        )}
                        {agents.task_agents?.length > 0 && (
                            <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                                <Cpu className="w-3 h-3" />
                                <span>{agents.task_agents.length} task agent{agents.task_agents.length !== 1 ? 's' : ''}</span>
                            </span>
                        )}
                    </div>
                )}

                {errorInfo && errorInfo.error_count > 0 && (
                    <div className="mt-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/5 border border-red-200 dark:border-red-500/20">
                        <AlertCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <span className="text-xs font-medium text-red-700 dark:text-red-400">
                                {errorInfo.error_count} error{errorInfo.error_count !== 1 ? 's' : ''} · retry {errorInfo.retry_count}/{errorInfo.max_retries}
                            </span>
                            {errorInfo.last_error && (
                                <p className="text-[10px] text-red-600 dark:text-red-500 mt-0.5 truncate">{errorInfo.last_error}</p>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* ── Subtasks section ──────────────────────────────────────── */}
            <div>
                <button
                    onClick={() => setSubtasksOpen(o => !o)}
                    className="w-full flex items-center gap-3 px-6 py-3 hover:bg-gray-50 dark:hover:bg-[#1e2535]/50 transition-colors duration-150 border-b border-gray-100 dark:border-[#1e2535] group"
                >
                    <CornerDownRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex-1 text-left">
                        Subtasks &amp; Critic Reviews
                    </span>
                    <ChevronDown
                        className={`w-4 h-4 text-gray-400 transition-transform duration-200 group-hover:text-gray-600 dark:group-hover:text-gray-300 ${subtasksOpen ? 'rotate-180' : ''}`}
                    />
                </button>
                {subtasksOpen && <TaskSubtaskAccordion task={task} />}
            </div>

            {/* ── Governance details (collapsible) ─────────────────────── */}
            {gov && (gov.constitutional_basis || gov.hierarchical_id || gov.parent_task_id) && (
                <div className="border-t border-gray-100 dark:border-[#1e2535]">
                    <button
                        onClick={() => setGovernanceOpen(o => !o)}
                        className="w-full flex items-center gap-3 px-6 py-3 hover:bg-gray-50 dark:hover:bg-[#1e2535]/50 transition-colors duration-150 group"
                    >
                        <Info className="w-4 h-4 text-gray-400 flex-shrink-0" />
                        <span className="text-sm font-medium text-gray-500 dark:text-gray-400 flex-1 text-left">
                            Governance details
                        </span>
                        <ChevronDown
                            className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${governanceOpen ? 'rotate-180' : ''}`}
                        />
                    </button>
                    {governanceOpen && (
                        <div className="px-6 pb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {gov.constitutional_basis && (
                                <div>
                                    <p className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1">Constitutional basis</p>
                                    <p className="text-xs text-gray-700 dark:text-gray-300">{gov.constitutional_basis}</p>
                                </div>
                            )}
                            {gov.hierarchical_id && (
                                <div>
                                    <p className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1">Hierarchical ID</p>
                                    <p className="text-xs font-mono text-gray-700 dark:text-gray-300">{gov.hierarchical_id}</p>
                                </div>
                            )}
                            {gov.parent_task_id && (
                                <div>
                                    <p className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 mb-1">Parent task</p>
                                    <p className="text-xs font-mono text-gray-700 dark:text-gray-300">{gov.parent_task_id}</p>
                                </div>
                            )}
                            <div className="sm:col-span-2 flex items-center gap-3 pt-1 flex-wrap">
                                {gov.council_approved && (
                                    <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                                        <CheckCircle className="w-3 h-3" /> Council approved
                                    </span>
                                )}
                                {gov.head_approved && (
                                    <span className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                                        <CheckCircle className="w-3 h-3" /> Head approved
                                    </span>
                                )}
                                {gov.requires_deliberation && (
                                    <span className="inline-flex items-center gap-1 text-xs text-purple-600 dark:text-purple-400">
                                        <AlertTriangle className="w-3 h-3" /> Requires deliberation
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── Footer meta ──────────────────────────────────────────── */}
            <div className="px-6 py-3 bg-gray-50 dark:bg-[#0f1117] border-t border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                <div className="flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500">
                    {/* FIX 8: task.created_at is string | null — guard null before passing to fmtDate */}
                    {task.created_at && (
                        <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {fmtDate(task.created_at)}
                        </span>
                    )}
                    {/* FIX 8: task.event_count is optional number — no as any */}
                    {(task.event_count ?? 0) > 0 && (
                        <span className="flex items-center gap-1">
                            <Hash className="w-3 h-3" />
                            {task.event_count} events
                        </span>
                    )}
                </div>
                <span className="text-[10px] font-mono text-gray-300 dark:text-gray-700 select-all">
                    {task.id}
                </span>
            </div>
        </div>
    );
});
MainTaskCard.displayName = 'MainTaskCard';

// ═══════════════════════════════════════════════════════════════════════════════
// User Preferences Components
// ═══════════════════════════════════════════════════════════════════════════════

const CATEGORY_META: Record<string, {
    label: string;
    icon: React.ElementType;
    color: string;
    bg: string;
    border: string;
}> = {
    general:       { label: 'General',       icon: Settings,          color: 'text-gray-600',   bg: 'bg-gray-50',   border: 'border-gray-200' },
    ui:            { label: 'UI',            icon: SlidersHorizontal, color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200' },
    notifications: { label: 'Notifications', icon: Activity,          color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200' },
    agents:        { label: 'Agents',        icon: Users,             color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200' },
    tasks:         { label: 'Tasks',         icon: CheckSquare,       color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-200' },
    chat:          { label: 'Chat',          icon: Users,             color: 'text-pink-600',   bg: 'bg-pink-50',   border: 'border-pink-200' },
    models:        { label: 'Models',        icon: Cpu,               color: 'text-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-200' },
    tools:         { label: 'Tools',         icon: Zap,               color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200' },
    privacy:       { label: 'Privacy',       icon: ShieldCheck,       color: 'text-teal-600',   bg: 'bg-teal-50',   border: 'border-teal-200' },
    custom:        { label: 'Custom',        icon: Edit3,             color: 'text-cyan-600',   bg: 'bg-cyan-50',   border: 'border-cyan-200' },
};

// ─── Preference Value Editor ──────────────────────────────────────────────────

const PreferenceValueEditor: React.FC<{
    value: any;
    dataType: string;
    onSave: (value: any) => void;
    onCancel: () => void;
}> = ({ value, dataType, onSave, onCancel }) => {
    const [inputValue, setInputValue] = useState(formatPreferenceValue(value, dataType));

    const handleSave = () => {
        const parsed = parsePreferenceValue(inputValue, dataType);
        onSave(parsed);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSave();
        } else if (e.key === 'Escape') {
            onCancel();
        }
    };

    if (dataType === 'boolean') {
        return (
            <div className="flex items-center gap-2">
                <button
                    onClick={() => onSave(true)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        value === true
                            ? 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400 border border-green-300 dark:border-green-500/30'
                            : 'bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                >
                    Yes
                </button>
                <button
                    onClick={() => onSave(false)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        value === false
                            ? 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400 border border-red-300 dark:border-red-500/30'
                            : 'bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                >
                    No
                </button>
                <button aria-label="Cancel"
                    onClick={onCancel}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        );
    }

    return (
        <div className="flex items-center gap-2">
            <input
                type={dataType === 'integer' || dataType === 'float' ? 'number' : 'text'}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                autoFocus
                className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-[#2a3347] rounded-lg
                    bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                    focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder={dataType === 'json' || dataType === 'array' ? 'Enter valid JSON...' : 'Enter value...'}
            />
            <button
                onClick={handleSave}
                className="p-1.5 rounded-lg text-green-600 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300
                    hover:bg-green-50 dark:hover:bg-green-500/10 transition-colors"
                title="Save"
            >
                <Save className="w-4 h-4" />
            </button>
            <button
                onClick={onCancel}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300
                    hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                title="Cancel"
            >
                <X className="w-4 h-4" />
            </button>
        </div>
    );
};

// ─── Preference Card ──────────────────────────────────────────────────────────

// FIX 2: React.memo prevents re-renders when the list changes but this card's props don't
const PreferenceCard: React.FC<{
    preference: UserPreference;
    onUpdate: (key: string, value: any, reason?: string) => void;
    onDelete: (key: string) => void;
}> = React.memo(({ preference, onUpdate, onDelete }) => {
    const [isEditing, setIsEditing] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [history, setHistory] = useState<any[]>([]);
    const [loadingHistory, setLoadingHistory] = useState(false);
    // FIX 10: local confirm state — replaces browser confirm() dialog
    const [confirmingDelete, setConfirmingDelete] = useState(false);
    const meta = CATEGORY_META[preference.category] || CATEGORY_META.general;

    const handleSave = (value: any) => {
        // FIX 17 (audit reason): use a descriptive reason string instead of hardcoded file name
        onUpdate(preference.key, value, 'Updated by user via preferences panel');
        setIsEditing(false);
    };

    const loadHistory = async () => {
        if (!showHistory) {
            setShowHistory(true);
            setLoadingHistory(true);
            try {
                const data = await preferencesService.admin.getPreferenceHistory(preference.agentium_id, 10);
                setHistory(data.history);
            } catch (err) {
                console.error('Failed to load history:', err);
            } finally {
                setLoadingHistory(false);
            }
        } else {
            setShowHistory(false);
        }
    };

    return (
        <div className="bg-white dark:bg-[#1e2535] rounded-lg border border-gray-200 dark:border-[#2a3347] p-4
            hover:border-gray-300 dark:hover:border-[#3a4560] transition-all duration-150">
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <meta.icon className={`w-4 h-4 ${meta.color}`} />
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                            {meta.label}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                            preference.editable
                                ? 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400'
                                : 'bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400'
                        }`}>
                            {preference.editable ? 'Editable' : 'Read-only'}
                        </span>
                        {preference.scope !== 'global' && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400">
                                {preference.scope}
                            </span>
                        )}
                    </div>
                    <h4 className="font-medium text-gray-900 dark:text-white mb-1 truncate" title={preference.key}>
                        {preference.key}
                    </h4>
                    {preference.description && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 line-clamp-2">
                            {preference.description}
                        </p>
                    )}
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={loadHistory}
                        className={`p-1.5 rounded-lg transition-colors ${
                            showHistory
                                ? 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400'
                                : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                        }`}
                        title="View history"
                    >
                        <History className="w-4 h-4" />
                    </button>
                    {preference.editable && (
                        <>
                            <button
                                onClick={() => setIsEditing(!isEditing)}
                                className={`p-1.5 rounded-lg transition-colors ${
                                    isEditing
                                        ? 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400'
                                        : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                                }`}
                                title="Edit"
                            >
                                <Edit3 className="w-4 h-4" />
                            </button>
                            {/* FIX 10: styled inline confirm instead of browser confirm() */}
                            {confirmingDelete ? (
                                <div className="flex items-center gap-1">
                                    <button
                                        onClick={() => { onDelete(preference.key); setConfirmingDelete(false); }}
                                        className="px-2 py-1 text-[10px] font-semibold rounded-md bg-red-600 hover:bg-red-700 text-white transition-colors"
                                    >
                                        Confirm
                                    </button>
                                    <button
                                        onClick={() => setConfirmingDelete(false)}
                                        className="px-2 py-1 text-[10px] font-medium rounded-md bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            ) : (
                                <button
                                    onClick={() => setConfirmingDelete(true)}
                                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 dark:hover:text-red-400
                                        hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                                    title="Delete"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            )}
                        </>
                    )}
                </div>
            </div>

            <div className="mt-3">
                {isEditing ? (
                    <PreferenceValueEditor
                        value={preference.value}
                        dataType={preference.data_type}
                        onSave={handleSave}
                        onCancel={() => setIsEditing(false)}
                    />
                ) : (
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <code className="px-2 py-1 bg-gray-100 dark:bg-[#161b27] rounded text-sm font-mono
                                text-gray-800 dark:text-gray-200">
                                {formatPreferenceValue(preference.value, preference.data_type)}
                            </code>
                            {/* FIX 4: use DATA_TYPE_BADGE_CLASSES for full static class names instead of
                                      bg-${color}-100 interpolation which Tailwind purges in production builds */}
                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                DATA_TYPE_BADGE_CLASSES[DATA_TYPE_LABELS[preference.data_type]?.color]
                                    ?? 'bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400'
                            }`}>
                                {DATA_TYPE_LABELS[preference.data_type]?.label || preference.data_type}
                            </span>
                        </div>
                        {preference.last_modified_by_agent && (
                            <span className="text-[10px] text-gray-400 dark:text-gray-500">
                                Modified by {preference.last_modified_by_agent}
                            </span>
                        )}
                    </div>
                )}
            </div>

            {showHistory && (
                <div className="mt-3 pt-3 border-t border-gray-100 dark:border-[#1e2535]">
                    <h5 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1">
                        <History className="w-3 h-3" />
                        Recent Changes
                    </h5>
                    {loadingHistory ? (
                        <div className="space-y-2">
                            {[...Array(2)].map((_, i) => (
                                <div key={i} className="h-8 bg-gray-100 dark:bg-[#161b27] rounded animate-pulse" />
                            ))}
                        </div>
                    ) : history.length === 0 ? (
                        <p className="text-xs text-gray-400 dark:text-gray-500 italic">No history available</p>
                    ) : (
                        <div className="space-y-2 max-h-32 overflow-y-auto">
                            {history.slice(0, 5).map((entry, idx) => (
                                <div key={idx} className="flex items-center gap-2 text-xs">
                                    <span className="text-gray-500 dark:text-gray-400">
                                        {entry.changed_by || 'User'}
                                    </span>
                                    <span className="text-gray-300 dark:text-gray-600">→</span>
                                    <code className="text-amber-600 dark:text-amber-400 line-through">
                                        {formatPreferenceValue(entry.previous_value, preference.data_type)}
                                    </code>
                                    <span className="text-gray-300 dark:text-gray-600">→</span>
                                    <code className="text-green-600 dark:text-green-400">
                                        {formatPreferenceValue(entry.new_value, preference.data_type)}
                                    </code>
                                    <span className="text-gray-400 dark:text-gray-500 ml-auto">
                                        {new Date(entry.timestamp).toLocaleDateString()}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
});
PreferenceCard.displayName = 'PreferenceCard';

// ─── Preferences Tab ────────────────────────────────────────────────────────────

const PreferencesTab: React.FC = () => {
    const [preferences, setPreferences] = useState<UserPreference[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [categoryFilter, setCategoryFilter] = useState<string>('');
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showDefaults, setShowDefaults] = useState(false);
    const [defaults, setDefaults] = useState<Record<string, unknown>>({});
    const [optimizing, setOptimizing] = useState(false);
    const [optimizationResult, setOptimizationResult] = useState<any>(null);

    const [newPref, setNewPref] = useState({
        key: '',
        value: '',
        category: 'general',
        dataType: 'string',
        scope: 'global',
        description: '',
        editableByAgents: true,
    });

    const loadPreferences = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            // FIX 9: backend filters by category; client-side re-filter removed below.
            const data = await preferencesService.getPreferences(
                categoryFilter ? { category: categoryFilter } : undefined
            );
            setPreferences(data);
        } catch (err: any) {
            const isNetworkError = !err?.response;
            const msg = isNetworkError
                ? 'Cannot reach the server — make sure the backend is running on port 8000.'
                : (err?.response?.data?.detail || 'Failed to load preferences');
            console.error('Failed to load preferences:', err);
            setLoadError(msg);
        } finally {
            setLoading(false);
        }
    }, [categoryFilter]);

    useEffect(() => { loadPreferences(); }, [loadPreferences]);

    const handleUpdate = async (key: string, value: any, reason?: string) => {
        try {
            await preferencesService.updatePreference(key, value);
            showToast.success('Preference updated');
            loadPreferences();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to update preference');
        }
    };

    // FIX 10: confirm() removed — PreferenceCard handles inline confirmation
    const handleDelete = async (key: string) => {
        try {
            await preferencesService.deletePreference(key);
            showToast.success('Preference deleted');
            loadPreferences();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to delete preference');
        }
    };

    const handleCreate = async () => {
        try {
            const value = parsePreferenceValue(newPref.value, newPref.dataType);
            await preferencesService.createPreference({
                key: newPref.key,
                value,
                category: newPref.category,
                description: newPref.description,
            });
            showToast.success('Preference created');
            setShowCreateModal(false);
            setNewPref({
                key: '',
                value: '',
                category: 'general',
                dataType: 'string',
                scope: 'global',
                description: '',
                editableByAgents: true,
            });
            loadPreferences();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to create preference');
        }
    };

    const handleInitializeDefaults = async () => {
        try {
            await preferencesService.admin.initializeSystem();
            loadPreferences();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to initialize defaults');
        }
    };

    const handleOptimize = async () => {
        setOptimizing(true);
        try {
            await preferencesService.admin.optimize();
            showToast.success('Optimization complete');
            loadPreferences();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to optimize');
        } finally {
            setOptimizing(false);
        }
    };

    const loadDefaults = async () => {
        if (!showDefaults) {
            try {
                const data = await preferencesService.admin.getSystemDefaults();
                setDefaults(data.defaults);
            } catch (err) {
                console.error('Failed to load defaults:', err);
            }
        }
        setShowDefaults(!showDefaults);
    };

    // FIX 9: backend already filtered by categoryFilter — no redundant client-side filter.
    // preferences is already the correctly-filtered list from the server.
    const filteredPreferences = preferences;

    const groupedByCategory = filteredPreferences.reduce((acc, pref) => {
        if (!acc[pref.category]) acc[pref.category] = [];
        acc[pref.category].push(pref);
        return acc;
    }, {} as Record<string, UserPreference[]>);

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Settings className="w-5 h-5 text-blue-500" />
                        User Preferences
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Manage system and user-specific preferences
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={loadDefaults}
                        className="px-3 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400
                            bg-gray-100 dark:bg-[#161b27] hover:bg-gray-200 dark:hover:bg-gray-700
                            transition-colors flex items-center gap-1.5"
                    >
                        <Database className="w-4 h-4" />
                        {showDefaults ? 'Hide' : 'View'} Defaults
                    </button>
                    <button
                        onClick={handleOptimize}
                        disabled={optimizing}
                        className="px-3 py-2 rounded-lg text-sm font-medium text-purple-600 dark:text-purple-400
                            bg-purple-50 dark:bg-purple-500/10 hover:bg-purple-100 dark:hover:bg-purple-500/20
                            transition-colors flex items-center gap-1.5 disabled:opacity-50"
                    >
                        <Sparkles className={`w-4 h-4 ${optimizing ? 'animate-spin' : ''}`} />
                        Optimize
                    </button>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="px-3 py-2 rounded-lg text-sm font-medium text-white
                            bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500
                            transition-colors flex items-center gap-1.5"
                    >
                        <Plus className="w-4 h-4" />
                        New Preference
                    </button>
                </div>
            </div>

            {/* Optimization Result */}
            {optimizationResult && (
                <div className="bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-lg p-4">
                    <h3 className="text-sm font-medium text-green-800 dark:text-green-400 mb-2 flex items-center gap-1">
                        <Sparkles className="w-4 h-4" />
                        Optimization Results
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                        <div className="text-center p-2 bg-white dark:bg-green-500/5 rounded">
                            <div className="font-semibold text-green-700 dark:text-green-400">{optimizationResult.duplicates_removed}</div>
                            <div className="text-xs text-green-600 dark:text-green-500">Duplicates</div>
                        </div>
                        <div className="text-center p-2 bg-white dark:bg-green-500/5 rounded">
                            <div className="font-semibold text-green-700 dark:text-green-400">{optimizationResult.unused_cleaned}</div>
                            <div className="text-xs text-green-600 dark:text-green-500">Unused</div>
                        </div>
                        <div className="text-center p-2 bg-white dark:bg-green-500/5 rounded">
                            <div className="font-semibold text-green-700 dark:text-green-400">{optimizationResult.history_compressed}</div>
                            <div className="text-xs text-green-600 dark:text-green-500">History</div>
                        </div>
                        <div className="text-center p-2 bg-white dark:bg-green-500/5 rounded">
                            <div className="font-semibold text-green-700 dark:text-green-400">{optimizationResult.conflicts_resolved}</div>
                            <div className="text-xs text-green-600 dark:text-green-500">Conflicts</div>
                        </div>
                    </div>
                    <button onClick={() => setOptimizationResult(null)} className="mt-2 text-xs text-green-600 dark:text-green-400 hover:underline">
                        Dismiss
                    </button>
                </div>
            )}

            {/* Defaults Panel */}
            {showDefaults && (
                <div className="bg-gray-50 dark:bg-[#161b27]/50 border border-gray-200 dark:border-[#1e2535] rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">System Defaults</h3>
                        <button onClick={handleInitializeDefaults} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
                            Initialize for my account
                        </button>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
                        {Object.entries(defaults).slice(0, 12).map(([key, value]) => (
                            <div key={key} className="flex items-center gap-2 p-2 bg-white dark:bg-[#1e2535] rounded">
                                <code className="text-gray-600 dark:text-gray-400 truncate">{key}</code>
                                <span className="text-gray-400">=</span>
                                <code className="text-blue-600 dark:text-blue-400 truncate">
                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                </code>
                            </div>
                        ))}
                        {Object.keys(defaults).length > 12 && (
                            <div className="text-center text-gray-400 dark:text-gray-500 py-2">
                                +{Object.keys(defaults).length - 12} more
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Category Filter */}
            <div className="flex flex-wrap items-center gap-2">
                <button
                    onClick={() => setCategoryFilter('')}
                    aria-pressed={categoryFilter === ''}
                    className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                        categoryFilter === ''
                            ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400'
                            : 'bg-gray-100 text-gray-600 dark:bg-[#161b27] dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                >
                    All ({preferences.length})
                </button>
                {Object.keys(groupedByCategory).map(cat => (
                    <button
                        key={cat}
                        onClick={() => setCategoryFilter(cat === categoryFilter ? '' : cat)}
                        aria-pressed={categoryFilter === cat}
                        className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors flex items-center gap-1 ${
                            categoryFilter === cat
                                ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400'
                                : 'bg-gray-100 text-gray-600 dark:bg-[#161b27] dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                        }`}
                    >
                        {CATEGORY_META[cat]?.icon && (
                            <span className="w-3 h-3">
                                {React.createElement(CATEGORY_META[cat].icon, { className: 'w-3 h-3' })}
                            </span>
                        )}
                        {CATEGORY_META[cat]?.label || cat}
                        <span className="text-xs opacity-70">({groupedByCategory[cat].length})</span>
                    </button>
                ))}
            </div>

            {/* Error state */}
            {loadError && !loading && (
                <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl p-6 text-center text-red-600 dark:text-red-400">
                    <AlertTriangle className="w-10 h-10 mx-auto mb-3 opacity-80" />
                    <h3 className="text-base font-semibold mb-1">Failed to load preferences</h3>
                    <p className="text-sm mb-4">{loadError}</p>
                    <button onClick={loadPreferences} className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium inline-flex items-center gap-2">
                        <RefreshCw className="w-4 h-4" />Retry
                    </button>
                </div>
            )}

            {loading ? (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="h-32 rounded-lg bg-gray-100 dark:bg-[#161b27] animate-pulse" />
                    ))}
                </div>
            ) : filteredPreferences.length === 0 ? (
                <div className="text-center py-12">
                    <Settings className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-1">No preferences found</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                        {categoryFilter
                            ? `No preferences in category "${categoryFilter}"`
                            : 'Create your first preference to get started'}
                    </p>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
                    >
                        Create Preference
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {filteredPreferences.map(pref => (
                        <PreferenceCard
                            key={pref.agentium_id}
                            preference={pref}
                            onUpdate={handleUpdate}
                            onDelete={handleDelete}
                        />
                    ))}
                </div>
            )}

            {/* Create Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white dark:bg-[#1e2535] rounded-xl shadow-xl max-w-md w-full p-6">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                            Create New Preference
                        </h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Key</label>
                                <input
                                    type="text"
                                    value={newPref.key}
                                    onChange={(e) => setNewPref({ ...newPref, key: e.target.value })}
                                    placeholder="e.g., ui.custom_setting"
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg
                                        bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                                        focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Value</label>
                                <input
                                    type="text"
                                    value={newPref.value}
                                    onChange={(e) => setNewPref({ ...newPref, value: e.target.value })}
                                    placeholder="Preference value"
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg
                                        bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                                        focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Category</label>
                                    <select aria-label="Category"
                                        value={newPref.category}
                                        onChange={(e) => setNewPref({ ...newPref, category: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg
                                            bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                                            focus:ring-2 focus:ring-blue-500 outline-none"
                                    >
                                        {PREFERENCE_CATEGORIES.map(cat => (
                                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Data Type</label>
                                    <select aria-label="Data Type"
                                        value={newPref.dataType}
                                        onChange={(e) => setNewPref({ ...newPref, dataType: e.target.value })}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg
                                            bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                                            focus:ring-2 focus:ring-blue-500 outline-none"
                                    >
                                        <option value="string">String</option>
                                        <option value="integer">Integer</option>
                                        <option value="float">Float</option>
                                        <option value="boolean">Boolean</option>
                                        <option value="json">JSON</option>
                                        <option value="array">Array</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                                <textarea
                                    value={newPref.description}
                                    onChange={(e) => setNewPref({ ...newPref, description: e.target.value })}
                                    placeholder="Optional description..."
                                    rows={2}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-[#2a3347] rounded-lg
                                        bg-white dark:bg-[#1e2535] text-gray-900 dark:text-white
                                        focus:ring-2 focus:ring-blue-500 outline-none resize-none"
                                />
                            </div>
                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="editableByAgents"
                                    checked={newPref.editableByAgents}
                                    onChange={(e) => setNewPref({ ...newPref, editableByAgents: e.target.checked })}
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <label htmlFor="editableByAgents" className="text-sm text-gray-700 dark:text-gray-300">
                                    Editable by agents
                                </label>
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 mt-6">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleCreate}
                                disabled={!newPref.key || !newPref.value}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium
                                    disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Create
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// ─── Critic Card (Critics tab) ────────────────────────────────────────────────

// FIX 2: React.memo prevents unnecessary re-renders when the stats grid refreshes
const CriticCard: React.FC<{ critic: CriticAgentStats }> = React.memo(({ critic }) => {
    const meta     = CRITIC_META[critic.critic_specialty] ?? CRITIC_META.output;
    const Icon     = meta.icon;
    const isActive = critic.status === 'active';

    return (
        <div className={`bg-white dark:bg-[#161b27] border ${meta.border} ${meta.borderDark} rounded-xl p-5 hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150`}>
            <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg ${meta.bg} ${meta.bgDark} flex items-center justify-center`}>
                        <Icon className={`w-5 h-5 ${meta.accent} ${meta.accentDark}`} />
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">{meta.label}</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 font-mono">{meta.id}</p>
                    </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-green-400' : 'bg-gray-300 dark:bg-[#2a3347]'}`} title={critic.status} />
                    {critic.preferred_review_model && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${meta.badge}`}>
                            {critic.preferred_review_model.split(':')[1] ?? critic.preferred_review_model}
                        </span>
                    )}
                </div>
            </div>

            <div className="mb-3">
                <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Approval rate</span>
                    <span className={`text-sm font-bold ${meta.accent} ${meta.accentDark}`}>
                        {critic.approval_rate.toFixed(1)}%
                    </span>
                </div>
                <MiniBar value={critic.approval_rate} color={meta.bar} />
            </div>

            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-gray-100 dark:border-[#1e2535]">
                {[
                    { label: 'Reviews',   value: critic.reviews_completed },
                    { label: 'Vetoes',    value: critic.vetoes_issued },
                    { label: 'Escalated', value: critic.escalations_issued },
                ].map(({ label, value }) => (
                    <div key={label} className="text-center">
                        <p className="text-base font-bold text-gray-900 dark:text-white">{value}</p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{label}</p>
                    </div>
                ))}
            </div>

            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                <span className="text-xs text-gray-400 dark:text-gray-500">Avg review</span>
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300 font-mono">
                    {fmtMs(critic.avg_review_time_ms)}
                </span>
            </div>
        </div>
    );
});
CriticCard.displayName = 'CriticCard';

// ─── Critics Tab ──────────────────────────────────────────────────────────────

// FIX 11: accepts an optional callback so the parent can show the real critic count in the tab badge
const CriticsTab: React.FC<{ onStatsLoaded?: (count: number) => void }> = ({ onStatsLoaded }) => {
    const [stats, setStats]           = useState<CriticStatsResponse | null>(null);
    const [loading, setLoading]       = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [inspectTask, setInspectTask]     = useState<string>('');
    const [showInspect, setShowInspect]     = useState(false);
    const [inspectReviews, setInspectReviews] = useState<CritiqueReview[]>([]);
    const [inspectLoading, setInspectLoading] = useState(false);

    const loadStats = useCallback(async (silent = false) => {
        try {
            if (silent) setRefreshing(true); else setLoading(true);
            // FIX 5: use service layer instead of api.get()
            const data = await criticsService.getStats();
            setStats(data);
            // FIX 11: surface the real count to the parent for the tab badge
            onStatsLoaded?.(data.total_critics);
        } catch {
            showToast.error('Failed to load critic stats');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, [onStatsLoaded]);

    useEffect(() => { loadStats(); }, [loadStats]);

    const handleInspect = async () => {
        if (!inspectTask.trim()) return;
        setInspectLoading(true);
        setShowInspect(true);
        try {
            // FIX 5: use service layer instead of api.get()
            const data = await criticsService.getTaskReviews(inspectTask.trim());
            setInspectReviews(data.reviews ?? []);
        } catch {
            showToast.error('Failed to load reviews');
        } finally {
            setInspectLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
                {[0, 1, 2].map(i => (
                    <div key={i} className="h-52 rounded-xl bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                ))}
            </div>
        );
    }

    if (!stats) return null;

    const overallCards = [
        { label: 'Total Reviews',  value: stats.total_reviews,                          icon: Activity,    bg: 'bg-blue-50 dark:bg-blue-500/10',   text: 'text-blue-600 dark:text-blue-400'   },
        { label: 'Approval Rate',  value: `${stats.overall_approval_rate.toFixed(1)}%`, icon: TrendingUp,  bg: 'bg-green-50 dark:bg-green-500/10',  text: 'text-green-600 dark:text-green-400' },
        { label: 'Total Vetoes',   value: stats.total_vetoes,                           icon: ShieldX,     bg: 'bg-red-50 dark:bg-red-500/10',     text: 'text-red-500 dark:text-red-400'     },
        { label: 'Escalations',    value: stats.total_escalations,                      icon: ShieldAlert, bg: 'bg-amber-50 dark:bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400' },
    ];

    return (
        <div className="mt-6 space-y-6">
            {/* Overall stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {overallCards.map(c => (
                    <div key={c.label} className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-3">
                            <div className={`w-9 h-9 rounded-lg ${c.bg} flex items-center justify-center`}>
                                <c.icon className={`w-4 h-4 ${c.text}`} />
                            </div>
                        </div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white">{c.value}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{c.label}</p>
                    </div>
                ))}
            </div>

            {/* Critic agent cards */}
            <div>
                <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Critic Agents
                        <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
                            operate outside democratic chain · absolute veto authority
                        </span>
                    </h3>
                    <button aria-label="Refresh stats"
                        onClick={() => loadStats(true)}
                        disabled={refreshing}
                        className="p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 disabled:opacity-50"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                {/* critics is absent when all ephemeral instances have been terminated */}
                {(stats.critics ?? []).length === 0 ? (
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-dashed border-gray-200 dark:border-[#2a3347] py-2">
                        <EmptyState
                            icon={ShieldCheck}
                            title="No active critic agents"
                            description="Critics spawn per-task (7xxxx code · 8xxxx output · 9xxxx plan) and terminate on completion"
                            size="sm"
                        />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {(stats.critics ?? []).map(c => <CriticCard key={c.agentium_id} critic={c} />)}
                    </div>
                )}
            </div>

            {/* Task inspector */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                <div className="px-5 py-4 border-b border-gray-100 dark:border-[#1e2535]">
                    <p className="text-sm font-semibold text-gray-900 dark:text-white mb-1">Inspect Reviews by Task</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                        Paste a task or subtask ID to see its full critic review history
                    </p>
                </div>
                <div className="px-5 py-4 flex gap-3">
                    <input
                        type="text"
                        placeholder="task-uuid-here…"
                        value={inspectTask}
                        onChange={e => { setInspectTask(e.target.value); setShowInspect(false); }}
                        onKeyDown={e => e.key === 'Enter' && handleInspect()}
                        className="flex-1 text-sm bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#2a3347] rounded-lg px-3 py-2 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 font-mono"
                    />
                    <button
                        onClick={handleInspect}
                        disabled={!inspectTask.trim() || inspectLoading}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition-colors duration-150 flex items-center gap-2"
                    >
                        {inspectLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                        Inspect
                    </button>
                </div>
                {showInspect && !inspectLoading && (
                    <div className="px-5 pb-5">
                        <div className="rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden">
                            <div className="px-4 py-3 bg-gray-50 dark:bg-[#0f1117] border-b border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                                    Reviews for <span className="font-mono text-gray-400 dark:text-gray-500">{inspectTask.slice(0, 8)}…</span>
                                </span>
                                <button
                                    onClick={() => setShowInspect(false)}
                                    className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                                >
                                    Close
                                </button>
                            </div>
                            <CriticReviewPanel reviews={inspectReviews} loading={false} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = 'tasks' | 'critics' | 'checkpoints' | 'preferences' | 'delegation' | 'workflows' | 'browser';

export const TasksPage: React.FC = () => {
    const [tasks, setTasks]               = useState<Task[]>([]);
    const [activeCount, setActiveCount]   = useState<number | null>(null);
    const [isLoading, setIsLoading]       = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [filterStatus, setFilterStatus] = useState<string>('');
    const [myTasksOnly, setMyTasksOnly]   = useState<boolean>(false);
    const [hideSystem, setHideSystem]     = useState<boolean>(true);
    const [activeTab, setActiveTab]       = useState<Tab>('tasks');
    const [checkpointSubTab, setCheckpointSubTab] = useState<'timeline' | 'diff'>('timeline');
    const [showImportModal, setShowImportModal] = useState(false);
    // FIX 11: track critic count from CriticsTab for the tab badge
    const [criticCount, setCriticCount] = useState<number | null>(null);
    
    // Phase 14.1
    const [selectedBrowserTask, setSelectedBrowserTask] = useState<string | null>(null);
    const [showLiveViewerTask, setShowLiveViewerTask] = useState<string | null>(null);

    useEffect(() => { loadTasks(); }, [filterStatus, myTasksOnly, hideSystem]);

    const loadTasks = useCallback(async (silent = false) => {
        try {
            if (!silent) setIsLoading(true);
            else setIsRefreshing(true);
            const [data, active] = await Promise.all([
                tasksService.getTasks({
                    status: filterStatus || undefined,
                    my_tasks: myTasksOnly,
                    hide_system: hideSystem,
                }),
                tasksService.getActiveTasks(),
            ]);
            setTasks(data);
            setActiveCount(active.length);
        } catch (err) {
            console.error(err);
            showToast.error('Failed to load tasks');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    }, [filterStatus, myTasksOnly, hideSystem]);

    const handleCreateTask = async (data: any) => {
        const requestData: CreateTaskRequest = {
            title: data.title,
            description: data.description,
            priority: data.priority,
            task_type: data.task_type,
        };
        await tasksService.createTask(requestData);
        await loadTasks();
        showToast.success('Task created successfully');
    };

    const stats = {
        total:     tasks.length,
        pending:   tasks.filter(t => t.status === 'pending').length,
        active:    activeCount ?? tasks.filter(t => ['in_progress', 'deliberating', 'retrying'].includes(t.status)).length,
        completed: tasks.filter(t => t.status === 'completed').length,
    };

    const statCards = [
        { label: 'Total Tasks',  value: stats.total,     icon: ListTodo,      bg: 'bg-blue-100 dark:bg-blue-500/10',     text: 'text-blue-600 dark:text-blue-400'    },
        { label: 'Pending',      value: stats.pending,   icon: Clock,         bg: 'bg-yellow-100 dark:bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400' },
        { label: 'In Progress',  value: stats.active,    icon: AlertTriangle, bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400' },
        { label: 'Completed',    value: stats.completed, icon: CheckCircle,   bg: 'bg-green-100 dark:bg-green-500/10',   text: 'text-green-600 dark:text-green-400'   },
    ];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">

            {/* ── Page Header ──────────────────────────────────────────────── */}
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">Tasks</h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">Monitor and manage agent operations.</p>
                </div>
                <div className="flex items-center gap-3">
                    {(activeTab === 'tasks' || activeTab === 'preferences') && (
                        <>
                            <button
                                onClick={() => loadTasks(true)}
                                disabled={isRefreshing}
                                className="p-2 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)] disabled:opacity-50"
                                title="Refresh"
                            >
                                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                            </button>
                            {activeTab === 'tasks' && (
                                <button
                                    onClick={() => setShowCreateModal(true)}
                                    className="bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors duration-150 shadow-sm text-sm font-medium"
                                >
                                    <Plus className="w-4 h-4" />
                                    New Task
                                </button>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* ── Stats Grid ───────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-6">
                {statCards.map(stat => (
                    <div
                        key={stat.label}
                        className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-11 h-11 rounded-lg ${stat.bg} flex items-center justify-center`}>
                                <stat.icon className={`w-5 h-5 ${stat.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {isLoading ? (
                                    <span className="inline-block w-7 h-6 rounded bg-gray-200 dark:bg-[#1e2535] animate-pulse" />
                                ) : stat.value}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{stat.label}</p>
                    </div>
                ))}
            </div>

            {/* ── Tab Switcher + Panel ─────────────────────────────────────── */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

                {/* Tab bar */}
                <div className="px-6 pt-4 border-b border-gray-100 dark:border-[#1e2535] flex items-center gap-1 flex-wrap">
                    {([
                        { id: 'tasks',       label: 'Tasks',       icon: ListTodo    },
                        { id: 'critics',     label: 'Critics',     icon: ShieldCheck },
                        { id: 'checkpoints', label: 'Checkpoints', icon: Milestone   },
                        { id: 'delegation',  label: 'Delegation',  icon: Brain       },
                        { id: 'preferences', label: 'Preferences', icon: Settings    },
                        { id: 'workflows',   label: 'Workflows',   icon: Network     },
                        { id: 'browser',     label: 'Browser',     icon: Monitor     },
                    ] as { id: Tab; label: string; icon: React.ElementType }[]).map(tab => {
                        const isActive = activeTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`
                                    flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg
                                    border-b-2 -mb-px transition-all duration-150
                                    ${isActive
                                        ? 'border-blue-500 text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-500/5'
                                        : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                                    }
                                `}
                            >
                                <tab.icon className="w-4 h-4" />
                                {tab.label}
                                {/* FIX 11: Show real critic count from loaded stats instead of hardcoded 3 */}
                                {tab.id === 'critics' && criticCount !== null && (
                                    <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">
                                        {criticCount}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                </div>

                {/* ── Tasks tab ─────────────────────────────────────────── */}
                {activeTab === 'tasks' && (
                    <>
                        {/* Filter bar */}
                        <div className="px-6 py-4 border-b border-gray-100 dark:border-[#1e2535] flex flex-wrap items-center gap-3">
                            <div className="flex items-center gap-2 text-gray-400 dark:text-gray-500">
                                <Filter className="w-4 h-4" />
                                <span className="text-sm font-medium">Filter:</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {STATUS_FILTERS.map(({ value, label, color }) => {
                                    const isActive = filterStatus === value;
                                    return (
                                        // FIX 12: aria-pressed announces the active filter to screen readers
                                        <button
                                            key={value}
                                            onClick={() => setFilterStatus(value)}
                                            aria-pressed={isActive}
                                            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${
                                                isActive ? FILTER_ACTIVE[color] : FILTER_COLORS[color]
                                            }`}
                                        >
                                            {label}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* ── View toggles ─────────────────────────── */}
                            <div className="flex items-center gap-2">
                                <div className="w-px h-4 bg-gray-200 dark:bg-[#2a3347] flex-shrink-0" />
                                {/* FIX 12: aria-pressed for toggle buttons */}
                                <button
                                    onClick={() => setMyTasksOnly(v => !v)}
                                    aria-pressed={myTasksOnly}
                                    title={myTasksOnly ? 'Showing your tasks — click to show all' : 'Show only your tasks'}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${
                                        myTasksOnly
                                            ? 'bg-blue-600 text-white border-blue-600 dark:bg-blue-500 dark:border-blue-500'
                                            : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-[#2a3347] hover:border-gray-300 dark:hover:border-[#3a4560]'
                                    }`}
                                >
                                    My Tasks
                                </button>
                                <button
                                    onClick={() => setHideSystem(v => !v)}
                                    aria-pressed={hideSystem}
                                    title={hideSystem ? 'System tasks hidden — click to show' : 'System tasks visible — click to hide'}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${
                                        hideSystem
                                            ? 'bg-gray-500 text-white border-gray-500 dark:bg-[#2a3347] dark:border-[#2a3347]'
                                            : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-[#2a3347] hover:border-gray-300 dark:hover:border-[#3a4560]'
                                    }`}
                                >
                                    {hideSystem ? 'System hidden' : 'Show system'}
                                </button>
                            </div>
                            {!isLoading && (
                                <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
                                    {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
                                </span>
                            )}
                        </div>

                        {/* Hierarchical task list */}
                        <div className="p-6">
                            {isLoading ? (
                                <div className="space-y-4">
                                    {[...Array(3)].map((_, i) => (
                                        <div key={i} className="h-40 rounded-xl bg-gray-100 dark:bg-[#1e2535] animate-pulse" />
                                    ))}
                                </div>
                            ) : tasks.length === 0 ? (
                                <div className="py-10">
                                    <EmptyState
                                        illustration="tasks"
                                        icon={ListTodo}
                                        title={filterStatus ? `No ${filterStatus} tasks` : 'No tasks yet'}
                                        description={filterStatus ? 'Try a different filter or create a new task' : 'Create your first task to get started'}
                                        action={!filterStatus ? { label: 'New Task', onClick: () => setShowCreateModal(true) } : undefined}
                                    />
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {tasks.map(task => (
                                        <MainTaskCard
                                            key={task.id}
                                            task={task}
                                            onUpdated={updated =>
                                                setTasks(prev => prev.map(t => t.id === updated.id ? updated : t))
                                            }
                                            onViewLive={(t) => setShowLiveViewerTask(t.id)}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}

                {/* ── Critics tab ───────────────────────────────────────── */}
                {activeTab === 'critics' && (
                    // FIX 14: TabErrorBoundary prevents a crash in CriticsTab from blanking the page
                    <div className="p-6">
                        <TabErrorBoundary tabName="Critics">
                            {/* FIX 11: pass the callback so the badge updates once stats are loaded */}
                            <CriticsTab onStatsLoaded={setCriticCount} />
                        </TabErrorBoundary>
                    </div>
                )}

                {/* ── Checkpoints tab ────────────────────────────────────── */}
                {activeTab === 'checkpoints' && (
                    <div className="p-6">
                        {/* Sub-tab bar */}
                        <div className="flex items-center gap-1 mb-6 bg-gray-100 dark:bg-[#0f1117] rounded-lg p-1 w-fit">
                            <button
                                onClick={() => setCheckpointSubTab('timeline')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                                    checkpointSubTab === 'timeline'
                                        ? 'bg-white dark:bg-[#161b27] text-gray-900 dark:text-white shadow-sm'
                                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                }`}
                            >
                                <Milestone className="w-3.5 h-3.5" />
                                Timeline
                            </button>
                            <button
                                onClick={() => setCheckpointSubTab('diff')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                                    checkpointSubTab === 'diff'
                                        ? 'bg-white dark:bg-[#161b27] text-gray-900 dark:text-white shadow-sm'
                                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                }`}
                            >
                                <GitCompareArrows className="w-3.5 h-3.5" />
                                Branch Diff
                            </button>
                        </div>
                        <div className="flex items-center justify-end mb-6">
                            <button
                                onClick={() => setShowImportModal(true)}
                                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium
                                    bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300
                                    border border-emerald-200 dark:border-emerald-500/25
                                    hover:bg-emerald-100 dark:hover:bg-emerald-500/25
                                    transition-colors duration-150"
                            >
                                <Upload className="w-3.5 h-3.5" />
                                Import Checkpoint
                            </button>
                        </div>
                        {/* FIX 14: error boundary for checkpoint sub-tabs */}
                        <TabErrorBoundary tabName="Checkpoints">
                            {checkpointSubTab === 'timeline' && <CheckpointTimeline />}
                            {checkpointSubTab === 'diff'     && <BranchDiffView />}
                        </TabErrorBoundary>
                    </div>
                )}

                {/* ── Delegation tab (Phase 13.1) ───────────────────────── */}
                {activeTab === 'delegation' && (
                    <div className="p-6 space-y-4">
                        <div className="flex items-center gap-2 mb-4">
                            <Brain className="w-5 h-5 text-violet-500 dark:text-violet-400" />
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Auto-Delegation Engine</h3>
                        </div>
                        {/* FIX 14: error boundary */}
                        <TabErrorBoundary tabName="Delegation">
                            {tasks.length === 0 ? (
                                <p className="text-sm text-gray-500 dark:text-gray-400 italic">No tasks to display.</p>
                            ) : (
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {tasks.map(t => (
                                        <AutoDelegationPanel
                                            key={t.id}
                                            task={t}
                                            onTaskUpdated={(updated) => {
                                                setTasks(prev => prev.map(p => p.id === updated.id ? updated : p));
                                            }}
                                        />
                                    ))}
                                </div>
                            )}
                        </TabErrorBoundary>
                    </div>
                )}

                {/* ── Preferences tab ───────────────────────────────────── */}
                {activeTab === 'preferences' && (
                    <div className="p-6">
                        {/* FIX 14: error boundary */}
                        <TabErrorBoundary tabName="Preferences">
                            <PreferencesTab />
                        </TabErrorBoundary>
                    </div>
                )}

                {/* ── Workflows tab ─────────────────────────────────────── */}
                {activeTab === 'workflows' && (
                    <div className="p-6">
                        {/* FIX 14: error boundary */}
                        <TabErrorBoundary tabName="Workflows">
                            <WorkflowAutomationPanel />
                        </TabErrorBoundary>
                    </div>
                )}

                {/* ── Browser tab ───────────────────────────────────────── */}
                {activeTab === 'browser' && (
                    <div className="p-6">
                        <TabErrorBoundary tabName="Browser">
                            {selectedBrowserTask ? (
                                <div className="space-y-4">
                                    <button 
                                        onClick={() => setSelectedBrowserTask(null)}
                                        className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                                    >
                                        &larr; Back to Sessions
                                    </button>
                                    <BrowserTaskViewer taskId={selectedBrowserTask} mode="tab" />
                                </div>
                            ) : (
                                <BrowserSessionsList tasks={tasks} onSelectTask={setSelectedBrowserTask} />
                            )}
                        </TabErrorBoundary>
                    </div>
                )}
            </div>

            {showCreateModal && (
                <CreateTaskModal
                    onConfirm={handleCreateTask}
                    onClose={() => setShowCreateModal(false)}
                />
            )}
            {showImportModal && (
                <CheckpointImportModal
                    isOpen={showImportModal}
                    onClose={() => setShowImportModal(false)}
                    onImportSuccess={async () => {
                        // FIX 13: replace window.location.reload() with a targeted data refresh.
                        // Preserves scroll position, expanded cards, and active tab state.
                        setShowImportModal(false);
                        await loadTasks(true);
                        showToast.success('Checkpoint imported — task list refreshed');
                    }}
                />
            )}

            {showLiveViewerTask && (
                <BrowserTaskViewer
                    taskId={showLiveViewerTask}
                    mode="modal"
                    onClose={() => setShowLiveViewerTask(null)}
                />
            )}
        </div>
    );
};