import { useRef, useState } from 'react';
import { useWebSocketStore } from '@/store/websocketStore';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { MarkdownMessage } from '@/components/chat/MarkdownMessage';
import { showToast } from '@/hooks/useToast';

export function GenesisNameModal() {
    const open = useWebSocketStore((s) => s.genesisAwaitingName);
    const prompt = useWebSocketStore((s) => s.genesisNamePrompt);
    const timeout = useWebSocketStore((s) => s.genesisNameTimeout);
    const submitCountryName = useWebSocketStore((s) => s.submitCountryName);
    const dismissGenesisNamePrompt = useWebSocketStore((s) => s.dismissGenesisNamePrompt);

    const [name, setName] = useState('');
    const [submitting, setSubmitting] = useState(false);
    // Once the Sovereign submits, hide the modal immediately and don't let a
    // late `awaiting_name` poll re-show it before genesis leaves the naming step.
    const submittedRef = useRef(false);

    if (!open) {
        // Do NOT reset submittedRef here — a late `awaiting_name` poll response
        // (racing with the user's submission) could toggle open back to true
        // and re-show the modal after the user already submitted.
        return null;
    }
    if (submittedRef.current) return null;

    const handleSubmit = async () => {
        if (submitting || submittedRef.current) return;
        const trimmed = name.trim();
        setSubmitting(true);
        // Await the result so a rejected submission (genesis already moved past
        // the prompt, e.g. the 60s timeout elapsed) is surfaced instead of
        // silently dropping the name and falling back to the default.
        const accepted = await submitCountryName(trimmed);
        setSubmitting(false);
        if (accepted) {
            submittedRef.current = true; // hidden until genesis clears the flag
            return;
        }
        // Also lock on rejection — otherwise a late `awaiting_name` poll
        // racing with the timeout response could re-show the modal.
        submittedRef.current = true;
        if (trimmed) {
            showToast.warning(
                'Naming timed out — your nation was given the default name.',
            );
        }
        dismissGenesisNamePrompt();
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
                    disabled={submitting}
                    className="mt-4 w-full rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                    {submitting ? <LoadingSpinner size="sm" /> : null}
                    {submitting ? 'Establishing…' : name.trim() ? 'Establish Nation' : 'Use Default Name'}
                </button>
            </div>
        </div>
    );
}
