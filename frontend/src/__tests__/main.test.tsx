import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import React from 'react';

// Test component that throws on render
function ThrowingApp() {
  throw new Error('Root app crashed');
}

function TestRootWrapper() {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary variant="page" fallbackHeading="App Crashed">
        <ThrowingApp />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

test('root error boundary catches thrown error and shows fallback', () => {
  render(<TestRootWrapper />);
  // ErrorBoundary should catch and render fallback
  expect(screen.getByRole('alert')).toBeInTheDocument();
  expect(screen.getByText('App Crashed')).toBeInTheDocument();
  expect(screen.getByText('A critical rendering error occurred in this view')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
});