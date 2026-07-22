import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockGetVoiceConfigDb = vi.fn();
const mockSetVoiceConfigDb = vi.fn();
const mockGetVoiceProviders = vi.fn();
const mockGetSpeakers = vi.fn();

vi.mock('@/services/voiceApi', () => ({
  voiceApi: {
    getVoiceConfigDb: (...args: any[]) => mockGetVoiceConfigDb(...args),
    setVoiceConfigDb: (...args: any[]) => mockSetVoiceConfigDb(...args),
    getVoiceProviders: (...args: any[]) => mockGetVoiceProviders(...args),
    getSpeakers: (...args: any[]) => mockGetSpeakers(...args),
  },
}));

vi.mock('@/services/voiceBridge', () => ({
  voiceBridgeService: {
    status: 'offline',
    onStatusChange: vi.fn(() => () => {}),
    connect: vi.fn(() => Promise.resolve()),
  },
}));

vi.mock('@/hooks/useToast', () => ({
  showToast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/ui/LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: { size?: string }) => <div data-testid={`spinner-${size}`} />,
}));

vi.mock('@/components/ui/Modal', () => ({
  Modal: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="modal">{children}</div> : null,
}));

describe('VoiceSettingsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders engine tab by default with provider filter tabs', async () => {
    mockGetVoiceConfigDb.mockResolvedValue({
      user_id: 'test',
      require_wake_word: true,
      tts_voice: 'am_adam',
      tts_provider: 'kokoro',
      proactive_enabled: false,
      speaker_identification: false,
    });
    mockGetVoiceProviders.mockResolvedValue({
      providers: {
        kokoro: { available: true, voices: [{ id: 'am_adam', name: 'Adam', gender: 'male' }], default_voice: 'am_adam' },
        openai: { available: false, voices: [], default_voice: 'alloy' },
      },
      current_provider: 'kokoro',
    });

    const { VoiceSettingsModal } = await import('../VoiceSettingsModal');
    render(<VoiceSettingsModal onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('All')).toBeTruthy();
      expect(screen.getByText('Kokoro (Offline)')).toBeTruthy();
      expect(screen.getByText('OpenAI (Cloud)')).toBeTruthy();
    });
  });

  it('shows voice selector when providers data loaded', async () => {
    mockGetVoiceConfigDb.mockResolvedValue({
      user_id: 'test',
      require_wake_word: true,
      tts_voice: 'am_adam',
      tts_provider: 'kokoro',
      proactive_enabled: false,
      speaker_identification: false,
    });
    mockGetVoiceProviders.mockResolvedValue({
      providers: {
        kokoro: {
          available: true,
          voices: [
            { id: 'am_adam', name: 'Adam', gender: 'male' },
            { id: 'af_bella', name: 'Bella', gender: 'female' },
          ],
          default_voice: 'am_adam',
        },
        openai: { available: false, voices: [], default_voice: 'alloy' },
      },
      current_provider: 'kokoro',
    });

    const { VoiceSettingsModal } = await import('../VoiceSettingsModal');
    render(<VoiceSettingsModal onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Adam (male) — Offline')).toBeTruthy();
    });
  });

  it('shows fallback voices when providers endpoint fails', async () => {
    mockGetVoiceConfigDb.mockResolvedValue({
      user_id: 'test',
      require_wake_word: true,
      tts_voice: 'af_bella',
      tts_provider: 'kokoro',
      proactive_enabled: false,
      speaker_identification: false,
    });
    mockGetVoiceProviders.mockRejectedValue(new Error('Network error'));

    const { VoiceSettingsModal } = await import('../VoiceSettingsModal');
    render(<VoiceSettingsModal onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Bella (Female)')).toBeTruthy();
      expect(screen.getByText('Adam (Male)')).toBeTruthy();
    });
  });

  it('saves config via setVoiceConfigDb on save button click', async () => {
    mockGetVoiceConfigDb.mockResolvedValue({
      user_id: 'test',
      require_wake_word: true,
      tts_voice: 'am_adam',
      tts_provider: 'kokoro',
      proactive_enabled: false,
      speaker_identification: false,
    });
    mockGetVoiceProviders.mockResolvedValue({
      providers: {
        kokoro: { available: true, voices: [{ id: 'am_adam', name: 'Adam', gender: 'male' }], default_voice: 'am_adam' },
        openai: { available: false, voices: [], default_voice: 'alloy' },
      },
      current_provider: 'kokoro',
    });
    mockSetVoiceConfigDb.mockResolvedValue({});

    const { VoiceSettingsModal } = await import('../VoiceSettingsModal');
    render(<VoiceSettingsModal onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockSetVoiceConfigDb).toHaveBeenCalledWith(
        expect.objectContaining({
          tts_voice: 'am_adam',
          tts_provider: 'kokoro',
        }),
      );
    });
  });
});
