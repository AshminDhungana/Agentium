import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AddPeerModal } from '../AddPeerModal';
import { DelegateTaskModal } from '../DelegateTaskModal';
import { PeerInstance } from '@/services/federation';
import { checkA11y } from '@/test/a11y';

const peer: PeerInstance = {
  id: 'p1',
  name: 'Engineering',
  base_url: 'https://e.example.com',
  trust_level: 'limited',
  status: 'active',
  shared_secret: '***',
  created_at: new Date().toISOString(),
} as unknown as PeerInstance;

describe('Federation modals accessibility', () => {
  it('AddPeerModal exposes a labelled dialog with fields', async () => {
    const { container, getByRole } = render(
      <AddPeerModal isSubmitting={false} onClose={() => {}} onSubmit={vi.fn()} />
    );
    const dialog = getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(getByRole('button', { name: 'Close dialog' })).toBeTruthy();
    await checkA11y(container);
  });

  it('DelegateTaskModal exposes a labelled dialog with fields', async () => {
    const { container, getByRole } = render(
      <DelegateTaskModal peers={[peer]} isSubmitting={false} onClose={() => {}} onSubmit={vi.fn()} />
    );
    const dialog = getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(getByRole('button', { name: 'Close dialog' })).toBeTruthy();
    await checkA11y(container);
  });
});
