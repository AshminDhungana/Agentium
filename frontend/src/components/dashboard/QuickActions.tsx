/**
 * @description Quick-navigation panel rendered in the Dashboard bottom row.
 * Provides shortcuts for Agents, Models, Tasks, and Channels.
 * @example
 * ```tsx
 * import { QuickActions } from '@/components/dashboard/QuickActions';
 *
 * <QuickActions />
 * ```
 */

import { ChevronRight, Cpu } from 'lucide-react';
import { Link } from 'react-router-dom';

interface ActionItem {
    to:          string;
    label:       string;
    description: string;
}

// Original two links preserved; Tasks + Channels added as new shortcuts.
const ACTIONS: ActionItem[] = [
    {
        to:          '/agents',
        label:       'Manage Agents',
        description: 'View and spawn new agents',
    },
    {
        to:          '/models',
        label:       'Configure AI Models',
        description: 'Set up API keys and providers',
    },
    {
        to:          '/tasks',
        label:       'View Tasks',
        description: 'Monitor task execution',
    },
    {
        to:          '/channels',
        label:       'Communication Channels',
        description: 'Manage external integrations',
    },
];

export function QuickActions() {
    return (
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

            {/* Header */}
            <div className="flex items-center gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                    <Cpu className="w-4 h-4 text-purple-600 dark:text-purple-400" aria-hidden="true" />
                </div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                    Quick Actions
                </h2>
            </div>

            {/* Links — identical class pattern to original */}
            <div className="space-y-2">
                {ACTIONS.map(action => (
                    <Link
                        key={action.to}
                        to={action.to}
                        className="group flex items-center justify-between w-full px-4 py-3.5 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-transparent hover:bg-gray-50 dark:hover:bg-[#0f1117] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                    >
                        <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                {action.label}
                            </p>
                            <p className="text-xs text-gray-600 dark:text-gray-500 mt-0.5">
                                {action.description}
                            </p>
                        </div>
                        <ChevronRight className="w-4 h-4 text--600 dark:text-gray-600 group-hover:text-gray-600 dark:group-hover:text--600 transition-colors duration-150 flex-shrink-0" />
                    </Link>
                ))}
            </div>
        </div>
    );
}