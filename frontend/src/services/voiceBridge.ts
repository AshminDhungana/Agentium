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

export type BridgeStatus = 'offline' | 'connecting' | 'connected' | 'error';

// Live agent state broadcast by the bridge (Jarvis upgrade, Phase H): the tab
// can show a live indicator instead of only the after-the-fact transcript.
export type VoiceState = 'listening' | 'thinking' | 'speaking' | 'interrupted';

export interface VoiceInteractionEvent {
  user:  string;   // what the user said
  reply: string;   // what the Head of Council replied
  ts:    number;   // unix timestamp
}

type InteractionHandler = (event: VoiceInteractionEvent) => void;
type StateHandler = (s: VoiceState) => void;

// ── Config ─────────────────────────────────────────────────────────────────────

const WS_URL       = 'ws://127.0.0.1:9999';
const MAX_RETRIES  = 5;
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 15000]; // ms, base delay per attempt (before jitter)

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
  private voiceToken:   string | null = null;

  status: BridgeStatus = 'offline';

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Fetch a voice token from the backend then open the WS connection. */
  async connect(): Promise<void> {
    if (this.status === 'connecting' || this.status === 'connected') return;

    // Fresh connection attempt — reset the retry budget and the one-shot
    // disconnect toast guard so a new attempt re-arms both. Without this,
    // a manual reconnect (or re-mount) after the first failed sequence
    // would see retryCount already at MAX_RETRIES and re-fire the toast
    // instantly on every connect() call.
    this.retryCount = 0;
    this._setStatus('connecting');

    let token: string | null = null;
    try {
      token = await this._fetchVoiceToken();
    } catch (err) {
      const errMsg = String(err);

      if (errMsg.includes('HTTP 404')) {
        // Endpoint not registered — VOICE_JWT_SECRET not configured server-side.
        // This is a deployment config issue, not a user-actionable error.
        console.warn('[voiceBridge] Voice token endpoint not found — VOICE_JWT_SECRET may not be configured');
        this._setStatus('offline');
        return;
      }

      if (err instanceof TypeError) {
        // fetch() network failure — backend unreachable or CORS issue.
        console.warn('[voiceBridge] Network error fetching voice token:', err);
        this._setStatus('offline');
        return;
      }

      // Any other error (401, 503, parse failure) — surface to the user.
      console.warn('[voiceBridge] Could not fetch voice token:', err);
      this._setStatus('error');
      return;
    }

    this.voiceToken = token;
    this._openSocket(token);
  }

  disconnect(): void {
    this._clearRetry();
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
      this._setStatus('connected');
      // Deliver a long-lived host token to the bridge so it can authenticate
      // to the backend even after this browser session is closed.
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
          // Live indicator: listening / thinking / speaking / interrupted.
          const state = msg.state as VoiceState;
          this.stateListeners.forEach((h) => {
            try { h(state); } catch (e) { console.warn('[voiceBridge] state handler error:', e); }
          });
        }
      } catch (e) {
        console.warn('[voiceBridge] Invalid message from bridge:', e);
      }
    };

    this.ws.onerror = (evt) => {
      // The native WebSocket error event carries no detail; surface what we
      // can so "connection refused" vs "auth rejected" vs "timeout" is at
      // least distinguishable in the console instead of a bare Event object.
      const ws = this.ws;
      const readyState = ws ? ws.readyState : 'unknown';
      const stateLabel =
        readyState === WebSocket.CONNECTING ? 'CONNECTING'
        : readyState === WebSocket.OPEN ? 'OPEN'
        : readyState === WebSocket.CLOSING ? 'CLOSING'
        : readyState === WebSocket.CLOSED ? 'CLOSED'
        : String(readyState);
      console.warn(
        `[voiceBridge] WebSocket error (state=${stateLabel}). ` +
        `Likely causes: bridge process not running on ${WS_URL} (connection refused), ` +
        `invalid/expired token (auth rejected), or network timeout. ` +
        `Raw event:`, evt,
      );
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (this.status === 'offline') return; // intentional disconnect

      if (this.retryCount < MAX_RETRIES) {
        // R4: jitter applied so multiple tabs don't reconnect in lockstep
        // after the host bridge restarts.
        const baseDelay = RETRY_DELAYS[this.retryCount] ?? 15000;
        const delay = withJitter(baseDelay);
        this.retryCount++;
        console.info(`[voiceBridge] Reconnecting in ${delay}ms (attempt ${this.retryCount}/${MAX_RETRIES})`);
        this._setStatus('connecting');
        this.retryTimer = setTimeout(() => this._openSocket(token), delay);
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