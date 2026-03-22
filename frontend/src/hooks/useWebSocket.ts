import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';

// Message types matching backend protocol
export type WebSocketMessageType = 'message' | 'status' | 'error' | 'system' | 'pong';

export interface WebSocketMessage {
    type: WebSocketMessageType;
    role?: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    metadata?: {
        agent_id?: string;
        model?: string;
        task_created?: boolean;
        task_id?: string;
        tokens_used?: number;
        connection_id?: number;
        requires_response?: boolean;
        prompt_type?: string;
    };
    timestamp?: string;
    agent_id?: string;
}

export interface UseWebSocketChatReturn {
    isConnected: boolean;
    isConnecting: boolean;
    error: string | null;
    connect: () => void;
    disconnect: () => void;
    sendMessage: (content: string) => boolean;
    sendPing: () => boolean;
    reconnect: () => void;
    connectionStats: {
        reconnectAttempts: number;
        lastPingTime: number | null;
        latencyMs: number | null;
    };
}

// Configuration constants
const WS_CONFIG = {
    MAX_RECONNECT_ATTEMPTS: 5,
    BASE_RECONNECT_DELAY_MS: 1000,
    MAX_RECONNECT_DELAY_MS: 30000,
    PING_INTERVAL_MS: 30000,
    PONG_TIMEOUT_MS: 10000,
    CONNECTION_TIMEOUT_MS: 10000,
} as const;

