import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { authService } from './services/auth';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import './index.css';

// Initialize authentication from stored token
authService.initAuth();

// Create Query Client for React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <ErrorBoundary variant="page" fallbackHeading="Application Error">
      <App />
    </ErrorBoundary>
  </QueryClientProvider>
);