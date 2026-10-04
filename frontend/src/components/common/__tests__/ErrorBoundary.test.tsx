import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ErrorBoundary } from '../ErrorBoundary';
import React from 'react';

// Mock the error reporting API
vi.mock('@/services/errorReporting', () => ({
  errorReportingApi: {
    report: vi.fn().mockResolvedValue(undefined),
  },
}));

// Access the mock
import { errorReportingApi } from '@/services/errorReporting';

// A component that throws on demand via a module-level ref
const throwRef = { current: true };

function ThrowOnDemand() {
  if (throwRef.current) throw new Error('Test render error');
  return <div>Child content rendered</div>;
}

// Suppress React error boundary console noise in tests
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  throwRef.current = true;
});

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Safe content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Safe content')).toBeInTheDocument();
  });

  it('renders widget fallback UI on child error (default variant)', () => {
    render(
      <ErrorBoundary fallbackHeading="Widget Error">
        <ThrowOnDemand />
      </ErrorBoundary>
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Widget Error')).toBeInTheDocument();
    expect(screen.getByText('Test render error')).toBeInTheDocument();
    // Widget variant has "Retry" button, not "Reload Page"
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByText('Reload Page')).not.toBeInTheDocument();
  });

  it('renders page fallback UI with both buttons for variant="page"', () => {
    render(
      <ErrorBoundary variant="page" fallbackHeading="Page Error">
        <ThrowOnDemand />
      </ErrorBoundary>
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Page Error')).toBeInTheDocument();
    expect(screen.getByText('Reload Page')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('retry button clears error and re-renders children', async () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();

    // Fix the error before clicking retry
    throwRef.current = false;

    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    // The component uses a 400ms setTimeout internally; waitFor will poll until it resolves
    await waitFor(() => {
      expect(screen.getByText('Child content rendered')).toBeInTheDocument();
    }, { timeout: 2000 });
  });

  it('calls errorReportingApi.report() with correct payload on error', () => {
    render(
      <ErrorBoundary>
        <ThrowOnDemand />
      </ErrorBoundary>
    );

    expect(errorReportingApi.report).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Test render error',
        name: 'Error',
        url: expect.any(String),
      })
    );
  });
});
