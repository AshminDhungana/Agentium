import { ReactNode } from 'react';

// Visually hides content while keeping it available to assistive technology.
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
