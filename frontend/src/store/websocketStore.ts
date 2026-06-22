/**
 * websocketStore.ts
 *
 */

import { create } from 'zustand';
import { showToast } from '@/hooks/useToast';

// ── Types ─────────────────────────────────────────────────────────────────────

/**
 * Attachment metadata forwarded with a chat message over WebSocket.
 * Mirrors the Attachment interface in ChatPage but lives here so the store
 * can be typed without importing from a page component.
 */
export interface MessageAttachment {
    name: string;
    type: string;
    size: number;
    url?: string;
    category?: string;
}

export interface WebSocketMessage {
    type: string;
    role?: string;
    content?: string;
    /** Server-generated stable ID — use for dedup, NOT timestamp */
    message_id?: string;
    timestamp?: string;
    metadata?: Record<string, unknown>;

    // ── Structured lifecycle event fields ──────────────────────────────────
    /** Present on: agent_spawned, agent_liquidated, agent_promoted, agent_status_changed */
    agent_id?:   string;
    /** Present on: agent_spawned, agent_liquidated, agent_promoted, agent_status_changed */
    agent_name?: string;
    /** Present on: agent_spawned */
    agent_type?: string;
    /** Present on: agent_spawned */
    parent_id?:  string;
    /** Present on: agent_status_changed */
    new_status?: string;
    /** Present on: agent_status_changed */
    old_status?: string;
    /** Present on: agent_promoted */
    old_agentium_id?: string;
    /** Present on: agent_promoted */
    new_agentium_id?: string;
    /** Present on: agent_promoted, agent_liquidated */
    promoted_by?:  string;
    liquidated_by?: string;
    /** Present on: agent_liquidated */
    tasks_reassigned?: number;

    [key: string]: unknown;
}

interface WebSocketState {
    // Public state
    isConnected: boolean;
    isConnecting: boolean;
    error: string | null;
    connectionStats: {
        reconnectAttempts: number;
        lastPingTime: string | null;
        latencyMs: number | null;
    };
    lastMessage: WebSocketMessage | null;
    unreadCount: number;
    messageHistory: WebSocketMessage[];

    // Internal (prefixed _)
    _ws: WebSocket | null;
    _reconnectTimeout: ReturnType<typeof setTimeout> | null;
    _pingInterval: ReturnType<typeof setInterval> | null;
    _pongTimeout: ReturnType<typeof setTimeout> | null;
    _connectionTimeout: ReturnType<typeof setTimeout> | null;
    _reconnectAttempts: number;
    _isManualDisconnect: boolean;
    _lastPingTime: string | null;
    _messageQueue: Array<{ content: string; timestamp: number; attachments?: MessageAttachment[] }>;
    /** Capped dedup set — prevents duplicate toast stacking */
    _processedIds: Set<string>;
    /** Toast dedup: tracks IDs of active council-message toasts */
    _activeToastId: string | null;
    /**
     * BUG 3 FIX: timestamp (ms) of the last connect() invocation.
     * Any call within 1 s of the previous one is dropped, preventing two
     * simultaneous callers from opening duplicate sockets when _ws is
     * momentarily null between close and reconnect.
     */
    _lastConnectTime: number;
    /**
     * True when the server returned system_not_ready with genesis_triggered=false
     * (i.e. no API key saved yet). While this is true the store stays completely
     * silent — no banner, no retry loop. It is cleared as soon as the user calls
     * notifyApiKeyAdded(), which immediately re-attempts connection.
     */
    _genesisWaitingForApiKey: boolean;
    /**
     * BUG 2 FIX: true after the first successful ping→pong round-trip,
     * which is when we consider the connection genuinely stable and safe to
     * reset _reconnectAttempts. Using the system handshake alone was too
     * early — it reset the backoff counter on every reconnect cycle.
     */
    _connectionStable: boolean;
    _lastMessageTimestamp: string | null;

    // Public actions
    connect: () => void;
    disconnect: (isManual?: boolean) => void;
    reconnect: () => void;
    sendMessage: (content: string, attachments?: MessageAttachment[]) => boolean;
    sendPing: () => boolean;
    markAsRead: () => void;
    addMessageToHistory: (message: WebSocketMessage) => void;
    clearError: () => void;
    /**
     * Call this after the user saves their first API key on the Models page.
     * It kicks the WebSocket out of the silent "no API key yet" state and
     * immediately attempts to reconnect — so chat activates without a page reload.
     */
    notifyApiKeyAdded: () => void;

