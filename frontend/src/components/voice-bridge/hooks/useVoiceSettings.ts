import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { VoiceSettings } from '../types';

const DEFAULT_SETTINGS: VoiceSettings = {
  model: 'whisper-1',
  voice: 'alloy',
  language: 'en',
  vadSensitivity: 0.5,
  autoStopSilence: 1000,
  inputDeviceId: 'default',
  outputDeviceId: 'default',
};

interface VoiceSettingsState {
  settings: VoiceSettings;
  availableVoices: string[];
  availableModels: string[];
  availableLanguages: string[];
  availableInputDevices: MediaDeviceInfo[];
  availableOutputDevices: MediaDeviceInfo[];
  isLoadingDevices: boolean;
  loadDevices: () => Promise<void>;
  updateSettings: (settings: Partial<VoiceSettings>) => void;
  resetSettings: () => void;
}

export const useVoiceSettingsStore = create<VoiceSettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      availableVoices: ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
      availableModels: ['whisper-1', 'whisper-large', 'whisper-turbo'],
      availableLanguages: ['en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh'],
      availableInputDevices: [],
      availableOutputDevices: [],
      isLoadingDevices: false,

      loadDevices: async () => {
        set({ isLoadingDevices: true });
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const inputDevices = devices.filter((d) => d.kind === 'audioinput');
          const outputDevices = devices.filter((d) => d.kind === 'audiooutput');
          set({
            availableInputDevices: inputDevices,
            availableOutputDevices: outputDevices,
          });
        } catch (error) {
          console.warn('[useVoiceSettings] Failed to load devices:', error);
        } finally {
          set({ isLoadingDevices: false });
        }
      },

      updateSettings: (newSettings) =>
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        })),

      resetSettings: () => set({ settings: DEFAULT_SETTINGS }),
    }),
    {
      name: 'voice-bridge-settings',
      partialize: (state) => ({ settings: state.settings }),
    }
  )
);

export function useVoiceSettings() {
  const store = useVoiceSettingsStore();
  return store;
}