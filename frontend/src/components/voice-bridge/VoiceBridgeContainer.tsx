import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { VoiceOrb } from './VoiceOrb';
import { WaveformVisualizer } from './WaveformVisualizer';
import { FrequencyBars } from './FrequencyBars';
import { VoiceControls } from './VoiceControls';
import { ConnectionStatusCompact } from './ConnectionStatus';
import { MicrophoneLevel } from './MicrophoneLevel';
import { TranscriptDisplay } from './TranscriptDisplay';
import { VoiceSettings } from './VoiceSettings';
import { useVoiceBridge } from './hooks/useVoiceBridge';
import { useAudioVisualization } from './hooks/useAudioVisualization';
import type { VoiceState } from './types';

const VISUALIZATION_WIDTH = 600;

export function VoiceBridgeContainer({ className = '' }: { className?: string }) {
  const {
    status,
    voiceState,
    isRecording,
    isMuted,
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

  const handleSettingsOpen = useCallback(() => setIsSettingsOpen(true), []);
  const handleSettingsClose = useCallback(() => setIsSettingsOpen(false), []);

  const handleSettingsChange = useCallback(
    (newSettings: Partial<typeof settings>) => updateSettings(newSettings),
    [updateSettings]
  );

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
  const isBusy = status === 'connecting' || status === 'reconnecting';

  return (
    <div className={`h-full flex flex-col bg-gray-50 dark:bg-[#0f1117] transition-colors duration-200 ${className}`}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none">
        <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-blue-500/25 dark:shadow-blue-900/40">
              <Mic className="w-5 h-5 text-white" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-gray-900 dark:text-white leading-tight">
                Voice Bridge
              </h1>
              <p className="text-xs text-gray-600 dark:text-gray-400 truncate">
                Talk to Agentium in real time
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            <ConnectionStatusCompact status={status} />
            <button
              onClick={handleConnect}
              disabled={isBusy}
              className={
                status === 'connected'
                  ? 'inline-flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg transition-colors duration-150'
                  : 'inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm dark:shadow-blue-900/30'
              }
            >
              {isBusy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {status === 'connected' ? 'Disconnect' : isBusy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Scrollable content ─────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-8 flex flex-col items-center gap-5">
          {status === 'error' && (
            <div className="w-full p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <p className="text-sm font-medium text-red-700 dark:text-red-400">Connection error</p>
                <p className="text-xs text-red-600/80 dark:text-red-400/70 mt-0.5">
                  Unable to connect. Is the voice bridge running?
                </p>
              </div>
            </div>
          )}

          {/* Orb */}
          <div className="w-full bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none p-8 flex items-center justify-center">
            <VoiceOrb size={180} state={voiceState} micLevel={micLevel} reducedMotion={prefersReduced} />
          </div>

          {/* Visualizations — only while actively listening or speaking */}
          <AnimatePresence>
            {showVisualization && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: prefersReduced ? 0 : 0.2 }}
                className="w-full flex flex-col items-center gap-4 overflow-hidden"
              >
                {timeDomainData && (
                  <div className="w-full bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none p-4">
                    <WaveformVisualizer
                      timeDomainData={timeDomainData}
                      color={vizColor}
                      width={VISUALIZATION_WIDTH}
                      height={60}
                      reducedMotion={prefersReduced}
                    />
                  </div>
                )}
                {frequencyData && (
                  <div className="w-full bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none p-4">
                    <FrequencyBars
                      frequencyData={frequencyData}
                      color={vizColor}
                      width={VISUALIZATION_WIDTH}
                      height={70}
                      reducedMotion={prefersReduced}
                    />
                  </div>
                )}
                <MicrophoneLevel level={micLevel} className="w-64" reducedMotion={prefersReduced} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Transcript */}
          <div className="w-full bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 dark:border-[#1e2535]">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Conversation</h2>
              {transcripts.length > 0 && (
                <button
                  onClick={handleClearTranscripts}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors duration-150"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  Clear
                </button>
              )}
            </div>
            <TranscriptDisplay transcripts={transcripts} maxHeight={320} className="p-4" />
          </div>
        </div>
      </div>

      {/* ── Controls ───────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535] px-6 py-5">
        <div className="max-w-2xl mx-auto">
          <VoiceControls
            voiceState={voiceState}
            isConnected={status === 'connected'}
            isMuted={isMuted}
            isRecording={isRecording}
            onRecord={handleRecord}
            onStop={handleStop}
            onMuteToggle={handleMuteToggle}
            onSettings={handleSettingsOpen}
            reducedMotion={prefersReduced}
          />
        </div>
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