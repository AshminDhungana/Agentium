/**
 * VotingPage
 *
 * Main page for constitutional amendment voting and task deliberations.
 *
 * Refactored to use extracted components and hooks:
 * - useVotingData: all data-fetching, WebSocket sync, auto-refresh
 * - CountdownTickProvider: single shared 1-second tick (replaces per-card intervals)
 * - VotingCard, DetailPanel, QuorumBar: extracted presentational components
 * - ConstitutionTab, GovernanceTab: extracted tab components
 * - ProposeAmendmentModal: extracted with inline field validation
 *
 * No behavior was changed — this is a structural refactor only.
 */

import React, { useState } from 'react';
import {
    Loader2,
    CheckCircle,
    XCircle,
    Plus,
    FileText,
    MessageSquare,
    Gavel,
    BarChart2,
    History,
    RefreshCw,
    BookOpen,
    Activity,
} from 'lucide-react';

import { isVotingActive } from '../services/voting';
import { VotingInterface } from '../components/council/VotingInterface';
import { CountdownTickProvider } from '../hooks/useCountdownTick';
import { useVotingData } from '../hooks/useVotingData';

import { VotingCard } from '../components/voting/VotingCard';
import { DetailPanel } from '../components/voting/DetailPanel';
import { ConstitutionTab } from '../components/voting/ConstitutionTab';
import { GovernanceTab } from '../components/voting/GovernanceTab';
import { ProposeAmendmentModal } from '../components/voting/ProposeAmendmentModal';

// ── Tab type ──────────────────────────────────────────────────────────────────

type Tab = 'amendments' | 'deliberations' | 'history' | 'constitution' | 'governance';

// ── Main Page ─────────────────────────────────────────────────────────────────

