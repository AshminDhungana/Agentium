/**
 * ConstitutionTab
 *
 * Displays the current active constitution text.
 * Extracted from VotingPage to keep the parent file lean.
 */

import React, { useState, useEffect } from 'react';
import { AlertCircle, BookOpen } from 'lucide-react';
import { api } from '../../services/api';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

export function ConstitutionTab() {
    const [constitution, setConstitution] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.get<{ content: string } | string>('/api/v1/constitution')
            .then(res => {
                const data = res.data as any;
                setConstitution(
                    typeof data === 'string'
                        ? data
                        : data.content ?? JSON.stringify(data, null, 2)
                );
            })
            .catch(err => {
                setError(err.response?.data?.detail || 'Failed to load constitution');
            })
            .finally(() => setIsLoading(false));
    }, []);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-24 text-gray-400 dark:text-gray-500">
                <LoadingSpinner size="md" label="Loading constitution…" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center py-24 gap-2 text-red-500 dark:text-red-400">
                <AlertCircle className="w-8 h-8" />
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-2">
                    <BookOpen className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                        Current Constitution
                    </h2>
                </div>
                <span className="text-xs text-gray-400 dark:text-gray-500">
                    Read-only · Propose an amendment to modify
                </span>
            </div>
            <div className="p-6 overflow-y-auto max-h-[70vh]">
                <pre className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap font-mono">
                    {constitution}
                </pre>
            </div>
        </div>
    );
}