/**
 * websocketStore.ts
 *
 */

import { create } from 'zustand';
import { showToast } from '@/hooks/useToast';
import { websocketReplayApi } from '@/services/websocketReplay';
import { logger } from '@/utils/logger';
import type { StructuredInputAnswer } from '../types/structuredInput';
import {
  ConnectionPhase, PhaseEvent, nextPhase,
  isActive, isConnectingPhase, canReconnect, isGenesisProgress, phaseFromGenesisStatus,
} from './connectionPhase';

/**
 * A Head of Council message should only bump the unread counter (and raise a
 * toast) when the user is NOT on the chat page. The chat page clears the
 * counter on entry and shows new messages inline, so counting them there would
 * re-show a badge for a conversation the user is actively viewing.
 */
export function isHeadMessageUnreadEligible(pathname: string): boolean {
    return pathname !== '/chat';
}

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
    /** Single source of truth for connection/genesis status. */
    connectionPhase: ConnectionPhase;
    /** Derived from connectionPhase (functions in the store body). */
    isConnected: () => boolean;
    isConnecting: () => boolean;
    error: string | null;
    connectionStats: {
        reconnectAttempts: number;
        lastPingTime: string | null;
        latencyMs: number | null;
    };
    lastMessage: WebSocketMessage | null;
    unreadCount: number;
    messageHistory: WebSocketMessage[];
    /** True while genesis is paused waiting for the user to name their nation. */
    genesisAwaitingName: boolean;
    /** Prompt text surfaced with the awaiting-name request. */
    genesisNamePrompt: string;
    /** Seconds the user has to respond to the awaiting-name request. */
    genesisNameTimeout: number;
    /**
     * Timestamp (ms) of the last API key save. Bumped by `notifyApiKeyAdded()`
     * so dashboard widgets (e.g. Provider Analytics) can auto-refresh without a
     * manual button click when providers become available.
     */
    apiKeyAddedAt: number | null;

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
    /** Consecutive not_started poll responses while genesis_running (P5 grace). */
    _genesisGraceCount: number;
    /**
     * poll while genesis runs in the background. Cleared on disconnect/unmount
     * so polling never outlives the component.
     */
    _genesisPollTimeout: ReturnType<typeof setTimeout> | null;
    /** Consecutive not_started poll responses while genesis_running (P5 grace). */
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

    /**
     * Submit the user's chosen nation name while genesis is paused for it.
     * Resolves true when the backend accepts the name (clearing the awaiting
     * flag), false when rejected or on error.
     */
    submitCountryName: (name: string) => Promise<boolean>;

    // Internal actions
    _transition: (event: PhaseEvent) => void;
    _connectNow: () => void;
    _genesisWatchdog: () => void;
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
    _openSocket: () => void;
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
    connectionPhase: 'offline',
    error: null,
    connectionStats: {
        reconnectAttempts: 0,
        lastPingTime: null,
        latencyMs: null,
    },
    lastMessage: null,
    unreadCount: 0,
    messageHistory: [],
    apiKeyAddedAt: null,

    genesisAwaitingName: false,
    genesisNamePrompt: '',
    genesisNameTimeout: 0,

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
    _genesisPollTimeout: null,
    _genesisGraceCount: 0,
    _connectionStable: false,   // BUG 2 FIX
    _lastMessageTimestamp: null,

    // ── Derived helpers (Spec §1: status derives from connectionPhase) ─────
    isConnected: () => get().connectionPhase === 'active',
    isConnecting: () => get().connectionPhase === 'connecting',

    _transition: (event) => {
        const cur = get().connectionPhase;
        const next = nextPhase(cur, event, { graceCount: get()._genesisGraceCount });
        if (next === cur) {
            // Staying in genesis_running: accumulate grace only on not_started.
            if (cur === 'genesis_running' && event.type === 'poll' && event.status === 'not_started') {
                set({ _genesisGraceCount: get()._genesisGraceCount + 1 });
            }
            return; // keep existing graceCount for 'running'
        }
        set({ connectionPhase: next, _genesisGraceCount: 0 });
    },

    _connectNow: () => {
        // P1: bypass the MIN_CONNECT_INTERVAL_MS debounce used by public connect().
        const s = get();
        if (s._ws?.readyState === WebSocket.CONNECTING || s._ws?.readyState === WebSocket.OPEN) return;
        set({ connectionPhase: 'connecting', _isManualDisconnect: false, _connectionStable: false });
        get()._openSocket();
    },
    _setError: (error) => set({ error }),
    _updateStats: (stats) => set(s => ({ connectionStats: { ...s.connectionStats, ...stats } })),
    _setLastMessage: (message) => set({ lastMessage: message }),
    _incrementUnread: () => set(s => ({ unreadCount: s.unreadCount + 1 })),
    markAsRead: () => set({ unreadCount: 0 }),
    clearError: () => set({ error: null }),

    notifyApiKeyAdded: () => {
        // Leave the silent "waiting_for_key" state and immediately try to connect.
        // This is called by the Models page after a successful API key save,
        // which ensures chat becomes active without requiring a page reload.
        logger.debug('[WebSocket] API key added — re-attempting connection');
        // Bump the timestamp so subscribers (e.g. Provider Analytics) can
        // auto-refresh without a manual button click.
        set({ apiKeyAddedAt: Date.now() });
        get().disconnect(true);
        setTimeout(() => {
            get()._transition({ type: 'notify_key_added' });
            get().connect();
        }, 100);
    },

    submitCountryName: async (name: string): Promise<boolean> => {
        try {
            const res = await websocketReplayApi.submitCountryName(name);
            if (res.accepted) {
                set({ genesisAwaitingName: false, genesisNamePrompt: '', genesisNameTimeout: 0 });
                return true;
            }
            return false;
        } catch (err) {
            logger.error('[WebSocket] submitCountryName failed:', err);
            return false;
        }
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
        // NOTE: the genesis-status poll timer is intentionally NOT cleared here.
        // The poll is meant to outlive a closed socket (that's the whole point —
        // see _pollGenesisStatus). Use _stopGenesisPoll() explicitly wherever the
        // genesis wait should actually be cancelled (manual disconnect or
        // non-1013 closes).
    },

    /** Explicitly cancel any in-flight genesis-status poll loop. Kept
     *  separate from _clearAllTimers() so the poll can survive the 1013
     *  close it's specifically designed to outlive — see note above. */
    _stopGenesisPoll: () => {
        const s = get();
        if (s._genesisPollTimeout) { clearTimeout(s._genesisPollTimeout); set({ _genesisPollTimeout: null }); }
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
                set({ _ws: null, _connectionStable: false, connectionPhase: 'offline' });
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
        if (attempt >= WS_CONFIG.GENESIS_POLL_MAX_ATTEMPTS) {
            logger.error('[WebSocket] Genesis poll exceeded max attempts — giving up');
            // No escape via the poll loop anymore — surface a real error and
            // move to a reconnectable terminal phase so the user can retry.
            get()._setError(
                'System initialization is taking longer than expected. ' +
                'Please refresh or contact support if this persists.'
            );
            set({ _genesisPollTimeout: null, connectionPhase: 'genesis_failed', _genesisGraceCount: 0 });
            return;
        }

        const poll = async () => {
            try {
                const data = await websocketReplayApi.pollGenesisStatus();

                // Surface the nation-name prompt while genesis is paused for it.
                if (data.status === 'awaiting_name') {
                    set({
                        genesisAwaitingName: true,
                        genesisNamePrompt: data.prompt ?? '',
                        genesisNameTimeout: data.timeout_seconds ?? 60,
                    });
                } else if (get().genesisAwaitingName) {
                    set({ genesisAwaitingName: false, genesisNamePrompt: '', genesisNameTimeout: 0 });
                }

                const nextPhase = phaseFromGenesisStatus(data.status);
                set({ _genesisPollTimeout: null });

                if (nextPhase === 'connecting') {
                    set({ _genesisGraceCount: 0 });
                    logger.debug('[WebSocket] Genesis complete — reconnecting now (debounce-exempt)');
                    get()._setError(null);
                    // P1: use _connectNow so a 1s debounce can't swallow the only reconnect.
                    get()._connectNow();
                    // P7: watchdog — if we're still not active shortly, retry.
                    get()._genesisWatchdog();
                    return;
                }
                if (nextPhase === 'genesis_failed') {
                    set({ _genesisGraceCount: 0 });
                    // P9: backend reported failure — surface it instead of polling forever.
                    const reason = (data as any).reason as string | undefined;
                    logger.error('[WebSocket] Genesis failed:', reason);
                    get()._transition({ type: 'poll', status: 'failed' });
                    get()._setError(reason
                        ? `Genesis failed: ${reason}`
                        : 'Genesis failed. Please check your API key and try again.');
                    return;
                }
                // running or not_started (grace handled inside _transition)
                get()._transition({ type: 'poll', status: data.status });
            } catch (err) {
                logger.warn('[WebSocket] Genesis status poll failed, will retry:', err);
                get()._transition({ type: 'poll', status: 'running' });
            }

            // Still running (or transient fetch error) — poll again.
            const t = setTimeout(() => get()._pollGenesisStatus(attempt + 1), WS_CONFIG.GENESIS_POLL_INTERVAL_MS);
            set({ _genesisPollTimeout: t });
        };

        poll();
    },

    _genesisWatchdog: () => {
        // P7: if the poll-complete reconnect didn't reach 'active' within 5s,
        // retry once. Prevents a single swallowed connect() from dead-ending.
        setTimeout(() => {
            const phase = get().connectionPhase;
            if (phase === 'genesis_running' || phase === 'connecting') {
                logger.warn('[WebSocket] Genesis watchdog — reconnect did not settle, retrying');
                get()._connectNow();
                get()._genesisWatchdog();
            }
        }, 5000);
    },

    // ── Connect ────────────────────────────────────────────────────────────
    connect: () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            get()._setError('No access token — please login');
            set({ connectionPhase: 'genesis_failed' });
            return;
        }

        // Silent wait: stay put until notifyApiKeyAdded() (Spec §1, P3 escape).
        if (get().connectionPhase === 'waiting_for_key') {
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
        set({ connectionPhase: 'connecting', _isManualDisconnect: false, _connectionStable: false });
        get()._openSocket();
    },

    _openSocket: () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            get()._setError('No access token — please login');
            set({ connectionPhase: 'genesis_failed' });
            return;
        }

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
                        // BUG 2 FIX: do NOT reset _reconnectAttempts here.
                        // We only reset it after the first successful pong
                        // round-trip (in _handlePong), which confirms the
                        // connection is genuinely stable. Resetting here caused
                        // the backoff to restart from 2 s on every reconnect.
                        get()._transition({ type: 'system' });
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
                    //                            poll genesis-status every 2s (P8: no
                    //                            red error — progress is its own state).
                    if (data.type === 'system_not_ready') {
                        const triggered = data.genesis_triggered as boolean | undefined;
                        if (triggered) {
                            logger.warn('[WebSocket] system_not_ready — genesis in progress, polling status every 2s');
                            get()._transition({ type: 'system_not_ready', genesisTriggered: true });
                            get()._pollGenesisStatus();
                        } else {
                            logger.warn('[WebSocket] system_not_ready — no API key configured yet, staying silent');
                            get()._transition({ type: 'system_not_ready', genesisTriggered: false });
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
                        // Only count as unread / toast when the user is NOT on the
                        // chat page — the chat page clears the counter on entry and
                        // shows new messages inline, so counting them there would
                        // re-show a badge for a conversation already being viewed.
                        if (isHeadMessageUnreadEligible(window.location.pathname)) {
                            get()._incrementUnread();
                            const existingToastId = get()._activeToastId;
                            if (existingToastId) showToast.dismiss(existingToastId);
                            // The global card hook shows a distinct, actionable
                            // question toast for cards; don't also fire the generic
                            // "New message" toast on top of it.
                            if (!data.metadata || !data.metadata.card) {
                                const toastId = showToast.success('New message from Head of Council');
                                set({ _activeToastId: toastId });
                            }
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
                set({ _ws: null, _connectionStable: false });

                let errorMsg: string | null = null;
                const code = event.code;
                if (code === 4001) {
                    errorMsg = 'Authentication failed — please log in again';
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                } else if (code === 1000 || code === 1006) {
                    if (code === 1006) errorMsg = 'Connection lost unexpectedly';
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                } else if (code === 1013) {
                    // Genesis poll owns reconnect; keep genesis_running.
                    get()._transition({ type: 'socket_close', code });
                    if (get().connectionPhase === 'genesis_running') {
                        get()._pollGenesisStatus();
                    }
                } else {
                    errorMsg = `Connection closed (${event.code})`;
                    get()._transition({ type: 'socket_close', code });
                    get()._stopGenesisPoll();
                }
                if (errorMsg) get()._setError(errorMsg);

                const isManual = get()._isManualDisconnect;
                if (!isManual && code !== 4001 && code !== 1013) {
                    // BUG 1 FIX: use the shared _scheduleReconnect() which
                    // applies exponential backoff.
                    get()._scheduleReconnect();
                }
            };

        } catch (err) {
            logger.error('[WebSocket] Failed to create connection:', err);
            get()._setError('Failed to create WebSocket connection');
            set({ connectionPhase: 'offline' });
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

        set({ connectionPhase: 'offline' });
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

/**
 * Submit a structured input card answer over the WebSocket.
 * Sends a `type: 'message'` frame with empty content plus a `card_response`
 * payload. The backend (api/routes/websocket.py) reads `card_response` and
 * persists it on the sovereign message (Task 4).
 */
export function submitCardAnswer(answer: StructuredInputAnswer): boolean {
    const s = useWebSocketStore.getState();
    if (s._ws?.readyState === WebSocket.OPEN) {
        try {
            s._ws.send(JSON.stringify({
                type: 'message',
                content: '',
                timestamp: new Date().toISOString(),
                attachments: [],
                card_response: answer,
            }));
            return true;
        } catch (e) {
            logger.error('[WebSocket] submitCardAnswer error:', e);
            return false;
        }
    }
    logger.warn('[WebSocket] Not connected — cannot submit card answer');
    return false;
}

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