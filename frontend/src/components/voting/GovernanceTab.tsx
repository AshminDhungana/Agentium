/**
 * GovernanceTab
 *
 * Idle governance status panel with pause/resume controls.
 * Extracted from VotingPage to keep the parent file lean.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    AlertCircle, Activity, PauseCircle, PlayCircle,
} from 'lucide-react';
import { api } from '../../services/api';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface IdleStatus {
    enabled: boolean;
    paused: boolean;
    paused_by?: string;
    paused_at?: string;
    current_activity?: string;
    next_run?: string;
    last_run?: string;
    cycle_count?: number;
}

export function GovernanceTab() {
    const [status, setStatus] = useState<IdleStatus | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isPausing, setIsPausing] = useState(false);
    const [isResuming, setIsResuming] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadStatus = useCallback(async () => {
        try {
            const res = await api.get<IdleStatus>('/api/v1/governance/idle/status');
            setStatus(res.data);
            setError(null);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load governance status');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        loadStatus();
        const id = setInterval(loadStatus, 15_000);
        return () => clearInterval(id);
    }, [loadStatus]);

    const handlePause = async () => {
        setIsPausing(true);
        try {
            await api.post('/api/v1/governance/idle/pause');
            showToast.success('Idle governance paused');
            await loadStatus();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to pause governance');
        } finally {
            setIsPausing(false);
        }
    };

    const handleResume = async () => {
        setIsResuming(true);
        try {
            await api.post('/api/v1/governance/idle/resume');
            showToast.success('Idle governance resumed');
            await loadStatus();
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || 'Failed to resume governance');
        } finally {
            setIsResuming(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-24 text-gray-400 dark:text-gray-500">
                <LoadingSpinner size="md" label="Loading governance status…" />
            </div>
        );
    }

    if (error || !status) {
        return (
            <div className="flex flex-col items-center justify-center py-24 gap-2 text-red-500 dark:text-red-400">
                <AlertCircle className="w-8 h-8" />
                <p className="text-sm">{error ?? 'No data'}</p>
                <button onClick={loadStatus} className="text-xs underline mt-1">Retry</button>
            </div>
        );
    }

    const statusColor = !status.enabled
        ? 'text-gray-500'
        : status.paused
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-green-600 dark:text-green-400';

    const statusLabel = !status.enabled ? 'Disabled' : status.paused ? 'Paused' : 'Running';

    return (
        <div className="space-y-4">
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6">
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                            !status.enabled
                                ? 'bg-gray-100 dark:bg-[#1e2535]'
                                : status.paused
                                ? 'bg-amber-50 dark:bg-amber-900/20'
                                : 'bg-green-50 dark:bg-green-900/20'
                        }`}>
                            <Activity className={`w-5 h-5 ${statusColor}`} />
                        </div>
                        <div>
                            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Idle Governance</h2>
                            <p className={`text-sm font-medium flex items-center gap-1.5 ${statusColor}`}>
                                {!status.paused && status.enabled && (
                                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                                )}
                                {statusLabel}
                            </p>
                        </div>
                    </div>

                    {status.enabled && (
                        status.paused ? (
                            <button
                                onClick={handleResume}
                                disabled={isResuming}
                                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
                            >
                                {isResuming ? <LoadingSpinner size="sm" /> : <PlayCircle className="w-4 h-4" />}
                                {isResuming ? 'Resuming…' : 'Resume'}
                            </button>
                        ) : (
                            <button
                                onClick={handlePause}
                                disabled={isPausing}
                                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium transition-colors disabled:opacity-50"
                            >
                                {isPausing ? <LoadingSpinner size="sm" /> : <PauseCircle className="w-4 h-4" />}
                                {isPausing ? 'Pausing…' : 'Pause'}
                            </button>
                        )
                    )}
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    {status.current_activity && (
                        <div className="col-span-2 sm:col-span-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-100 dark:border-blue-800/40">
                            <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-0.5">Current Activity</p>
                            <p className="text-sm text-blue-800 dark:text-blue-200">{status.current_activity}</p>
                        </div>
                    )}
                    {status.cycle_count !== undefined && (
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3">
                            <p className="text-xs text-gray-500 dark:text-gray-400">Cycles Run</p>
                            <p className="text-xl font-bold text-gray-900 dark:text-white">{status.cycle_count}</p>
                        </div>
                    )}
                    {status.last_run && (
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3">
                            <p className="text-xs text-gray-500 dark:text-gray-400">Last Run</p>
                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {new Date(status.last_run).toLocaleString()}
                            </p>
                        </div>
                    )}
                    {status.next_run && !status.paused && (
                        <div className="bg-gray-50 dark:bg-[#0f1117]/60 rounded-lg p-3">
                            <p className="text-xs text-gray-500 dark:text-gray-400">Next Run</p>
                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {new Date(status.next_run).toLocaleString()}
                            </p>
                        </div>
                    )}
                    {status.paused && status.paused_at && (
                        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
                            <p className="text-xs text-amber-600 dark:text-amber-400">Paused At</p>
                            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                                {new Date(status.paused_at).toLocaleString()}
                            </p>
                        </div>
                    )}
                    {status.paused_by && (
                        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
                            <p className="text-xs text-amber-600 dark:text-amber-400">Paused By</p>
                            <p className="text-sm font-medium font-mono text-amber-800 dark:text-amber-200">
                                {status.paused_by}
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}