import { useState, useEffect } from 'react';

/**
 * Standard Tailwind breakpoints as media query strings.
 * Use with `useMediaQuery` to detect the current device class.
 */
export const BREAKPOINTS = {
  sm: '(min-width: 640px)',
  md: '(min-width: 768px)',
  lg: '(min-width: 1024px)',
  xl: '(min-width: 1280px)',
} as const;

/**
 * Reactive hook that wraps `window.matchMedia`.
 * Returns `true` when the viewport matches the given media query string.
 *
 * @example
 *   const isDesktop = useMediaQuery(BREAKPOINTS.lg);   // ≥ 1024px
 *   const isTablet  = useMediaQuery(BREAKPOINTS.sm);    // ≥ 640px
 *   // phone = !isTablet
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);

    // Set initial value in case SSR hydration differs
    setMatches(mql.matches);

    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}
