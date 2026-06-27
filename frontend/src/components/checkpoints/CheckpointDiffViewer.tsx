import React, { useState, useEffect, useRef } from 'react';
import { X, AlertCircle, Code2, GitCompare, ChevronsRight } from 'lucide-react';
import { DiffEditor } from '@monaco-editor/react';
import { checkpointsService, CheckpointDiffResult } from '../../services/checkpoints';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { useFocusTrap } from '../../hooks/useFocusTrap';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CheckpointDiffViewerProps {
    /** Base checkpoint ID */
    checkpointId: string;
    /** Checkpoint to compare against */
    compareToId: string;
    /** Human-readable labels for the header */
    leftLabel?: string;
    rightLabel?: string;
    onClose: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CheckpointDiffViewer: React.FC<CheckpointDiffViewerProps> = ({
    checkpointId,
    compareToId,
    leftLabel,
    rightLabel,
    onClose,
}) => {
    const [data, setData] = useState<CheckpointDiffResult | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [editorTheme, setEditorTheme] = useState<'vs' | 'vs-dark'>('vs');

    const containerRef = useRef<HTMLDivElement>(null);
    useFocusTrap(containerRef, true);

    // Detect dark mode once on mount + on system changes
    useEffect(() => {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const update = () => setEditorTheme(mq.matches ? 'vs-dark' : 'vs');
        update();
        mq.addEventListener('change', update);
        return () => mq.removeEventListener('change', update);
    }, []);

    // Fetch diff data
    useEffect(() => {
        let isMounted = true;
        const fetchData = async () => {
            try {
                const result = await checkpointsService.getCheckpointDiff(
                    checkpointId,
                    compareToId
                );
                if (isMounted) setData(result);
            } catch (err: any) {
                if (isMounted) {
                    setError(err?.response?.data?.detail || err?.message || 'Failed to load checkpoint diff');
                }
            } finally {
                if (isMounted) setIsLoading(false);
            }
        };
        fetchData();
        return () => { isMounted = false; };
    }, [checkpointId, compareToId]);

    // Keyboard shortcut: Escape to close
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [onClose]);

    // ─── Render ──────────────────────────────────────────────────────────────

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={onClose}
            ref={containerRef}
        >
            <div
                className="bg-white dark:bg-[#161b27] border border-slate-200 dark:border-[#1e2535] rounded-2xl shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* ── Header ──────────────────────────────────────────── */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-[#1e2535] bg-slate-50/50 dark:bg-[#1e2535]/20 flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <GitCompare className="w-5 h-5 text-violet-600" />
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                                Checkpoint Diff
                            </h2>
                            <div className="flex items-center gap-2 mt-1 text-xs font-mono">
                                <span className="px-1.5 py-0.5 rounded bg-rose-100 dark:bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-500/20">
                                    {leftLabel || data?.left_agentium_id || 'Left'}
                                </span>
                                <ChevronsRight className="w-3 h-3 text-slate-400" />
                                <span className="px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20">
                                    {rightLabel || data?.right_agentium_id || 'Right'}
                                </span>
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close diff viewer"
                        className="p-2 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-xl transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* ── Loading ─────────────────────────────────────── */}
                {isLoading && (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500">
                        <LoadingSpinner size="lg" />
                        <p className="mt-3 text-sm">Computing unified diff…</p>
                    </div>
                )}

                {/* ── Error ───────────────────────────────────────── */}
                {error && !isLoading && (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                        <AlertCircle className="w-10 h-10 text-rose-500 mb-4 opacity-80" />
                        <p className="text-rose-600 dark:text-rose-400 font-medium mb-2">{error}</p>
                        <button
                            onClick={onClose}
                            className="text-sm px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                )}

                {/* ── Monaco Diff Editor ──────────────────────────── */}
                {!isLoading && !error && data && (
                    <div className="flex-1 min-h-0">
                        <DiffEditor
                            height="100%"
                            theme={editorTheme}
                            language="json"
                            original={data.left_json}
                            modified={data.right_json}
                            options={{
                                readOnly: true,
                                minimap: { enabled: false },
                                scrollBeyondLastLine: false,
                                wordWrap: 'on',
                                renderSideBySide: true,
                                diffWordWrap: 'on',
                                fontSize: 13,
                                lineNumbers: 'on',
                                folding: true,
                                foldingHighlight: true,
                                automaticLayout: true,
                            }}
                            loading={
                                <div className="flex items-center justify-center h-full text-slate-500">
                                    <LoadingSpinner size="md" />
                                    <span className="ml-2 text-sm">Loading editor…</span>
                                </div>
                            }
                        />
                    </div>
                )}

                {/* ── Footer ──────────────────────────────────────── */}
                {!isLoading && !error && data && (
                    <div className="flex items-center justify-between px-6 py-2.5 border-t border-slate-200 dark:border-[#1e2535] bg-slate-50/50 dark:bg-[#1e2535]/20 text-xs text-slate-500 dark:text-slate-400">
                        <div className="flex items-center gap-4">
                            <span>Diff mode: <strong className="text-slate-700 dark:text-slate-300">Unified (side-by-side)</strong></span>
                            <span className="text-slate-300 dark:text-slate-600">|</span>
                            <span>Language: JSON</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <Code2 className="w-3 h-3" />
                            <span>Monaco Editor</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

