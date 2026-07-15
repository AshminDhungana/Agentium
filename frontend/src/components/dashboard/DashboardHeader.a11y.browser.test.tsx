import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';

describe('DashboardHeader color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<DashboardHeader />, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<DashboardHeader />, 'dark');
    expect(result).toHaveNoViolations();
  });
});
