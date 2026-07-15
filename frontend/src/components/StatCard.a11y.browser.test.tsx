import { describe, it } from 'vitest';
import { Users } from 'lucide-react';
import { auditRoute } from '@/test/a11yBrowser';
import { StatCard } from '@/components/ui/StatCard';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

describe('StatCard color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <Shell><StatCard title="Active Agents" value={42} icon={Users} color="blue" /></Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <Shell><StatCard title="Active Agents" value={42} icon={Users} color="blue" /></Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
