// frontend/src/components/auth/AuthCard.a11y.browser.test.tsx
import { describe, it, expect } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { AuthCard } from '@/components/auth/AuthCard';

describe('AuthCard color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <AuthCard title="Welcome Back" subtitle="Sign in to manage your AI governance system">
        <div className="text-gray-900 dark:text-white">Form content</div>
      </AuthCard>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <AuthCard title="Create Account" subtitle="Request access to the governance system">
        <div className="text-gray-900 dark:text-white">Form content</div>
      </AuthCard>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
