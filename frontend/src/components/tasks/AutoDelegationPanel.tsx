import React, { useState } from 'react';
import { Task } from '../../types';
import { tasksService } from '../../services/tasks';
import { Brain, RefreshCw, Users, ArrowRight, Zap, Shield } from 'lucide-react';

interface AutoDelegationPanelProps {
    task: Task;
    onTaskUpdated?: (task: Task) => void;
}

/** Colour ramp for complexity scores 1–10 */
const COMPLEXITY_COLORS: Record<number, string> = {
    1: 'bg-emerald-500',
    2: 'bg-emerald-400',
    3: 'bg-lime-400',
    4: 'bg-yellow-400',
    5: 'bg-amber-400',
    6: 'bg-orange-400',
    7: 'bg-orange-500',
    8: 'bg-red-400',
    9: 'bg-red-500',
    10: 'bg-rose-600',
};

const COMPLEXITY_LABELS: Record<number, string> = {
    1: 'Trivial', 2: 'Simple', 3: 'Easy', 4: 'Moderate',
    5: 'Medium', 6: 'Involved', 7: 'Complex', 8: 'Very Complex',
    9: 'Highly Complex', 10: 'Critical',
};

export const AutoDelegationPanel: React.FC<AutoDelegationPanelProps> = ({ task, onTaskUpdated }) => {
    const [isRedelegating, setIsRedelegating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const delegation = task.delegation;
    const meta = delegation?.delegation_metadata;
    const score = delegation?.complexity_score ?? 0;

    const handleReDelegate = async () => {
        setIsRedelegating(true);
        setError(null);
        try {
            const result = await tasksService.autoDelegate(task.id);
            if (result?.task) {
                onTaskUpdated?.(result.task);
            }
        } catch (e: any) {
            setError(e?.response?.data?.detail || 'Re-delegation failed');
        } finally {
            setIsRedelegating(false);
        }
    };

    return (
        <div className="rounded-xl border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] p-5 space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Brain className="w-5 h-5 text-violet-500 dark:text-violet-400" />
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        Auto-Delegation
                    </h3>
                </div>
                <button
                    onClick={handleReDelegate}
                    disabled={isRedelegating}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                        bg-violet-50 text-violet-700 border border-violet-200
                        dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20
                        hover:bg-violet-100 dark:hover:bg-violet-500/20
                        disabled:opacity-50 disabled:cursor-not-allowed
                        transition-colors duration-150"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${isRedelegating ? 'animate-spin' : ''}`} />
                    {isRedelegating ? 'Delegating…' : 'Re-delegate'}
                </button>
            </div>

            {error && (
                <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 
                    border border-rose-200 dark:border-rose-500/20 rounded-lg px-3 py-2">
                    {error}
                </div>
            )}

            {/* Complexity Score Gauge */}
            <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 dark:text-gray-400 font-medium">Complexity</span>
                    <span className="font-bold text-gray-900 dark:text-gray-100">
                        {score > 0 ? `${score}/10 · ${COMPLEXITY_LABELS[score] || ''}` : 'Not scored'}
                    </span>
                </div>
                <div className="flex gap-1">
                    {Array.from({ length: 10 }, (_, i) => (
                        <div
                            key={i}
                            className={`h-2 flex-1 rounded-full transition-all duration-300 ${
                                i < score
                                    ? COMPLEXITY_COLORS[i + 1] || 'bg-gray-300'
                                    : 'bg-gray-100 dark:bg-gray-800'
                            }`}
                        />
                    ))}
                </div>
            </div>

            {/* Delegation Metadata */}
            {meta && (
                <div className="space-y-3">
                    {/* Target Tier */}
                    {meta.target_tier && (
                        <div className="flex items-center gap-2 text-xs">
                            <Shield className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400" />
                            <span className="text-gray-500 dark:text-gray-400">Target Tier:</span>
                            <span className="font-semibold text-gray-900 dark:text-gray-100">
                                {meta.target_tier === '2' ? 'Lead Agent' : 'Task Agent'}
                            </span>
                        </div>
                    )}

                    {/* Assigned Agent */}
                    {meta.assigned_to && (
                        <div className="flex items-center gap-2 text-xs">
                            <ArrowRight className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
                            <span className="text-gray-500 dark:text-gray-400">Assigned to:</span>
                            <span className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">
                                {meta.assigned_to}
                            </span>
                            {meta.agent_score !== undefined && (
                                <span className="text-gray-400 dark:text-gray-500">
                                    (score: {meta.agent_score})
                                </span>
                            )}
                        </div>
                    )}

                    {/* Candidates List */}
                    {meta.candidates && meta.candidates.length > 0 && (
                        <div className="space-y-1.5">
                            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                                <Users className="w-3.5 h-3.5" />
                                <span className="font-medium">
                                    Candidate Agents ({meta.candidate_count})
                                </span>
                            </div>
                            <div className="grid grid-cols-2 gap-1">
                                {meta.candidates.map((c: any, i: number) => (
                                    <div
                                        key={i}
                                        className={`text-xs px-2 py-1 rounded-md font-mono
                                            ${c.agentium_id === meta.assigned_to
                                                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
                                                : 'bg-gray-50 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                                            }`}
                                    >
                                        {c.agentium_id} <span className="opacity-60">({c.score})</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Sub-tasks & Cost-Aware info */}
                    <div className="flex flex-wrap gap-2 text-xs">
                        {meta.subtasks_created > 0 && (
                            <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/20">
                                {meta.subtasks_created} sub-tasks
                            </span>
                        )}
                        {meta.force_local_model && (
                            <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-300 border border-amber-200 dark:border-amber-500/20 flex items-center gap-1">
                                <Zap className="w-3 h-3" /> Local Model
                            </span>
                        )}
                    </div>

                    {/* Delegation time */}
                    {meta.delegated_at && (
                        <p className="text-[10px] text-gray-400 dark:text-gray-600">
                            Delegated at {new Date(meta.delegated_at).toLocaleString()}
                        </p>
                    )}
                </div>
            )}

            {!meta && !error && (
                <p className="text-xs text-gray-400 dark:text-gray-600 italic">
                    No delegation data yet. Click "Re-delegate" to auto-assign this task.
                </p>
            )}
        </div>
    );
};
