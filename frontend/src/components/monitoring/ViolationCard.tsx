import React from 'react';
import { ViolationReport } from '../../types';
import { AlertOctagon, ShieldAlert, AlertTriangle, Info, Clock, User, CheckCircle2, XCircle } from 'lucide-react';

interface ViolationCardProps {
    violation: ViolationReport;
    onResolve?: (id: string) => void;
    onDismiss?: (id: string) => void;
}

export const ViolationCard: React.FC<ViolationCardProps> = ({ 
    violation, 
    onResolve, 
    onDismiss 
}) => {
    const getSeverityConfig = () => {
        switch (violation.severity) {
            case 'critical': 
                return { 
                    color: 'rose', 
                    icon: AlertOctagon, 
                    label: 'Critical',
                    priority: 1
                };
            case 'major': 
                return { 
                    color: 'orange', 
                    icon: ShieldAlert, 
                    label: 'Major',
                    priority: 2
                };
            case 'moderate': 
                return { 
                    color: 'amber', 
                    icon: AlertTriangle, 
                    label: 'Moderate',
                    priority: 3
                };
            default: 
                return { 
                    color: 'blue', 
                    icon: Info, 
                    label: 'Minor',
                    priority: 4
                };
        }
    };

    const config = getSeverityConfig();
    const Icon = config.icon;
    
    // Unified color classes for consistency
    const colorClasses = {
        rose: {
            border: 'border-rose-200 dark:border-rose-500/30',
            borderHover: 'hover:border-rose-300 dark:hover:border-rose-500/50',
            bg: 'bg-rose-50 dark:bg-rose-500/10',
            text: 'text-rose-700 dark:text-rose-300',
            icon: 'text-rose-600 dark:text-rose-400',
            badge: 'bg-rose-100 dark:bg-rose-500/20 text-rose-800 dark:text-rose-200'
        },
        orange: {
            border: 'border-orange-200 dark:border-orange-500/30',
            borderHover: 'hover:border-orange-300 dark:hover:border-orange-500/50',
            bg: 'bg-orange-50 dark:bg-orange-500/10',
            text: 'text-orange-700 dark:text-orange-300',
            icon: 'text-orange-600 dark:text-orange-400',
            badge: 'bg-orange-100 dark:bg-orange-500/20 text-orange-800 dark:text-orange-200'
        },
        amber: {
            border: 'border-amber-200 dark:border-amber-500/30',
            borderHover: 'hover:border-amber-300 dark:hover:border-amber-500/50',
            bg: 'bg-amber-50 dark:bg-amber-500/10',
            text: 'text-amber-700 dark:text-amber-300',
            icon: 'text-amber-600 dark:text-amber-400',
            badge: 'bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-200'
        },
        blue: {
            border: 'border-blue-200 dark:border-blue-500/30',
            borderHover: 'hover:border-blue-300 dark:hover:border-blue-500/50',
            bg: 'bg-blue-50 dark:bg-blue-500/10',
            text: 'text-blue-700 dark:text-blue-300',
            icon: 'text-blue-600 dark:text-blue-400',
            badge: 'bg-blue-100 dark:bg-blue-500/20 text-blue-800 dark:text-blue-200'
        }
    };

    const theme = colorClasses[config.color as keyof typeof colorClasses];

    const formatDate = (dateString: string) => {
        const date = new Date(dateString);
        const now = new Date();
        const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));
        
        if (diffInHours < 1) return 'Just now';
        if (diffInHours < 24) return `${diffInHours}h ago`;
        if (diffInHours < 48) return 'Yesterday';
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    const getStatusConfig = (status: string) => {
        switch (status) {
            case 'resolved': return { icon: CheckCircle2, class: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10' };
            case 'dismissed': return { icon: XCircle, class: 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-500/10' };
            default: return { icon: Clock, class: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10' };
        }
    };

    const statusConfig = getStatusConfig(violation.status);
    const StatusIcon = statusConfig.icon;

    return (
        <div className={`
            group relative overflow-hidden rounded-xl border p-5 
            bg-white dark:bg-[#161b27] 
            ${theme.border} ${theme.borderHover}
            shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.3)]
            hover:shadow-md dark:hover:shadow-[0_4px_16px_rgba(0,0,0,0.4)]
            transition-all duration-200 ease-out
        `}>
            {/* Severity indicator strip */}
            <div className={`absolute left-0 top-0 bottom-0 w-1 ${theme.bg.replace('bg-', 'bg-').replace('/10', '')} dark:opacity-60`} />

            {/* Header */}
            <div className="flex justify-between items-start mb-3 pl-3">
                <div className="flex items-center gap-2.5">
                    <div className={`
                        p-2 rounded-lg ${theme.bg} ${theme.icon}
                        transition-transform duration-200 group-hover:scale-105
                    `}>
                        <Icon className="w-4 h-4" />
                    </div>
                    <div>
                        <span className={`
                            inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider
                            ${theme.badge}
                        `}>
                            {config.label}
                        </span>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatDate(violation.created_at)}
                        </p>
                    </div>
                </div>

                {/* Status badge */}
                <div className={`
                    flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
                    ${statusConfig.class}
                `}>
                    <StatusIcon className="w-3.5 h-3.5" />
                    <span className="capitalize">{violation.status}</span>
                </div>
            </div>

            {/* Content */}
            <div className="pl-3 space-y-2">
                <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100 leading-tight">
                    {violation.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-2">
                    {violation.description}
                </p>
            </div>

            {/* Footer metadata */}
            <div className="pl-3 mt-4 pt-4 border-t border-gray-100 dark:border-gray-700/50 flex items-center justify-between">
                <div className="flex items-center gap-4 text-xs">
                    <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                        <User className="w-3.5 h-3.5" />
                        <span className="font-mono text-gray-700 dark:text-gray-300">#{violation.violator}</span>
                    </div>
                </div>

                {/* Actions */}
                {violation.status === 'pending' && (onResolve || onDismiss) && (
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                        {onResolve && (
                            <button
                                onClick={() => onResolve(violation.id)}
                                className="p-1.5 rounded-md text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
                                title="Resolve"
                            >
                                <CheckCircle2 className="w-4 h-4" />
                            </button>
                        )}
                        {onDismiss && (
                            <button
                                onClick={() => onDismiss(violation.id)}
                                className="p-1.5 rounded-md text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-500/10 transition-colors"
                                title="Dismiss"
                            >
                                <XCircle className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
