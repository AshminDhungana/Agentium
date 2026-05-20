// ─── StatCard ─────────────────────────────────────────────────────────────────
// Reusable stat tile used in the dashboard stats grid.
// Preserves the exact visual style from the original Dashboard.tsx inline cards,
// but adds:  loading skeleton  ·  ARIA labels  ·  optional link wrapper.

import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

type CardColor = 'blue' | 'green' | 'yellow' | 'purple';

export interface StatCardProps {
    title:      string;
    value:      number | string;
    icon:       LucideIcon;
    color:      CardColor;
    /** When supplied the whole card becomes a router <Link>. */
    link?:      string;
    isLoading?: boolean;
}

const COLOR_MAP: Record<CardColor, { bg: string; text: string }> = {
    blue:   { bg: 'bg-blue-100 dark:bg-blue-500/10',    text: 'text-blue-600 dark:text-blue-400'   },
    green:  { bg: 'bg-green-100 dark:bg-green-500/10',  text: 'text-green-600 dark:text-green-400' },
    yellow: { bg: 'bg-yellow-100 dark:bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400' },
    purple: { bg: 'bg-purple-100 dark:bg-purple-500/10', text: 'text-purple-600 dark:text-purple-400' },
};

/** Inner card — shared between the linked and non-linked variants. */
function CardInner({ title, value, icon: Icon, color, isLoading }: StatCardProps) {
    const c = COLOR_MAP[color];
    return (
        <div className="group bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
            <div className="flex items-center justify-between mb-4">
                <div className={`w-11 h-11 rounded-lg ${c.bg} flex items-center justify-center transition-colors duration-200`}>
                    <Icon className={`w-5 h-5 ${c.text}`} aria-hidden="true" />
                </div>
                <span className="text-2xl font-bold text-gray-900 dark:text-white">
                    {isLoading ? (
                        <span className="inline-block w-7 h-6 rounded bg-gray-200 dark:bg-[#1e2535] animate-pulse" />
                    ) : (
                        value
                    )}
                </span>
            </div>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400 group-hover:text-gray-700 dark:group-hover:text-gray-300 transition-colors duration-150">
                {title}
            </p>
        </div>
    );
}

export function StatCard(props: StatCardProps) {
    const ariaLabel = `${props.title}: ${props.isLoading ? 'loading' : props.value}`;

    if (props.link) {
        return (
            <Link to={props.link} aria-label={ariaLabel}>
                <CardInner {...props} />
            </Link>
        );
    }

    return (
        <div role="region" aria-label={ariaLabel}>
            <CardInner {...props} />
        </div>
    );
}