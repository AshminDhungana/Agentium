import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import React, { Suspense, lazy } from 'react';

// Simulate a page component that throws on render
const ThrowingPage = () => {
  throw new Error('Page component crashed');
};

// Simulate a lazy component that fails to load
const FailingLazyPage = lazy(() => Promise.reject(new Error('Chunk load failed')));

function TestApp() {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Root level - from main.tsx */}
        <ErrorBoundary variant="page" fallbackHeading="Root Error">
          <div>App Content</div>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe('Layered error boundary integration', () => {
  test('root error boundary catches App-level crashes', () => {
    // This would need a modified App that throws, or we test the boundary directly
    function ThrowingApp() {
      throw new Error('App init failed');
    }

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ErrorBoundary variant="page" fallbackHeading="Root Error">
            <ThrowingApp />
          </ErrorBoundary>
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Root Error')).toBeInTheDocument();
  });

  test('page error boundary in MainLayout catches chunk load failures', async () => {
    // Test the ErrorBoundary + Suspense combo from MainLayout
    function TestWrapper() {
      return (
        <ErrorBoundary variant="widget" fallbackHeading="Chunk Failed">
          <Suspense fallback={<div>Loading...</div>}>
            <FailingLazyPage />
          </Suspense>
        </ErrorBoundary>
      );
    }

    render(<TestWrapper />);

    await waitFor(() => {
      expect(screen.getByText('Chunk Failed')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});