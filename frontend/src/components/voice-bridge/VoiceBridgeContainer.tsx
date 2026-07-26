import { useState, useEffect, useCallback, useRef, Suspense, lazy } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Loader2, AlertCircle, Trash2, Settings, MicOff, Volume2, MessageSquare, Copy } from 'lucide-react';
import { ConnectionStatusCompact } from './ConnectionStatus';
import { TranscriptDisplay } from './TranscriptDisplay';
import { VoiceControls } from './VoiceControls';
import { VoiceSettings } from './VoiceSettings';
import { useVoiceBridge } from './hooks/useVoiceBridge';
import { useAudioVisualization } from './hooks/useAudioVisualization';
import { useReducedMotion } from './hooks/useReducedMotion';
import type { VoiceState } from './types';
import type { ConnectionStatus } from './types';
import { WidgetCard } from '@/components/dashboard/WidgetCard';
import { EmptyState } from '@/components/ui/EmptyState';

// Lazy-load ThreeScene for code splitting
const ThreeScene = lazy(() => import('./ThreeScene').then(m => ({ default: m.ThreeScene })));

// Page-level staggered motion variants
const pageVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring' as const, stiffness: 300, damping: 30 }
  },
};

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

  // Status color from CSS variables
  const getStatusColor = useCallback((status: ConnectionStatus): string => {
    const style = getComputedStyle(document.documentElement);
    switch (status) {
      case 'connected': return style.getPropertyValue('--c-success').trim() || '#10b981';
      case 'connecting': return style.getPropertyValue('--c-warning').trim() || '#f59e0b';
      case 'reconnecting': return style.getPropertyValue('--c-voice-listening').trim() || '#3b82f6';
      case 'error': return style.getPropertyValue('--c-error').trim() || '#ef4444';
      default: return style.getPropertyValue('--color-text-muted').trim() || '#64748b';
    }
  }, []);

  const statusColor = getStatusColor(status);
  const isConnected = status === 'connected';
  const isConnecting = status === 'connecting' || status === 'reconnecting';
  const isError = status === 'error';
  const isBusy = status === 'connecting' || status === 'reconnecting';

  return (
    <motion.div
      data-testid="page-motion-wrapper"
      variants={pageVariants}
      initial="hidden"
      animate="visible"
      className={`h-full flex flex-col bg-[var(--c-canvas)] transition-colors duration-200 ${className}`}
    >
      {/* ── Header ── */}
      <motion.header
        data-testid="voice-bridge-header"
        variants={sectionVariants}
        className="flex-shrink-0 bg-[var(--c-glass-bg)] border-b border-[var(--c-glass-border)] backdrop-blur-xl sticky top-0 z-10"
      >
        <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          {/* Brand with gradient orb */}
          <motion.div
            data-testid="voice-bridge-brand-orb"
            initial={{ opacity: 0, scale: 0.8, rotate: -15 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, var(--c-voice-listening), var(--c-voice-speaking))',
              boxShadow: '0 4px 20px var(--c-voice-glow)',
            }}
          >
            <Mic className="w-5 h-5 text-white" aria-hidden="true" />
          </motion.div>
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.05 }}
            className="min-w-0"
          >
            <h1 className="text-base font-semibold text-[var(--color-text-primary)] leading-tight">Voice Bridge</h1>
            <p className="text-xs text-[var(--color-text-muted)] truncate">Talk to Agentium in real time</p>
          </motion.div>

          {/* Connection status + connect button */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
            className="flex items-center gap-3 flex-shrink-0"
          >
            {/* 3D-style status dot (pure CSS) */}
            <div className="flex items-center gap-2">
              <motion.span
                data-testid="connection-status-dot"
                className="relative w-3 h-3 rounded-full"
                style={{
                  backgroundColor: statusColor,
                  boxShadow: `0 0 8px ${statusColor}, 0 0 16px ${statusColor}40`,
                }}
                animate={isConnecting || isError ? {
                  boxShadow: [
                    `0 0 8px ${statusColor}`,
                    `0 0 16px ${statusColor}80`,
                    `0 0 8px ${statusColor}`
                  ],
                  transition: { duration: 1.5, repeat: Infinity }
                } : {}}
                aria-hidden="true"
              />
              <span className="text-xs font-medium text-[var(--color-text-secondary)] capitalize">
                {status === 'reconnecting' ? 'Reconnecting' : status}
              </span>
            </div>

            <motion.button
              onClick={handleConnect}
              disabled={isBusy}
              className={`
                inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-150
                ${isConnected
                  ? 'bg-[var(--c-subtle)] hover:bg-[var(--c-hairline)] dark:bg-[var(--c-panel-2)] dark:hover:bg-[var(--c-hairline)] text-[var(--color-text-secondary)] dark:text-[var(--color-text-muted)]'
                  : 'bg-[var(--c-brand)] hover:bg-[var(--color-primary-hover)] text-white shadow-sm dark:shadow-[0_4px_14px_var(--c-brand)/30]'
                }
              `}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              style={{ transition: prefersReduced ? 'none' : undefined }}
            >
              {isBusy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {status === 'connected' ? 'Disconnect' : isBusy ? 'Connecting…' : 'Connect'}
            </motion.button>
          </motion.div>
        </div>
      </motion.header>

      {/* ── Three.js Canvas ── */}
      <motion.section
        data-testid="visualization-section"
        variants={sectionVariants}
        className="relative flex-1 overflow-hidden"
      >
        {/* Depth layer 1: Radial glow matching voice state */}
        <motion.div
          data-testid="viz-radial-glow"
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at center, var(--c-voice-glow) 0%, transparent 70%)`,
            opacity: voiceState === 'listening' || voiceState === 'speaking' ? 1 : 0.3,
          }}
          animate={{ opacity: voiceState === 'listening' || voiceState === 'speaking' ? 1 : 0.3 }}
          transition={{ duration: 300, ease: 'easeOut' }}
        />

        {/* Depth layer 2: Dot grid (matches AgentsPage) */}
        <div
          data-testid="viz-dot-grid"
          className="absolute inset-0 pointer-events-none opacity-[0.06]"
          style={{
            backgroundImage: 'radial-gradient(circle, var(--c-hairline) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />

        {/* Depth layer 3: Vignette fade top */}
        <div
          data-testid="viz-vignette-top"
          className="absolute inset-0 pointer-events-none bg-gradient-to-t from-[var(--c-canvas)]/60 via-transparent to-transparent"
        />

        {/* Depth layer 4: Vignette fade bottom */}
        <div
          data-testid="viz-vignette-bottom"
          className="absolute inset-0 pointer-events-none bg-gradient-to-b from-[var(--c-canvas)]/60 via-transparent to-transparent"
        />

        {/* The visualization */}
        <Suspense fallback={
          <div data-testid="viz-loading-fallback" className="absolute inset-0 flex items-center justify-center bg-[var(--c-canvas)]">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--c-brand)]" aria-label="Loading 3D visualization" />
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
      </motion.section>

      {/* ── Transcript Panel ── */}
      <motion.section
        data-testid="transcript-section"
        variants={sectionVariants}
        className="flex-shrink-0 w-full max-w-2xl mx-auto px-6 pb-8"
      >
        <WidgetCard
          data-testid="transcript-widget-card"
          title="Conversation"
          icon={MessageSquare}
          className="h-[320px] flex flex-col"
          action={
            transcripts.length > 0 && (
              <motion.button
                onClick={handleClearTranscripts}
                className="p-1.5 rounded-lg bg-[var(--c-subtle)] hover:bg-[var(--c-hairline)] dark:bg-[var(--c-panel-2)] dark:hover:bg-[var(--c-hairline)] text-[var(--color-text-muted)] hover:text-[var(--c-error)] transition-colors"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                aria-label="Clear transcript"
              >
                <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
              </motion.button>
            )
          }
        >
          <TranscriptDisplay transcripts={transcripts} maxHeight={280} className="flex-1" />

          {/* Scroll shadow hint */}
          <div className="relative">
            <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-[var(--c-panel)] to-transparent pointer-events-none" />
          </div>
        </WidgetCard>
      </motion.section>

      {/* ── Controls ── */}
      <motion.section
        data-testid="controls-section"
        variants={sectionVariants}
        className="flex-shrink-0"
      >
        <div className="max-w-2xl mx-auto px-6 pb-6">
          <div data-testid="controls-glass-pill" className="relative">
            {/* Glass pill background */}
            <div className="absolute inset-0 bg-[var(--c-glass-bg)] border border-[var(--c-glass-border)] rounded-3xl backdrop-blur-2xl shadow-2xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)]" />

            {/* Actual controls */}
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
              className="relative z-10 px-4 py-4"
            />
          </div>
        </div>
      </motion.section>

      <VoiceSettings
        isOpen={isSettingsOpen}
        onClose={handleSettingsClose}
        settings={settings}
        onSettingsChange={handleSettingsChange}
        availableInputDevices={availableInputDevices}
        availableOutputDevices={availableOutputDevices}
      />
    </motion.div>
  );
}