export function useWebSocketChat(onMessage: (msg: WebSocketMessage) => void): UseWebSocketChatReturn {
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [connectionStats, setConnectionStats] = useState({
        reconnectAttempts: 0,
        lastPingTime: null as number | null,
        latencyMs: null as number | null,
    });

    const ws = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const pongTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const connectionTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const reconnectAttemptsRef = useRef(0);
    const isManualDisconnect = useRef(false);
    const lastPingTimeRef = useRef<number | null>(null);
    // Stable ref so onMessage identity changes don't trigger reconnects
    const onMessageRef = useRef(onMessage);
    useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

    const isAuthenticated = useAuthStore(state => state.user?.isAuthenticated ?? false);
    const logout = useAuthStore(state => state.logout);

    const clearAllTimers = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }
        if (pongTimeoutRef.current) {
            clearTimeout(pongTimeoutRef.current);
            pongTimeoutRef.current = null;
        }
        if (connectionTimeoutRef.current) {
            clearTimeout(connectionTimeoutRef.current);
            connectionTimeoutRef.current = null;
        }
    }, []);

    const stopHeartbeat = useCallback(() => {
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }
        if (pongTimeoutRef.current) {
            clearTimeout(pongTimeoutRef.current);
            pongTimeoutRef.current = null;
        }
    }, []);

    const startHeartbeat = useCallback(() => {
        stopHeartbeat();

        pingIntervalRef.current = setInterval(() => {
            if (ws.current?.readyState === WebSocket.OPEN) {
                const pingTime = Date.now();
                lastPingTimeRef.current = pingTime;
                setConnectionStats(prev => ({ ...prev, lastPingTime: pingTime }));
                ws.current.send(JSON.stringify({ type: 'ping', timestamp: pingTime }));

                pongTimeoutRef.current = setTimeout(() => {
                    console.warn('[WebSocket] Pong timeout - connection may be dead');
                    ws.current?.close();
                }, WS_CONFIG.PONG_TIMEOUT_MS);
            }
        }, WS_CONFIG.PING_INTERVAL_MS);
    }, [stopHeartbeat]);

    const handlePong = useCallback((_timestamp: string) => {
        if (pongTimeoutRef.current) {
            clearTimeout(pongTimeoutRef.current);
            pongTimeoutRef.current = null;
        }
        const latency = Date.now() - (lastPingTimeRef.current || Date.now());
        setConnectionStats(prev => ({ ...prev, latencyMs: latency }));
    }, []);

    const disconnect = useCallback((isManual: boolean = false) => {
        isManualDisconnect.current = isManual;
        clearAllTimers();

        if (ws.current) {
            ws.current.onopen = null;
            ws.current.onclose = null;
            ws.current.onerror = null;
            ws.current.onmessage = null;

            if (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING) {
                ws.current.close(1000, 'Client disconnect');
            }
            ws.current = null;
        }

        setIsConnected(false);
        setIsConnecting(false);

        if (isManual) {
            reconnectAttemptsRef.current = 0;
            setConnectionStats(prev => ({ ...prev, reconnectAttempts: 0 }));
        }
    }, [clearAllTimers]);

    // connect is defined with useCallback but doesn't list isConnected/isConnecting
    // as dependencies — we use the ws.current ref directly to avoid stale closures
    // that previously caused the useEffect connection logic to re-run on every state change.
    const connect = useCallback(() => {
        if (!isAuthenticated) {
            setError('Not authenticated');
            return;
        }

        if (ws.current?.readyState === WebSocket.CONNECTING) {
            return;
        }

        if (ws.current?.readyState === WebSocket.OPEN) {
            return;
        }

        const token = localStorage.getItem('access_token');
        if (!token) {
            setError('No access token - please login');
            return;
        }

        setIsConnecting(true);
        setError(null);
        isManualDisconnect.current = false;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat?token=${encodeURIComponent(token)}`;

        try {
            ws.current = new WebSocket(wsUrl);

            connectionTimeoutRef.current = setTimeout(() => {
                if (ws.current?.readyState !== WebSocket.OPEN) {
                    console.error('[WebSocket] Connection timeout');
                    ws.current?.close();
                    setError('Connection timeout');
                }
            }, WS_CONFIG.CONNECTION_TIMEOUT_MS);

            ws.current.onopen = () => {
                clearAllTimers();
                setIsConnected(true);
                setIsConnecting(false);
                reconnectAttemptsRef.current = 0;
                setConnectionStats(prev => ({ ...prev, reconnectAttempts: 0 }));
                startHeartbeat();
            };

            ws.current.onmessage = (event) => {
                try {
                    const data: WebSocketMessage = JSON.parse(event.data);

                    if (data.type === 'pong') {
                        handlePong(data.timestamp || '');
                        return;
                    }

                    if ((data as any).type === 'auth_required') {
                        console.warn('[WebSocket] Received auth_required — resending auth token');
                        const token = localStorage.getItem('access_token');
                        if (token && ws.current?.readyState === WebSocket.OPEN) {
                            ws.current.send(JSON.stringify({ type: 'auth', token }));
                        } else {
                            setError('Session expired — please log in again');
                            logout();
                        }
                        return;
                    }

                    onMessageRef.current(data);
                } catch (e) {
                    console.error('[WebSocket] Parse error:', e);
                }
            };

            ws.current.onerror = (event) => {
                console.error('[WebSocket] Error:', event);
                setError('Connection error occurred');
                setIsConnected(false);
            };

            ws.current.onclose = (event) => {
                stopHeartbeat();
                setIsConnected(false);
                setIsConnecting(false);

                switch (event.code) {
                    case 1000:
                        if (!isManualDisconnect.current) {
                            setError('Connection closed');
                        }
                        break;
                    case 4001:
                        setError('Authentication failed - please login again');
                        logout();
                        return;
                    case 1011:
                        setError('Server error - please try again later');
                        break;
                    case 1006:
                        setError('Connection lost');
                        break;
                    default:
                        setError(`Connection closed (${event.code})`);
                }

                if (!isManualDisconnect.current && event.code !== 4001) {
                    if (reconnectAttemptsRef.current < WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
                        reconnectAttemptsRef.current += 1;
                        const delay = Math.min(
                            WS_CONFIG.BASE_RECONNECT_DELAY_MS * Math.pow(2, reconnectAttemptsRef.current),
                            WS_CONFIG.MAX_RECONNECT_DELAY_MS
                        );

                        setConnectionStats(prev => ({
                            ...prev,
                            reconnectAttempts: reconnectAttemptsRef.current
                        }));
                        setError(`Reconnecting in ${delay / 1000}s... (${reconnectAttemptsRef.current}/${WS_CONFIG.MAX_RECONNECT_ATTEMPTS})`);

                        reconnectTimeoutRef.current = setTimeout(() => {
                            connect();
                        }, delay);
                    } else {
                        setError('Max retries reached. Click Reconnect to try again.');
                    }
                }
            };

        } catch (err) {
            console.error('[WebSocket] Failed to create connection:', err);
            setError('Failed to create WebSocket connection');
            setIsConnecting(false);
        }
    // Note: connect intentionally omits isConnected/isConnecting to avoid
    // the reconnect loop bug. State is read from ws.current ref instead.
    }, [isAuthenticated, clearAllTimers, startHeartbeat, handlePong, logout, stopHeartbeat]);

    const reconnect = useCallback(() => {
        reconnectAttemptsRef.current = 0;
        setConnectionStats(prev => ({ ...prev, reconnectAttempts: 0 }));
        disconnect(true);
        setTimeout(connect, 100);
    }, [connect, disconnect]);

    const sendMessage = useCallback((content: string): boolean => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            try {
                ws.current.send(JSON.stringify({
                    type: 'message',
                    content: content.trim(),
                    timestamp: new Date().toISOString()
                }));
                return true;
            } catch (e) {
                console.error('[WebSocket] Send error:', e);
                return false;
            }
        }
        console.warn('[WebSocket] Cannot send - not connected');
        return false;
    }, []);

    const sendPing = useCallback((): boolean => {
        if (ws.current?.readyState === WebSocket.OPEN) {
            try {
                ws.current.send(JSON.stringify({
                    type: 'ping',
                    timestamp: Date.now()
                }));
                return true;
            } catch (e) {
                return false;
            }
        }
        return false;
    }, []);

    // Initial connection — only re-runs when auth state changes, not on every
    // connect/disconnect state update (the previous bug).
    useEffect(() => {
        if (isAuthenticated) {
            connect();
        }

        return () => {
            disconnect(true);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isAuthenticated]);

    useEffect(() => {
        const handleStorage = (e: StorageEvent) => {
            if (e.key === 'access_token') {
                if (e.newValue) {
                    disconnect(true);
                    setTimeout(connect, 100);
                } else {
                    disconnect(true);
                    setError('Logged out in another tab');
                }
            }
        };

        window.addEventListener('storage', handleStorage);
        return () => window.removeEventListener('storage', handleStorage);
    }, [connect, disconnect]);

    return {
        isConnected,
        isConnecting,
        error,
        connect,
        disconnect: () => disconnect(true),
        sendMessage,
        sendPing,
        reconnect,
        connectionStats
    };
}