// frontend/src/pages/SignupPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { SignupPage } from '@/pages/SignupPage';

describe('SignupPage color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><SignupPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><SignupPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});