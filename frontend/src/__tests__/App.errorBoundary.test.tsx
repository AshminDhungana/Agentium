import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import React from 'react';
import { Toaster } from 'react-hot-toast';

// Throwing component simulating GlobalWebSocketProvider crash
function ThrowingProvider({ children }: { children: React.ReactNode }) {
  throw new Error('WebSocket provider crashed');
}

function TestAppWrapper() {
  const queryClient = new QueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary variant="page" fallbackHeading="App Error">
          <Toaster position="top-right" />
          <ThrowingProvider>
            <div>App Content</div>
          </ThrowingProvider>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

test('error boundary wraps GlobalWebSocketProvider and Toaster', () => {
  render(<TestAppWrapper />);
  expect(screen.getByRole('alert')).toBeInTheDocument();
  expect(screen.getByText('App Error')).toBeInTheDocument();
});