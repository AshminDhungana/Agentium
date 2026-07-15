import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { ViolationCard } from '@/components/monitoring/ViolationCard';
import type { ViolationReport } from '@/types';

const mockViolation: ViolationReport = {
  id: 'v1',
  reporter: '00001',
  violator: '30042',
  severity: 'major',
  type: 'unconstitutional_action',
  article: 'Art III',
  description: 'Agent executed a restricted operation without Head ratification.',
  status: 'pending',
  created_at: new Date().toISOString(),
};

describe('ViolationCard color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <ViolationCard violation={mockViolation} />,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <ViolationCard violation={mockViolation} />,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
