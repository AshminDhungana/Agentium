/**
 * websocketStore.ts
 *
 */

import { create } from 'zustand';
import { showToast } from '@/hooks/useToast';
import { websocketReplayApi } from '@/services/websocketReplay';
import { logger } from '@/utils/logger';

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
    agent_id?: string;
    /** Present on: agent_spawned, agent_liquidated, agent_promoted, agent_status_changed */
    agent_name?: string;
    /** Present on: agent_spawned */
    agent_type?: string;
    /** Present on: agent_spawned */
    parent_id?: string;
    /** Present on: agent_status_changed */
    new_status?: string;
    /** Present on: agent_status_changed */
    old_status?: string;
    /** Present on: agent_promoted */
    old_agentium_id?: string;
    /** Present on: agent_promoted */
    new_agentium_id?: string;
    /** Present on: agent_promoted, agent_liquidated */
    promoted_by?: string;
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
     * Handle for the active genesis-status poll timer (GET /ws/genesis-status).
     * Replaces the old blind 10s WS-reconnect loop with a fast, cheap HTTP
     * poll while genesis runs in the background. Cleared on disconnect/unmount
     * so polling never outlives the component.
     */
    _genesisPollTimeout: ReturnType<typeof setTimeout> | null;
    /** True from the moment a poll loop starts until it stops; closes the race
     *  where onmessage and onclose(1013) could otherwise both start a loop. */
    _genesisPollActive: boolean;
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
    _pollGenesisStatus: (attempt?: number) => void;
    _stopGenesisPoll: () => void;
}

// ── Config ────────────────────────────────────────────────────────────────────

const WS_CONFIG = {
    MAX_RECONNECT_ATTEMPTS: 10,
    BASE_RECONNECT_DELAY_MS: 1_000,
    MAX_RECONNECT_DELAY_MS: 30_000,
    PING_INTERVAL_MS: 30_000,
    PONG_TIMEOUT_MS: 10_000,
    CONNECTION_TIMEOUT_MS: 10_000,
    MAX_HISTORY_SIZE: 100,
    /** Cap the dedup set so it doesn't grow forever */
    MAX_PROCESSED_IDS: 500,
    /**
     * BUG 3 FIX: minimum ms between connect() calls.
     * Prevents duplicate sockets when multiple callers race on a briefly-null _ws.
     */
    MIN_CONNECT_INTERVAL_MS: 1_000,
    /**
     * How often to poll GET /ws/genesis-status while waiting for the
     * background genesis task to finish. Much cheaper than retrying the
     * full WS handshake, so we can afford to check far more often than
     * the old 10s blind-retry loop.
     */
    GENESIS_POLL_INTERVAL_MS: 2_000,
    /** Safety cap so a stuck/failed genesis doesn't poll forever. */
    GENESIS_POLL_MAX_ATTEMPTS: 150, // 2s * 150 = 5 minutes
} as const;

// ── Store ─────────────────────────────────────────────────────────────────────

