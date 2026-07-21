import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  VoiceState,
  ConnectionStatus,
  VoiceSettings,
  TranscriptEntry,
  AudioVisualizationData,
} from '@/components/voice-bridge/types';

const DEFAULT_SETTINGS: VoiceSettings = {
  model: 'whisper-1',
  voice: 'nova',
  language: 'en',
  vadSensitivity: 0.5,
  autoStopSilence: 1000,
  inputDeviceId: 'default',
  outputDeviceId: 'default',
};

interface VoiceStore {
  // Connection state
  status: ConnectionStatus;
  setStatus: (status: ConnectionStatus) => void;

  // Voice state
  voiceState: VoiceState;
  setVoiceState: (state: VoiceState) => void;

  // Recording state
  isRecording: boolean;
  setIsRecording: (recording: boolean) => void;

  // Mute state
  isMuted: boolean;
  setIsMuted: (muted: boolean) => void;

  // Processing state
  isProcessing: boolean;
  setIsProcessing: (processing: boolean) => void;

  // Audio visualization
  audioData: AudioVisualizationData | null;
  setAudioData: (data: AudioVisualizationData | null) => void;
  updateMicLevel: (level: number) => void;
  updateTimeDomainData: (data: Uint8Array) => void;
  updateFrequencyData: (data: Uint8Array) => void;

  // Transcripts
  transcripts: TranscriptEntry[];
  addTranscript: (entry: TranscriptEntry) => void;
  updateLastTranscript: (text: string) => void;
  clearTranscripts: () => void;

  // Settings
  settings: VoiceSettings;
  updateSettings: (settings: Partial<VoiceSettings>) => void;
  resetSettings: () => void;
  loadSettings: () => void;
  saveSettings: () => void;

  // Devices
  availableInputDevices: MediaDeviceInfo[];
  availableOutputDevices: MediaDeviceInfo[];
  setAvailableInputDevices: (devices: MediaDeviceInfo[]) => void;
  setAvailableOutputDevices: (devices: MediaDeviceInfo[]) => void;

  // Actions
  reset: () => void;
}

export const useVoiceStore = create<VoiceStore>()(
  persist(
    (set, get) => ({
      // Connection state
      status: 'disconnected',
      setStatus: (status) => set({ status }),

      // Voice state
      voiceState: 'idle',
      setVoiceState: (voiceState) => set({ voiceState }),

      // Recording state
      isRecording: false,
      setIsRecording: (isRecording) => set({ isRecording }),

      // Mute state
      isMuted: false,
      setIsMuted: (isMuted) => set({ isMuted }),

      // Processing state
      isProcessing: false,
      setIsProcessing: (isProcessing) => set({ isProcessing }),

      // Audio visualization
      audioData: null,
      setAudioData: (audioData) => set({ audioData }),
      updateMicLevel: (micLevel) =>
        set((state) => ({
          audioData: state.audioData ? { ...state.audioData, micLevel } : null,
        })),
      updateTimeDomainData: (timeDomainData) =>
        set((state) => ({
          audioData: state.audioData ? { ...state.audioData, timeDomainData } : null,
        })),
      updateFrequencyData: (frequencyData) =>
        set((state) => ({
          audioData: state.audioData ? { ...state.audioData, frequencyData } : null,
        })),

      // Transcripts
      transcripts: [],
      addTranscript: (entry) =>
        set((state) => ({
          transcripts: [...state.transcripts.slice(-49), entry],
        })),
      updateLastTranscript: (text) =>
        set((state) => {
          const transcripts = [...state.transcripts];
          if (transcripts.length > 0) {
            transcripts[transcripts.length - 1] = {
              ...transcripts[transcripts.length - 1],
              text,
              isStreaming: false,
            };
          }
          return { transcripts };
        }),
      clearTranscripts: () => set({ transcripts: [] }),

      // Settings
      settings: DEFAULT_SETTINGS,
      updateSettings: (settings) =>
        set((state) => ({
          settings: { ...state.settings, ...settings },
        })),
      resetSettings: () => set({ settings: DEFAULT_SETTINGS }),
      loadSettings: () => {
        try {
          const saved = localStorage.getItem('voice_bridge_settings');
          if (saved) {
            const parsed = JSON.parse(saved);
            set({ settings: { ...DEFAULT_SETTINGS, ...parsed } });
          }
        } catch {
          // Ignore parse errors
        }
      },
      saveSettings: () => {
        try {
          localStorage.setItem('voice_bridge_settings', JSON.stringify(get().settings));
        } catch {
          // Ignore storage errors
        }
      },

      // Devices
      availableInputDevices: [],
      availableOutputDevices: [],
      setAvailableInputDevices: (availableInputDevices) => set({ availableInputDevices }),
      setAvailableOutputDevices: (availableOutputDevices) => set({ availableOutputDevices }),

      // Reset all
      reset: () =>
        set({
          status: 'disconnected',
          voiceState: 'idle',
          isRecording: false,
          isMuted: false,
          isProcessing: false,
          audioData: null,
          transcripts: [],
        }),
    }),
    {
      name: 'voice-bridge-store',
      partialize: (state) => ({
        settings: state.settings,
        isMuted: state.isMuted,
      }),
    }
  )
);