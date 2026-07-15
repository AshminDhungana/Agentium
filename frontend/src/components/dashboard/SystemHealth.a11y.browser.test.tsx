import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { SystemHealth } from '@/components/dashboard/SystemHealth';

describe('SystemHealth color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<SystemHealth />, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<SystemHealth />, 'dark');
    expect(result).toHaveNoViolations();
  });
});
