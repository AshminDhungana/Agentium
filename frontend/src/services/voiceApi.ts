/**
 * voiceApi.ts — Voice feature API service
 *
 * Covers:
 *  - GET  /api/v1/voice/status          (existing)
 *  - GET  /api/v1/voice/enhanced-status (NEW)
 *  - POST /api/v1/voice/transcribe      (existing)
 *  - POST /api/v1/voice/synthesize      (existing)
 *  - GET  /api/v1/voice/voices          (existing)
 *  - GET  /api/v1/voice/languages       (existing)
 */

import { api } from './api';
import { localVoice } from './localVoice';

const API_BASE = '/api/v1/voice';
const STATUS_CACHE_TTL = 60_000; // 60 s

// ─── Types ────────────────────────────────────────────────────────────────────

export interface VoiceStatus {
  available: boolean;
  message: string;
  provider: 'openai' | 'local' | null;
  action_required?: string;
}

export interface EnhancedVoiceStatus {
  openai: {
    available: boolean;
    message: string;
    action_required?: string;
  };
  local: {
    available: boolean;
    message: string;
    supports_recognition: boolean;
    supports_synthesis: boolean;
  };
  recommended: 'openai' | 'local';
  current: 'openai' | 'local';
}

export interface TranscribeResponse {
  text: string;
  language: string | null;
  duration_seconds: number | null;
}

export interface SynthesizeRequest {
  text: string;
  voice?: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  speed?: number;
}

// ─── Language mapping helper ──────────────────────────────────────────────────

const LANG_MAP: Record<string, string> = {
  en: 'en-US', es: 'es-ES', fr: 'fr-FR', de: 'de-DE',
  it: 'it-IT', pt: 'pt-BR', ru: 'ru-RU', zh: 'zh-CN',
  ja: 'ja-JP', ko: 'ko-KR', ar: 'ar-SA', hi: 'hi-IN',
};

function normaliseLang(lang: string): string {
  if (!lang) return 'en-US';
  if (lang.includes('-')) return lang;
  return LANG_MAP[lang] ?? 'en-US';
}

// ─── Cache (non-exported, module-scope is fine since this runs in browser) ────
// Each user session gets a fresh module instance. The cache is intentionally
// module-scoped (not singleton class) so it survives across component remounts
// without requiring React context.

let cachedStatus: VoiceStatus | null = null;
let statusCacheTime = 0;

// ─── Service ──────────────────────────────────────────────────────────────────

export const voiceApi = {

  // ── Status / Provider Detection ────────────────────────────────────────────

  /**
   * Determine which provider to use.
   *
   * 1. Ask backend → does the user have an active OpenAI key?
   *    YES → provider = 'openai'
   *    NO  → check browser support → provider = 'local'
   *
   * Result is cached for 60 s. Call clearStatusCache() to force a re-check.
   */
  checkStatus: async (forceRefresh = false): Promise<VoiceStatus> => {
    const now = Date.now();

    if (!forceRefresh && cachedStatus && (now - statusCacheTime) < STATUS_CACHE_TTL) {
      return cachedStatus;
    }

    // Step 1: Ask the backend
    try {
      const response = await api.get<VoiceStatus>(`${API_BASE}/status`);
      if (response.data.available && response.data.provider === 'openai') {
        cachedStatus = { ...response.data, provider: 'openai' };
        statusCacheTime = now;
        return cachedStatus;
      }
    } catch {
      // Backend unreachable — fall through to local
    }

    // Step 2: Fall back to browser Web Speech API
    const localAvail = await localVoice.checkAvailability();
    if (localAvail.available) {
      cachedStatus = {
        available: true,
        message: 'No OpenAI key found — using browser voice instead',
        provider: 'local',
      };
      statusCacheTime = now;
      return cachedStatus;
    }

    // Step 3: Nothing works
    cachedStatus = {
      available: false,
      message: localAvail.message,
      provider: null,
      action_required: 'add_openai_provider',
    };
    statusCacheTime = now;
    return cachedStatus;
  },

  /**
   * Detailed voice status including both OpenAI and local (browser) availability.
   * Maps to: GET /api/v1/voice/enhanced-status
   */
  getEnhancedStatus: async (): Promise<EnhancedVoiceStatus> => {
    const response = await api.get<EnhancedVoiceStatus>(`${API_BASE}/enhanced-status`);
    return response.data;
  },

  /**
   * Clear the status cache — call after the user adds/removes an OpenAI key.
   */
  clearStatusCache: (): void => {
    cachedStatus = null;
    statusCacheTime = 0;
  },

  getCurrentProvider: (): 'openai' | 'local' | null => cachedStatus?.provider ?? null,

  requireVoice: async (): Promise<boolean> => {
    const status = await voiceApi.checkStatus();
    return status.available;
  },

  // ── Transcription ──────────────────────────────────────────────────────────

  transcribe: async (
    audioBlob: Blob,
    language?: string,
  ): Promise<TranscribeResponse> => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    if (language) {
      formData.append('language', normaliseLang(language));
    }

    const response = await api.post<TranscribeResponse>(
      `${API_BASE}/transcribe`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },

  // ── Text-to-Speech ─────────────────────────────────────────────────────────

  synthesize: async (request: SynthesizeRequest): Promise<Blob> => {
    const response = await api.post(`${API_BASE}/synthesize`, request, {
      responseType: 'blob',
    });
    return response.data as Blob;
  },

  // ── Options ────────────────────────────────────────────────────────────────

  getVoices: async (): Promise<{ voices: string[]; default: string }> => {
    const response = await api.get(`${API_BASE}/voices`);
    return response.data;
  },

  getLanguages: async (): Promise<{ languages: { code: string; name: string }[] }> => {
    const response = await api.get(`${API_BASE}/languages`);
    return response.data;
  },
};