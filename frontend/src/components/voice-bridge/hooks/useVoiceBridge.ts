import { useCallback, useEffect, useRef, useMemo } from 'react';
import { useVoiceStore } from '@/stores/voiceStore';
import { voiceBridgeService, BridgeStatus, VoiceState, VoiceInteractionEvent, TranscriptEvent } from '@/services/voiceBridge';
import type {
  VoiceState as VoiceStateType,
  ConnectionStatus,
  TranscriptEntry,
  VoiceSettings,
} from '../types';

const STATUS_MAP: Record<BridgeStatus, ConnectionStatus> = {
  offline: 'disconnected',
  connecting: 'connecting',
  connected: 'connected',
  error: 'error',
};

const VOICE_STATE_MAP: Record<VoiceState, VoiceStateType> = {
  idle: 'idle',
  listening: 'listening',
  thinking: 'processing',
  speaking: 'speaking',
  interrupted: 'error',
};

export function useVoiceBridge() {
  const {
    status,
    setStatus,
    voiceState,
    setVoiceState,
    isRecording,
    setIsRecording,
    isMuted,
    setIsMuted,
    isProcessing,
    setIsProcessing,
    audioData,
    setAudioData,
    updateMicLevel,
    updateTimeDomainData,
    updateFrequencyData,
    transcripts,
    addTranscript,
    updateLastTranscript,
    clearTranscripts,
    settings,
    updateSettings,
    resetSettings,
    loadSettings,
    saveSettings,
    availableInputDevices,
    availableOutputDevices,
    setAvailableInputDevices,
    setAvailableOutputDevices,
  } = useVoiceStore();

  const micLevel = useMemo(() => audioData?.micLevel ?? 0, [audioData?.micLevel]);
  const timeDomainData = useMemo(() => audioData?.timeDomainData, [audioData?.timeDomainData]);
  const frequencyData = useMemo(() => audioData?.frequencyData, [audioData?.frequencyData]);

  const onInteractionRef = useRef<((event: VoiceInteractionEvent) => void) | null>(null);
  const onTranscriptRef = useRef<((event: TranscriptEvent) => void) | null>(null);
  const isInitializedRef = useRef(false);

  useEffect(() => {
    const unsubStatus = voiceBridgeService.onStatusChange((bridgeStatus) => {
      setStatus(STATUS_MAP[bridgeStatus]);
    });

    const unsubState = voiceBridgeService.onStateChange((state) => {
      if (state) {
        setVoiceState(VOICE_STATE_MAP[state]);
      }
    });

    const unsubInteraction = voiceBridgeService.onInteraction((event) => {
      onInteractionRef.current?.(event);
    });

    const unsubTranscript = voiceBridgeService.onTranscript((event) => {
      onTranscriptRef.current?.(event);
    });

    if (!isInitializedRef.current) {
      isInitializedRef.current = true;
      loadSettings();
      loadDevices();
    }

    return () => {
      unsubStatus();
      unsubState();
      unsubInteraction();
      unsubTranscript();
    };
  }, [setStatus, setVoiceState, loadSettings]);

  const loadDevices = async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      setAvailableInputDevices(devices.filter((d) => d.kind === 'audioinput'));
      setAvailableOutputDevices(devices.filter((d) => d.kind === 'audiooutput'));
    } catch {
      // Ignore device enumeration errors
    }
  };

  const connect = useCallback(async () => {
    try {
      await voiceBridgeService.connect();
    } catch (error) {
      console.warn('[useVoiceBridge] connect error:', error);
    }
  }, []);

  const disconnect = useCallback(() => {
    voiceBridgeService.disconnect();
    setIsRecording(false);
    setIsProcessing(false);
  }, [setIsRecording, setIsProcessing]);

  const startRecording = useCallback(() => {
    if (status === 'connected' && !isMuted) {
      setIsRecording(true);
      setVoiceState('listening');
    }
  }, [status, isMuted, setIsRecording, setVoiceState]);

  const stopRecording = useCallback(() => {
    setIsRecording(false);
    setVoiceState('processing');
    setIsProcessing(true);
    setTimeout(() => {
      setIsProcessing(false);
      setVoiceState('idle');
    }, 1000);
  }, [setIsRecording, setVoiceState, setIsProcessing]);

  const toggleMute = useCallback(() => {
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    if (newMuted) {
      setVoiceState('muted');
      stopRecording();
    } else {
      setVoiceState('idle');
    }
  }, [isMuted, setIsMuted, setVoiceState, stopRecording]);

  const addTranscriptEntry = useCallback(
    (entry: TranscriptEntry) => {
      addTranscript(entry);
    },
    [addTranscript]
  );

  const updateStreamingTranscript = useCallback(
    (text: string) => {
      updateLastTranscript(text);
    },
    [updateLastTranscript]
  );

  const handleInteraction = useCallback(
    (event: VoiceInteractionEvent) => {
      addTranscriptEntry({
        id: `user-${Date.now()}`,
        speaker: 'user',
        text: event.user,
        timestamp: new Date(event.ts * 1000),
      });
      addTranscriptEntry({
        id: `assistant-${Date.now()}`,
        speaker: 'assistant',
        text: event.reply,
        timestamp: new Date(event.ts * 1000),
      });
      setVoiceState('idle');
      setIsProcessing(false);
    },
    [addTranscriptEntry, setVoiceState, setIsProcessing]
  );

  const handleTranscript = useCallback(
    (event: TranscriptEvent) => {
      if (event.role === 'user') {
        addTranscriptEntry({
          id: `user-stream-${Date.now()}`,
          speaker: 'user',
          text: event.text,
          timestamp: new Date(event.ts * 1000),
          isStreaming: true,
        });
      } else {
        addTranscriptEntry({
          id: `assistant-stream-${Date.now()}`,
          speaker: 'assistant',
          text: event.text,
          timestamp: new Date(event.ts * 1000),
          isStreaming: true,
        });
      }
    },
    [addTranscriptEntry]
  );

  useEffect(() => {
    onInteractionRef.current = handleInteraction;
  }, [handleInteraction]);

  useEffect(() => {
    onTranscriptRef.current = handleTranscript;
  }, [handleTranscript]);

  useEffect(() => {
    saveSettings();
  }, [settings, saveSettings]);

  return {
    status,
    voiceState,
    isRecording,
    isMuted,
    isProcessing,
    micLevel,
    timeDomainData,
    frequencyData,
    transcripts,
    settings,
    availableInputDevices,
    availableOutputDevices,
    connect,
    disconnect,
    startRecording,
    stopRecording,
    toggleMute,
    updateSettings,
    resetSettings,
    loadSettings,
    saveSettings,
    addTranscript: addTranscriptEntry,
    updateStreamingTranscript,
    clearTranscripts,
    setMicLevel: updateMicLevel,
    setTimeDomainData: updateTimeDomainData,
    setFrequencyData: updateFrequencyData,
  };
}