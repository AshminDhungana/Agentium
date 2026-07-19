import React from 'react';
import { render } from '@testing-library/react';
import { ProviderLogo } from './ProviderLogo';

describe('ProviderLogo', () => {
  it('renders a brand <img> for a known provider', () => {
    const { container } = render(<ProviderLogo provider="openai" />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('alt')).toBe('');
  });

  it('falls back to the Lucide icon (no <img>) for an unknown provider', () => {
    const { container } = render(<ProviderLogo provider="some-unknown-provider" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('svg')).not.toBeNull();
  });
});
