// src/components/federation/AddPeerModal.tsx
// Extracted from FederationPage.
// Owns its own form state internally; calls onSubmit with typed RegisterPeerRequest.
// The parent controls visibility by conditionally mounting this component.

import { useState } from 'react';
import { Plus } from 'lucide-react';
import type { RegisterPeerRequest } from '@/services/federation';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Props ─────────────────────────────────────────────────────────────────────

interface AddPeerModalProps {
    /** Whether the API call is in-flight (disables submit button + shows spinner). */
    isSubmitting: boolean;
    /** Called when the user cancels or closes the modal. */
    onClose: () => void;
    /**
     * Called with the validated form data when the user submits.
     * The parent is responsible for the API call and showing toast feedback.
     */
    onSubmit: (data: RegisterPeerRequest) => Promise<void>;
}

// ── Default form state ────────────────────────────────────────────────────────

const DEFAULT_FORM = {
    name:          '',
    base_url:      '',
    shared_secret: '',
    trust_level:   'limited' as const,
    capabilities:  '',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function AddPeerModal({ isSubmitting, onClose, onSubmit }: AddPeerModalProps) {
    const [form, setForm] = useState(DEFAULT_FORM);

    const set = (field: keyof typeof DEFAULT_FORM) =>
        (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
            setForm(prev => ({ ...prev, [field]: e.target.value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        await onSubmit({
            name:          form.name.trim(),
            base_url:      form.base_url.trim(),
            shared_secret: form.shared_secret,
            trust_level:   form.trust_level as RegisterPeerRequest['trust_level'],
            capabilities:  form.capabilities
                               .split(',')
                               .map(c => c.trim())
                               .filter(Boolean),
        });
        // Only reset on success — parent controls unmounting on success,
        // so this only runs if the parent leaves the modal open after an error.
        setForm(DEFAULT_FORM);
    };

    return (
        <div
            className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-peer-modal-title"
        >
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-lg w-full border border-gray-200 dark:border-[#1e2535]">

                {/* Header */}
                <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 flex items-center justify-center">
                            <Plus className="w-5 h-5 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
                        </div>
                        <div>
                            <h3
                                id="add-peer-modal-title"
                                className="text-base font-semibold text-gray-900 dark:text-white"
                            >
                                Add Peer Instance
                            </h3>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                Register a new Agentium peer
                            </p>
                        </div>
                    </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="p-6 space-y-4">

                    {/* Peer Name */}
                    <div>
                        <label
                            htmlFor="peer-name"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Peer Name
                        </label>
                        <input
                            id="peer-name"
                            type="text"
                            value={form.name}
                            onChange={set('name')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="Engineering Dept"
                            required
                            disabled={isSubmitting}
                        />
                    </div>

                    {/* Base URL */}
                    <div>
                        <label
                            htmlFor="peer-base-url"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Base URL
                        </label>
                        <input
                            id="peer-base-url"
                            type="url"
                            value={form.base_url}
                            onChange={set('base_url')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="https://agentium-dept.company.com"
                            required
                            disabled={isSubmitting}
                        />
                    </div>

                    {/* Shared Secret */}
                    <div>
                        <label
                            htmlFor="peer-secret"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Shared Secret
                        </label>
                        <input
                            id="peer-secret"
                            type="password"
                            value={form.shared_secret}
                            onChange={set('shared_secret')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="Enter shared secret"
                            required
                            disabled={isSubmitting}
                        />
                    </div>

                    {/* Trust Level */}
                    <div>
                        <label
                            htmlFor="peer-trust-level"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Trust Level
                        </label>
                        <select
                            id="peer-trust-level"
                            value={form.trust_level}
                            onChange={set('trust_level')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                            disabled={isSubmitting}
                        >
                            <option value="limited">Limited — standard task delegation</option>
                            <option value="full">Full — unrestricted access</option>
                            <option value="read_only">Read Only — no task delegation</option>
                        </select>
                    </div>

                    {/* Capabilities */}
                    <div>
                        <label
                            htmlFor="peer-capabilities"
                            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
                        >
                            Capabilities{' '}
                            <span className="text-gray-400 dark:text-gray-500 font-normal">(comma-separated, optional)</span>
                        </label>
                        <input
                            id="peer-capabilities"
                            type="text"
                            value={form.capabilities}
                            onChange={set('capabilities')}
                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150"
                            placeholder="task_delegation, knowledge_sharing"
                            disabled={isSubmitting}
                        />
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
                            disabled={isSubmitting}
                            className="flex-1 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 dark:hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center justify-center gap-2"
                        >
                            {isSubmitting ? (
                                <>
                                    <LoadingSpinner size="sm" />
                                    Adding…
                                </>
                            ) : (
                                'Add Peer'
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default AddPeerModal;