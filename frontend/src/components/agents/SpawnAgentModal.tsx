import React, { useState } from 'react';
import { Agent } from '../../types';
import { UserPlus, AlertCircle } from 'lucide-react';
import { AGENT_DESC_MIN_LENGTH, AGENT_DESC_MAX_LENGTH, AGENT_NAME_MIN_LENGTH, AGENT_NAME_MAX_LENGTH } from '../../constants/agents';
import { Modal } from '@/components/ui/Modal';

interface SpawnAgentModalProps {
    parent:    Agent;
    onConfirm: (name: string, childType: 'council_member' | 'lead_agent' | 'task_agent', description: string) => Promise<void>;
    onClose:   () => void;
}

/**
 * @description Modal for spawning a new agent under an existing parent.
 * Validates child type restrictions per parent tier and enforces backend description constraints.
 * @example
 * ```tsx
 * import { SpawnAgentModal } from '@/components/agents/SpawnAgentModal';
 *
 * <SpawnAgentModal parent={parentAgent} onConfirm={handleSpawn} onClose={close} />
 * ```
 * @param {Agent} props.parent - The parent agent that will spawn the new child.
 * @param {(name: string, childType: string, description: string) => Promise<void>} props.onConfirm - Callback to execute spawn with validated inputs.
 * @param {() => void} props.onClose - Callback to close the modal.
 */
export const SpawnAgentModal: React.FC<SpawnAgentModalProps> = ({ parent, onConfirm, onClose }) => {
    const [name,        setName]        = useState('');
    const [description, setDescription] = useState('');
    const [childType,   setChildType]   = useState<string>('');
    const [isLoading,   setIsLoading]   = useState(false);
    const [error,       setError]       = useState<string | null>(null);

    const getAllowedTypes = (): { value: string; label: string }[] => {
        switch (parent.agent_type) {
            case 'head_of_council':
                return [
                    { value: 'council_member', label: 'Council Member (1xxxx)' },
                    { value: 'lead_agent',     label: 'Lead Agent (2xxxx)'     },
                ];
            case 'council_member':
                return [
                    { value: 'lead_agent', label: 'Lead Agent (2xxxx)' },
                ];
            case 'lead_agent':
                return [
                    { value: 'task_agent', label: 'Task Agent (3xxxx)' },
                ];
            default:
                return [];
        }
    };

    const allowedTypes = getAllowedTypes();

    const nameOk  = name.trim().length >= AGENT_NAME_MIN_LENGTH && name.trim().length <= AGENT_NAME_MAX_LENGTH;
    const descOk  = description.trim().length >= AGENT_DESC_MIN_LENGTH && description.trim().length <= AGENT_DESC_MAX_LENGTH;
    const typeOk  = childType.length > 0;
    const canSubmit = nameOk && descOk && typeOk && !isLoading;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!canSubmit) return;

        setIsLoading(true);
        setError(null);
        try {
            await onConfirm(name.trim(), childType as 'council_member' | 'lead_agent' | 'task_agent', description.trim());
            onClose();
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setError(detail || 'Failed to spawn agent. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const parentTypeLabel = parent.agent_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    if (allowedTypes.length === 0) {
        return (
            <Modal open onClose={onClose} title="Spawn New Agent" size="sm">
                <div className="space-y-4">
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                        A <strong>{parentTypeLabel}</strong> cannot spawn subordinates.
                    </p>
                    <button onClick={onClose} className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-sm font-medium rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                        Close
                    </button>
                </div>
            </Modal>
        );
    }

    return (
        <Modal open onClose={onClose} title="Spawn New Agent" size="md">
            <form onSubmit={handleSubmit} className="p-6 space-y-4">

                    {/* ── Parent context ──────────────────────────────────── */}
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/15 flex items-center justify-center flex-shrink-0">
                            <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <p className="text-sm text-blue-800 dark:text-blue-300">
                                Subordinate of{' '}
                                <span className="font-semibold">{parent.name}</span>
                            </p>
                            <p className="text-xs text-blue-600/70 dark:text-blue-400/60 font-mono mt-0.5">
                                {parent.agentium_id} · {parentTypeLabel}
                            </p>
                        </div>
                    </div>

                    {/* ── Agent type ───────────────────────────────────────── */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Agent Type
                        </label>
                        <select
                            aria-label="Agent Type"
                            value={childType}
                            onChange={e => setChildType(e.target.value)}
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150 appearance-none cursor-pointer"
                            required
                        >
                            <option value="">Select a role…</option>
                            {allowedTypes.map(type => (
                                <option key={type.value} value={type.value}>{type.label}</option>
                            ))}
                        </select>
                    </div>

                    {/* ── Agent name ───────────────────────────────────────── */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Agent Name
                            <span className="ml-1.5 text-xs text-gray-600 dark:text-gray-500 font-normal">
                                ({name.length}/{AGENT_NAME_MAX_LENGTH})
                            </span>
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            placeholder="e.g. Research Specialist"
                            minLength={AGENT_NAME_MIN_LENGTH}
                            maxLength={AGENT_NAME_MAX_LENGTH}
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
                            required
                        />
                        {name.length > 0 && name.trim().length < AGENT_NAME_MIN_LENGTH && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                                Minimum {AGENT_NAME_MIN_LENGTH} characters required
                            </p>
                        )}
                    </div>

                    {/* ── Description ──────────────────────────────────────── */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Description
                            <span className="ml-1.5 text-xs text-gray-600 dark:text-gray-500 font-normal">
                                ({description.length}/{AGENT_DESC_MAX_LENGTH} · min {AGENT_DESC_MIN_LENGTH})
                            </span>
                        </label>
                        <textarea
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="Describe this agent's purpose and responsibilities…"
                            rows={2}
                            minLength={AGENT_DESC_MIN_LENGTH}
                            maxLength={AGENT_DESC_MAX_LENGTH}
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150 resize-none"
                            required
                        />
                        {description.length > 0 && description.trim().length < AGENT_DESC_MIN_LENGTH && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                                {AGENT_DESC_MIN_LENGTH - description.trim().length} more character
                                {AGENT_DESC_MIN_LENGTH - description.trim().length !== 1 ? 's' : ''} required
                            </p>
                        )}
                    </div>

                    {/* ── Error ────────────────────────────────────────────── */}
                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-4 py-3 rounded-xl">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* ── Footer ───────────────────────────────────────────── */}
                    <div className="flex gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={isLoading}
                            className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 disabled:opacity-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={!canSubmit}
                            className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            {isLoading ? 'Spawning…' : 'Spawn Agent'}
                        </button>
                    </div>
                </form>
        </Modal>
    );
};