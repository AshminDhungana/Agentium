import React, { useEffect, useState } from 'react';
import { constitutionService } from '@/services/constitution';
import { toast } from 'react-hot-toast';
import {
    BookOpen, AlertTriangle, Save, RotateCcw,
    Check, X, Clock, Shield, Edit3, FileText,
    ChevronDown, ChevronUp, Sliders, Lock
} from 'lucide-react';

const DEFAULT_CONSTITUTION = {
    id: '',
    version: 'v1.0.0',
    version_number: 1,
    preamble: 'We the Sovereign...',
    articles: {
        'article_1': { title: 'Default', content: 'Default content' }
    },
    prohibited_actions: [],
    sovereign_preferences: { transparency: 'high' },
    effective_date: new Date().toISOString(),
    created_by: 'system',
    is_active: true
};

// ─── Section Wrapper ────────────────────────────────────────────────────────
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
        blue:   { bar: 'bg-blue-500',   iconText: 'text-blue-600 dark:text-blue-400',   iconBg: 'bg-blue-100 dark:bg-blue-500/15'   },
        red:    { bar: 'bg-red-500',    iconText: 'text-red-600 dark:text-red-400',     iconBg: 'bg-red-100 dark:bg-red-500/15'     },
        purple: { bar: 'bg-purple-500', iconText: 'text-purple-600 dark:text-purple-400', iconBg: 'bg-purple-100 dark:bg-purple-500/15' },
        amber:  { bar: 'bg-amber-500',  iconText: 'text-amber-600 dark:text-amber-400', iconBg: 'bg-amber-100 dark:bg-amber-500/15'  },
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

