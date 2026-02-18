import React from 'react';
import { HeartPulse, Activity } from 'lucide-react';

interface HealthScoreProps {
    score: number;
    size?: 'sm' | 'md' | 'lg';
    showLabel?: boolean;
}

export const HealthScore: React.FC<HealthScoreProps> = ({ 
    score, 
    size = 'md',
    showLabel = true 
}) => {
    // Color system with dark mode support - desaturated for comfort
    const getColorClasses = (s: number) => {
        if (s >= 90) return {
            text: 'text-emerald-600 dark:text-emerald-400',
            stroke: 'stroke-emerald-500 dark:stroke-emerald-400',
            bg: 'bg-emerald-50 dark:bg-emerald-500/10',
            glow: 'shadow-emerald-500/20 dark:shadow-emerald-400/20'
        };
        if (s >= 70) return {
            text: 'text-blue-600 dark:text-blue-400',
            stroke: 'stroke-blue-500 dark:stroke-blue-400',
            bg: 'bg-blue-50 dark:bg-blue-500/10',
            glow: 'shadow-blue-500/20 dark:shadow-blue-400/20'
        };
        if (s >= 50) return {
            text: 'text-amber-600 dark:text-amber-400',
            stroke: 'stroke-amber-500 dark:stroke-amber-400',
            bg: 'bg-amber-50 dark:bg-amber-500/10',
            glow: 'shadow-amber-500/20 dark:shadow-amber-400/20'
        };
        return {
            text: 'text-rose-600 dark:text-rose-400',
            stroke: 'stroke-rose-500 dark:stroke-rose-400',
            bg: 'bg-rose-50 dark:bg-rose-500/10',
            glow: 'shadow-rose-500/20 dark:shadow-rose-400/20'
        };
    };

    const colors = getColorClasses(score);
    const radius = 36;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (score / 100) * circumference;

    const sizeConfig = {
        sm: { 
            container: 'w-16 h-16', 
            stroke: 6, 
            text: 'text-sm',
            icon: 'w-4 h-4'
        },
        md: { 
            container: 'w-24 h-24', 
            stroke: 8, 
            text: 'text-xl',
            icon: 'w-5 h-5'
        },
        lg: { 
            container: 'w-32 h-32', 
            stroke: 10, 
            text: 'text-2xl',
            icon: 'w-6 h-6'
        }
    };

    const config = sizeConfig[size];

    return (
        <div className={`relative flex items-center justify-center ${config.container} group`}>
            {/* Background glow effect for dark mode */}
            <div className={`absolute inset-0 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 ${colors.glow}`} />
            
            <svg className="transform -rotate-90 w-full h-full" viewBox="0 0 100 100">
                {/* Track background */}
                <circle
                    className="stroke-gray-200 dark:stroke-gray-700/50 transition-colors duration-200"
                    strokeWidth={config.stroke}
                    cx="50"
                    cy="50"
                    r={radius}
                    fill="transparent"
                />
                {/* Progress arc */}
                <circle
                    className={`${colors.stroke} transition-all duration-1000 ease-out drop-shadow-sm`}
                    strokeWidth={config.stroke}
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    cx="50"
                    cy="50"
                    r={radius}
                    fill="transparent"
                    style={{
                        filter: 'drop-shadow(0 0 2px currentColor)'
                    }}
                />
            </svg>
            
            {/* Center content */}
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <Activity className={`${config.icon} ${colors.text} mb-0.5 opacity-80 transition-colors duration-200`} />
                <span className={`font-bold text-gray-900 dark:text-gray-100 ${config.text} transition-colors duration-200`}>
                    {Math.round(score)}%
                </span>
            </div>

            {/* Optional label */}
            {showLabel && size === 'lg' && (
                <div className={`absolute -bottom-8 px-3 py-1 rounded-full text-xs font-medium ${colors.bg} ${colors.text} border border-transparent dark:border-white/5 transition-colors duration-200`}>
                    Health Score
                </div>
            )}
        </div>
    );
};
