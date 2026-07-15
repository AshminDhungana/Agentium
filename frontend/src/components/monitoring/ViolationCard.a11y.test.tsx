import { render } from '@testing-library/react';
import { describe, it } from 'vitest';
import { ViolationCard } from './ViolationCard';
import { ViolationReport } from '@/types';
import { checkA11y } from '@/test/a11y';

const violation: ViolationReport = {
  id: 'v-1',
  reporter: '00001',
  violator: '30001',
  severity: 'major',
  type: 'unauthorized_tool',
  description: 'Used a forbidden tool without Head approval',
  status: 'pending',
  created_at: new Date().toISOString(),
};

describe('ViolationCard accessibility', () => {
  it('has no axe violations and icon buttons are named', async () => {
    const { container, getByRole } = render(
      <ViolationCard violation={violation} onResolve={() => {}} onDismiss={() => {}} />
    );

    // Icon-only action buttons must expose an accessible name.
    expect(getByRole('button', { name: 'Resolve violation' })).toBeInTheDocument();
    expect(getByRole('button', { name: 'Dismiss violation' })).toBeInTheDocument();

    await checkA11y(container!);
  });
});
