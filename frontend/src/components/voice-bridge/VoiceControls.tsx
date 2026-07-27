import { useCallback, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Settings, Volume2, VolumeX, Loader2, AlertCircle, MicOff, AudioWaveform } from 'lucide-react';
import type { VoiceControlsProps } from './types';

const BUTTON_VARIANTS = {
  primary: {
    base: 'relative w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300',
    idle: 'bg-[var(--c-brand)] text-white shadow-lg shadow-[var(--c-brand)]/40',
    recording: 'bg-[var(--c-error)] text-white shadow-lg shadow-[var(--c-error)]/40',
    processing: 'bg-[var(--c-warning)] text-white shadow-lg shadow-[var(--c-warning)]/40 opacity-70',
    disabled: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)] text-[var(--color-text-muted)] cursor-not-allowed',
  },
  secondary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    active: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)] text-[var(--color-text-secondary)] dark:text-[var(--color-text-muted)] border border-[var(--c-hairline)] hover:bg-[var(--c-hairline)] dark:hover:bg-[var(--c-subtle-dark)]',
    muted: 'bg-[var(--c-error)]/15 dark:bg-[var(--c-error)]/20 text-[var(--c-error)] dark:text-[var(--c-error-light)] border border-[var(--c-error)]/30 dark:border-[var(--c-error)]/40',
    disabled: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)]/60 text-[var(--color-text-muted)] dark:text-[var(--color-text-muted)] border border-[var(--c-hairline)] dark:border-[var(--c-subtle-dark)] cursor-not-allowed',
  },
  tertiary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    default: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)] text-[var(--color-text-muted)] dark:text-[var(--color-text-muted)] border border-[var(--c-hairline)] dark:border-[var(--c-subtle-dark)] hover:bg-[var(--c-hairline)] dark:hover:bg-[var(--c-subtle-dark)] hover:text-[var(--color-text-primary)] dark:hover:text-white',
    disabled: 'bg-[var(--c-subtle)] dark:bg-[var(--c-subtle-dark)]/60 text-[var(--color-text-muted)] dark:text-[var(--color-text-muted)] border border-[var(--c-hairline)] dark:border-[var(--c-subtle-dark)] cursor-not-allowed',
  },
};

// State-specific pulse ring colors
const PULSE_RING_COLORS: Record<string, string> = {
  idle: 'var(--c-brand)',
  listening: 'var(--c-voice-listening)',
  speaking: 'var(--c-voice-speaking)',
  processing: 'var(--c-voice-thinking)',
  error: 'var(--c-voice-error)',
  muted: 'var(--color-text-muted)',
};

// State-specific status messages
const STATUS_MESSAGES: Record<string, string> = {
  disconnected: 'Voice bridge disconnected. Click connect to start.',
  idle: 'Tap the mic or say "Hey Agentium" to start',
  listening: 'Listening… Speak now',
  speaking: 'Speaking response',
  processing: 'Thinking…',
  error: 'Error occurred. Try again',
  muted: 'Microphone muted',
};

// SVG path definitions for morphing icons
const ICON_PATHS = {
  mic: 'M12 2a3 3 0 0 1 3 3v11a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3zM19 10v2a7 7 0 0 1-14 0v-2',
  waveform: 'M4 13a2 2 0 0 1 2-2h1M4 10a7 7 0 0 1 14 0',
  loader: 'M12 2v1M12 21v1M2 12h1M21 12h1M4.93 4.93l.71.71M18.36 18.36l.71.71M2 12h1M21 12h1',
  alert: 'M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z',
  micOff: 'M10.7 7.7a3 3 0 0 1 4.24 4.24M9 9v3a3 3 0 0 0 5.12 2.12M15 5.5A3 3 0 0 1 18 8.5M1 1l22 22M9 19v-5',
};

interface LucideIconConfig {
  type: 'lucide';
  icon: any;
  path: string;
}

interface PathIconConfig {
  type: 'path';
  path: string;
  animate: boolean;
}

type IconConfig = LucideIconConfig | PathIconConfig;

const STATE_ICONS: Record<string, IconConfig> = {
  idle: { type: 'lucide', icon: Mic, path: ICON_PATHS.mic },
  listening: { type: 'path', path: ICON_PATHS.waveform, animate: true },
  speaking: { type: 'lucide', icon: AudioWaveform, path: ICON_PATHS.waveform },
  processing: { type: 'lucide', icon: Loader2, path: ICON_PATHS.loader },
  error: { type: 'lucide', icon: AlertCircle, path: ICON_PATHS.alert },
  muted: { type: 'lucide', icon: MicOff, path: ICON_PATHS.micOff },
};

const buttonTapVariants = {
  tap: { scale: 0.92 },
  hover: { scale: 1.05 },
  focus: { scale: 1.02 },
};

const secondaryButtonVariants = {
  active: { scale: 1 },
  inactive: { scale: 1 },
  tap: { scale: 0.9 },
  hover: { scale: 1.08 },
  focus: { scale: 1.04 },
};

