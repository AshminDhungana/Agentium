import React, { useState } from 'react';
import { Agent } from '../../types';
import { X, AlertTriangle, Trash2 } from 'lucide-react';
import { AGENT_REASON_MIN_LENGTH, AGENT_REASON_MAX_LENGTH } from '../../constants/agents';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface TerminateAgentModalProps {
    agent:     Agent;
    agents:    Agent[];
    onConfirm: (reason: string, authorizedById: string) => Promise<void>;
    onClose:   () => void;
}

/**
 * TerminateAgentModal
 *
 * Replaces the previous `window.confirm()` anti-pattern.
 * Enforces the backend LiquidateAgentRequest constraints:
 *   - reason: min_length=20, max_length=500
 *   - liquidated_by_agentium_id: must be a real Head (0xxxx) or Council (1xxxx) agent
 */
export const TerminateAgentModal: React.FC<TerminateAgentModalProps> = ({
    agent, agents, onConfirm, onClose,
}) => {
    const [reason,       setReason]       = useState('');
    const [authorizedBy, setAuthorizedBy] = useState('');
    const [isLoading,    setIsLoading]    = useState(false);
    const [error,        setError]        = useState<string | null>(null);

    // Only Head (0xxxx) and Council (1xxxx) can authorize liquidation
    const authorizers = agents.filter(a =>
        a.status !== 'terminated' &&
        a.status !== 'terminating' &&
        /^[01]/.test(a.agentium_id ?? a.id ?? '') &&
        a.agentium_id !== agent.agentium_id,
    );

    const reasonOk  = reason.length >= AGENT_REASON_MIN_LENGTH && reason.length <= AGENT_REASON_MAX_LENGTH;
    const canSubmit = reasonOk && authorizedBy.length > 0 && !isLoading;

    const handleConfirm = async () => {
        if (!canSubmit) return;
        setIsLoading(true);
        setError(null);
        try {
            await onConfirm(reason, authorizedBy);
            onClose();
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setError(detail || 'Termination failed. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] w-full max-w-md border border-gray-200 dark:border-[#1e2535]">

                {/* ── Header ─────────────────────────────────────────────── */}
                <div className="flex justify-between items-center px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-rose-100 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 flex items-center justify-center">
                            <Trash2 className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                        </div>
                        Terminate Agent
                    </h2>
                    <button
                        aria-label="Close"
                        onClick={onClose}
                        disabled={isLoading}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors duration-150 disabled:opacity-40"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="p-6 space-y-4">

                    {/* ── Target agent info ───────────────────────────────── */}
                    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20">
                        <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-rose-800 dark:text-rose-300">{agent.name}</p>
                            <p className="text-xs text-rose-600/80 dark:text-rose-400/70 font-mono mt-0.5">
                                {agent.agentium_id} · {agent.agent_type?.replace(/_/g, ' ')}
                            </p>
                            <p className="text-xs text-rose-700 dark:text-rose-300 mt-1.5">
                                This will cancel all active tasks, reassign child agents, and permanently
                                revoke all capabilities. This action cannot be undone.
                            </p>
                        </div>
                    </div>

                    {/* ── Authorized by ───────────────────────────────────── */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Authorized by
                        </label>
                        {authorizers.length === 0 ? (
                            <p className="text-sm text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg px-4 py-2.5">
                                No Head or Council agents available to authorize.
                            </p>
                        ) : (
                            <select
                                aria-label="Authorized by"
                                value={authorizedBy}
                                onChange={e => setAuthorizedBy(e.target.value)}
                                className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-rose-500/40 focus:border-rose-500 transition-colors duration-150 appearance-none cursor-pointer"
                            >
                                <option value="">Select authorizing agent…</option>
                                {authorizers.map(a => (
                                    <option key={a.agentium_id} value={a.agentium_id}>
                                        {a.name} ({a.agentium_id})
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>

                    {/* ── Reason ──────────────────────────────────────────── */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Reason for termination
                            <span className="ml-1.5 text-xs text-gray-400 dark:text-gray-500 font-normal">
                                ({reason.length}/{AGENT_REASON_MAX_LENGTH} · min {AGENT_REASON_MIN_LENGTH})
                            </span>
                        </label>
                        <textarea
                            value={reason}
                            onChange={e => setReason(e.target.value)}
                            placeholder="Describe why this agent is being terminated…"
                            rows={3}
                            maxLength={AGENT_REASON_MAX_LENGTH}
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-rose-500/40 focus:border-rose-500 transition-colors duration-150 resize-none"
                        />
                        {reason.length > 0 && !reasonOk && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                                {AGENT_REASON_MIN_LENGTH - reason.length} more character
                                {AGENT_REASON_MIN_LENGTH - reason.length !== 1 ? 's' : ''} required
                            </p>
                        )}
                    </div>

                    {/* ── Error ───────────────────────────────────────────── */}
                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-4 py-3 rounded-xl">
                            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* ── Footer ──────────────────────────────────────────── */}
                    <div className="flex gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={isLoading}
                            className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 disabled:opacity-40"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={handleConfirm}
                            disabled={!canSubmit}
                            className="flex-1 px-4 py-2.5 bg-rose-600 hover:bg-rose-700 dark:hover:bg-rose-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm flex items-center justify-center gap-2"
                        >
                            {isLoading ? (
                                <><LoadingSpinner size="sm" /> Terminating…</>
                            ) : (
                                <><Trash2 className="w-4 h-4" /> Terminate Agent</>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};