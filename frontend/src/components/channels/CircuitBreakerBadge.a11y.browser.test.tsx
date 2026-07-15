import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { CircuitBreakerBadge } from '@/components/channels/CircuitBreakerBadge';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

describe('CircuitBreakerBadge color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <Shell><CircuitBreakerBadge state="closed" /></Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <Shell><CircuitBreakerBadge state="open" /></Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
