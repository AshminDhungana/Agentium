import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { constitutionService } from '@/services/constitution';
import { votingService, AmendmentVoting } from '@/services/voting';
import { Constitution, ConstitutionArticle } from '@/types';
import { toast } from 'react-hot-toast';
import {
    BookOpen, AlertTriangle, Save, RotateCcw,
    Check, X, Clock, Shield, Edit3, FileText,
    ChevronDown, ChevronUp, Sliders, Lock,
    Search, Download, GitPullRequest, Loader2,
    Highlighter, XCircle, History, CheckCircle2,
    RefreshCw, Users,
} from 'lucide-react';

// ─── Module-level constants ────────────────────────────────────────────────────
// Declared outside the component so they are never recreated on re-render.
const RECENTLY_AMENDED_DAYS = 7;
const RECENTLY_AMENDED_MS   = RECENTLY_AMENDED_DAYS * 24 * 60 * 60 * 1000;

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Safely parse raw article data from the API into the canonical
 * { title, content } shape.  Handles three possible backend states:
 *   1. Already a proper Record<string, ConstitutionArticle> object  → use as-is
 *   2. A JSON string (legacy / in-transit format)                    → parse it
 *   3. Anything else                                                  → fall back
 */
function safeParseArticles(
    raw: unknown,
    fallback: Record<string, ConstitutionArticle>,
): Record<string, ConstitutionArticle> {
    if (typeof raw === 'string') {
        try {
            return JSON.parse(raw) as Record<string, ConstitutionArticle>;
        } catch {
            return fallback;
        }
    }
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        return raw as Record<string, ConstitutionArticle>;
    }
    return fallback;
}

// ─── Default / fallback constitution ─────────────────────────────────────────
const DEFAULT_CONSTITUTION: Constitution = {
    id: '',
    version: 'v1.0.0',
    version_number: 1,
    preamble: 'We the Sovereign...',
    articles: {
        article_1: { title: 'Default', content: 'Default content' },
    },
    prohibited_actions: [],
    sovereign_preferences: { transparency: 'high' },
    effective_date: new Date().toISOString(),
    created_by: 'system',
    is_active: true,
};

// ─── Proposal form state shape ────────────────────────────────────────────────
interface ProposalForm {
    title: string;
    diff: string;
    rationale: string;
}
const EMPTY_PROPOSAL: ProposalForm = { title: '', diff: '', rationale: '' };

