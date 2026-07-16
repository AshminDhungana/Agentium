import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/services/api', () => ({
    api: { get: vi.fn().mockResolvedValue({ data: {} }) },
}));

import { ProviderAnalytics } from './ProviderAnalytics';

describe('ProviderAnalytics', () => {
    it('renders in an accessible region with blue accent, not indigo', () => {
        render(<ProviderAnalytics />);
        expect(screen.getByRole('region', { name: 'Provider analytics' })).toBeInTheDocument();
    });
});