export const VotingPage: React.FC = () => {
    const [activeTab, setActiveTab] = useState<Tab>('amendments');
    const [showProposalModal, setShowProposalModal] = useState(false);

    const {
        amendments,
        deliberations,
        isLoading,
        isRefreshing,
        selectedItem,
        setSelectedItem,
        loadData,
    } = useVotingData();

    const activeAmendments   = amendments.filter(isVotingActive);
    const closedAmendments   = amendments.filter(a => !isVotingActive(a));
    const activeDeliberations = deliberations.filter(isVotingActive);
    const closedDeliberations = deliberations.filter(d => !isVotingActive(d));

    // ── Loading state ─────────────────────────────────────────────────────────

    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading voting data…</span>
                </div>
            </div>
        );
    }

    const isListTab = activeTab === 'amendments' || activeTab === 'deliberations' || activeTab === 'history';

    // ── Tab navigation config ─────────────────────────────────────────────────

    const tabs: {
        id: Tab;
        label: string;
        Icon: React.ComponentType<{ className?: string }>;
        count?: number;
    }[] = [
        { id: 'amendments',    label: 'Amendments',        Icon: FileText,     count: activeAmendments.length    },
        { id: 'deliberations', label: 'Task Deliberations',Icon: MessageSquare, count: activeDeliberations.length },
        { id: 'history',       label: 'History',           Icon: History,
          count: closedAmendments.length + closedDeliberations.length },
        { id: 'constitution',  label: 'Constitution',      Icon: BookOpen  },
        { id: 'governance',    label: 'Governance',        Icon: Activity  },
    ];

    return (
        // CountdownTickProvider wraps the entire page so all cards share one timer
        <CountdownTickProvider>
            <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-6 transition-colors duration-200">
                <div className="max-w-7xl mx-auto">

                    {/* ── Header ─────────────────────────────────────────────── */}
                    <div className="mb-6 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center shadow-lg">
                                <Gavel className="w-7 h-7 text-white" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                                    Council Voting
                                </h1>
                                <p className="text-gray-500 dark:text-gray-400 text-sm">
                                    Constitutional amendments and task deliberations
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => loadData(true)}
                                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 transition-colors"
                                title="Refresh now"
                            >
                                <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                            </button>
                            <button
                                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition-colors"
                                onClick={() => setShowProposalModal(true)}
                            >
                                <Plus className="w-4 h-4" />
                                Propose Amendment
                            </button>
                        </div>
                    </div>

                    {/* ── Stats Row ───────────────────────────────────────────── */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                        {[
                            {
                                label: 'Active Amendments',
                                value: activeAmendments.length,
                                Icon: FileText,
                                color: 'text-blue-600 dark:text-blue-400',
                                bg: 'bg-blue-50 dark:bg-blue-900/20',
                            },
                            {
                                label: 'Active Deliberations',
                                value: activeDeliberations.length,
                                Icon: MessageSquare,
                                color: 'text-purple-600 dark:text-purple-400',
                                bg: 'bg-purple-50 dark:bg-purple-900/20',
                            },
                            {
                                label: 'Passed',
                                value:
                                    closedAmendments.filter(a => (a as any).final_result === 'passed').length +
                                    closedDeliberations.filter(d => (d as any).final_decision === 'approved').length,
                                Icon: CheckCircle,
                                color: 'text-green-600 dark:text-green-400',
                                bg: 'bg-green-50 dark:bg-green-900/20',
                            },
                            {
                                label: 'Rejected',
                                value:
                                    closedAmendments.filter(a => (a as any).final_result === 'rejected').length +
                                    closedDeliberations.filter(d => (d as any).final_decision === 'rejected').length,
                                Icon: XCircle,
                                color: 'text-red-600 dark:text-red-400',
                                bg: 'bg-red-50 dark:bg-red-900/20',
                            },
                        ].map(({ label, value, Icon, color, bg }) => (
                            <div
                                key={label}
                                className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 flex items-center gap-3"
                            >
                                <div className={`w-10 h-10 rounded-lg ${bg} flex items-center justify-center`}>
                                    <Icon className={`w-5 h-5 ${color}`} />
                                </div>
                                <div>
                                    <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* ── VotingInterface banner (active amendments only) ──────── */}
                    {activeAmendments.length > 0 && activeTab === 'amendments' && (
                        <div className="mb-6">
                            <VotingInterface />
                        </div>
                    )}

                    {/* ── Tab Navigation ─────────────────────────────────────── */}
                    <div className="flex border-b border-gray-200 dark:border-gray-700 mb-6 gap-1 overflow-x-auto">
                        {tabs.map(({ id, label, Icon, count }) => (
                            <button
                                key={id}
                                className={`relative px-5 py-3 font-medium text-sm transition-colors flex items-center gap-2 whitespace-nowrap ${
                                    activeTab === id
                                        ? 'text-blue-600 dark:text-blue-400'
                                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                                }`}
                                onClick={() => {
                                    setActiveTab(id);
                                    setSelectedItem(null);
                                }}
                            >
                                <Icon className="w-4 h-4" />
                                {label}
                                {count !== undefined && count > 0 && (
                                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                                        activeTab === id
                                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                                            : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400'
                                    }`}>
                                        {count}
                                    </span>
                                )}
                                {activeTab === id && (
                                    <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 dark:bg-blue-400 rounded-t" />
                                )}
                            </button>
                        ))}
                    </div>

                    {/* ── Full-width tabs ─────────────────────────────────────── */}
                    {activeTab === 'constitution' && <ConstitutionTab />}
                    {activeTab === 'governance'   && <GovernanceTab />}

                    {/* ── List + Detail layout ────────────────────────────────── */}
                    {isListTab && (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                            {/* Left: item list */}
                            <div className="space-y-3">

                                {/* Amendments tab */}
                                {activeTab === 'amendments' && (
                                    <>
                                        {activeAmendments.length === 0 && (
                                            <div className="text-center py-16 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
                                                <FileText className="w-14 h-14 mx-auto mb-3 text-gray-300 dark:text-gray-700" />
                                                <p className="font-medium text-gray-700 dark:text-gray-300 mb-1">No active amendments</p>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">Propose a constitutional amendment to get started</p>
                                            </div>
                                        )}
                                        {activeAmendments.map(a => (
                                            <VotingCard
                                                key={a.id}
                                                item={a}
                                                isSelected={selectedItem?.id === a.id}
                                                onClick={() => setSelectedItem(prev => prev?.id === a.id ? null : a)}
                                                isAmendment
                                            />
                                        ))}
                                    </>
                                )}

                                {/* Deliberations tab */}
                                {activeTab === 'deliberations' && (
                                    <>
                                        {activeDeliberations.length === 0 && (
                                            <div className="text-center py-16 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
                                                <MessageSquare className="w-14 h-14 mx-auto mb-3 text-gray-300 dark:text-gray-700" />
                                                <p className="font-medium text-gray-700 dark:text-gray-300 mb-1">No active deliberations</p>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">Task deliberations will appear here</p>
                                            </div>
                                        )}
                                        {activeDeliberations.map(d => (
                                            <VotingCard
                                                key={d.id}
                                                item={d}
                                                isSelected={selectedItem?.id === d.id}
                                                onClick={() => setSelectedItem(prev => prev?.id === d.id ? null : d)}
                                                isAmendment={false}
                                            />
                                        ))}
                                    </>
                                )}

                                {/* History tab */}
                                {activeTab === 'history' && (
                                    <>
                                        {closedAmendments.length + closedDeliberations.length === 0 && (
                                            <div className="text-center py-16 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
                                                <History className="w-14 h-14 mx-auto mb-3 text-gray-300 dark:text-gray-700" />
                                                <p className="font-medium text-gray-700 dark:text-gray-300 mb-1">No vote history yet</p>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">Completed votes will appear here</p>
                                            </div>
                                        )}
                                        {[...closedAmendments, ...closedDeliberations]
                                            .sort((a, b) =>
                                                new Date(b.ended_at ?? 0).getTime() -
                                                new Date(a.ended_at ?? 0).getTime()
                                            )
                                            .map(item => (
                                                <VotingCard
                                                    key={item.id}
                                                    item={item}
                                                    isSelected={selectedItem?.id === item.id}
                                                    onClick={() => setSelectedItem(prev => prev?.id === item.id ? null : item)}
                                                    isAmendment={'sponsors' in item}
                                                />
                                            ))
                                        }
                                    </>
                                )}
                            </div>

                            {/* Right: detail panel */}
                            <div>
                                {selectedItem ? (
                                    <DetailPanel
                                        key={selectedItem.id}
                                        item={selectedItem}
                                        onClose={() => setSelectedItem(null)}
                                        onVoteSuccess={() => loadData(true)}
                                    />
                                ) : (
                                    <div className="hidden lg:flex flex-col items-center justify-center py-24 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 border-dashed text-gray-400 dark:text-gray-600">
                                        <BarChart2 className="w-12 h-12 mb-3" />
                                        <p className="text-sm font-medium">Select an item to view details</p>
                                        <p className="text-xs mt-1">Click any card to see the diff, tally, and vote</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Propose Amendment Modal ──────────────────────────────── */}
                {showProposalModal && (
                    <ProposeAmendmentModal
                        onClose={() => setShowProposalModal(false)}
                        onSuccess={() => loadData(true)}
                    />
                )}
            </div>
        </CountdownTickProvider>
    );
};

export default VotingPage;