    // Internal actions
    _setConnected: (connected: boolean) => void;
    _setConnecting: (connecting: boolean) => void;
    _setError: (error: string | null) => void;
    _updateStats: (stats: Partial<WebSocketState['connectionStats']>) => void;
    _setLastMessage: (message: WebSocketMessage) => void;
    _incrementUnread: () => void;
    _clearAllTimers: () => void;
    _stopHeartbeat: () => void;
    _startHeartbeat: () => void;
    _handlePong: (timestamp: string) => void;
    _trackProcessedId: (id: string) => void;
    _scheduleReconnect: () => void;
    _fetchReplay: () => Promise<void>;
}

// ── Config ────────────────────────────────────────────────────────────────────

const WS_CONFIG = {
    MAX_RECONNECT_ATTEMPTS:   10,
    BASE_RECONNECT_DELAY_MS:  1_000,
    MAX_RECONNECT_DELAY_MS:   30_000,
    PING_INTERVAL_MS:         30_000,
    PONG_TIMEOUT_MS:          10_000,
    CONNECTION_TIMEOUT_MS:    10_000,
    MAX_HISTORY_SIZE:         100,
    /** Cap the dedup set so it doesn't grow forever */
    MAX_PROCESSED_IDS:        500,
    /**
     * BUG 3 FIX: minimum ms between connect() calls.
     * Prevents duplicate sockets when multiple callers race on a briefly-null _ws.
     */
    MIN_CONNECT_INTERVAL_MS:  1_000,
} as const;

// ── Store ─────────────────────────────────────────────────────────────────────

