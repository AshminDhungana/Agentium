import { useState } from 'react';
import { useWebSocketStore } from '@/store/websocketStore';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';

export function GenesisNameModal() {
    const open = useWebSocketStore((s) => s.genesisAwaitingName);
    const prompt = useWebSocketStore((s) => s.genesisNamePrompt);
    const timeout = useWebSocketStore((s) => s.genesisNameTimeout);
    const submitCountryName = useWebSocketStore((s) => s.submitCountryName);

    const [name, setName] = useState('');
    const [submitting, setSubmitting] = useState(false);

    if (!open) return null;

    const handleSubmit = async () => {
        const trimmed = name.trim();
        if (!trimmed || submitting) return;
        setSubmitting(true);
        await submitCountryName(trimmed);
        setSubmitting(false);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white dark:bg-[#161b27] p-6 shadow-2xl">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Establish Your AI Nation
                </h2>
                <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    <MarkdownMessage
                        content={prompt || 'What shall we name this sovereign domain?'}
                        className="text-sm text-gray-600 dark:text-gray-400"
                    />
                </div>
                <input
                    className="mt-4 w-full rounded-xl border border-gray-300 dark:border-gray-700 bg-transparent px-3 py-2 text-sm text-gray-900 dark:text-white outline-none focus:border-violet-500"
                    placeholder="Enter nation name"
                    value={name}
                    maxLength={60}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
                    autoFocus
                />
                <p className="mt-1 text-xs text-gray-500">
                    You have {timeout} seconds before a default name is used.
                </p>
                <button
                    onClick={handleSubmit}
                    disabled={!name.trim() || submitting}
                    className="mt-4 w-full rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {submitting ? <LoadingSpinner size="sm" /> : null}
                    {submitting ? 'Establishing…' : 'Establish Nation'}
                </button>
            </div>
        </div>
    );
}
