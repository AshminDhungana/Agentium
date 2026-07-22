/**
 * voiceBridge.ts — Browser WebSocket client for the Agentium host-native voice bridge.
 *
 * Connects to the local bridge process running on the host at ws://127.0.0.1:9999.
 * Emits VoiceInteractionEvents so ChatPage can append voice exchanges to chat history.
 *
 *
 */

import { api } from './api';

// ── Types ─────────────────────────────────────────────────────────────────────

export type ConnectionErrorStage = 'token-fetch' | 'socket-open' | 'token-rejected' | 'unknown';

export interface ConnectionError {
  stage: ConnectionErrorStage;
  message: string;
  statusCode?: number;
  lastAttempt: number;
}

export type BridgeStatus = 'offline' | 'connecting' | 'connected' | 'error';

// Live agent state broadcast by the bridge (Jarvis upgrade, Phase H): the tab
// can show a live indicator instead of only the after-the-fact transcript.
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted';

export interface VoiceInteractionEvent {
  user:  string;   // what the user said
  reply: string;   // what the Head of Council replied
  ts:    number;   // unix timestamp
}

export interface TranscriptEvent {
  role: 'user' | 'agent';
  text: string;
  ts: number;
}

type InteractionHandler = (event: VoiceInteractionEvent) => void;
type StateHandler = (s: VoiceState) => void;
type TranscriptHandler = (event: TranscriptEvent) => void;

// ── Config ─────────────────────────────────────────────────────────────────────

const WS_URL       = 'ws://127.0.0.1:9999';
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 15000]; // ms, base delay per attempt (before jitter)

// Token-fetch retries (backend may not be up at install time)
const TOKEN_RETRIES    = 8;
const TOKEN_BASE_DELAY = 2000; // ms, doubles each attempt: 2s, 4s, 8s, …, ~4min

/**
 * R4: apply ±20% jitter to a base delay so multiple tabs reconnecting after
 * the same bridge restart don't all retry at exactly the same instant.
 */
function withJitter(baseDelayMs: number): number {
  const jitterFactor = 0.8 + Math.random() * 0.4; // 0.8x .. 1.2x
  return Math.round(baseDelayMs * jitterFactor);
}

// ── VoiceBridgeService ────────────────────────────────────────────────────────

class VoiceBridgeService {
  private ws:           WebSocket | null = null;
  private retryCount    = 0;
  private retryTimer:   ReturnType<typeof setTimeout> | null = null;
  private handlers      = new Set<InteractionHandler>();
  private statusListeners = new Set<(s: BridgeStatus) => void>();
  private stateListeners = new Set<StateHandler>();
  private transcriptHandlers = new Set<TranscriptHandler>();
  private voiceToken:   string | null = null;
  private tokenRetryCount = 0;
  private tokenRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private _connectionError: ConnectionError | null = null;
  private _errorListeners: Array<(err: ConnectionError | null) => void> = [];

  status: BridgeStatus = 'offline';

