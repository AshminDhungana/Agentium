import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { HealthScore } from '@/components/monitoring/HealthScore';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

describe('HealthScore color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<Shell><HealthScore score={85} size="lg" /></Shell>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<Shell><HealthScore score={85} size="lg" /></Shell>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
