import { useEffect, useState } from 'react';

type Breakpoint = 'mobile' | 'tablet' | 'desktop-sm' | 'desktop-lg';

const BREAKPOINTS = {
  mobile: 768,
  tablet: 1024,
  'desktop-sm': 1280,
} as const;

export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>('desktop-lg');

  useEffect(() => {
    const updateBreakpoint = () => {
      const width = window.innerWidth;
      if (width < BREAKPOINTS.mobile) {
        setBreakpoint('mobile');
      } else if (width < BREAKPOINTS.tablet) {
        setBreakpoint('tablet');
      } else if (width < BREAKPOINTS['desktop-sm']) {
        setBreakpoint('desktop-sm');
      } else {
        setBreakpoint('desktop-lg');
      }
    };

    updateBreakpoint();
    window.addEventListener('resize', updateBreakpoint);
    return () => window.removeEventListener('resize', updateBreakpoint);
  }, []);

  return breakpoint;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(query);
    setMatches(mediaQuery.matches);
    const handler = (event: MediaQueryListEvent) => setMatches(event.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

export const BREAKPOINT_VALUES = BREAKPOINTS;