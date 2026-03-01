/**
 * voiceBridge.ts — Browser WebSocket client for the Agentium host-native voice bridge.
 *
 * Connects to the local bridge process running on the host at ws://127.0.0.1:9999.
 * Emits VoiceInteractionEvents so ChatPage can append voice exchanges to chat history.
 *
 * All errors are caught internally; the rest of the app is never affected.
 */

import toast from 'react-hot-toast';

// ── Types ─────────────────────────────────────────────────────────────────────

export type BridgeStatus = 'offline' | 'connecting' | 'connected' | 'error';

export interface VoiceInteractionEvent {
  user:  string;   // what the user said
  reply: string;   // what the Head of Council replied
  ts:    number;   // unix timestamp
}

type InteractionHandler = (event: VoiceInteractionEvent) => void;

// ── Config ─────────────────────────────────────────────────────────────────────

const WS_URL       = 'ws://127.0.0.1:9999';
const MAX_RETRIES  = 5;
const RETRY_DELAYS = [1000, 2000, 4000, 8000, 15000]; // ms, per attempt

// ── VoiceBridgeService ────────────────────────────────────────────────────────

class VoiceBridgeService {
  private ws:           WebSocket | null = null;
  private retryCount    = 0;
  private retryTimer:   ReturnType<typeof setTimeout> | null = null;
  private handlers      = new Set<InteractionHandler>();
  private statusListeners = new Set<(s: BridgeStatus) => void>();

  status: BridgeStatus = 'offline';

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Fetch a voice token from the backend then open the WS connection. */
  async connect(): Promise<void> {
    if (this.status === 'connecting' || this.status === 'connected') return;

    this._setStatus('connecting');

    let token: string | null = null;
    try {
      token = await this._fetchVoiceToken();
    } catch (err) {
      console.warn('[voiceBridge] Could not fetch voice token:', err);
      toast.error('Voice bridge: failed to get token — running in text mode');
      this._setStatus('error');
      return;
    }

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

  // ── Private ─────────────────────────────────────────────────────────────────

  private async _fetchVoiceToken(): Promise<string> {
    const res = await fetch('/api/v1/auth/voice-token', {
      method:  'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${this._getSessionToken()}`,
      },
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    }

    const data = await res.json();
    return data.voice_token as string;
  }

  private _getSessionToken(): string {
    // Reads from localStorage where authStore persists the JWT
    try {
      const raw = localStorage.getItem('auth-storage');
      if (raw) {
        const parsed = JSON.parse(raw);
        return parsed?.state?.token ?? '';
      }
    } catch {
      // ignore
    }
    return '';
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
        }
      } catch (e) {
        console.warn('[voiceBridge] Invalid message from bridge:', e);
      }
    };

    this.ws.onerror = (evt) => {
      console.warn('[voiceBridge] WebSocket error', evt);
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (this.status === 'offline') return; // intentional disconnect

      if (this.retryCount < MAX_RETRIES) {
        const delay = RETRY_DELAYS[this.retryCount] ?? 15000;
        this.retryCount++;
        console.info(`[voiceBridge] Reconnecting in ${delay}ms (attempt ${this.retryCount}/${MAX_RETRIES})`);
        this._setStatus('connecting');
        this.retryTimer = setTimeout(() => this._openSocket(token), delay);
      } else {
        console.warn('[voiceBridge] Max reconnect attempts reached — going offline');
        toast.error('Voice bridge disconnected — text chat unaffected');
        this._setStatus('offline');
      }
    };
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