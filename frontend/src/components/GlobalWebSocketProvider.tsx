// src/components/GlobalWebSocketProvider.tsx
import { useEffect } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

export function GlobalWebSocketProvider({ children }: { children: React.ReactNode }) {
    const { user, isInitialized } = useAuthStore();
    const { connect, disconnect, isConnected, isConnecting, error } = useWebSocketStore();

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

    const showBanner = isConnecting && !isConnected && user?.isAuthenticated;

    return (
        <>
            {showBanner && (
                <div className="fixed bottom-4 right-4 z-50 bg-amber-500/90 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-in fade-in slide-in-from-bottom-4 backdrop-blur-sm pointer-events-none">
                    <LoadingSpinner size="md" />
                    <div>
                        <div className="text-sm font-semibold">Reconnecting to Server...</div>
                        {error && <div className="text-xs opacity-90 mt-0.5">{error}</div>}
                    </div>
                </div>
            )}
            {children}
        </>
    );
}