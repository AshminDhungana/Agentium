import axe, { type AxeResults } from 'axe-core';
import { render } from '@testing-library/react';

// Renders `ui` in a real Chromium layout and runs axe-core WITH the
// color-contrast rule enabled. `theme` toggles the `dark` class on <html>
// to match MainLayout.toggleTheme, so we audit BOTH themes for WCAG AA.
export async function auditRoute(
  ui: React.ReactElement,
  theme: 'light' | 'dark'
): Promise<AxeResults> {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  const result = render(ui);
  return (await axe.run(result.container, {
    rules: { 'color-contrast': { enabled: true } },
  })) as AxeResults;
}
