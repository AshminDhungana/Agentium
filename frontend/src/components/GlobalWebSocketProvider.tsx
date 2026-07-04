// src/components/GlobalWebSocketProvider.tsx
import { useEffect } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

/**
 * @description Global WebSocket lifecycle manager that connects/disconnects based on auth state.
 * Automatically establishes WebSocket when a user is authenticated and tears down on logout.
 * @listens logout — Dispatches disconnect on window 'logout' event.
 * @example
 * ```tsx
 * import { GlobalWebSocketProvider } from '@/components/GlobalWebSocketProvider';
 *
 * <GlobalWebSocketProvider>
 *   <App />
 * </GlobalWebSocketProvider>
 * ```
 * @param {React.ReactNode} props.children - Child components wrapped by the provider.
 */
export function GlobalWebSocketProvider({ children }: { children: React.ReactNode }) {
    const { user, isInitialized } = useAuthStore();
    const { connect, disconnect } = useWebSocketStore();

    // Initialize WebSocket when auth is ready
    useEffect(() => {
        if (isInitialized && user?.isAuthenticated) {
            connect();
        } else if (isInitialized && !user?.isAuthenticated) {
            disconnect(true);
        }

        return () => {
            // Don't disconnect on unmount - we want it to persist!
            // Only disconnect on actual logout
        };
    }, [isInitialized, user?.isAuthenticated, connect, disconnect]);

    // Listen for logout events
    useEffect(() => {
        const handleLogout = () => {
            disconnect(true);
        };

        window.addEventListener('logout', handleLogout);
        return () => window.removeEventListener('logout', handleLogout);
    }, [disconnect]);

    return <>{children}</>;
}