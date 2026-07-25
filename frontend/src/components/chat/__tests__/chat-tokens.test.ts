// frontend/src/components/chat/__tests__/chat-tokens.test.ts
import { render, screen } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

test('chat tokens are injected into document', () => {
  const { container } = render(<FloatingChatWidget />);
  const styles = getComputedStyle(container.firstElementChild as HTMLElement);
  // Tokens defined in :root should be readable
  expect(styles.getPropertyValue('--c-chat-glass-bg')).toBeTruthy();
  expect(styles.getPropertyValue('--c-chat-glass-border')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-float')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-elevated')).toBeTruthy();
  expect(styles.getPropertyValue('--shadow-chat-magnetic')).toBeTruthy();
});