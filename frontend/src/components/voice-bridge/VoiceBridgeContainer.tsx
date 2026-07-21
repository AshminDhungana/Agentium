import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { VoiceOrb } from './VoiceOrb';
import { WaveformVisualizer } from './WaveformVisualizer';
import { FrequencyBars } from './FrequencyBars';
import { VoiceControls } from './VoiceControls';
import { ConnectionStatus, ConnectionStatusCompact } from './ConnectionStatus';
import { MicrophoneLevel } from './MicrophoneLevel';
import { TranscriptDisplay } from './TranscriptDisplay';
import { VoiceSettings } from './VoiceSettings';
import { useVoiceBridge } from './hooks/useVoiceBridge';
import { useAudioVisualization } from './hooks/useAudioVisualization';
import type { VoiceState, ConnectionStatus as ConnectionStatusType } from './types';

const VISUALIZATION_WIDTH = 600;
const VISUALIZATION_HEIGHT = 100;

export function VoiceBridgeContainer({ className = '' }: { className?: string }) {
  const {
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
    addTranscript,
    clearTranscripts,
    setMicLevel,
    setTimeDomainData,
    setFrequencyData,
  } = useVoiceBridge();

  const { start: startVisualization, stop: stopVisualization } = useAudioVisualization();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (status === 'connected' && !stream) {
      navigator.mediaDevices
        .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
        .then((mediaStream) => {
          setStream(mediaStream);
          streamRef.current = mediaStream;
          startVisualization(mediaStream);
        })
        .catch((err) => {
          console.warn('[VoiceBridgeContainer] Microphone access denied:', err);
        });
    }
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      stopVisualization();
    };
  }, [status, startVisualization, stopVisualization]);

  useEffect(() => {
    if (status === 'connected') {
      setMicLevel(micLevel);
      if (timeDomainData) setTimeDomainData(timeDomainData);
      if (frequencyData) setFrequencyData(frequencyData);
    }
  }, [micLevel, timeDomainData, frequencyData, setMicLevel, setTimeDomainData, setFrequencyData, status]);

  const handleRecord = useCallback(async () => {
    if (status !== 'connected' || isMuted) return;
    startRecording();
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      // Already have stream from mount
    }
  }, [status, isMuted, startRecording]);

  const handleStop = useCallback(() => {
    stopRecording();
  }, [stopRecording]);

  const handleMuteToggle = useCallback(() => {
    toggleMute();
    if (!isMuted && streamRef.current) {
      streamRef.current.getAudioTracks().forEach((track) => (track.enabled = false));
    } else if (isMuted && streamRef.current) {
      streamRef.current.getAudioTracks().forEach((track) => (track.enabled = true));
    }
  }, [isMuted, toggleMute]);

  const handleConnect = useCallback(() => {
    if (status === 'disconnected' || status === 'error') {
      connect();
    } else if (status === 'connected') {
      disconnect();
    }
  }, [status, connect, disconnect]);

  const handleSettingsOpen = useCallback(() => {
    setIsSettingsOpen(true);
  }, []);

  const handleSettingsClose = useCallback(() => {
    setIsSettingsOpen(false);
  }, []);

  const handleSettingsChange = useCallback((newSettings: Partial<typeof settings>) => {
    updateSettings(newSettings);
  }, [updateSettings]);

  const handleClearTranscripts = useCallback(() => {
    clearTranscripts();
  }, [clearTranscripts]);

  const getVisualizationColor = (state: VoiceState): string => {
    switch (state) {
      case 'listening':
        return '#3b82f6';
      case 'speaking':
        return '#8b5cf6';
      case 'processing':
        return '#f59e0b';
      case 'error':
        return '#ef4444';
      case 'muted':
        return '#9ca3af';
      default:
        return '#64748b';
    }
  };

  const vizColor = getVisualizationColor(voiceState);
  const showVisualization = voiceState === 'listening' || voiceState === 'speaking';

  return (
    <div
      className={`min-h-screen bg-slate-950 flex flex-col ${className}`}
      style={{
        background: 'radial-gradient(ellipse at center, rgba(59, 130, 246, 0.08) 0%, transparent 70%)',
      }}
    >
      <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full blur-3xl bg-blue-500/10" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full blur-3xl bg-purple-500/10" />
      </div>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center p-4 sm:p-6 lg:p-10">
        <motion.div
          className="w-full max-w-4xl flex flex-col items-center gap-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, type: prefersReduced ? 'tween' : 'spring', stiffness: 100, damping: 20 }}
        >
          <motion.div
            className="flex items-center justify-between w-full"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Voice Bridge</h1>
            <ConnectionStatusCompact status={status} />
          </motion.div>

          <motion.div
            className="relative flex flex-col items-center gap-6 w-full"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2, type: prefersReduced ? 'tween' : 'spring', stiffness: 200, damping: 20 }}
          >
            <div className="relative w-full max-w-md mx-auto">
              <VoiceOrb
                size={240}
                state={voiceState}
                micLevel={micLevel}
                reducedMotion={prefersReduced}
              />
            </div>

            <AnimatePresence mode="wait">
              {showVisualization && (
                <motion.div
                  key="visualizations"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                  className="w-full max-w-2xl space-y-4"
                >
                  {timeDomainData && (
                  <motion.div
                    initial={{ opacity: 0, scaleY: 0.8 }}
                    animate={{ opacity: 1, scaleY: 1 }}
                    className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-4"
                  >
                    <WaveformVisualizer
                      timeDomainData={timeDomainData}
                      color={vizColor}
                      width={VISUALIZATION_WIDTH}
                      height={60}
                      reducedMotion={prefersReduced}
                    />
                  </motion.div>
                  )}
                  {frequencyData && (
                  <motion.div
                    initial={{ opacity: 0, scaleY: 0.8 }}
                    animate={{ opacity: 1, scaleY: 1 }}
                    transition={{ delay: 0.1 }}
                    className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-4"
                  >
                    <FrequencyBars
                      frequencyData={frequencyData}
                      color={vizColor}
                      width={VISUALIZATION_WIDTH}
                      height={80}
                      reducedMotion={prefersReduced}
                    />
                  </motion.div>
                  )}
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="flex justify-center"
                  >
                    <MicrophoneLevel
                      level={micLevel}
                      className="w-64"
                      reducedMotion={prefersReduced}
                    />
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>

            <motion.div
              className="w-full max-w-2xl"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <TranscriptDisplay
                transcripts={transcripts}
                maxHeight={300}
                className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl"
              />
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
            >
              <VoiceControls
                voiceState={voiceState}
                isConnected={status === 'connected'}
                isMuted={isMuted}
                isRecording={isRecording}
                onRecord={handleRecord}
                onStop={handleStop}
                onMuteToggle={handleMuteToggle}
                onSettings={handleSettingsOpen}
                onClose={() => handleSettingsClose()}
                reducedMotion={prefersReduced}
              />
            </motion.div>

            <motion.div
              className="flex items-center justify-center gap-4 text-xs text-gray-500"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
            >
              <span className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${status === 'connected' ? 'bg-emerald-500' : 'bg-gray-600'}`} />
                {status === 'connected' ? 'Bridge connected' : 'Bridge offline'}
              </span>
              <span className="hidden sm:inline">·</span>
              <span>
                {status === 'connected'
                  ? voiceState === 'idle'
                    ? 'Tap mic or say "Hey Agentium"'
                    : voiceState === 'listening'
                    ? 'Listening...'
                    : voiceState === 'speaking'
                    ? 'Speaking...'
                    : voiceState === 'processing'
                    ? 'Processing...'
                    : 'Ready'
                  : 'Connect the voice bridge to start'}
              </span>
            </motion.div>
          </motion.div>
        </motion.div>
      </div>

      <VoiceSettings
        isOpen={isSettingsOpen}
        onClose={handleSettingsClose}
        settings={settings}
        onSettingsChange={handleSettingsChange}
        availableInputDevices={availableInputDevices}
        availableOutputDevices={availableOutputDevices}
      />
    </div>
  );
}