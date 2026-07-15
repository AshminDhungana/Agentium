import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { CriticStatsPanel } from '@/components/agents/CriticStatsPanel';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

describe('CriticStatsPanel color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(<Shell><CriticStatsPanel /></Shell>, 'light');
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<Shell><CriticStatsPanel /></Shell>, 'dark');
    expect(result).toHaveNoViolations();
  });
});
