import { useState, useEffect, useCallback, useRef, Suspense, lazy } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Loader2, AlertCircle, Trash2, Settings, MicOff, Circle } from 'lucide-react';
import { ConnectionStatusCompact } from './ConnectionStatus';
import { TranscriptDisplay } from './TranscriptDisplay';
import { VoiceControls } from './VoiceControls';
import { VoiceSettings } from './VoiceSettings';
import { useVoiceBridge } from './hooks/useVoiceBridge';
import { useAudioVisualization } from './hooks/useAudioVisualization';
import { useReducedMotion } from './hooks/useReducedMotion';
import type { VoiceState } from './types';

// Lazy-load ThreeScene for code splitting
const ThreeScene = lazy(() => import('./ThreeScene').then(m => ({ default: m.ThreeScene })));

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
  const { prefersReduced } = useReducedMotion();

  // Mic access on connect
  useEffect(() => {
    if (status === 'connected' && !stream) {
      navigator.mediaDevices
        .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
        .then((mediaStream) => {
          setStream(mediaStream);
          streamRef.current = mediaStream;
          startVisualization(mediaStream);
        })
        .catch((err) => console.warn('[VoiceBridgeContainer] Microphone access denied:', err));
    }
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      stopVisualization();
    };
  }, [status, startVisualization, stopVisualization, stream]);

  // Forward audio data to bridge
  useEffect(() => {
    if (status === 'connected') {
      setMicLevel(micLevel);
      if (timeDomainData) setTimeDomainData(timeDomainData);
      if (frequencyData) setFrequencyData(frequencyData);
    }
  }, [micLevel, timeDomainData, frequencyData, setMicLevel, setTimeDomainData, setFrequencyData, status]);

  const handleConnect = useCallback(() => {
    if (status === 'disconnected' || status === 'error') connect();
    else if (status === 'connected') disconnect();
  }, [status, connect, disconnect]);

  const handleRecord = useCallback(async () => {
    if (status !== 'connected' || isMuted) return;
    startRecording();
    try { await navigator.mediaDevices.getUserMedia({ audio: true }); } catch {}
  }, [status, isMuted, startRecording]);

  const handleStop = useCallback(() => stopRecording(), [stopRecording]);

  const handleMuteToggle = useCallback(() => {
    toggleMute();
    if (!isMuted && streamRef.current) {
      streamRef.current.getAudioTracks().forEach(track => track.enabled = false);
    } else if (isMuted && streamRef.current) {
      streamRef.current.getAudioTracks().forEach(track => track.enabled = true);
    }
  }, [isMuted, toggleMute]);

  const handleSettingsOpen = useCallback(() => setIsSettingsOpen(true), []);
  const handleSettingsClose = useCallback(() => setIsSettingsOpen(false), []);
  const handleSettingsChange = useCallback((s: Partial<typeof settings>) => updateSettings(s), [updateSettings]);
  const handleClearTranscripts = useCallback(() => clearTranscripts(), [clearTranscripts]);

  const getVisualizationColor = (state: VoiceState): string => {
    switch (state) {
      case 'listening': return '#3b82f6';
      case 'speaking': return '#059669';
      case 'processing': return '#7c3aed';
      case 'error': return '#dc2626';
      case 'muted': return '#9ca3af';
      default: return '#64748b';
    }
  };

  const vizColor = getVisualizationColor(voiceState);
  const showVisualization = voiceState === 'listening' || voiceState === 'speaking';
  const isBusy = status === 'connecting' || status === 'reconnecting';

  return (
    <div className={`h-full flex flex-col bg-[var(--c-canvas)] transition-colors duration-200 ${className}`}>
      {/* ── Header ── */}
      <div className="flex-shrink-0 bg-[var(--c-panel)] border-b border-[var(--c-hairline)] shadow-sm dark:shadow-none sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-blue-500/25 dark:shadow-blue-900/40">
              <Mic className="w-5 h-5 text-white" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-[var(--color-text-primary)] leading-tight">Voice Bridge</h1>
              <p className="text-xs text-[var(--color-text-muted)] truncate">Talk to Agentium in real time</p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            <ConnectionStatusCompact status={status} />
            <button
              onClick={handleConnect}
              disabled={isBusy}
              className={
                status === 'connected'
                  ? 'inline-flex items-center justify-center gap-2 px-4 py-2 bg-[var(--c-subtle)] hover:bg-[var(--c-hairline)] dark:bg-[var(--c-panel-2)] dark:hover:bg-[var(--c-hairline)] text-[var(--color-text-secondary)] dark:text-[var(--color-text-muted)] text-sm font-medium rounded-lg transition-colors duration-150'
                  : 'inline-flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm dark:shadow-blue-900/30'
              }
            >
              {isBusy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {status === 'connected' ? 'Disconnect' : isBusy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Three.js Canvas ── */}
      <div className="flex-1 overflow-hidden relative">
        <Suspense fallback={
          <div className="absolute inset-0 flex items-center justify-center bg-[var(--c-canvas)]">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-label="Loading 3D visualization" />
          </div>
        }>
          <ThreeScene
            voiceState={voiceState}
            micLevel={micLevel}
            timeDomainData={timeDomainData ?? null}
            frequencyData={frequencyData ?? null}
            status={status}
            prefersReduced={prefersReduced}
          />
        </Suspense>
      </div>

      {/* ── Transcript Panel ── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        className="flex-shrink-0 w-full max-w-2xl mx-auto px-6 pb-8"
      >
        <div className="rounded-2xl border border-[var(--c-hairline)] bg-[var(--c-panel)] shadow-sm dark:shadow-none overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--c-hairline)]">
            <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Conversation</h2>
            {transcripts.length > 0 && (
              <button
                onClick={handleClearTranscripts}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:text-red-600 dark:hover:text-red-400 transition-colors duration-150"
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                Clear
              </button>
            )}
          </div>
          <TranscriptDisplay transcripts={transcripts} maxHeight={320} className="p-4" />
        </div>
      </motion.div>

      {/* ── Controls ── */}
      <div className="flex-shrink-0 bg-[var(--c-panel)] border-t border-[var(--c-hairline)] px-6 py-5">
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