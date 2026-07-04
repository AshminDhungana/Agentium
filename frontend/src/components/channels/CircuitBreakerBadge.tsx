/**
 * @description Badge component showing the current circuit breaker state for a channel.
 * Displays CLOSED (green), HALF-OPEN (yellow), or OPEN (red, pulsing).
 * @example
 * ```tsx
 * import { CircuitBreakerBadge } from '@/components/channels/CircuitBreakerBadge';
 *
 * <CircuitBreakerBadge state="closed" />
 * ```
 * @param {CircuitBreakerState} props.state - Current circuit breaker state.
 */
import type { CircuitBreakerState } from '@/types';

interface CircuitBreakerBadgeProps {
  state: CircuitBreakerState;
}

export function CircuitBreakerBadge({ state }: CircuitBreakerBadgeProps) {
  const config = {
    closed: {
      label: 'CLOSED',
      class: 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400 border-green-200 dark:border-green-500/20'
    },
    half_open: {
      label: 'HALF-OPEN',
      class: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20'
    },
    open: {
      label: 'OPEN',
      class: 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20 animate-pulse'
    }
  };

  const { label, class: className } = config[state];

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${className}`}>
      Circuit: {label}
    </span>
  );
}