export const useWebSocketStore = create<WebSocketState>()((set, get) => ({
    // ── Initial state ──────────────────────────────────────────────────────
    isConnected:    false,
    isConnecting:   false,
    error:          null,
    connectionStats: {
        reconnectAttempts: 0,
        lastPingTime:      null,
        latencyMs:         null,
    },
    lastMessage:     null,
    unreadCount:     0,
    messageHistory:  [],

    _ws:                 null,
    _reconnectTimeout:   null,
    _pingInterval:       null,
    _pongTimeout:        null,
    _connectionTimeout:  null,
    _reconnectAttempts:  0,
    _isManualDisconnect: false,
    _lastPingTime:       null,
    _messageQueue:       [],
    _processedIds:       new Set<string>(),
    _activeToastId:      null,
    _lastConnectTime:    0,       // BUG 3 FIX
    _genesisWaitingForApiKey: false,
    _connectionStable:   false,   // BUG 2 FIX
    _lastMessageTimestamp: null,

    // ── Internal setters ───────────────────────────────────────────────────
    _setConnected:   (connected)  => set({ isConnected: connected }),
    _setConnecting:  (connecting) => set({ isConnecting: connecting }),
    _setError:       (error)      => set({ error }),
    _updateStats:    (stats)      => set(s => ({ connectionStats: { ...s.connectionStats, ...stats } })),
    _setLastMessage: (message)    => set({ lastMessage: message }),
    _incrementUnread: ()          => set(s => ({ unreadCount: s.unreadCount + 1 })),
    markAsRead:      ()           => set({ unreadCount: 0 }),
    clearError:      ()           => set({ error: null }),

    notifyApiKeyAdded: () => {
        // Clear the "waiting for API key" flag and immediately try to connect.
        // This is called by the Models page after a successful API key save,
        // which ensures chat becomes active without requiring a page reload.
        console.log('[WebSocket] API key added — re-attempting connection');
        set({ _genesisWaitingForApiKey: false });
        get().disconnect(true);
        setTimeout(() => get().connect(), 100);
    },

    /** Keep the dedup set bounded to MAX_PROCESSED_IDS */
    _trackProcessedId: (id: string) => {
        const ids = get()._processedIds;
        if (ids.size >= WS_CONFIG.MAX_PROCESSED_IDS) {
            const arr     = Array.from(ids);
            const trimmed = arr.slice(Math.floor(WS_CONFIG.MAX_PROCESSED_IDS / 4));
            set({ _processedIds: new Set(trimmed) });
        }
        get()._processedIds.add(id);
    },

    addMessageToHistory: (message) =>
        set(s => {
            const next = [...s.messageHistory, message];
            if (next.length > WS_CONFIG.MAX_HISTORY_SIZE) next.shift();
            return { messageHistory: next };
        }),

    // ── Timers ─────────────────────────────────────────────────────────────
    _clearAllTimers: () => {
        const s = get();
        if (s._reconnectTimeout)  { clearTimeout(s._reconnectTimeout);  set({ _reconnectTimeout: null }); }
        if (s._pingInterval)      { clearInterval(s._pingInterval);      set({ _pingInterval: null }); }
        if (s._pongTimeout)       { clearTimeout(s._pongTimeout);        set({ _pongTimeout: null }); }
        if (s._connectionTimeout) { clearTimeout(s._connectionTimeout);  set({ _connectionTimeout: null }); }
    },

    _stopHeartbeat: () => {
        const s = get();
        if (s._pingInterval) { clearInterval(s._pingInterval); set({ _pingInterval: null }); }
        if (s._pongTimeout)  { clearTimeout(s._pongTimeout);   set({ _pongTimeout: null }); }
    },

    // ── BUG 1 FIX: shared reconnect scheduling ─────────────────────────────
    // Both onclose and the pong timeout now call _scheduleReconnect() instead
    // of directly calling connect(). This ensures exponential backoff is
    // always applied, regardless of which code path triggers the reconnect.
    _scheduleReconnect: () => {
        const attempts = get()._reconnectAttempts;
        if (attempts >= WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
            get()._setError('Max retries reached. Click Reconnect to try again.');
            return;
        }
        const newAttempts = attempts + 1;
        set({ _reconnectAttempts: newAttempts });
        get()._updateStats({ reconnectAttempts: newAttempts });
        const delay = Math.min(
            WS_CONFIG.BASE_RECONNECT_DELAY_MS * Math.pow(2, newAttempts),
            WS_CONFIG.MAX_RECONNECT_DELAY_MS,
        );
        get()._setError(`Reconnecting in ${delay / 1000}s… (${newAttempts}/${WS_CONFIG.MAX_RECONNECT_ATTEMPTS})`);
        const t = setTimeout(() => get().connect(), delay);
        set({ _reconnectTimeout: t });
    },

    _startHeartbeat: () => {
        get()._stopHeartbeat();
        const interval = setInterval(() => {
            get().sendPing();
            // BUG 1 FIX: pong timeout now uses _scheduleReconnect() instead of
            // calling connect() directly. The old direct call bypassed backoff
            // entirely, producing an immediate reconnect on every pong failure
            // and causing the rapid 499 loop visible in nginx logs.
            const pongTimeout = setTimeout(() => {
                console.warn('[WebSocket] Pong timeout — scheduling reconnect with backoff');
                get()._setError('Connection lost (pong timeout)');
                get()._stopHeartbeat();
                // Cleanly close the socket without triggering the onclose
                // reconnect path (disconnect() nulls the handlers). The
                // reconnect is instead handled by _scheduleReconnect() below.
                const ws = get()._ws;
                if (ws) {
                    ws.onopen    = null;
                    ws.onclose   = null;
                    ws.onerror   = null;
                    ws.onmessage = null;
                    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                        ws.close(1000, 'Pong timeout');
                    }
                }
                set({ _ws: null, _connectionStable: false });
                get()._setConnected(false);
                get()._setConnecting(false);
                get()._scheduleReconnect();
            }, WS_CONFIG.PONG_TIMEOUT_MS);
            set({ _pongTimeout: pongTimeout });
        }, WS_CONFIG.PING_INTERVAL_MS);
        set({ _pingInterval: interval });
    },

    _handlePong: (timestamp: string) => {
        const s = get();
        if (s._pongTimeout) { clearTimeout(s._pongTimeout); set({ _pongTimeout: null }); }
        if (s._lastPingTime) {
            const latencyMs = Date.now() - new Date(s._lastPingTime).getTime();
            get()._updateStats({ latencyMs });
        }
        // BUG 2 FIX: reset _reconnectAttempts here (first successful pong)
        // instead of in the system message handler. The system message fires
        // immediately after auth — too early to call the connection stable.
        // A completed ping→pong round-trip proves the connection is healthy.
        if (!s._connectionStable) {
            set({ _connectionStable: true, _reconnectAttempts: 0 });
            get()._updateStats({ reconnectAttempts: 0 });
            console.log('[WebSocket] Connection stable — backoff counter reset');
            get()._fetchReplay();
        }
    },

    _fetchReplay: async () => {
        const since = get()._lastMessageTimestamp;
        if (!since) return;
        try {
            const token = localStorage.getItem('access_token');
            const headers: Record<string, string> = {};
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            const res = await fetch(`/ws/replay?since=${encodeURIComponent(since)}`, { headers });
            if (!res.ok) return;
            const data = await res.json();
            if (data.events && Array.isArray(data.events)) {
                if (data.events.length > 0) {
                    console.log(`[WebSocket] Replaying ${data.events.length} missed events`);
                }
                const ws = get()._ws;
                if (!ws || !ws.onmessage) return;
                
                data.events.forEach((ev: any) => {
                    const syntheticEvent = new MessageEvent('message', {
                        data: JSON.stringify(ev)
                    });
                    ws.onmessage!.call(ws, syntheticEvent as any);
                });
            }
        } catch (err) {
            console.error('[WebSocket] Replay fetch failed:', err);
        }
    },

    // ── Connect ────────────────────────────────────────────────────────────
    connect: () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            get()._setError('No access token — please login');
            return;
        }

        // If the server told us there is no API key yet, stay silent until the
        // user saves one and calls notifyApiKeyAdded(). Without this guard the
        // reconnect timer / effect re-runs would keep re-connecting and the
        // "System Initializing" banner would flash on every attempt.
        if (get()._genesisWaitingForApiKey) {
            console.debug('[WebSocket] connect() suppressed — waiting for API key');
            return;
        }

        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING) return;
        if (s._ws?.readyState === WebSocket.OPEN)       return;

        // BUG 3 FIX: reject calls that arrive within MIN_CONNECT_INTERVAL_MS
        // of the previous call. When _ws is momentarily null (between close and
        // reconnect timer), two callers (e.g. reconnect timer + effect re-run)
        // can both pass the readyState guards above and open duplicate sockets.
        const now = Date.now();
        if (now - s._lastConnectTime < WS_CONFIG.MIN_CONNECT_INTERVAL_MS) {
            console.debug('[WebSocket] connect() called too soon — debounced');
            return;
        }
        set({ _lastConnectTime: now });

        get()._setConnecting(true);
        get()._setError(null);
        set({ _isManualDisconnect: false, _connectionStable: false });

        // NO token in URL — connect cleanly, send auth as first message
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl    = `${protocol}//${window.location.host}/ws/chat`;

        console.log(`[WebSocket] Connecting to ${wsUrl} (attempt ${get()._reconnectAttempts + 1})`);

        try {
            const ws = new WebSocket(wsUrl);
            set({ _ws: ws });

            const connectionTimeout = setTimeout(() => {
                if (ws.readyState !== WebSocket.OPEN) {
                    console.error('[WebSocket] Connection timeout');
                    ws.close();
                    get()._setError('Connection timeout');
                }
            }, WS_CONFIG.CONNECTION_TIMEOUT_MS);
            set({ _connectionTimeout: connectionTimeout });

            ws.onopen = () => {
                console.log('[WebSocket] ✅ Connected — sending auth handshake');
                get()._clearAllTimers();
                ws.send(JSON.stringify({ type: 'auth', token }));
            };

            ws.onmessage = (event) => {
                try {
                    const data: WebSocketMessage = JSON.parse(event.data);

                    if (data.type === 'pong') {
                        get()._handlePong(String(data.timestamp ?? ''));
                        return;
                    }

                    // Auth confirmed — system welcome message
                    if (data.type === 'system') {
                        get()._setConnected(true);
                        get()._setConnecting(false);
                        // BUG 2 FIX: do NOT reset _reconnectAttempts here.
                        // We only reset it after the first successful pong
                        // round-trip (in _handlePong), which confirms the
                        // connection is genuinely stable. Resetting here caused
                        // the backoff to restart from 2 s on every reconnect.
                        get()._startHeartbeat();

                        // Flush queued messages
                        const queued = get()._messageQueue;
                        if (queued.length > 0) {
                            queued.forEach(msg =>
                                ws.send(JSON.stringify({
                                    type:        'message',
                                    content:     msg.content,
                                    timestamp:   new Date(msg.timestamp).toISOString(),
                                    attachments: msg.attachments,
                                }))
                            );
                            set({ _messageQueue: [] });
                        }
                        return;
                    }

                    if (data.type === 'auth_required') {
                        console.warn('[WebSocket] Received auth_required — resending auth');
                        ws.send(JSON.stringify({ type: 'auth', token }));
                        return;
                    }

                    // genesis_triggered=false  → no API key saved yet, stay silent.
                    // genesis_triggered=true   → API key exists, genesis is running,
                    //                            show banner and poll every 10 s.
                    if (data.type === 'system_not_ready') {
                        const triggered = data.genesis_triggered as boolean | undefined;
                        // We are definitively not connected, but keep isConnecting true
                        // so the reconnect / initialization banner stays visible while
                        // the client polls for genesis completion.
                        get()._setConnected(false);

                        if (triggered) {
                            // API key saved, genesis running — surface status and
                            // poll gently every 10 s without burning the backoff counter.
                            console.warn('[WebSocket] system_not_ready — genesis in progress, will retry in 10s');
                            set({ _genesisWaitingForApiKey: false });
                            get()._setError(
                                (data.content as string | undefined) ??
                                'Genesis in progress. Retrying…'
                            );
                            const t = setTimeout(() => {
                                get()._setError(null);
                                get().connect();
                            }, 10_000);
                            set({ _reconnectTimeout: t });
                        } else {
                            // No API key yet — user hasn't triggered genesis.
                            // Set the waiting flag so connect() is a no-op until
                            // notifyApiKeyAdded() is called. Clear any error so
                            // no banner appears and no retry loop starts.
                            console.warn('[WebSocket] system_not_ready — no API key configured yet, staying silent');
                            set({ _genesisWaitingForApiKey: true });
                            get()._setError(null);
                        }
                        return;
                    }

                    if (data.timestamp) {
                        set({ _lastMessageTimestamp: data.timestamp });
                    }

                    get()._setLastMessage(data);
                    get().addMessageToHistory(data);

                    // ── Toast deduplication for Head of Council messages ──
                    if (data.type === 'message' && data.role === 'head_of_council') {
                        get()._incrementUnread();
                        const currentPath = window.location.pathname;
                        if (currentPath !== '/chat') {
                            const existingToastId = get()._activeToastId;
                            if (existingToastId) showToast.dismiss(existingToastId);
                            const toastId = showToast.success('New message from Head of Council');
                            set({ _activeToastId: toastId });
                        }
                    }
                } catch (e) {
                    console.error('[WebSocket] Failed to parse message:', e);
                }
            };

            ws.onerror = (event) => {
                console.error('[WebSocket] Error:', event);
            };

            ws.onclose = (event) => {
                get()._clearAllTimers();
                get()._setConnected(false);
                set({ _ws: null, _connectionStable: false });

                let errorMsg: string | null = null;
                switch (event.code) {
                    case 4001:
                        errorMsg = 'Authentication failed — please log in again';
                        get()._setConnecting(false);
                        break;
                    case 1000:
                        get()._setConnecting(false);
                        break; // clean close
                    case 1006:
                        errorMsg = 'Connection lost unexpectedly';
                        get()._setConnecting(false);
                        break;
                    case 1013:
                        // onmessage may have scheduled a reconnect timeout, but
                        // _clearAllTimers() above already cancelled it. If onmessage
                        // never ran (message lost before delivery) the client would
                        // be stuck forever. Recreate the retry here. Skip entirely
                        // when the server already told us no API key is saved yet
                        // so we remain silent in that silent-waiting state.
                        if (!get()._genesisWaitingForApiKey) {
                            if (!get().error) {
                                get()._setError('Genesis in progress. Retrying…');
                            }
                            {
                                const t = setTimeout(() => {
                                    get()._setError(null);
                                    get().connect();
                                }, 10_000);
                                set({ _reconnectTimeout: t });
                            }
                        }
                        // Keep isConnecting true so the reconnect/init banner
                        // stays visible while we poll every 10s.
                        break;
                    default:
                        errorMsg = `Connection closed (${event.code})`;
                        get()._setConnecting(false);
                        break;
                }
                if (errorMsg) get()._setError(errorMsg);

                const isManual = get()._isManualDisconnect;
                if (!isManual && event.code !== 4001 && event.code !== 1013) {
                    // BUG 1 FIX: use the shared _scheduleReconnect() which
                    // applies exponential backoff. Previously this path had
                    // its own inline backoff while the pong timeout bypassed
                    // it entirely — now both code paths behave consistently.
                    get()._scheduleReconnect();
                }
            };

        } catch (err) {
            console.error('[WebSocket] Failed to create connection:', err);
            get()._setError('Failed to create WebSocket connection');
            get()._setConnecting(false);
        }
    },

    // ── Disconnect ─────────────────────────────────────────────────────────
    disconnect: (isManual = false) => {
        const s = get();
        set({ _isManualDisconnect: isManual, _connectionStable: false });
        get()._clearAllTimers();

        if (s._ws) {
            s._ws.onopen    = null;
            s._ws.onclose   = null;
            s._ws.onerror   = null;
            s._ws.onmessage = null;
            if (s._ws.readyState === WebSocket.OPEN || s._ws.readyState === WebSocket.CONNECTING) {
                s._ws.close(1000, 'Client disconnect');
            }
            set({ _ws: null });
        }

        get()._setConnected(false);
        get()._setConnecting(false);
        if (isManual) {
            set({ _reconnectAttempts: 0 });
            get()._updateStats({ reconnectAttempts: 0 });
        }
    },

    // ── Reconnect ──────────────────────────────────────────────────────────
    reconnect: () => {
        console.log('[WebSocket] Manual reconnect triggered');
        set({ _reconnectAttempts: 0 });
        get()._updateStats({ reconnectAttempts: 0 });
        get().disconnect(true);
        setTimeout(() => get().connect(), 100);
    },

    // ── Send message ───────────────────────────────────────────────────────
    sendMessage: (content: string, attachments?: MessageAttachment[]) => {
        const s = get();
        if (s._ws?.readyState === WebSocket.OPEN) {
            try {
                s._ws.send(JSON.stringify({
                    type:        'message',
                    content:     content.trim(),
                    timestamp:   new Date().toISOString(),
                    attachments: attachments && attachments.length > 0 ? attachments : undefined,
                }));
                return true;
            } catch (e) {
                console.error('[WebSocket] Send error:', e);
                return false;
            }
        }
        console.warn('[WebSocket] Not connected — queuing message');
        set({ _messageQueue: [...get()._messageQueue, { content, timestamp: Date.now(), attachments }] });
        return false;
    },

    // ── Ping ───────────────────────────────────────────────────────────────
    sendPing: () => {
        const s = get();
        if (s._ws?.readyState === WebSocket.OPEN) {
            try {
                const ts = new Date().toISOString();
                s._ws.send(JSON.stringify({ type: 'ping', timestamp: ts }));
                set({ _lastPingTime: ts });
                get()._updateStats({ lastPingTime: ts });
                return true;
            } catch {
                return false;
            }
        }
        return false;
    },
}));

// ── Auto-connect on init ──────────────────────────────────────────────────────
export const initWebSocket = () => {
    const token = localStorage.getItem('access_token');
    if (token) useWebSocketStore.getState().connect();
};

// ── Cross-tab token change ────────────────────────────────────────────────────
if (typeof window !== 'undefined') {
    window.addEventListener('storage', (e) => {
        if (e.key === 'access_token') {
            if (e.newValue) {
                useWebSocketStore.getState().connect();
            } else {
                useWebSocketStore.getState().disconnect(true);
            }
        }
    });
}