export type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';

export interface VoiceSettings {
  model: string;
  voice: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  language: string;
  vadSensitivity: number;
  autoStopSilence: number;
  inputDeviceId: string;
  outputDeviceId: string;
  localProcessingOnly?: boolean;
  saveRecordings?: boolean;
  requireWakeWord?: boolean;
  proactiveEnabled?: boolean;
  speakerIdentification?: boolean;
  voiceMode?: 'push-to-talk' | 'open-mic';
  ttsVoice?: string;
  speechRate?: number;
  pitch?: number;
  volume?: number;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  pingInterval?: number;
  maxReconnectAttempts?: number;
}

export interface TranscriptEntry {
  id: string;
  speaker: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  isStreaming?: boolean;
}

export interface VoiceMessage {
  type: 'audio' | 'text' | 'control' | 'config';
  payload: unknown;
}

export interface AudioVisualizationData {
  timeDomainData: Uint8Array;
  frequencyData: Uint8Array;
  micLevel: number;
}

export interface VoiceOrbProps {
  size: number;
  state: VoiceState;
  micLevel: number;
  className?: string;
  reducedMotion?: boolean;
}

export interface VisualizerProps {
  timeDomainData?: Uint8Array;
  frequencyData?: Uint8Array;
  state?: VoiceState;
  color?: string;
  width?: number;
  height?: number;
  className?: string;
  reducedMotion?: boolean;
}

export interface WaveformVisualizerProps extends VisualizerProps {
  timeDomainData: Uint8Array;
}

export interface FrequencyBarsProps extends VisualizerProps {
  frequencyData: Uint8Array;
}

export interface MicrophoneLevelProps {
  level: number;
  maxLevel?: number;
  segments?: number;
  className?: string;
  reducedMotion?: boolean;
}

export interface MicrophoneLevelRingProps {
  level: number;
  maxLevel?: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
  reducedMotion?: boolean;
}

export interface VoiceControlsProps {
  voiceState: VoiceState;
  isConnected: boolean;
  isMuted: boolean;
  isRecording: boolean;
  onRecord: () => void;
  onStop: () => void;
  onMuteToggle: () => void;
  onSettings: () => void;
  onClose?: () => void;
  reducedMotion?: boolean;
  className?: string;
}

export interface ConnectionStatusProps {
  status: ConnectionStatus;
  className?: string;
  showLabel?: boolean;
  compact?: boolean;
}

export interface ConnectionStatusConfig {
  label: string;
  color: string;
  icon: React.ReactNode;
  bgColor: string;
  ringColor: string;
}

export interface VoiceSettingsProps {
  isOpen: boolean;
  onClose: () => void;
  settings: VoiceSettings;
  onSettingsChange: (settings: Partial<VoiceSettings>) => void;
  availableInputDevices: MediaDeviceInfo[];
  availableOutputDevices: MediaDeviceInfo[];
  className?: string;
}

export interface TranscriptDisplayProps {
  transcripts: TranscriptEntry[];
  className?: string;
  maxHeight?: number;
}

export interface VoiceBridgeContainerProps {
  className?: string;
}

export interface UseVoiceBridgeReturn {
  status: ConnectionStatus;
  voiceState: VoiceState;
  isRecording: boolean;
  isMuted: boolean;
  isProcessing: boolean;
  micLevel: number;
  timeDomainData: Uint8Array | undefined;
  frequencyData: Uint8Array | undefined;
  transcripts: TranscriptEntry[];
  settings: VoiceSettings;
  availableInputDevices: MediaDeviceInfo[];
  availableOutputDevices: MediaDeviceInfo[];
  connect: () => Promise<void>;
  disconnect: () => void;
  startRecording: () => void;
  stopRecording: () => void;
  toggleMute: () => void;
  updateSettings: (settings: Partial<VoiceSettings>) => void;
  addTranscript: (entry: TranscriptEntry) => void;
  clearTranscripts: () => void;
}

export interface UseAudioVisualizationReturn {
  timeDomainData: Uint8Array;
  frequencyData: Uint8Array;
  micLevel: number;
  start: (stream: MediaStream) => void;
  stop: () => void;
}

export interface UseVoiceSettingsReturn {
  settings: VoiceSettings;
  updateSettings: (settings: Partial<VoiceSettings>) => void;
  resetSettings: () => void;
  loadSettings: () => void;
  saveSettings: () => void;
}