import React, { useState } from 'react';
import { Agent } from '../../types';
import { X, UserPlus, AlertCircle } from 'lucide-react';

interface SpawnAgentModalProps {
    parent: Agent;
    onConfirm: (name: string, childType: 'council_member' | 'lead_agent' | 'task_agent') => Promise<void>;
    onClose: () => void;
}

export const SpawnAgentModal: React.FC<SpawnAgentModalProps> = ({ parent, onConfirm, onClose }) => {
    const [name, setName] = useState('');
    const [childType, setChildType] = useState<string>('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const getAllowedTypes = () => {
        switch (parent.agent_type) {
            case 'head_of_council':
                return [
                    { value: 'council_member', label: 'Council Member' },
                    { value: 'lead_agent',      label: 'Lead Agent'      },
                ];
            case 'lead_agent':
                return [{ value: 'task_agent', label: 'Task Agent' }];
            default:
                return [];
        }
    };

    const allowedTypes = getAllowedTypes();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!name || !childType) return;

        setIsLoading(true);
        setError(null);
        try {
            await onConfirm(name, childType as any);
            onClose();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to spawn agent');
        } finally {
            setIsLoading(false);
        }
    };

    const parentTypeLabel = parent.agent_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    return (
        <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] w-full max-w-md border border-gray-200 dark:border-[#1e2535]">

                {/* Header */}
                <div className="flex justify-between items-center px-6 py-5 border-b border-gray-100 dark:border-[#1e2535]">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center">
                            <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        </div>
                        Spawn New Agent
                    </h2>
                    <button aria-label="Close"
                        onClick={onClose}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-colors duration-150"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">

                    {/* Parent context info */}
                    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/15 flex items-center justify-center flex-shrink-0">
                            <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        </div>
                        <p className="text-sm text-blue-800 dark:text-blue-300">
                            Spawning subordinate for{' '}
                            <span className="font-semibold">{parent.name}</span>
                            <span className="text-blue-600/70 dark:text-blue-400/70 ml-1">({parentTypeLabel})</span>
                        </p>
                    </div>

                    {/* Agent name */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Agent Name
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Research Specialist"
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150"
                            required
                        />
                    </div>

                    {/* Agent type */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Agent Type
                        </label>
                        <select aria-label="Agent Type"
                            value={childType}
                            onChange={(e) => setChildType(e.target.value)}
                            className="w-full px-4 py-2.5 text-sm bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-colors duration-150 appearance-none cursor-pointer"
                            required
                        >
                            <option value="">Select a role…</option>
                            {allowedTypes.map(type => (
                                <option key={type.value} value={type.value}>{type.label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-4 py-3 rounded-xl">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* Footer */}
                    <div className="flex gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading || !childType || !name}
                            className="flex-1 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                        >
                            {isLoading ? 'Spawning…' : 'Spawn Agent'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
