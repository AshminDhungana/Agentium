// frontend/src/pages/LoginPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { LoginPage } from '@/pages/LoginPage';

describe('LoginPage color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><LoginPage /></MemoryRouter>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><LoginPage /></MemoryRouter>, 'dark');
    expect(result).toHaveNoViolations();
  });
});