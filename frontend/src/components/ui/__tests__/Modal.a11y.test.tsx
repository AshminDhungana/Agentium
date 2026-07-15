import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Modal } from '../Modal';
import { checkA11y } from '@/test/a11y';

function OpenButton() {
  return <button>Open</button>;
}

describe('Modal accessibility', () => {
  it('exposes dialog semantics and traps focus', async () => {
    const onClose = vi.fn();
    render(
      <>
        <OpenButton />
        <Modal open title="Create peer" onClose={onClose}>
          <input aria-label="Peer name" />
          <button>Save</button>
        </Modal>
      </>
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    // Initial focus moves into the dialog (the header close button is first).
    expect(dialog.contains(document.activeElement)).toBe(true);

    // Escape closes.
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('restores focus to the trigger on close', async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <>
        <button>Open</button>
        <Modal open title="Create peer" onClose={onClose}>
          <button>Save</button>
        </Modal>
      </>
    );
    const openBtn = screen.getByText('Open');
    openBtn.focus();
    expect(document.activeElement).toBe(openBtn);

    rerender(
      <>
        <button>Open</button>
        <Modal open={false} title="Create peer" onClose={onClose}>
          <button>Save</button>
        </Modal>
      </>
    );
    // On unmount the focus-trap cleanup restores focus to the trigger.
    await act(async () => {});
    expect(document.activeElement).toBe(openBtn);
  });

  it('has no axe violations', async () => {
    const { container } = render(
      <Modal open title="Create peer" onClose={() => {}}>
        <input aria-label="Peer name" />
      </Modal>
    );
    await checkA11y(container);
  });
});
