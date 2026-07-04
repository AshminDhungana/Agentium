import React from 'react';
import { Loader2 } from 'lucide-react';

/**
 * @description A reusable loading spinner that renders a centered animated icon with an optional label.
 * Uses Lucide's Loader2 icon with a CSS spin animation.
 * @example
 * ```tsx
 * import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
 *
 * <LoadingSpinner size="lg" label="Loading agents..." />
 * ```
 * @param {'xs'|'sm'|'md'|'lg'|'xl'} [props.size] - Spinner diameter preset (default: 'md').
 * @param {string} [props.className] - Additional Tailwind classes to merge.
 * @param {string} [props.label] - Optional text label shown beneath the spinner.
 */

interface LoadingSpinnerProps {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  label?: string;
}

const sizeClasses = {
  xs: 'w-3 h-3',
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8',
  xl: 'w-12 h-12',
};

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  size = 'md', 
  className,
  label 
}) => {
  return (
    <div className="flex flex-col items-center justify-center gap-2">
      <Loader2 
        className={`animate-spin text-current ${sizeClasses[size]} ${className || ''}`} 
        aria-label="Loading"
      />
      {label && <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>}
    </div>
  );
};
