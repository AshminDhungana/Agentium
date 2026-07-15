import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { EmptyState } from '@/components/ui/EmptyState';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

describe('EmptyState color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <Shell><EmptyState title="No agents found" description="Create your first agent to get started." /></Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <Shell><EmptyState title="No agents found" description="Create your first agent to get started." /></Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