// ─── Article Card ────────────────────────────────────────────────────────────
function ArticleCard({
    index,
    articleKey,
    article,
    isEditing,
    onContentChange,
}: {
    index: number;
    articleKey: string;
    article: any;
    isEditing: boolean;
    onContentChange: (key: string, content: string) => void;
}) {
    return (
        <div className="group relative">
            <div className="absolute -left-px top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/60 via-indigo-400/30 to-transparent" />
            <div className="pl-5 py-4 rounded-r-xl transition-colors duration-150 hover:bg-gray-50 dark:hover:bg-white/[0.03]">
                <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 text-xs font-bold flex items-center justify-center border border-blue-200 dark:border-blue-500/20">
                        {index + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">
                            {article?.title || 'Untitled'}
                        </p>
                        {isEditing ? (
                            <textarea
                                value={article?.content || ''}
                                onChange={e => onContentChange(articleKey, e.target.value)}
                                className="w-full mt-1 p-3 text-sm rounded-xl border border-gray-300 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/40 dark:focus:ring-blue-500/30 focus:border-blue-500 dark:focus:border-blue-500/50 resize-none transition duration-150"
                                rows={3}
                                placeholder="Article content…"
                            />
                        ) : (
                            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                                {article?.content || <span className="italic text-gray-400 dark:text-gray-600">No content defined.</span>}
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Main Component ──────────────────────────────────────────────────────────
export function ConstitutionPage() {
    const [constitution, setConstitution] = useState<any>(DEFAULT_CONSTITUTION);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isEditing, setIsEditing] = useState(false);
    const [editedConstitution, setEditedConstitution] = useState<any>(DEFAULT_CONSTITUTION);
    const [saving, setSaving] = useState(false);

    useEffect(() => { loadConstitution(); }, []);

    const loadConstitution = async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await constitutionService.getCurrentConstitution();
            const safeData = {
                ...DEFAULT_CONSTITUTION,
                ...data,
                articles: data?.articles || DEFAULT_CONSTITUTION.articles,
                prohibited_actions: Array.isArray(data?.prohibited_actions)
                    ? data.prohibited_actions
                    : (typeof data?.prohibited_actions === 'string'
                        ? [data.prohibited_actions]
                        : DEFAULT_CONSTITUTION.prohibited_actions),
                sovereign_preferences: {
                    ...DEFAULT_CONSTITUTION.sovereign_preferences,
                    ...(data?.sovereign_preferences || {})
                }
            };
            setConstitution(safeData);
            setEditedConstitution(JSON.parse(JSON.stringify(safeData)));
        } catch (err: any) {
            const errorMsg = err.response?.data?.detail || err.message || 'Failed to load constitution';
            setError(errorMsg);
            toast.error('Failed to load constitution');
            setConstitution(DEFAULT_CONSTITUTION);
            setEditedConstitution(JSON.parse(JSON.stringify(DEFAULT_CONSTITUTION)));
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        try {
            setSaving(true);
            if (!editedConstitution.preamble?.trim()) {
                toast.error('Preamble cannot be empty');
                return;
            }
            await constitutionService.updateConstitution({
                preamble: editedConstitution.preamble,
                articles: editedConstitution.articles,
                prohibited_actions: Array.isArray(editedConstitution.prohibited_actions)
                    ? editedConstitution.prohibited_actions
                    : [],
                sovereign_preferences: editedConstitution.sovereign_preferences
            });
            toast.success('Constitution updated successfully');
            setIsEditing(false);
            await loadConstitution();
        } catch (err: any) {
            toast.error(err.response?.data?.detail || 'Update failed');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        setEditedConstitution(JSON.parse(JSON.stringify(constitution)));
        setIsEditing(false);
    };

    // ── Loading ────────────────────────────────────────────────────────────
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

    const data = isEditing ? (editedConstitution || DEFAULT_CONSTITUTION) : (constitution || DEFAULT_CONSTITUTION);

    // ── Error Fallback ─────────────────────────────────────────────────────
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
                    {error || 'An unexpected error occurred.'}
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
                    <div className="flex items-center gap-2 flex-shrink-0">
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

                {/* ── Error Banner ─────────────────────────────────────────── */}
                {error && (
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-sm text-red-700 dark:text-red-400">
                        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                        {error}
                    </div>
                )}

                {/* ── Stats Row ────────────────────────────────────────────── */}
                <div className="grid grid-cols-3 gap-4">
                    {[
                        { label: 'Articles',     value: articleCount,    icon: FileText, color: 'blue'   },
                        { label: 'Prohibitions', value: prohibitedCount, icon: Lock,     color: 'red'    },
                        { label: 'Preferences',  value: prefCount,       icon: Sliders,  color: 'purple' },
                    ].map(({ label, value, icon: Icon, color }) => {
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
                                <Icon className="h-5 w-5 flex-shrink-0" />
                                <div>
                                    <p className="text-xl font-bold leading-none text-gray-900 dark:text-white">{value}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</p>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* ── Preamble ─────────────────────────────────────────────── */}
                <Section icon={BookOpen} title="Preamble" accent="blue">
                    {isEditing ? (
                        <textarea
                            value={data.preamble || ''}
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
                        {data.articles && Object.entries(data.articles).map(([key, article]: [string, any], index) => (
                            <ArticleCard
                                key={key}
                                index={index}
                                articleKey={key}
                                article={article}
                                isEditing={isEditing}
                                onContentChange={(k, content) => {
                                    const newArticles = {
                                        ...editedConstitution.articles,
                                        [k]: { ...article, content }
                                    };
                                    setEditedConstitution({ ...editedConstitution, articles: newArticles });
                                }}
                            />
                        ))}
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
                                        .filter((l: string) => l.length > 0)
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
                                        className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/8 border border-red-100 dark:border-red-500/15 transition-colors duration-200"
                                    >
                                        <div className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-red-100 dark:bg-red-500/20 border border-red-200 dark:border-red-500/25 flex items-center justify-center">
                                            <X className="h-3 w-3 text-red-500 dark:text-red-400" />
                                        </div>
                                        <span className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">{action}</span>
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
                        {data.sovereign_preferences && Object.entries(data.sovereign_preferences).map(([key, value]: [string, any]) => (
                            <div
                                key={key}
                                className="px-4 py-3 rounded-xl bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] transition-colors duration-200"
                            >
                                <label className="block text-xs font-medium text-gray-500 dark:text-gray-500 tracking-wide capitalize mb-1.5">
                                    {key.replace(/_/g, ' ')}
                                </label>
                                {isEditing ? (
                                    <input aria-label="Sovereign Preference"
                                        type="text"
                                        value={String(value ?? '')}
                                        onChange={e => {
                                            const newPrefs = {
                                                ...editedConstitution.sovereign_preferences,
                                                [key]: e.target.value
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
                        Created by <span className="font-medium text-gray-700 dark:text-gray-300">{data.created_by || 'System'}</span>
                    </span>
                    <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Last updated {new Date(data.effective_date).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
                    </span>
                </div>

            </div>
        </div>
    );
}
