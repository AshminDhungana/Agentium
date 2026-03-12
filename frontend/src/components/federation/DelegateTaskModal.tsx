// src/components/federation/DelegateTaskModal.tsx
// Extracted from FederationPage.
// Owns its own form state internally.
// Validates that the payload is legal JSON before calling onSubmit.
// The parent controls visibility by conditionally mounting this component.

import { useState } from 'react';
import { Send, Loader2, AlertCircle } from 'lucide-react';
import type { PeerInstance, DelegateTaskRequest } from '@/services/federation';

// ── Props ─────────────────────────────────────────────────────────────────────

interface DelegateTaskModalProps {
    /** Active peers to populate the target-peer dropdown. */
    peers: PeerInstance[];
    /** Whether the API call is in-flight (disables submit button + shows spinner). */
    isSubmitting: boolean;
    /** Called when the user cancels or closes the modal. */
    onClose: () => void;
    /**
     * Called with validated, type-safe form data when the user submits.
     * payload is already parsed from the JSON textarea — never a raw string.
     */
    onSubmit: (data: DelegateTaskRequest) => Promise<void>;
}

// ── Default form state ────────────────────────────────────────────────────────

const DEFAULT_FORM = {
    target_peer_id:   '',
    original_task_id: '',
    payload:          '',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function DelegateTaskModal({ peers, isSubmitting, onClose, onSubmit }: DelegateTaskModalProps) {
    const [form, setForm] = useState(DEFAULT_FORM);
    /** Inline JSON parse error shown under the payload textarea. */
    const [payloadError, setPayloadError] = useState<string | null>(null);

    const activePeers = peers.filter(p => p.status === 'active');

    const set = (field: keyof typeof DEFAULT_FORM) =>
        (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
            setForm(prev => ({ ...prev, [field]: e.target.value }));
            // Clear JSON error whenever the user edits the payload
            if (field === 'payload') setPayloadError(null);
        };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setPayloadError(null);

        // ── Client-side JSON validation ───────────────────────────────────────
        let parsedPayload: Record<string, unknown>;
        try {
            parsedPayload = JSON.parse(form.payload || '{}');
            if (typeof parsedPayload !== 'object' || Array.isArray(parsedPayload)) {
                setPayloadError('Payload must be a JSON object, e.g. { "key": "value" }');
                return;
            }
        } catch {
            setPayloadError('Invalid JSON — check for missing quotes or commas.');
            return;
        }

        await onSubmit({
            target_peer_id:   form.target_peer_id,
            original_task_id: form.original_task_id.trim(),
            payload:          parsedPayload,
        });

        // Reset on success (parent unmounts on success, but reset anyway for safety)
        setForm(DEFAULT_FORM);
        setPayloadError(null);
    };

    return (
        <div
            className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delegate-task-modal-title"
        >
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-lg w-full border border-gray-200 dark:border-[#1e2535]">

                {/* Header */}
                <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center">
                            <Send className="w-5 h-5 text-blue-600 dark:text-blue-400" aria-hidden="true" />
                        </div>
                        <div>
                            <h3
                                id="delegate-task-modal-title"
                                className="text-base font-semibold text-gray-900 dark:text-white"
                            >
                                Delegate Task
                            </h3>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                Send a task to a peer instance for execution
                            </p>
                        </div>
                    </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="p-6 space-y-4">

                    {/* Target Peer */}
                    <div>
                        <label
                            htmlFor="delegate-target-peer"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Target Peer
                        </label>
                        {activePeers.length === 0 ? (
                            <div className="flex items-center gap-2 px-4 py-2.5 border border-yellow-200 dark:border-yellow-500/30 rounded-lg bg-yellow-50 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 text-sm">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                                No active peers available to delegate to.
                            </div>
                        ) : (
                            <select
                                id="delegate-target-peer"
                                value={form.target_peer_id}
                                onChange={set('target_peer_id')}
                                className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                required
                                disabled={isSubmitting}
                            >
                                <option value="">Select a peer…</option>
                                {activePeers.map(peer => (
                                    <option key={peer.id} value={peer.id}>
                                        {peer.name}
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>

                    {/* Original Task ID */}
                    <div>
                        <label
                            htmlFor="delegate-task-id"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Original Task ID
                        </label>
                        <input
                            id="delegate-task-id"
                            type="text"
                            value={form.original_task_id}
                            onChange={set('original_task_id')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="local-task-abc123"
                            required
                            disabled={isSubmitting}
                        />
                    </div>

                    {/* Payload (JSON) */}
                    <div>
                        <label
                            htmlFor="delegate-payload"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Payload{' '}
                            <span className="text-gray-400 dark:text-gray-500 font-normal">(JSON object)</span>
                        </label>
                        <textarea
                            id="delegate-payload"
                            value={form.payload}
                            onChange={set('payload')}
                            className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:border-blue-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150 font-mono resize-none ${
                                payloadError
                                    ? 'border-red-300 dark:border-red-500/40 focus:ring-red-500'
                                    : 'border-gray-200 dark:border-[#1e2535] focus:ring-blue-500'
                            }`}
                            placeholder='{"task": "analyze data", "priority": "high"}'
                            rows={4}
                            disabled={isSubmitting}
                            aria-describedby={payloadError ? 'delegate-payload-error' : undefined}
                        />
                        {payloadError && (
                            <p
                                id="delegate-payload-error"
                                role="alert"
                                className="mt-1.5 flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400"
                            >
                                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                                {payloadError}
                            </p>
                        )}
                    </div>

                    {/* Actions */}
                    <div className="flex gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={isSubmitting}
                            className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isSubmitting || activePeers.length === 0}
                            className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center justify-center gap-2"
                        >
                            {isSubmitting ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                                    Delegating…
                                </>
                            ) : (
                                <>
                                    <Send className="w-4 h-4" aria-hidden="true" />
                                    Delegate
                                </>
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default DelegateTaskModal;