/**
 * ProposeAmendmentModal
 *
 * Modal for proposing a new constitutional amendment.
 * Extracted from VotingPage and improved with:
 * - Inline field validation (errors appear beneath each field, not just as toasts)
 * - Error cleared when user starts correcting a field
 */

import React, { useState } from 'react';
import { AlertCircle, Shield, X } from 'lucide-react';
import { votingService, AmendmentProposal } from '../../services/voting';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

interface ProposeAmendmentModalProps {
    onClose: () => void;
    onSuccess: () => void;
}

const EMPTY_FORM: AmendmentProposal = {
    title: '',
    diff_markdown: '',
    rationale: '',
    voting_period_hours: 48,
};

export function ProposeAmendmentModal({ onClose, onSuccess }: ProposeAmendmentModalProps) {
    const [form, setForm] = useState<AmendmentProposal>(EMPTY_FORM);
    const [errors, setErrors] = useState<Partial<Record<keyof AmendmentProposal, string>>>({});
    const [isSubmitting, setIsSubmitting] = useState(false);

    // Validate all fields; return true if valid
    const validate = (): boolean => {
        const e: Partial<Record<keyof AmendmentProposal, string>> = {};
        if (!form.title.trim())         e.title         = 'Title is required';
        if (!form.diff_markdown.trim()) e.diff_markdown = 'Proposed changes are required';
        if (!form.rationale.trim())     e.rationale     = 'Rationale is required';
        setErrors(e);
        return Object.keys(e).length === 0;
    };

    const clearFieldError = (field: keyof AmendmentProposal) => {
        if (errors[field]) {
            setErrors(prev => {
                const next = { ...prev };
                delete next[field];
                return next;
            });
        }
    };

    const handleSubmit = async () => {
        if (!validate()) return;

        setIsSubmitting(true);
        try {
            await votingService.proposeAmendment(form);
            showToast.success('Amendment proposed successfully!');
            onSuccess();
            onClose();
        } catch (error: any) {
            showToast.error(
                `Failed to propose amendment: ${error.response?.data?.detail || error.message}`
            );
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-[#161b27] rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl border border-gray-200 dark:border-[#1e2535]">
                <div className="p-6">
                    {/* Header */}
                    <div className="flex justify-between items-center mb-6">
                        <div className="flex items-center gap-2">
                            <Shield className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                                Propose Amendment
                            </h2>
                        </div>
                        <button
                            aria-label="close"
                            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors duration-200"
                            onClick={onClose}
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <div className="space-y-4">
                        {/* Title */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Title <span className="text-red-500">*</span>
                            </label>
                            <input
                                type="text"
                                className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-colors duration-200 ${
                                    errors.title
                                        ? 'border-red-400 focus:ring-red-400/30'
                                        : 'border-gray-300 dark:border-[#1e2535] focus:ring-blue-500/40'
                                }`}
                                placeholder="Brief title for the amendment"
                                value={form.title}
                                onChange={e => {
                                    setForm(f => ({ ...f, title: e.target.value }));
                                    clearFieldError('title');
                                }}
                            />
                            {errors.title && (
                                <p className="text-xs text-red-600 dark:text-red-400 mt-1">{errors.title}</p>
                            )}
                        </div>

                        {/* Proposed Changes */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Proposed Changes (Diff) <span className="text-red-500">*</span>
                            </label>
                            <textarea
                                className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white font-mono text-sm focus:outline-none focus:ring-2 transition-colors duration-200 ${
                                    errors.diff_markdown
                                        ? 'border-red-400 focus:ring-red-400/30'
                                        : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500/40'
                                }`}
                                placeholder={`+ Add new article\n- Remove old article`}
                                rows={8}
                                value={form.diff_markdown}
                                onChange={e => {
                                    setForm(f => ({ ...f, diff_markdown: e.target.value }));
                                    clearFieldError('diff_markdown');
                                }}
                            />
                            {errors.diff_markdown ? (
                                <p className="text-xs text-red-600 dark:text-red-400 mt-1">{errors.diff_markdown}</p>
                            ) : (
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                    Use <code className="bg-gray-100 dark:bg-[#1e2535] px-1 rounded">+</code> to add and{' '}
                                    <code className="bg-gray-100 dark:bg-[#1e2535] px-1 rounded">-</code> to remove content
                                </p>
                            )}
                        </div>

                        {/* Rationale */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Rationale <span className="text-red-500">*</span>
                            </label>
                            <textarea
                                className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:outline-none focus:ring-2 transition-colors duration-200 ${
                                    errors.rationale
                                        ? 'border-red-400 focus:ring-red-400/30'
                                        : 'border-gray-300 dark:border-gray-600 focus:ring-blue-500/40'
                                }`}
                                placeholder="Explain why this amendment should be adopted..."
                                rows={4}
                                value={form.rationale}
                                onChange={e => {
                                    setForm(f => ({ ...f, rationale: e.target.value }));
                                    clearFieldError('rationale');
                                }}
                            />
                            {errors.rationale && (
                                <p className="text-xs text-red-600 dark:text-red-400 mt-1">{errors.rationale}</p>
                            )}
                        </div>

                        {/* Voting Period */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                Voting Period
                            </label>
                            <select
                                aria-label="voting period"
                                className="w-full px-4 py-2 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-colors duration-200"
                                value={form.voting_period_hours}
                                onChange={e => setForm(f => ({ ...f, voting_period_hours: parseInt(e.target.value) }))}
                            >
                                <option value={24}>24 hours</option>
                                <option value={48}>48 hours (default)</option>
                                <option value={72}>72 hours</option>
                                <option value={168}>1 week</option>
                            </select>
                        </div>

                        {/* Info banner */}
                        <div className="flex gap-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/40">
                            <AlertCircle className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                            <p className="text-xs text-blue-700 dark:text-blue-300">
                                Amendments require 2 Council sponsors and a 60% quorum to pass. A debate window opens before voting begins.
                            </p>
                        </div>

                        {/* Actions */}
                        <div className="flex justify-end gap-3 pt-2">
                            <button
                                className="px-4 py-2 border border-gray-300 dark:border-[#1e2535] rounded-lg hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-700 dark:text-gray-300 font-medium text-sm transition-colors duration-200"
                                onClick={onClose}
                                disabled={isSubmitting}
                            >
                                Cancel
                            </button>
                            <button
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
                                onClick={handleSubmit}
                                disabled={isSubmitting}
                            >
                                {isSubmitting && <LoadingSpinner size="sm" />}
                                {isSubmitting ? 'Submitting…' : 'Submit Proposal'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}