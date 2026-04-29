// ─── EmptyState ──────────────────────────────────────────────────────────────
// Shared empty state component used when a list/table has zero items.
// Provides contextual icon, title, description, optional CTA, and optional
// inline SVG illustration for visual richness.
// ─────────────────────────────────────────────────────────────────────────────

import { Inbox } from 'lucide-react';
import { ILLUSTRATION_MAP } from './EmptyStateIllustrations';

export interface EmptyStateProps {
    /** Lucide icon component to render. Defaults to Inbox. */
    icon?: React.ComponentType<{ className?: string }>;
    /** Primary heading text. */
    title: string;
    /** Secondary description below the title. */
    description?: string;
    /** Optional call-to-action button. */
    action?: {
        label: string;
        onClick: () => void;
    };
    /** Visual size variant. 'sm' = compact inline, 'md' = full section. */
    size?: 'sm' | 'md';
    /** Optional illustration key for a contextual SVG graphic above the icon. */
    illustration?: 'agents' | 'tasks' | 'inbox' | 'knowledge' | 'workflows';
}

export function EmptyState({
    icon: Icon = Inbox,
    title,
    description,
    action,
    size = 'md',
    illustration,
}: EmptyStateProps) {
    const py = size === 'sm' ? 'py-8' : 'py-16';
    const iconSize = size === 'sm' ? 'w-8 h-8' : 'w-12 h-12';
    const iconBoxSize = size === 'sm' ? 'w-14 h-14' : 'w-20 h-20';
    const titleSize = size === 'sm' ? 'text-sm' : 'text-base';

    const IllustrationComponent = illustration ? ILLUSTRATION_MAP[illustration] : null;
    const illustrationSize = size === 'sm' ? 'w-24 h-20' : 'w-32 h-28';

    return (
        <div
            className={`flex flex-col items-center justify-center ${py} text-center animate-in fade-in duration-300`}
        >
            {/* Illustration OR icon box — never both */}
            {IllustrationComponent ? (
                <div className="animate-float mb-4">
                    <IllustrationComponent className={illustrationSize} />
                </div>
            ) : (
                <div
                    className={`${iconBoxSize} rounded-2xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mb-4 transition-colors duration-200`}
                >
                    <Icon className={`${iconSize} text-gray-400 dark:text-gray-500`} />
                </div>
            )}

            <h3 className={`${titleSize} font-medium text-gray-700 dark:text-gray-300 mb-1`}>
                {title}
            </h3>

            {description && (
                <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
                    {description}
                </p>
            )}

            {action && (
                <button
                    onClick={action.onClick}
                    className="mt-4 px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 hover:bg-blue-100 dark:hover:bg-blue-500/20 rounded-lg transition-all duration-200"
                >
                    {action.label}
                </button>
            )}
        </div>
    );
}