import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';

vi.mock('../api');

const mockApiGet = vi.fn();
const mockApiPost = vi.fn();
const mockApiPut = vi.fn();

vi.mock('../api', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    put: (...args: any[]) => mockApiPut(...args),
  },
}));

describe('voiceApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getVoiceConfigDb', () => {
    it('returns voice config from /voice-config endpoint', async () => {
      const mockConfig = {
        user_id: 'test-user',
        require_wake_word: true,
        tts_voice: 'am_adam',
        tts_provider: 'kokoro' as const,
        proactive_enabled: false,
        speaker_identification: false,
      };
      mockApiGet.mockResolvedValue({ data: mockConfig });

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.getVoiceConfigDb();

      expect(result).toEqual(mockConfig);
      expect(mockApiGet).toHaveBeenCalledWith('/api/v1/voice/voice-config');
    });

    it('returns null on failure', async () => {
      mockApiGet.mockRejectedValue(new Error('Network error'));

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.getVoiceConfigDb();

      expect(result).toBeNull();
    });
  });

  describe('setVoiceConfigDb', () => {
    it('sends config to /voice-config endpoint', async () => {
      const update = {
        require_wake_word: false,
        tts_voice: 'bm_george',
        tts_provider: 'kokoro' as const,
      };
      mockApiPut.mockResolvedValue({ data: { ...update, user_id: 'test-user' } });

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.setVoiceConfigDb(update);

      expect(result).toHaveProperty('tts_voice', 'bm_george');
      expect(mockApiPut).toHaveBeenCalledWith('/api/v1/voice/voice-config', update);
    });

    it('returns null on failure', async () => {
      mockApiPut.mockRejectedValue(new Error('Network error'));

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.setVoiceConfigDb({ tts_voice: 'am_adam' });

      expect(result).toBeNull();
    });
  });

  describe('getVoiceProviders', () => {
    it('returns providers from /voice-config/providers endpoint', async () => {
      const mockProviders = {
        providers: {
          kokoro: { available: true, voices: [{ id: 'am_adam', name: 'Adam', gender: 'male' }], default_voice: 'am_adam' },
          openai: { available: false, voices: [], default_voice: 'alloy' },
        },
        current_provider: 'kokoro',
      };
      mockApiGet.mockResolvedValue({ data: mockProviders });

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.getVoiceProviders();

      expect(result).toEqual(mockProviders);
      expect(mockApiGet).toHaveBeenCalledWith('/api/v1/voice/voice-config/providers');
    });

    it('returns null on failure', async () => {
      mockApiGet.mockRejectedValue(new Error('Network error'));

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.getVoiceProviders();

      expect(result).toBeNull();
    });
  });

  describe('synthesize', () => {
    it('sends text and voice to /synthesize endpoint', async () => {
      const mockBlob = new Blob(['RIFF....WAVE'], { type: 'audio/wav' });
      mockApiPost.mockResolvedValue({ data: mockBlob });

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.synthesize({ text: 'Hello', voice: 'am_adam' });

      expect(result).toBe(mockBlob);
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/v1/voice/synthesize',
        { text: 'Hello', voice: 'am_adam' },
        { responseType: 'blob' },
      );
    });

    it('works with Kokoro voice IDs in the type', async () => {
      const mockBlob = new Blob(['RIFF....WAVE'], { type: 'audio/wav' });
      mockApiPost.mockResolvedValue({ data: mockBlob });

      const { voiceApi } = await import('../voiceApi');
      const result = await voiceApi.synthesize({ text: 'Hi', voice: 'af_bella' });

      expect(result).toBe(mockBlob);
    });
  });
});