const settingsButtonVariants = {
  initial: { rotate: 0 },
  hover: { rotate: 30, transition: { type: 'spring', stiffness: 400, damping: 20 } },
  tap: { rotate: 0, scale: 0.9 },
} as const;

const pulseRingVariants = {
  initial: { scale: 1, opacity: 0.6 },
  animate: { scale: 2, opacity: 0 },
  transition: { duration: 1.5, repeat: Infinity, ease: 'easeOut' },
} as const;

interface MorphingIconProps {
  state: keyof typeof STATE_ICONS;
  prefersReduced: boolean;
  className?: string;
}

function MorphingIcon({ state, prefersReduced, className = 'w-8 h-8' }: MorphingIconProps) {
  const iconConfig = STATE_ICONS[state] || STATE_ICONS.idle;

  if (iconConfig.type === 'lucide') {
    const Icon = iconConfig.icon;
    return (
      <motion.svg
        className={`${className} text-current`}
        aria-hidden="true"
        initial={false}
        animate={{ rotate: state === 'processing' && !prefersReduced ? 360 : 0 }}
        transition={{ duration: 1, repeat: state === 'processing' ? Infinity : 0, ease: 'linear' }}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={iconConfig.path} />
      </motion.svg>
    );
  }

  // For path-based icons (listening waveform)
  return (
    <motion.svg
      className={`${className} text-current`}
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <motion.path
        d={iconConfig.path}
        initial={false}
        animate={iconConfig.animate && !prefersReduced
          ? { pathLength: [0, 1, 0] }
          : {}}
        transition={{ duration: 1, repeat: iconConfig.animate ? Infinity : 0, ease: 'easeInOut' }}
      />
    </motion.svg>
  );
}

