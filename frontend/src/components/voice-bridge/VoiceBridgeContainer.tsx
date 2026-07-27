import { useState, useEffect, useCallback, useRef, Suspense, lazy } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Loader2, AlertCircle, Trash2, Settings, MicOff, Volume2, MessageSquare, Copy } from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { TranscriptDrawer } from './TranscriptDrawer';
import { TranscriptDisplay } from './TranscriptDisplay';
import { VoiceControls } from './VoiceControls';
import { VoiceSettings } from './VoiceSettings';
import { useVoiceBridge } from './hooks/useVoiceBridge';
import { useAudioVisualization } from './hooks/useAudioVisualization';
import { useReducedMotion } from './hooks/useReducedMotion';
import { useBreakpoint } from './hooks/useBreakpoint';
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
      staggerChildren: 0.08,
      delayChildren: 0.15,
    },
  },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring' as const, stiffness: 300, damping: 30 },
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
  const breakpoint = useBreakpoint();

  // Responsive breakpoints
  const isMobile = breakpoint === 'mobile';
  const isTablet = breakpoint === 'tablet';
  const isDesktopSm = breakpoint === 'desktop-sm';
  const isDesktopLg = breakpoint === 'desktop-lg';

  // Orb size: 80vw on mobile, fixed on larger screens
  const orbSize = isMobile ? Math.min(window.innerWidth * 0.8, window.innerHeight * 0.5) : 320;

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
      className={`h-screen w-full flex bg-[var(--c-canvas)] transition-colors duration-200 ${className}`}
    >
      {/* === CANVAS LAYER (fixed, inset-0, z-0) === */}
      <div className="fixed inset-0 z-0" data-testid="canvas-layer">
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

        {/* The visualization - responsive orb size */}
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            padding: isMobile ? '40px 20px' : 0,
          }}
        >
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
              orbSize={orbSize}
            />
          </Suspense>
        </div>
      </div>

      {/* === FLOATING GLASS PANELS (z-20, absolute) === */}

      {/* Status Badge (Top-Right) */}
      <StatusBadge status={status} voiceState={voiceState} />

      {/* Transcript Drawer (Bottom-Left) - responsive positioning handled internally */}
      <TranscriptDrawer transcripts={transcripts} />

      {/* Controls Pill (Bottom-Center) - responsive */}
      <motion.div
        className={`fixed z-20 transition-all duration-300 ${
          isMobile
            ? 'bottom-4 left-1/2 -translate-x-1/2'
            : isTablet
            ? 'bottom-20 left-1/2 -translate-x-1/2'
            : 'bottom-6 left-1/2 -translate-x-1/2'
        }`}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.4 }}
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
          reducedMotion={prefersReduced}
          glassPill={true}
          condensed={isMobile}
        />
      </motion.div>

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