  get connectionError(): ConnectionError | null {
    return this._connectionError;
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Fetch a voice token from the backend then open the WS connection. */
  async connect(): Promise<void> {
    if (this.status === 'connecting' || this.status === 'connected') return;

    this.retryCount = 0;
    this.tokenRetryCount = 0;
    this._setStatus('connecting');

    this._retryTokenFetch();
  }

  /**
   * Retry fetching a voice token with exponential backoff.
   * No warnings/notifications until connected — the bridge silently retries
   * so post-install startup backends aren't spammed with console noise.
   */
  private async _retryTokenFetch(): Promise<void> {
    try {
      const token = await this._fetchVoiceToken();
      // Success — clear retry state and open the socket.
      this._clearTokenRetry();
      this.tokenRetryCount = 0;
      this.voiceToken = token;
      this._openSocket(token);
      return;
    } catch (err) {
      const errMsg = String(err);
      const errStatus = (err as any)?.response?.status as number | undefined;

      this._setConnectionError({
        stage: 'token-fetch',
        message: err instanceof Error ? err.message : errMsg,
        statusCode: errStatus,
        lastAttempt: Date.now(),
      });

      // Non-transient errors: give up immediately.
      if (errMsg.includes('HTTP 404')) {
        this._clearTokenRetry();
        this._setStatus('offline');
        return;
      }

      // Transient errors (network, 503, etc) — retry with backoff.
      const isLastAttempt = this.tokenRetryCount >= TOKEN_RETRIES;
      if (!isLastAttempt) {
        const delay = TOKEN_BASE_DELAY * Math.pow(2, this.tokenRetryCount);
        this.tokenRetryCount++;
        this.tokenRetryTimer = setTimeout(() => this._retryTokenFetch(), delay);
        return;
      }

      // All retries exhausted — give up silently.
      this._clearTokenRetry();
      this.tokenRetryCount = 0;
      this._setStatus('offline');
    }
  }

  private _clearTokenRetry(): void {
    if (this.tokenRetryTimer) {
      clearTimeout(this.tokenRetryTimer);
      this.tokenRetryTimer = null;
    }
  }

  private _setConnectionError(err: ConnectionError | null): void {
    this._connectionError = err;
    for (const listener of this._errorListeners) {
      try { listener(err); } catch { /* ignore */ }
    }
  }

  disconnect(): void {
    this._clearRetry();
    this._clearTokenRetry();
    this.ws?.close();
    this.ws = null;
    this._setStatus('offline');
  }

  onInteraction(handler: InteractionHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  onStatusChange(listener: (s: BridgeStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  onStateChange(listener: (s: VoiceState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  onTranscript(handler: TranscriptHandler): () => void {
    this.transcriptHandlers.add(handler);
    return () => this.transcriptHandlers.delete(handler);
  }

  onErrorChange(listener: (err: ConnectionError | null) => void): () => void {
    this._errorListeners.push(listener);
    return () => {
      this._errorListeners = this._errorListeners.filter(l => l !== listener);
    };
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  private async _fetchVoiceToken(): Promise<string> {
    const { data } = await api.post<{ voice_token: string }>('/api/v1/auth/voice-token');
    return data.voice_token;
  }

  /**
   * B3: reads the JWT from the single key the rest of the app actually uses.
   * Confirmed against auth.ts (authService.login/logout/getToken/initAuth)
   * and api.ts's request interceptor — both read/write 'access_token'
   * directly. There is no 'auth-storage' Zustand-persist key anywhere in
   * this app; the previous fallback parse of that key was dead code that
   * could only ever return ''.
   */
  private _getSessionToken(): string {
    try {
      return localStorage.getItem('access_token') ?? '';
    } catch {
      // localStorage unavailable (e.g. private browsing edge cases) — treat
      // as no token rather than throwing.
      return '';
    }
  }

  private _openSocket(token: string): void {
    try {
      const url = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
      this.ws = new WebSocket(url);
    } catch (err) {
      console.warn('[voiceBridge] WebSocket constructor failed:', err);
      this._setStatus('error');
      return;
    }

    this.ws.onopen = () => {
      console.info('[voiceBridge] Connected to bridge at', WS_URL);
      this.retryCount = 0;
      this._setConnectionError(null);
      this._setStatus('connected');
      this._pushHostToken();
    };

    this.ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string);
        if (msg?.type === 'voice_interaction') {
          const event: VoiceInteractionEvent = {
            user:  msg.user  ?? '',
            reply: msg.reply ?? '',
            ts:    msg.ts    ?? Date.now() / 1000,
          };
          this.handlers.forEach((h) => {
            try { h(event); } catch (e) { console.warn('[voiceBridge] handler error:', e); }
          });
        } else if (msg?.type === 'voice_state' && msg.state) {
          const state = msg.state as VoiceState;
          this.stateListeners.forEach((h) => {
            try { h(state); } catch (e) { console.warn('[voiceBridge] state handler error:', e); }
          });
        } else if (msg?.type === 'transcript' && msg.text && msg.role) {
          const event: TranscriptEvent = {
            role: msg.role,
            text: msg.text,
            ts:   msg.ts ?? Date.now() / 1000,
          };
          this.transcriptHandlers.forEach((h) => {
            try { h(event); } catch (e) { console.warn('[voiceBridge] transcript handler error:', e); }
          });
        }
      } catch (e) {
        console.warn('[voiceBridge] Invalid message from bridge:', e);
      }
    };

    this.ws.onerror = () => {
      const readyState = this.ws ? this.ws.readyState : 'unknown';
      const stateLabel =
        readyState === WebSocket.CONNECTING ? 'CONNECTING'
        : readyState === WebSocket.OPEN ? 'OPEN'
        : readyState === WebSocket.CLOSING ? 'CLOSING'
        : readyState === WebSocket.CLOSED ? 'CLOSED'
        : String(readyState);
      console.warn(
        `[voiceBridge] WebSocket error (state=${stateLabel}). ` +
        `Likely causes: bridge process not running on ${WS_URL} (connection refused), ` +
        `invalid/expired token (auth rejected), or network timeout.`,
      );
      this._setConnectionError({
        stage: 'socket-open',
        message: `Bridge at ${WS_URL} unreachable (state=${stateLabel})`,
        lastAttempt: Date.now(),
      });
    };

    this.ws.onclose = (closeEvt) => {
      this.ws = null;

      if (closeEvt?.code === 1008) {
        console.warn('[voiceBridge] Bridge rejected token — reconnecting without one');
        this._setConnectionError({
          stage: 'token-rejected',
          message: 'Bridge rejected the voice token (code 1008)',
          lastAttempt: Date.now(),
        });
      }

      if (this.status === 'offline') return; // intentional disconnect

      if (this.retryCount < RETRY_DELAYS.length) {
        // R4: jitter applied so multiple tabs don't reconnect in lockstep
        // after the host bridge restarts.
        const baseDelay = RETRY_DELAYS[this.retryCount] ?? 15000;
        const delay = withJitter(baseDelay);
        this.retryCount++;
        console.info(`[voiceBridge] Reconnecting in ${delay}ms (attempt ${this.retryCount}/${RETRY_DELAYS.length})`);
        this._setStatus('connecting');
        // Use empty token on reconnect — the bridge accepts connections
        // without a token, and _pushHostToken will set it after connecting.
        this.retryTimer = setTimeout(() => this._openSocket(''), delay);
      } else {
        console.warn('[voiceBridge] Max reconnect attempts reached — going offline');
        // The bottom-left install notification (VoiceIndicator) already
        // surfaces the offline state, so no duplicate top-right toast here.
        this._setStatus('offline');
      }
    };
  }

  /**
   * Push a backend-issued voice token to the host bridge over the local WS so
   * it can authenticate to the backend without a browser session.  Prefers the
   * long-lived admin host token; falls back to the session voice token (which
   * keeps voice working only while this browser is open).
   */
  private async _pushHostToken(): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    let token: string | null = null;
    try {
      const { data } = await api.post<{ voice_token: string }>('/api/v1/auth/voice-token/host');
      token = data.voice_token;
    } catch {
      // Non-admin or endpoint unavailable — use the session voice token.
      token = this.voiceToken;
    }
    if (token) {
      // Guard: the WebSocket may have closed during the async HTTP call
      // above. onclose nulls this.ws, so check before calling send().
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try {
        this.ws.send(JSON.stringify({ type: 'set_token', token }));
        console.info('[voiceBridge] Pushed voice token to host bridge');
      } catch (e) {
        console.warn('[voiceBridge] Failed to push token to bridge:', e);
      }
    }
  }

  private _clearRetry(): void {
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }

  private _setStatus(s: BridgeStatus): void {
    this.status = s;
    this.statusListeners.forEach((l) => {
      try { l(s); } catch { /* ignore */ }
    });
  }
}

// ── Singleton export ──────────────────────────────────────────────────────────

export const voiceBridgeService = new VoiceBridgeService();