export const useWebSocketStore = create<WebSocketState>()((set, get) => ({
    // ── Initial state ──────────────────────────────────────────────────────
    isConnected: false,
    isConnecting: false,
    error: null,
    connectionStats: {
        reconnectAttempts: 0,
        lastPingTime: null,
        latencyMs: null,
    },
    lastMessage: null,
    unreadCount: 0,
    messageHistory: [],

    _ws: null,
    _reconnectTimeout: null,
    _pingInterval: null,
    _pongTimeout: null,
    _connectionTimeout: null,
    _reconnectAttempts: 0,
    _isManualDisconnect: false,
    _lastPingTime: null,
    _messageQueue: [],
    _processedIds: new Set<string>(),
    _activeToastId: null,
    _lastConnectTime: 0,       // BUG 3 FIX
    _genesisWaitingForApiKey: false,
    _genesisPollTimeout: null,
    _genesisPollActive: false,
    _connectionStable: false,   // BUG 2 FIX
    _lastMessageTimestamp: null,

    // ── Internal setters ───────────────────────────────────────────────────
    _setConnected: (connected) => set({ isConnected: connected }),
    _setConnecting: (connecting) => set({ isConnecting: connecting }),
    _setError: (error) => set({ error }),
    _updateStats: (stats) => set(s => ({ connectionStats: { ...s.connectionStats, ...stats } })),
    _setLastMessage: (message) => set({ lastMessage: message }),
    _incrementUnread: () => set(s => ({ unreadCount: s.unreadCount + 1 })),
    markAsRead: () => set({ unreadCount: 0 }),
    clearError: () => set({ error: null }),

    notifyApiKeyAdded: () => {
        // Clear the "waiting for API key" flag and immediately try to connect.
        // This is called by the Models page after a successful API key save,
        // which ensures chat becomes active without requiring a page reload.
        logger.debug('[WebSocket] API key added — re-attempting connection');
        set({ _genesisWaitingForApiKey: false });
        get().disconnect(true);
        setTimeout(() => get().connect(), 100);
    },

    /** Keep the dedup set bounded to MAX_PROCESSED_IDS */
    _trackProcessedId: (id: string) => {
        const ids = get()._processedIds;
        if (ids.size >= WS_CONFIG.MAX_PROCESSED_IDS) {
            const arr = Array.from(ids);
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
        if (s._reconnectTimeout) { clearTimeout(s._reconnectTimeout); set({ _reconnectTimeout: null }); }
        if (s._pingInterval) { clearInterval(s._pingInterval); set({ _pingInterval: null }); }
        if (s._pongTimeout) { clearTimeout(s._pongTimeout); set({ _pongTimeout: null }); }
        if (s._connectionTimeout) { clearTimeout(s._connectionTimeout); set({ _connectionTimeout: null }); }
        // NOTE: genesis-poll timer/flag are intentionally NOT cleared here.
        // The genesis poll is meant to outlive a closed socket (that's the
        // whole point — see _pollGenesisStatus). _clearAllTimers() used to
        // wipe _genesisPollActive too, which raced with onclose's 1013
        // handler: onmessage(system_not_ready) starts the poll and sets
        // _genesisPollActive=true, then onclose fires, calls this function
        // (wiping the flag back to false), then its own 1013 branch sees
        // _genesisPollActive=false and starts a SECOND, independent poll
        // loop — doubling requests to /ws/genesis-status every cycle, since
        // both events fire on every gated connection attempt, not just an
        // edge case. Use _stopGenesisPoll() explicitly wherever the genesis
        // wait should actually be cancelled (manual disconnect, a fresh
        // socket opening, or non-1013 closes).
    },

    /** Explicitly cancel any in-flight genesis-status poll loop. Kept
     *  separate from _clearAllTimers() so the poll can survive the 1013
     *  close it's specifically designed to outlive — see note above. */
    _stopGenesisPoll: () => {
        const s = get();
        if (s._genesisPollTimeout) { clearTimeout(s._genesisPollTimeout); set({ _genesisPollTimeout: null }); }
        if (s._genesisPollActive) { set({ _genesisPollActive: false }); }
    },

    _stopHeartbeat: () => {
        const s = get();
        if (s._pingInterval) { clearInterval(s._pingInterval); set({ _pingInterval: null }); }
        if (s._pongTimeout) { clearTimeout(s._pongTimeout); set({ _pongTimeout: null }); }
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
                logger.warn('[WebSocket] Pong timeout — scheduling reconnect with backoff');
                get()._setError('Connection lost (pong timeout)');
                get()._stopHeartbeat();
                // Cleanly close the socket without triggering the onclose
                // reconnect path (disconnect() nulls the handlers). The
                // reconnect is instead handled by _scheduleReconnect() below.
                const ws = get()._ws;
                if (ws) {
                    ws.onopen = null;
                    ws.onclose = null;
                    ws.onerror = null;
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
            logger.debug('[WebSocket] Connection stable — backoff counter reset');
            get()._fetchReplay();
        }
    },

    _fetchReplay: async () => {
        const since = get()._lastMessageTimestamp;
        if (!since) return;
        try {
            const events = await websocketReplayApi.fetchReplay(since);
            if (events.length > 0) {
                logger.debug(`[WebSocket] Replaying ${events.length} missed events`);
            }
            const ws = get()._ws;
            if (!ws || !ws.onmessage) return;

            events.forEach((ev: any) => {
                const syntheticEvent = new MessageEvent('message', {
                    data: JSON.stringify(ev)
                });
                ws.onmessage!.call(ws, syntheticEvent as any);
            });
        } catch (err) {
            logger.error('[WebSocket] Replay fetch failed:', err);
        }
    },

    // ── Genesis status polling ────────────────────────────────────────────
    // While genesis runs in the background, repeatedly retrying the full WS
    // handshake every 10s is slow and gives no real signal. Instead, poll a
    // cheap HTTP status endpoint every 2s and reconnect the instant it
    // reports "complete" — typically saves up to ~8s of dead waiting per
    // cycle, and removes the false impression that chat is "stuck".
    _pollGenesisStatus: (attempt: number = 0) => {
        // Avoid double-starting: onmessage (system_not_ready) and onclose
        // (code 1013) both call this as a safety net for each other in case
        // one of the two events doesn't fire. The flag is set synchronously
        // below, before any async work, so this check is race-free even
        // though the timer handle itself is only set later.
        if (attempt === 0) {
            if (get()._genesisPollActive) return;
            set({ _genesisPollActive: true });
        }

        if (attempt >= WS_CONFIG.GENESIS_POLL_MAX_ATTEMPTS) {
            logger.error('[WebSocket] Genesis poll exceeded max attempts — giving up');
            set({ _genesisPollActive: false });
            // Without this, isConnecting stays true forever (it's deliberately
            // kept true through the whole 1013 polling window — see onclose),
            // which hides the "Reconnect" button (gated on !isConnecting) and
            // leaves the user stuck on "Connecting…" with no way to retry short
            // of a full page refresh — the exact symptom this fix was meant to
            // eliminate, just for the genesis-stalled-or-failed case instead.
            get()._setConnecting(false);
            get()._setError(
                'System initialization is taking longer than expected. ' +
                'Please refresh or contact support if this persists.'
            );
            return;
        }

        const poll = async () => {
            try {
                const data = await websocketReplayApi.pollGenesisStatus();
                if (data.status === 'complete') {
                    logger.debug('[WebSocket] Genesis complete — reconnecting now');
                    get()._setError(null);
                    set({ _genesisPollTimeout: null, _genesisPollActive: false });
                    get().connect();
                    return;
                }
                if (data.status === 'not_started') {
                    // API key was removed/genesis hasn't started — stop polling
                    // and fall back to the silent waiting state.
                    set({ _genesisWaitingForApiKey: true, _genesisPollTimeout: null, _genesisPollActive: false });
                    get()._setError(null);
                    return;
                }
            } catch (err) {
                logger.warn('[WebSocket] Genesis status poll failed, will retry:', err);
            }

            // Still running (or transient fetch error) — poll again.
            const t = setTimeout(() => get()._pollGenesisStatus(attempt + 1), WS_CONFIG.GENESIS_POLL_INTERVAL_MS);
            set({ _genesisPollTimeout: t });
        };

        poll();
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
            logger.debug('[WebSocket] connect() suppressed — waiting for API key');
            return;
        }

        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING) return;
        if (s._ws?.readyState === WebSocket.OPEN) return;

        // BUG 3 FIX: reject calls that arrive within MIN_CONNECT_INTERVAL_MS
        // of the previous call. When _ws is momentarily null (between close and
        // reconnect timer), two callers (e.g. reconnect timer + effect re-run)
        // can both pass the readyState guards above and open duplicate sockets.
        const now = Date.now();
        if (now - s._lastConnectTime < WS_CONFIG.MIN_CONNECT_INTERVAL_MS) {
            logger.debug('[WebSocket] connect() called too soon — debounced');
            return;
        }
        set({ _lastConnectTime: now });

        get()._setConnecting(true);
        get()._setError(null);
        set({ _isManualDisconnect: false, _connectionStable: false });

        // NO token in URL — connect cleanly, send auth as first message
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

        logger.debug(`[WebSocket] Connecting to ${wsUrl} (attempt ${get()._reconnectAttempts + 1})`);

        try {
            const ws = new WebSocket(wsUrl);
            set({ _ws: ws });

            const connectionTimeout = setTimeout(() => {
                if (ws.readyState !== WebSocket.OPEN) {
                    logger.error('[WebSocket] Connection timeout');
                    ws.close();
                    get()._setError('Connection timeout');
                }
            }, WS_CONFIG.CONNECTION_TIMEOUT_MS);
            set({ _connectionTimeout: connectionTimeout });

            ws.onopen = () => {
                logger.debug('[WebSocket] ✅ Connected — sending auth handshake');
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
                                    type: 'message',
                                    content: msg.content,
                                    timestamp: new Date(msg.timestamp).toISOString(),
                                    attachments: msg.attachments,
                                }))
                            );
                            set({ _messageQueue: [] });
                        }
                        return;
                    }

                    if (data.type === 'auth_required') {
                        logger.warn('[WebSocket] Received auth_required — resending auth');
                        ws.send(JSON.stringify({ type: 'auth', token }));
                        return;
                    }

                    // genesis_triggered=false  → no API key saved yet, stay silent.
                    // genesis_triggered=true   → API key exists, genesis is running,
                    //                            show banner and poll genesis-status every 2s.
                    if (data.type === 'system_not_ready') {
                        const triggered = data.genesis_triggered as boolean | undefined;
                        // We are definitively not connected, but keep isConnecting true
                        // so the reconnect / initialization banner stays visible while
                        // the client polls for genesis completion.
                        get()._setConnected(false);

                        if (triggered) {
                            // API key saved, genesis running — surface status and poll
                            // the lightweight HTTP status endpoint every 2s instead of
                            // blindly retrying the full WS handshake every 10s. This
                            // reconnects within ~2s of genesis actually finishing instead
                            // of however much of the old 10s window was left.
                            logger.warn('[WebSocket] system_not_ready — genesis in progress, polling status every 2s');
                            set({ _genesisWaitingForApiKey: false });
                            get()._setError(
                                (data.content as string | undefined) ??
                                'System is initializing — this usually takes under a minute.'
                            );
                            get()._pollGenesisStatus();
                        } else {
                            // No API key yet — user hasn't triggered genesis.
                            // Set the waiting flag so connect() is a no-op until
                            // notifyApiKeyAdded() is called. Clear any error so
                            // no banner appears and no retry loop starts.
                            logger.warn('[WebSocket] system_not_ready — no API key configured yet, staying silent');
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
                    logger.error('[WebSocket] Failed to parse message:', e);
                }
            };

            ws.onerror = (event) => {
                logger.error('[WebSocket] Error:', event);
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
                        get()._stopGenesisPoll();
                        break;
                    case 1000:
                        get()._setConnecting(false);
                        get()._stopGenesisPoll();
                        break; // clean close
                    case 1006:
                        errorMsg = 'Connection lost unexpectedly';
                        get()._setConnecting(false);
                        get()._stopGenesisPoll();
                        break;
                    case 1013:
                        // onmessage normally already started polling via
                        // _pollGenesisStatus() (which sets _genesisPollActive=true
                        // synchronously). _clearAllTimers() above no longer touches
                        // that flag/timer — it used to, which raced with this branch:
                        // onmessage starts the poll, _clearAllTimers() here wiped the
                        // flag back to false, and this branch then started a SECOND
                        // independent poll loop every single cycle (both events fire
                        // on every gated attempt, not just an edge case), doubling
                        // requests to /ws/genesis-status. Now the guard inside
                        // _pollGenesisStatus() correctly no-ops here when onmessage
                        // already started it, and only takes over if onmessage never
                        // ran (e.g. the message was lost before delivery).
                        if (!get()._genesisWaitingForApiKey) {
                            if (!get().error) {
                                get()._setError('System is initializing — this usually takes under a minute.');
                            }
                            get()._pollGenesisStatus();
                        } else {
                            get()._stopGenesisPoll();
                        }
                        // Keep isConnecting true so the reconnect/init banner
                        // stays visible while we poll genesis-status every 2s.
                        break;
                    default:
                        errorMsg = `Connection closed (${event.code})`;
                        get()._setConnecting(false);
                        get()._stopGenesisPoll();
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
            logger.error('[WebSocket] Failed to create connection:', err);
            get()._setError('Failed to create WebSocket connection');
            get()._setConnecting(false);
        }
    },

    // ── Disconnect ─────────────────────────────────────────────────────────
    disconnect: (isManual = false) => {
        const s = get();
        set({ _isManualDisconnect: isManual, _connectionStable: false });
        get()._clearAllTimers();
        get()._stopGenesisPoll();

        if (s._ws) {
            s._ws.onopen = null;
            s._ws.onclose = null;
            s._ws.onerror = null;
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
        logger.debug('[WebSocket] Manual reconnect triggered');
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
                    type: 'message',
                    content: content.trim(),
                    timestamp: new Date().toISOString(),
                    attachments: attachments && attachments.length > 0 ? attachments : undefined,
                }));
                return true;
            } catch (e) {
                logger.error('[WebSocket] Send error:', e);
                return false;
            }
        }
        logger.warn('[WebSocket] Not connected — queuing message');
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