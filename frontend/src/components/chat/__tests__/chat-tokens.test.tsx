// frontend/src/components/chat/__tests__/chat-tokens.test.tsx
// Chat design-token contract: every token FloatingChatWidget consumes must be
// defined in styles/chat-tokens.css (imported globally via index.css). jsdom
// has no cascade for custom properties from external sheets, so the test
// attaches the sheet text to the document itself and reads it back.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { FloatingChatWidget } from '../FloatingChatWidget';

const TOKENS_USED_BY_WIDGET = [
  '--c-chat-glass-bg',
  '--c-chat-glass-border',
  '--shadow-chat-float',
  '--shadow-chat-elevated',
  '--shadow-chat-magnetic',
];

test('chat tokens are injected into document', () => {
  // Attach the real stylesheet so jsdom's computed style resolves :root vars
  const css = readFileSync(
    join(__dirname, '..', '..', '..', 'styles', 'chat-tokens.css'),
    'utf-8',
  );
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const { container, unmount } = render(<FloatingChatWidget />);
  const styles = getComputedStyle(document.documentElement);
  // Tokens defined in :root should be readable
  for (const token of TOKENS_USED_BY_WIDGET) {
    expect(styles.getPropertyValue(token)).toBeTruthy();
  }

  unmount();
  style.remove();
});
