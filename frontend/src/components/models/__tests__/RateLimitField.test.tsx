import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RateLimitField } from '../RateLimitField';

describe('RateLimitField per-second helper', () => {
    it('shows ≈ 0.5 requests/second for 30/min', () => {
        render(<RateLimitField value={30} onChange={() => {}} />);
        expect(screen.getByText('≈ 0.5 requests/second')).toBeTruthy();
    });

    it('shows ≈ 2 requests/second for 120/min', () => {
        render(<RateLimitField value={120} onChange={() => {}} />);
        expect(screen.getByText('≈ 2 requests/second')).toBeTruthy();
    });

    it('shows ≈ 1 requests/second for the default 60/min', () => {
        render(<RateLimitField value={60} onChange={() => {}} />);
        expect(screen.getByText('≈ 1 requests/second')).toBeTruthy();
    });

    it('shows the provider-plan hint', () => {
        render(<RateLimitField value={60} onChange={() => {}} />);
        expect(
            screen.getByText(/1 request every 2 seconds = 30\/min/i)
        ).toBeTruthy();
    });

    it('calls onChange with the parsed integer when typed', () => {
        const onChange = vi.fn();
        render(<RateLimitField value={60} onChange={onChange} />);
        const input = screen.getByRole('spinbutton') as HTMLInputElement;
        fireEvent.change(input, { target: { value: '30' } });
        expect(onChange).toHaveBeenCalledWith(30);
    });

    it('falls back to 60 when input is emptied', () => {
        const onChange = vi.fn();
        render(<RateLimitField value={60} onChange={onChange} />);
        const input = screen.getByRole('spinbutton') as HTMLInputElement;
        fireEvent.change(input, { target: { value: '' } });
        expect(onChange).toHaveBeenCalledWith(60);
    });
});
