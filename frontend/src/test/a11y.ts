import axe, { type AxeResults } from 'axe-core';
import { render, type RenderResult } from '@testing-library/react';
import { expect } from 'vitest';

// Custom `toHaveNoViolations` matcher backed by axe-core directly (avoids the
// vitest-axe peer-dependency on a specific Vitest major). Registered globally
// via this module, which is imported by src/test/setup.ts.
expect.extend({
  toHaveNoViolations(received: AxeResults) {
    const violations = received.violations ?? [];
    const pass = violations.length === 0;
    return {
      pass,
      message: () =>
        pass
          ? 'expected no accessibility violations but found none'
          : `Expected no accessibility violations but found ${violations.length}:\n` +
            violations
              .map((v) => `  • [${v.id}] ${v.help} — ${v.nodes.length} node(s)`)
              .join('\n'),
    };
  },
});

// Run axe in jsdom. The color-contrast rule needs layout/getComputedStyle and
// is unreliable under jsdom, so it is disabled here; the browser `a11y` project
// (Task 2) enables it against a real Chromium layout.
export async function checkA11y(ui: React.ReactElement): Promise<RenderResult> {
  const result = render(ui);
  const results = (await axe.run(result.container, {
    rules: { 'color-contrast': { enabled: false } },
  })) as AxeResults;
  expect(results).toHaveNoViolations();
  return result;
}
