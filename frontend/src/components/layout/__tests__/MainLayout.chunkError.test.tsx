import { render, screen, waitFor } from '@testing-library/react';
import { Suspense } from 'react';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import React from 'react';

// Simulate a lazy component that fails to load
const FailingLazyComponent = React.lazy(() =>
  Promise.reject(new Error('Chunk load failed'))
);

function PageSkeleton() {
  return <div data-testid="skeleton">Loading...</div>;
}

function TestWrapper() {
  return (
    <ErrorBoundary variant="widget" fallbackHeading="Page Chunk Failed">
      <Suspense fallback={<PageSkeleton />}>
        <FailingLazyComponent />
      </Suspense>
    </ErrorBoundary>
  );
}

test('error boundary catches failed lazy chunk load', async () => {
  render(<TestWrapper />);

  // Initially shows skeleton (Suspense fallback)
  await waitFor(() => {
    expect(screen.getByText('Page Chunk Failed')).toBeInTheDocument();
  });

  expect(screen.getByRole('alert')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
});