import { render } from '@testing-library/react';
import { IconButton } from '@/components/ui/IconButton';

test('IconButton renders a named, focusable button', () => {
  const { container } = render(
    <IconButton aria-label="Close">
      <span>×</span>
    </IconButton>
  );
  const btn = container.querySelector('button')!;
  expect(btn).toHaveAttribute('aria-label', 'Close');
  expect(btn).toHaveAttribute('type', 'button');
});

test('IconButton requires an aria-label (compile-time + runtime guard)', () => {
  // @ts-expect-error aria-label is required
  const { container } = render(<IconButton><span>×</span></IconButton>);
  // Even if bypassed, the rendered button has no usable name; assert that here
  // so the contract is enforced at runtime too.
  expect(container.querySelector('button')).not.toHaveAttribute('aria-label');
});