// ─── Section Wrapper ──────────────────────────────────────────────────────────
function Section({
    icon: Icon,
    title,
    accent = 'blue',
    children,
    collapsible = false,
}: {
    icon: React.ElementType;
    title: string;
    accent?: 'blue' | 'red' | 'purple' | 'amber';
    children: React.ReactNode;
    collapsible?: boolean;
}) {
    const [open, setOpen] = useState(true);

    const accentMap: Record<string, { bar: string; iconText: string; iconBg: string }> = {
        blue:   { bar: 'bg-blue-500',   iconText: 'text-blue-600 dark:text-blue-400',     iconBg: 'bg-blue-100 dark:bg-blue-500/15'     },
        red:    { bar: 'bg-red-500',    iconText: 'text-red-600 dark:text-red-400',       iconBg: 'bg-red-100 dark:bg-red-500/15'       },
        purple: { bar: 'bg-purple-500', iconText: 'text-purple-600 dark:text-purple-400', iconBg: 'bg-purple-100 dark:bg-purple-500/15' },
        amber:  { bar: 'bg-amber-500',  iconText: 'text-amber-600 dark:text-amber-400',   iconBg: 'bg-amber-100 dark:bg-amber-500/15'   },
    };
    const a = accentMap[accent];

    return (
        <div className="relative bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
            {/* left accent stripe */}
            <div className={`absolute left-0 top-0 bottom-0 w-1 ${a.bar}`} />

            <div className="pl-6 pr-6 pt-5 pb-5">
                <button
                    type="button"
                    onClick={() => collapsible && setOpen(o => !o)}
                    aria-expanded={collapsible ? open : undefined}
                    aria-label={collapsible ? `${open ? 'Collapse' : 'Expand'} ${title} section` : undefined}
                    className={`w-full flex items-center justify-between ${collapsible ? 'cursor-pointer' : 'cursor-default'}`}
                >
                    <div className="flex items-center gap-3">
                        <span className={`p-2 rounded-lg ${a.iconBg} ${a.iconText} transition-colors duration-200`}>
                            <Icon className="h-4 w-4" />
                        </span>
                        <h2 className="text-base font-semibold tracking-tight text-gray-900 dark:text-white">
                            {title}
                        </h2>
                    </div>
                    {collapsible && (
                        open
                            ? <ChevronUp className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                            : <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                    )}
                </button>

                {open && (
                    <div className="mt-4">
                        {children}
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Article Card ─────────────────────────────────────────────────────────────
function ArticleCard({
    index,
    articleKey,
    article,
    isEditing,
    onContentChange,
    recentlyAmended = false,
    searchQuery = '',
}: {
    index: number;
    articleKey: string;
    article: ConstitutionArticle | string;
    isEditing: boolean;
    onContentChange: (key: string, content: string) => void;
    recentlyAmended?: boolean;
    searchQuery?: string;
}) {
    // Always derive a clean Title Case title from the key (e.g. "article_3" → "Article 3").
    const displayTitle = articleKey
        .split('_')
        .map((w: string) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');

    // Derive content safely — article may be a string or { title, content }
    const displayContent = typeof article === 'string'
        ? article
        : article?.content ?? '';

    // Highlight search matches within content
    const highlightText = (text: string, query: string) => {
        if (!query.trim()) return <>{text}</>;
        const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escaped})`, 'gi');
        const parts = text.split(regex);
        return (
            <>
                {parts.map((part, i) =>
                    regex.test(part)
                        ? <mark key={i} className="bg-yellow-200 dark:bg-yellow-500/40 text-yellow-900 dark:text-yellow-100 rounded px-0.5">{part}</mark>
                        : part
                )}
            </>
        );
    };

    return (
        <div className={`group relative ${recentlyAmended ? 'rounded-r-xl ring-1 ring-amber-400/40 dark:ring-amber-500/30 bg-amber-50/60 dark:bg-amber-500/5' : ''}`}>
            {recentlyAmended && (
                <div className="absolute -left-px top-0 bottom-0 w-px bg-amber-400 dark:bg-amber-500" />
            )}
            {!recentlyAmended && (
                <div className="absolute -left-px top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/60 via-indigo-400/30 to-transparent" />
            )}
            <div className="pl-5 py-4 rounded-r-xl transition-colors duration-150 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 text-xs font-bold flex items-center justify-center border border-blue-200 dark:border-blue-500/20">
                        {index + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                            <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                                {displayTitle}
                            </p>
                            {recentlyAmended && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/25">
                                    <Highlighter className="w-3 h-3" />
                                    Recently amended
                                </span>
                            )}
                        </div>
                        {isEditing ? (
                            <textarea
                                value={displayContent}
                                onChange={e => onContentChange(articleKey, e.target.value)}
                                className="w-full mt-1 p-3 text-sm rounded-xl border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 dark:focus:ring-blue-500/30 focus:border-blue-500 dark:focus:border-blue-500/50 resize-none transition duration-150"
                                rows={3}
                                placeholder="Article content…"
                            />
                        ) : (
                            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                                {displayContent
                                    ? highlightText(displayContent, searchQuery)
                                    : <span className="italic text-gray-400 dark:text-gray-600">No content defined.</span>
                                }
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function ConstitutionPage() {
    // ── Core data state ────────────────────────────────────────────────────
    const [constitution, setConstitution]             = useState<Constitution>(DEFAULT_CONSTITUTION);
    const [editedConstitution, setEditedConstitution] = useState<Constitution>(DEFAULT_CONSTITUTION);
    const [loading, setLoading]                       = useState(true);
    const [error, setError]                           = useState<string | null>(null);
    const [isEditing, setIsEditing]                   = useState(false);
    const [saving, setSaving]                         = useState(false);

    // ── Search ─────────────────────────────────────────────────────────────
    const [searchQuery, setSearchQuery] = useState('');

    // ── Proposal modal — all fields grouped into one state object ──────────
    const [showProposalModal, setShowProposalModal]       = useState(false);
    const [proposalForm, setProposalForm]                 = useState<ProposalForm>(EMPTY_PROPOSAL);
    const [isSubmittingProposal, setIsSubmittingProposal] = useState(false);

    // ── PDF export ─────────────────────────────────────────────────────────
    const [isExportingPdf, setIsExportingPdf] = useState(false);

    // ── Amendment history ──────────────────────────────────────────────────
    const [amendments, setAmendments]           = useState<AmendmentVoting[]>([]);
    const [amendmentsLoading, setAmendmentsLoading] = useState(false);
    const [showHistory, setShowHistory]         = useState(false);

    // ── Derived: active data (edited vs live) ──────────────────────────────
    // Computed before any callbacks so handlers can capture it through closure.
    const activeConstitution = isEditing ? editedConstitution : constitution;

    // ── Memoised: filtered articles ────────────────────────────────────────
    // useMemo on the *result* (not useCallback on the function) gives a real
    // perf benefit: the expensive filter only runs when articles or the query change.
    const filteredArticles = useMemo(() => {
        const articles = activeConstitution.articles ?? {};
        if (!searchQuery.trim()) return articles;
        const q = searchQuery.toLowerCase();
        return Object.fromEntries(
            Object.entries(articles).filter(([key, article]) => {
                const titleText  = key.replace(/_/g, ' ').toLowerCase();
                const contentText = (typeof article === 'string' ? article : article?.content ?? '').toLowerCase();
                return titleText.includes(q) || contentText.includes(q);
            })
        );
    }, [activeConstitution.articles, searchQuery]);

    // ── Memoised: recently amended keys ───────────────────────────────────
    const recentlyAmendedKeys = useMemo((): Set<string> => {
        const result    = new Set<string>();
        const cutoff    = Date.now() - RECENTLY_AMENDED_MS;
        const effective = activeConstitution.effective_date
            ? new Date(activeConstitution.effective_date).getTime()
            : 0;

        // If the whole constitution was updated recently, mark all articles
        if (effective > cutoff && activeConstitution.articles) {
            Object.keys(activeConstitution.articles).forEach(k => result.add(k));
        }
        // Also honour per-article amended_at if backend provides it
        Object.entries(activeConstitution.articles ?? {}).forEach(([k, v]) => {
            if (typeof v === 'object' && v.amended_at && new Date(v.amended_at).getTime() > cutoff) {
                result.add(k);
            }
        });
        return result;
    }, [activeConstitution.effective_date, activeConstitution.articles]);

    // ── Load constitution ──────────────────────────────────────────────────
    // Defined with useCallback so it can be safely listed as a useEffect dep
    // and used as a "Retry" handler in the error UI.
    const loadConstitution = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await constitutionService.getCurrentConstitution();

            const safeData: Constitution = {
                ...DEFAULT_CONSTITUTION,
                ...data,
                // safeParseArticles handles JSON-string payloads from older backend versions
                articles: safeParseArticles(data?.articles, DEFAULT_CONSTITUTION.articles),
                prohibited_actions: Array.isArray(data?.prohibited_actions)
                    ? data.prohibited_actions
                    : typeof data?.prohibited_actions === 'string'
                        ? [data.prohibited_actions]
                        : DEFAULT_CONSTITUTION.prohibited_actions,
                sovereign_preferences: {
                    ...DEFAULT_CONSTITUTION.sovereign_preferences,
                    ...(data?.sovereign_preferences ?? {}),
                },
            };

            setConstitution(safeData);
            // structuredClone is safer than JSON.parse(JSON.stringify(...)):
            // handles undefined values and avoids issues with Date / Set / Map.
            setEditedConstitution(structuredClone(safeData));
        } catch (err: unknown) {
            const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
            const msg = axiosErr?.response?.data?.detail ?? axiosErr?.message ?? 'Failed to load constitution';
            setError(msg);
            toast.error('Failed to load constitution');
            setConstitution(DEFAULT_CONSTITUTION);
            setEditedConstitution(structuredClone(DEFAULT_CONSTITUTION));
        } finally {
            setLoading(false);
        }
    }, []);

    // ── Load amendment history ─────────────────────────────────────────────
    const loadAmendmentHistory = useCallback(async () => {
        setAmendmentsLoading(true);
        try {
            // Promise.allSettled reports partial failures instead of silently
            // swallowing them the way .catch(() => []) did.
            const [ratifiedResult, passedResult] = await Promise.allSettled([
                votingService.getAmendmentVotings('ratified'),
                votingService.getAmendmentVotings('passed'),
            ]);

            const ratified = ratifiedResult.status === 'fulfilled' ? ratifiedResult.value : [];
            const passed   = passedResult.status  === 'fulfilled' ? passedResult.value  : [];

            if (ratifiedResult.status === 'rejected' || passedResult.status === 'rejected') {
                toast.error('Some amendment history could not be loaded');
            }

            // Merge, deduplicate by id, sort newest first
            const seen   = new Set<string>();
            const unique = [...ratified, ...passed].filter(a => {
                if (seen.has(a.id)) return false;
                seen.add(a.id);
                return true;
            });
            unique.sort((a, b) =>
                new Date(b.ended_at ?? b.created_at ?? 0).getTime() -
                new Date(a.ended_at ?? a.created_at ?? 0).getTime()
            );
            setAmendments(unique);
        } finally {
            setAmendmentsLoading(false);
        }
    }, []);

    // ── Boot load ──────────────────────────────────────────────────────────
    useEffect(() => { loadConstitution(); }, [loadConstitution]);

    // ── Save ───────────────────────────────────────────────────────────────
    const handleSave = async () => {
        // Validate BEFORE setting saving state to avoid a flash of the spinner
        // on a validation-only failure path.
        if (!editedConstitution.preamble?.trim()) {
            toast.error('Preamble cannot be empty');
            return;
        }
        try {
            setSaving(true);
            await constitutionService.updateConstitution({
                preamble:             editedConstitution.preamble,
                articles:             editedConstitution.articles,
                prohibited_actions:   Array.isArray(editedConstitution.prohibited_actions)
                    ? editedConstitution.prohibited_actions
                    : [],
                sovereign_preferences: editedConstitution.sovereign_preferences as Record<string, unknown>,
            });
            toast.success('Constitution updated successfully');
            setIsEditing(false);
            await loadConstitution();
        } catch (err: unknown) {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            toast.error(axiosErr?.response?.data?.detail ?? 'Update failed');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        setEditedConstitution(structuredClone(constitution));
        setIsEditing(false);
    };

    // ── Propose amendment ──────────────────────────────────────────────────
    const handleProposalSubmit = async () => {
        if (!proposalForm.title.trim() || !proposalForm.diff.trim()) {
            toast.error('Title and diff are required');
            return;
        }
        setIsSubmittingProposal(true);
        try {
            // Use votingService instead of a raw dynamic import
            await votingService.proposeAmendment({
                title:                proposalForm.title.trim(),
                diff_markdown:        proposalForm.diff.trim(),
                rationale:            proposalForm.rationale.trim(),
                voting_period_hours:  48,
            });
            toast.success('Amendment proposal submitted for council vote');
            setShowProposalModal(false);
            setProposalForm(EMPTY_PROPOSAL);
        } catch (err: unknown) {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            toast.error(axiosErr?.response?.data?.detail ?? 'Failed to submit proposal');
        } finally {
            setIsSubmittingProposal(false);
        }
    };

    // ── Export PDF ─────────────────────────────────────────────────────────
    const handleExportPdf = async () => {
        setIsExportingPdf(true);
        try {
            // Snapshot the current display data at call time
            const data = isEditing ? editedConstitution : constitution;

            const printContent = `
<!DOCTYPE html>
<html>
<head>
  <title>Constitution - ${data.version}</title>
  <style>
    body { font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 40px; color: #111; }
    h1 { font-size: 28px; border-bottom: 2px solid #333; padding-bottom: 12px; }
    h2 { font-size: 18px; margin-top: 32px; color: #1e3a5f; }
    h3 { font-size: 14px; margin-top: 20px; }
    p  { line-height: 1.7; }
    blockquote { border-left: 3px solid #888; padding-left: 16px; color: #555; font-style: italic; }
    .meta { color: #666; font-size: 13px; margin-bottom: 24px; }
    .prohibited { background: #fff5f5; border-left: 3px solid #e53e3e; padding: 8px 12px; margin: 6px 0; }
    @media print { body { padding: 0; } }
  </style>
</head>
<body>
  <h1>The Constitution</h1>
  <div class="meta">Version: ${data.version} · Effective: ${new Date(data.effective_date).toLocaleDateString()}</div>
  <h2>Preamble</h2>
  <blockquote>${data.preamble}</blockquote>
  <h2>Articles</h2>
  ${data.articles
      ? Object.entries(data.articles).map(([key, art], i) => {
            const title   = key.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            const content = typeof art === 'string' ? art : art?.content ?? '';
            return `<h3>${i + 1}. ${title}</h3><p>${content}</p>`;
        }).join('')
      : ''}
  <h2>Prohibited Actions</h2>
  ${Array.isArray(data.prohibited_actions)
      ? data.prohibited_actions.map((a: string) => `<div class="prohibited">${a}</div>`).join('')
      : ''}
</body>
</html>`;

            const win = window.open('', '_blank');
            if (win) {
                win.document.write(printContent);
                win.document.close();
                win.focus();
                setTimeout(() => { win.print(); }, 500);
            } else {
                toast.error('Popup blocked — please allow popups for PDF export');
            }
        } catch {
            toast.error('PDF export failed');
        } finally {
            setIsExportingPdf(false);
        }
    };

    // ── Early return: loading ──────────────────────────────────────────────
    if (loading) {
        return (
            <div className="flex items-center justify-center h-80">
                <div className="text-center space-y-4">
                    <div className="relative mx-auto w-14 h-14">
                        <div className="absolute inset-0 rounded-full border-4 border-gray-200 dark:border-[#1e2535]" />
                        <div className="absolute inset-0 rounded-full border-4 border-blue-500 border-t-transparent animate-spin" />
                        <Shield className="absolute inset-0 m-auto h-5 w-5 text-blue-500 dark:text-blue-400" />
                    </div>
                    <p className="text-sm font-medium text-gray-500 dark:text-gray-400 tracking-wide uppercase">
                        Loading Constitution…
                    </p>
                </div>
            </div>
        );
    }

    const data = activeConstitution;

    // ── Early return: fatal load error ─────────────────────────────────────
    if (!data || !data.prohibited_actions) {
        return (
            <div className="max-w-lg mx-auto mt-20 p-8 rounded-2xl border border-red-200 dark:border-red-500/20 bg-red-50 dark:bg-red-500/5 text-center shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)]">
                <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-red-100 dark:bg-red-500/15 border border-red-200 dark:border-red-500/20 flex items-center justify-center">
                    <AlertTriangle className="h-6 w-6 text-red-500 dark:text-red-400" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                    Failed to Load Constitution
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                    {error ?? 'An unexpected error occurred.'}
                </p>
                <button
                    onClick={loadConstitution}
                    className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-xl transition-colors duration-150"
                >
                    Try Again
                </button>
            </div>
        );
    }

    // ── Render-time computed values ────────────────────────────────────────
    const articleCount    = data.articles ? Object.keys(data.articles).length : 0;
    const prohibitedCount = Array.isArray(data.prohibited_actions) ? data.prohibited_actions.length : 0;
    const prefCount       = data.sovereign_preferences ? Object.keys(data.sovereign_preferences).length : 0;

    // ── Render ─────────────────────────────────────────────────────────────
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] px-6 py-8 transition-colors duration-200">
            <div className="max-w-4xl mx-auto space-y-6">

                {/* ── Page Header ─────────────────────────────────────────── */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    {/* Title block */}
                    <div className="flex items-center gap-4">
                        <div className="relative flex-shrink-0">
                            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-blue-500/25 dark:shadow-blue-900/40">
                                <Shield className="h-7 w-7 text-white" />
                            </div>
                            {data.is_active && (
                                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-400 rounded-full border-2 border-white dark:border-[#0f1117]" />
                            )}
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
                                The Constitution
                            </h1>
                            <div className="flex flex-wrap items-center gap-2 mt-1">
                                <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/20">
                                    {data.version}
                                </span>
                                <span className="inline-flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                                    <Clock className="h-3 w-3" />
                                    {new Date(data.effective_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                </span>
                                {data.is_active && (
                                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20">
                                        <Check className="h-3 w-3" />
                                        Active
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 flex-shrink-0 flex-wrap">
                        {/* PDF Export */}
                        <button
                            onClick={handleExportPdf}
                            disabled={isExportingPdf}
                            title="Export as PDF"
                            aria-label="Export constitution as PDF"
                            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl hover:bg-gray-50 dark:hover:bg-[#1e2535] disabled:opacity-50 transition-all duration-150"
                        >
                            {isExportingPdf
                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                : <Download className="h-4 w-4" />
                            }
                            Export PDF
                        </button>

                        {/* Amendment History */}
                        {!isEditing && (
                            <button
                                onClick={() => {
                                    setShowHistory(x => !x);
                                    if (!showHistory && amendments.length === 0) loadAmendmentHistory();
                                }}
                                aria-label={showHistory ? 'Hide amendment history' : 'Show amendment history'}
                                className={`inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-xl border transition-all duration-150
                                    ${showHistory
                                        ? 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300'
                                        : 'bg-white dark:bg-[#161b27] border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                                    }`}
                            >
                                <History className="h-4 w-4" />
                                History
                            </button>
                        )}

                        {/* Propose Amendment */}
                        {!isEditing && (
                            <button
                                onClick={() => setShowProposalModal(true)}
                                aria-label="Propose a constitutional amendment"
                                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 rounded-xl hover:bg-violet-100 dark:hover:bg-violet-500/20 transition-all duration-150"
                            >
                                <GitPullRequest className="h-4 w-4" />
                                Propose Amendment
                            </button>
                        )}

                        {isEditing ? (
                            <>
                                <button
                                    onClick={handleReset}
                                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150"
                                >
                                    <RotateCcw className="h-4 w-4" />
                                    Discard
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={saving}
                                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-60 rounded-xl transition-all duration-150 shadow-sm shadow-blue-500/20 dark:shadow-blue-900/30"
                                >
                                    {saving ? (
                                        <div className="h-4 w-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                                    ) : (
                                        <Save className="h-4 w-4" />
                                    )}
                                    {saving ? 'Saving…' : 'Save Changes'}
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 shadow-sm dark:shadow-none"
                            >
                                <Edit3 className="h-4 w-4" />
                                Edit Constitution
                            </button>
                        )}
                    </div>
                </div>

                {/* ── Edit Mode Banner ─────────────────────────────────────── */}
                {isEditing && (
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-sm text-amber-800 dark:text-amber-300 transition-colors duration-200">
                        <Edit3 className="h-4 w-4 flex-shrink-0" />
                        <span>You are currently editing the constitution. Changes are not saved until you click <strong>Save Changes</strong>.</span>
                    </div>
                )}

                {/* ── Search Bar ───────────────────────────────────────────── */}
                {!isEditing && (
                    <div className="relative">
                        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
                        <input
                            type="text"
                            placeholder="Search articles by title or content…"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-10 py-2.5 text-sm rounded-xl border border-gray-200 dark:border-[#1e2535]
                                bg-white dark:bg-[#161b27] text-gray-800 dark:text-gray-100
                                placeholder-gray-400 dark:placeholder-gray-500
                                focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500
                                transition-colors duration-150"
                        />
                        {searchQuery && (
                            <button
                                aria-label="Clear search"
                                onClick={() => setSearchQuery('')}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                            >
                                <XCircle className="h-4 w-4" />
                            </button>
                        )}
                    </div>
                )}

                {/* Search results count */}
                {searchQuery && !isEditing && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2">
                        {Object.keys(filteredArticles).length} article{Object.keys(filteredArticles).length !== 1 ? 's' : ''} matching <strong>"{searchQuery}"</strong>
                        {recentlyAmendedKeys.size > 0 && (
                            <span className="ml-3 inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                                <Highlighter className="w-3 h-3" />
                                {recentlyAmendedKeys.size} recently amended
                            </span>
                        )}
                    </p>
                )}

                {/* ── Inline error banner (shown alongside data, not instead of it) ── */}
                {error && (
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-sm text-red-700 dark:text-red-400">
                        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                        <span className="flex-1">{error}</span>
                        <button
                            onClick={loadConstitution}
                            className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-medium underline underline-offset-2 hover:no-underline"
                        >
                            <RefreshCw className="h-3 w-3" />
                            Retry
                        </button>
                    </div>
                )}

                {/* ── Stats Row ────────────────────────────────────────────── */}
                <div className="grid grid-cols-3 gap-4">
                    {[
                        { label: 'Articles',     value: articleCount,    icon: FileText, color: 'blue'   },
                        { label: 'Prohibitions', value: prohibitedCount, icon: Lock,     color: 'red'    },
                        { label: 'Preferences',  value: prefCount,       icon: Sliders,  color: 'purple' },
                    ].map(({ label, value, icon: StatIcon, color }) => {
                        const colorMap: Record<string, string> = {
                            blue:   'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-100 dark:border-blue-500/20',
                            red:    'bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border-red-100 dark:border-red-500/20',
                            purple: 'bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-100 dark:border-purple-500/20',
                        };
                        return (
                            <div
                                key={label}
                                className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border ${colorMap[color]} transition-colors duration-200`}
                            >
                                <StatIcon className="h-5 w-5 flex-shrink-0" />
                                <div>
                                    <p className="text-xl font-bold leading-none text-gray-900 dark:text-white">{value}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</p>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* ── Amendment History Timeline ────────────────────────── */}
                {showHistory && !isEditing && (
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">
                        <div className="pl-6 pr-6 pt-5 pb-5">
                            <div className="flex items-center gap-3 mb-5">
                                <span className="p-2 rounded-lg bg-slate-100 dark:bg-slate-500/15 text-slate-600 dark:text-slate-400">
                                    <History className="h-4 w-4" />
                                </span>
                                <h2 className="text-base font-semibold tracking-tight text-gray-900 dark:text-white">
                                    Amendment History
                                </h2>
                                {!amendmentsLoading && (
                                    <span className="text-xs text-gray-400 dark:text-gray-500">
                                        {amendments.length} concluded
                                    </span>
                                )}
                                <button
                                    onClick={loadAmendmentHistory}
                                    disabled={amendmentsLoading}
                                    aria-label="Refresh amendment history"
                                    className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
                                        border border-gray-200 dark:border-[#1e2535]
                                        bg-white dark:bg-[#0f1117] text-gray-500 dark:text-gray-400
                                        hover:bg-gray-50 dark:hover:bg-[#1e2535]
                                        disabled:opacity-50 transition-colors"
                                >
                                    <RefreshCw className={`h-3 w-3 ${amendmentsLoading ? 'animate-spin' : ''}`} />
                                    Refresh
                                </button>
                            </div>

                            {amendmentsLoading ? (
                                <div className="flex items-center justify-center py-10 gap-2 text-gray-400 dark:text-gray-500">
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    <span className="text-sm">Loading history…</span>
                                </div>
                            ) : amendments.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-10 text-gray-400 dark:text-gray-500 gap-2">
                                    <History className="w-8 h-8 opacity-40" />
                                    <p className="text-sm">No concluded amendments yet.</p>
                                </div>
                            ) : (
                                <div className="space-y-0">
                                    {amendments.map((amendment, idx) => {
                                        const isPassed = amendment.final_result === 'passed' || amendment.status === 'ratified' || amendment.status === 'passed';
                                        const date     = amendment.ended_at ?? amendment.created_at;
                                        const isLast   = idx === amendments.length - 1;
                                        const totalVotes = amendment.votes_for + amendment.votes_against + amendment.votes_abstain;
                                        return (
                                            <div key={amendment.id} className="relative flex gap-4">
                                                {/* Spine */}
                                                <div className="flex flex-col items-center flex-shrink-0 w-6">
                                                    <div className={`w-3 h-3 rounded-full ring-2 ring-white dark:ring-[#161b27] mt-1 flex-shrink-0
                                                        ${isPassed ? 'bg-emerald-500 dark:bg-emerald-400' : 'bg-red-400 dark:bg-red-500'}`}
                                                    />
                                                    {!isLast && (
                                                        <div className="flex-1 w-px border-l-2 border-dashed border-gray-200 dark:border-[#1e2535] mt-1" />
                                                    )}
                                                </div>

                                                {/* Card */}
                                                <div className="flex-1 pb-5">
                                                    <div className={`rounded-xl border p-4 transition-colors duration-150
                                                        ${isPassed
                                                            ? 'border-emerald-100 dark:border-emerald-500/20 bg-emerald-50/40 dark:bg-emerald-500/5'
                                                            : 'border-red-100 dark:border-red-500/20 bg-red-50/40 dark:bg-red-500/5'
                                                        }`}
                                                    >
                                                        <div className="flex items-start justify-between gap-3 flex-wrap">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2 mb-1 flex-wrap">
                                                                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
                                                                        ${isPassed
                                                                            ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                                                                            : 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300'
                                                                        }`}
                                                                    >
                                                                        {isPassed
                                                                            ? <CheckCircle2 className="w-3 h-3" />
                                                                            : <XCircle className="w-3 h-3" />
                                                                        }
                                                                        {amendment.status.toUpperCase()}
                                                                    </span>
                                                                </div>
                                                                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                                                    {amendment.title ?? amendment.agentium_id}
                                                                </p>
                                                                {amendment.sponsors?.length > 0 && (
                                                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                                                        Sponsored by {amendment.sponsors.join(', ')}
                                                                    </p>
                                                                )}
                                                                {totalVotes > 0 && (
                                                                    <div className="flex items-center gap-3 mt-2 text-xs">
                                                                        <span className="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                                                                            <Users className="w-3 h-3" />
                                                                            ✓ {amendment.votes_for}
                                                                        </span>
                                                                        <span className="text-red-500 dark:text-red-400 font-medium">✗ {amendment.votes_against}</span>
                                                                        <span className="text-gray-400 dark:text-gray-500">— {amendment.votes_abstain}</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div className="flex-shrink-0 text-right">
                                                                <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1 justify-end">
                                                                    <Clock className="w-3 h-3" />
                                                                    {date ? new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                                                                </p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Preamble ─────────────────────────────────────────────── */}
                <Section icon={BookOpen} title="Preamble" accent="blue">
                    {isEditing ? (
                        <textarea
                            value={data.preamble ?? ''}
                            onChange={e => setEditedConstitution({ ...editedConstitution, preamble: e.target.value })}
                            className="w-full h-36 p-4 rounded-xl border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 dark:focus:ring-blue-500/30 focus:border-blue-500 dark:focus:border-blue-500/50 resize-none font-serif leading-relaxed transition duration-150"
                            placeholder="Enter the preamble…"
                        />
                    ) : (
                        <blockquote className="relative pl-5 border-l-2 border-blue-400 dark:border-blue-500/60">
                            <p className="font-serif italic text-gray-700 dark:text-gray-300 leading-relaxed text-sm">
                                {data.preamble}
                            </p>
                        </blockquote>
                    )}
                </Section>

                {/* ── Articles ─────────────────────────────────────────────── */}
                <Section icon={FileText} title="Articles" accent="blue" collapsible>
                    <div className="relative ml-3 space-y-1 border-l border-gray-200 dark:border-[#1e2535]">
                        {Object.entries(isEditing ? (data.articles ?? {}) : filteredArticles).map(([key, article], index) => (
                            <ArticleCard
                                key={key}
                                index={index}
                                articleKey={key}
                                article={article}
                                isEditing={isEditing}
                                recentlyAmended={recentlyAmendedKeys.has(key)}
                                searchQuery={searchQuery}
                                onContentChange={(k, content) => {
                                    const existing = editedConstitution.articles[k];
                                    const newArticles = {
                                        ...editedConstitution.articles,
                                        [k]: {
                                            title:   typeof existing === 'object' ? existing.title : k,
                                            content,
                                        } satisfies ConstitutionArticle,
                                    };
                                    setEditedConstitution({ ...editedConstitution, articles: newArticles });
                                }}
                            />
                        ))}
                        {!isEditing && Object.keys(filteredArticles).length === 0 && searchQuery && (
                            <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500 italic">
                                No articles match "{searchQuery}"
                            </div>
                        )}
                    </div>
                </Section>

                {/* ── Prohibited Actions ───────────────────────────────────── */}
                <Section icon={Lock} title="Prohibited Actions" accent="red" collapsible>
                    {isEditing ? (
                        <div className="space-y-2">
                            <textarea
                                value={Array.isArray(data.prohibited_actions) ? data.prohibited_actions.join('\n') : ''}
                                onChange={e => setEditedConstitution({
                                    ...editedConstitution,
                                    prohibited_actions: e.target.value
                                        .split('\n')
                                        .map((l: string) => l.trim())
                                        .filter((l: string) => l.length > 0),
                                })}
                                className="w-full h-32 p-4 rounded-xl border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-sm font-mono text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-red-500/40 dark:focus:ring-red-500/25 focus:border-red-500 dark:focus:border-red-500/50 resize-none transition duration-150"
                                placeholder="One prohibited action per line…"
                            />
                            <p className="text-xs text-gray-400 dark:text-gray-500">Enter one prohibited action per line.</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {Array.isArray(data.prohibited_actions) && data.prohibited_actions.length > 0 ? (
                                data.prohibited_actions.map((action: string, idx: number) => (
                                    <div
                                        key={idx}
                                        className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-[#1e1215] border border-red-100 dark:border-red-500/20 transition-colors duration-200"
                                    >
                                        <div className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/30 flex items-center justify-center">
                                            <X className="h-3 w-3 text-red-500 dark:text-red-400" />
                                        </div>
                                        <span className="text-sm text-gray-800 dark:text-gray-300 leading-relaxed">{action}</span>
                                    </div>
                                ))
                            ) : (
                                <div className="px-4 py-6 text-center rounded-xl border border-dashed border-gray-200 dark:border-[#1e2535]">
                                    <p className="text-sm text-gray-400 dark:text-gray-500 italic">No prohibited actions defined.</p>
                                </div>
                            )}
                        </div>
                    )}
                </Section>

                {/* ── Sovereign Preferences ────────────────────────────────── */}
                <Section icon={Sliders} title="Sovereign Preferences" accent="purple" collapsible>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {data.sovereign_preferences && Object.entries(data.sovereign_preferences).map(([key, value]) => (
                            <div
                                key={key}
                                className="px-4 py-3 rounded-xl bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] transition-colors duration-200"
                            >
                                <label className="block text-xs font-medium text-gray-500 dark:text-gray-500 tracking-wide capitalize mb-1.5">
                                    {key.replace(/_/g, ' ')}
                                </label>
                                {isEditing ? (
                                    <input
                                        aria-label={`Sovereign preference: ${key.replace(/_/g, ' ')}`}
                                        type="text"
                                        value={String(value ?? '')}
                                        onChange={e => {
                                            const newPrefs = {
                                                ...editedConstitution.sovereign_preferences,
                                                [key]: e.target.value,
                                            };
                                            setEditedConstitution({ ...editedConstitution, sovereign_preferences: newPrefs });
                                        }}
                                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500/40 dark:focus:ring-purple-500/25 focus:border-purple-500 dark:focus:border-purple-500/50 transition duration-150"
                                    />
                                ) : (
                                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                        {String(value ?? 'N/A')}
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                </Section>

                {/* ── Footer ───────────────────────────────────────────────── */}
                <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-4 rounded-xl bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-xs text-gray-500 dark:text-gray-500 transition-colors duration-200">
                    <span>
                        Created by <span className="font-medium text-gray-700 dark:text-gray-300">{data.created_by ?? 'System'}</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Last updated {new Date(data.effective_date).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
                    </span>
                </div>

            </div>

            {/* ── Propose Amendment Modal ───────────────────────────────────── */}
            {showProposalModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] w-full max-w-lg border border-gray-200 dark:border-[#1e2535]">

                        {/* Modal Header */}
                        <div className="flex justify-between items-center px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                            <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2.5">
                                <div className="w-8 h-8 rounded-lg bg-violet-100 dark:bg-violet-500/10 border border-violet-200 dark:border-violet-500/20 flex items-center justify-center">
                                    <GitPullRequest className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                                </div>
                                Propose Constitutional Amendment
                            </h2>
                            <button
                                onClick={() => { setShowProposalModal(false); setProposalForm(EMPTY_PROPOSAL); }}
                                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors"
                                aria-label="Close proposal modal"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        <div className="p-6 space-y-4">
                            {/* Title */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Title <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="text"
                                    value={proposalForm.title}
                                    onChange={e => setProposalForm(f => ({ ...f, title: e.target.value }))}
                                    placeholder="e.g. Amend Article 5 — Add Privacy Rights"
                                    className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500 transition-colors"
                                />
                            </div>

                            {/* Diff Markdown */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Proposed Changes (Markdown diff) <span className="text-red-500">*</span>
                                </label>
                                <textarea
                                    value={proposalForm.diff}
                                    onChange={e => setProposalForm(f => ({ ...f, diff: e.target.value }))}
                                    rows={6}
                                    placeholder={`- Old text to remove\n+ New text to add\n\nUse +/- prefix per line for diff format.`}
                                    className="w-full px-4 py-2.5 text-sm font-mono bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500 resize-none transition-colors"
                                />
                            </div>

                            {/* Rationale */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Rationale
                                </label>
                                <textarea
                                    value={proposalForm.rationale}
                                    onChange={e => setProposalForm(f => ({ ...f, rationale: e.target.value }))}
                                    rows={3}
                                    placeholder="Why is this amendment necessary?"
                                    className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500/40 focus:border-violet-500 resize-none transition-colors"
                                />
                            </div>

                            {/* Info note */}
                            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-100 dark:border-blue-500/20 text-xs text-blue-700 dark:text-blue-300">
                                <Shield className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                                Submitting will create a voting session requiring 60% council quorum and a 48-hour deliberation window.
                            </div>

                            {/* Footer buttons */}
                            <div className="flex gap-3 pt-1">
                                <button
                                    onClick={() => { setShowProposalModal(false); setProposalForm(EMPTY_PROPOSAL); }}
                                    className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleProposalSubmit}
                                    disabled={isSubmittingProposal || !proposalForm.title.trim() || !proposalForm.diff.trim()}
                                    className="flex-1 px-4 py-2.5 bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                >
                                    {isSubmittingProposal
                                        ? <Loader2 className="w-4 h-4 animate-spin" />
                                        : <GitPullRequest className="w-4 h-4" />
                                    }
                                    {isSubmittingProposal ? 'Submitting…' : 'Submit Proposal'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}