export function VoiceControls({
  voiceState,
  isConnected,
  isMuted,
  isRecording,
  onRecord,
  onStop,
  onMuteToggle,
  onSettings,
  onClose,
  reducedMotion = false,
  className = '',
  glassPill = false,
  condensed = false,
}: VoiceControlsProps) {
  const [prefersReduced, setPrefersReduced] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReduced(mediaQuery.matches);
    const handler = (e: MediaQueryListEvent) => setPrefersReduced(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  const isReduced = reducedMotion || prefersReduced;

  // Inject pulse ring CSS once
  useEffect(() => {
    const styleEl = document.createElement('style');
    styleEl.textContent = `
      @keyframes pulseRing {
        0% { transform: scale(1); opacity: 0.6; }
        100% { transform: scale(1.8); opacity: 0; }
      }
      .pulse-ring {
        animation: pulseRing 1.5s ease-out infinite;
      }
      @media (prefers-reduced-motion: reduce) {
        .pulse-ring { animation: none; }
      }
    `;
    document.head.appendChild(styleEl);
    return () => {
      document.head.removeChild(styleEl);
    };
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose?.();
      }
      if (e.key === ' ' || e.key === 'Enter') {
        const target = e.target as HTMLButtonElement;
        if (target.tagName === 'BUTTON' && !target.disabled) {
          target.click();
        }
      }
    },
    [onClose]
  );

  const getPrimaryButtonClass = () => {
    const base = BUTTON_VARIANTS.primary.base;
    if (!isConnected) return `${base} ${BUTTON_VARIANTS.primary.disabled}`;
    if (isRecording) return `${base} ${BUTTON_VARIANTS.primary.recording}`;
    if (voiceState === 'processing' || voiceState === 'speaking') return `${base} ${BUTTON_VARIANTS.primary.processing}`;
    return `${base} ${BUTTON_VARIANTS.primary.idle}`;
  };

  const getMuteButtonClass = () => {
    const base = BUTTON_VARIANTS.secondary.base;
    if (!isConnected) return `${base} ${BUTTON_VARIANTS.secondary.disabled}`;
    if (isMuted) return `${base} ${BUTTON_VARIANTS.secondary.muted}`;
    return `${base} ${BUTTON_VARIANTS.secondary.active}`;
  };

  const getSettingsButtonClass = () => {
    const base = BUTTON_VARIANTS.tertiary.base;
    if (!isConnected) return `${base} ${BUTTON_VARIANTS.tertiary.disabled}`;
    return `${base} ${BUTTON_VARIANTS.tertiary.default}`;
  };

  const handleRecordClick = () => {
    if (!isConnected) return;
    if (isRecording) {
      onStop?.();
    } else {
      onRecord?.();
    }
  };

  // Determine current status message
  const getStatusMessage = () => {
    if (!isConnected) return STATUS_MESSAGES.disconnected;
    if (isMuted) return STATUS_MESSAGES.muted;
    if (voiceState === 'processing') return STATUS_MESSAGES.processing;
    if (voiceState === 'speaking') return STATUS_MESSAGES.speaking;
    if (voiceState === 'listening' || isRecording) return STATUS_MESSAGES.listening;
    if (voiceState === 'error') return STATUS_MESSAGES.error;
    return STATUS_MESSAGES.idle;
  };

  // Determine pulse ring color
  const getPulseRingColor = () => PULSE_RING_COLORS[voiceState] || PULSE_RING_COLORS.idle;

  return (
    <>
      {glassPill && (
        <div
          data-testid="controls-glass-bg"
          className="absolute inset-0 bg-[var(--c-glass-bg)] border border-[var(--c-glass-border)] rounded-3xl backdrop-blur-2xl shadow-2xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.4)]"
        />
      )}
      <div
        className={`flex flex-col items-center gap-6 ${condensed ? 'flex-row gap-4' : ''} ${className}`}
        onKeyDown={handleKeyDown}
        role="group"
        aria-label="Voice controls"
      >
        <motion.div
          className={`flex items-center gap-4 ${condensed ? 'gap-3' : ''}`}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1, type: isReduced ? 'tween' : 'spring', stiffness: 100, damping: 20 }}
        >
          <motion.button
            className={`${getMuteButtonClass()} ${condensed ? 'w-10 h-10' : ''}`}
            onClick={onMuteToggle}
            disabled={!isConnected}
            aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
            aria-pressed={isMuted}
            variants={secondaryButtonVariants}
            initial="inactive"
            animate={isMuted ? 'inactive' : 'active'}
            whileTap="tap"
            whileHover="hover"
            whileFocus="focus"
            style={{ transition: isReduced ? 'none' : undefined }}
          >
            {isMuted ? (
              <VolumeX className={condensed ? 'w-4 h-4' : 'w-5 h-5'} aria-hidden="true" />
            ) : (
              <Volume2 className={condensed ? 'w-4 h-4' : 'w-5 h-5'} aria-hidden="true" />
            )}
          </motion.button>

          <motion.button
            className={`${getPrimaryButtonClass()} ${condensed ? 'w-16 h-16' : 'w-20 h-20'}`}
            onClick={handleRecordClick}
            disabled={!isConnected}
            aria-label={isRecording ? 'Stop recording' : 'Start recording'}
            aria-pressed={isRecording}
            variants={buttonTapVariants}
            whileTap="tap"
            whileHover={isConnected && !isRecording ? 'hover' : undefined}
            whileFocus="focus"
            style={{ transition: isReduced ? 'none' : undefined }}
          >
            {isRecording ? (
              <>
                <motion.div
                  data-testid="record-pulse-ring"
                  className={`pulse-ring absolute inset-0 rounded-full border-2 ${condensed ? 'inset-[-2px]' : ''}`}
                  style={{ borderColor: 'var(--c-error)', pointerEvents: 'none' }}
                  animate={!isReduced ? {} : { opacity: 0 }}
                  aria-hidden="true"
                />
                <motion.div
                  className={`w-8 h-8 rounded bg-white ${condensed ? 'w-6 h-6' : ''}`}
                  animate={{ scale: isReduced ? 1 : [1, 0.8, 1] }}
                  transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
                  aria-hidden="true"
                />
              </>
            ) : voiceState === 'processing' || voiceState === 'speaking' ? (
              <motion.svg
                className={`w-8 h-8 text-current ${condensed ? 'w-6 h-6' : ''}`}
                animate={{ rotate: isReduced ? 0 : 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeOpacity="1" />
              </motion.svg>
            ) : (
              <AnimatePresence mode="wait">
                <MorphingIcon key={voiceState} state={voiceState} prefersReduced={isReduced} className={condensed ? 'w-6 h-6' : 'w-8 h-8'} />
              </AnimatePresence>
            )}
          </motion.button>

          <motion.button
            className={`${getSettingsButtonClass()} ${condensed ? 'w-10 h-10' : ''}`}
            onClick={onSettings}
            disabled={!isConnected}
            aria-label="Open voice settings"
            variants={settingsButtonVariants}
            whileHover={{ rotate: isReduced ? 0 : 30, transition: { type: 'spring', stiffness: 400, damping: 20 } }}
            whileTap={{ rotate: 0, scale: 0.9 }}
            style={{ transition: isReduced ? 'none' : undefined }}
          >
            <Settings className={condensed ? 'w-4 h-4' : 'w-5 h-5'} aria-hidden="true" />
          </motion.button>
        </motion.div>

        <AnimatePresence mode="wait">
          <motion.p
            key={voiceState + (isMuted ? '-muted' : '') + (!isConnected ? '-disconnected' : '')}
            role="status"
            className={`text-center text-sm text-[var(--color-text-secondary)] max-w-md px-4 flex items-center justify-center gap-2 ${condensed ? 'hidden' : ''}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            aria-live="polite"
            aria-atomic="true"
          >
            <AnimatePresence mode="wait">
              <MorphingIcon
                key={`icon-${voiceState}`}
                state={isMuted ? 'muted' : !isConnected ? 'idle' : voiceState}
                prefersReduced={isReduced}
                className="w-5 h-5 flex-shrink-0"
              />
            </AnimatePresence>
            <span>{getStatusMessage()}</span>
          </motion.p>
        </AnimatePresence>
      </div>
    </>
  );
}