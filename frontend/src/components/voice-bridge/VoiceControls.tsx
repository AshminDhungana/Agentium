import { useCallback } from 'react';
import { motion } from 'framer-motion';
import { Mic, Settings, Volume2, VolumeX } from 'lucide-react';
import type { VoiceControlsProps } from './types';

const BUTTON_VARIANTS = {
  primary: {
    base: 'relative w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300',
    idle: 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/40',
    recording: 'bg-gradient-to-br from-red-500 to-red-600 text-white shadow-lg shadow-red-500/40 animate-pulse-ring',
    processing: 'bg-gradient-to-br from-amber-500 to-amber-600 text-white shadow-lg shadow-amber-500/40 opacity-70',
    disabled: 'bg-gray-200 dark:bg-gray-800 text-gray-400 dark:text-gray-500 cursor-not-allowed',
  },
  secondary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    active: 'bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347]',
    muted: 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 border border-red-300 dark:border-red-500/30',
    disabled: 'bg-gray-100 dark:bg-[#1e2535]/60 text-gray-400 dark:text-gray-600 border border-gray-200 dark:border-[#1e2535] cursor-not-allowed',
  },
  tertiary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    default: 'bg-gray-100 dark:bg-[#1e2535] text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] hover:text-gray-900 dark:hover:text-white',
    disabled: 'bg-gray-100 dark:bg-[#1e2535]/60 text-gray-400 dark:text-gray-600 border border-gray-200 dark:border-[#1e2535] cursor-not-allowed',
  },
};

const pulseRingVariants = {
  initial: { boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.4)' },
  animate: { boxShadow: '0 0 0 30px rgba(239, 68, 68, 0)' },
  transition: { duration: 1.5, repeat: Infinity, ease: 'easeOut' as const },
} as const;

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
  hover: { rotate: 30, transition: { type: 'spring' as const, stiffness: 400, damping: 20 } },
  tap: { rotate: 0, scale: 0.9 },
};

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
}: VoiceControlsProps) {
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

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

  return (
    <div
      className={`flex flex-col items-center gap-6 ${className}`}
      onKeyDown={handleKeyDown}
      role="group"
      aria-label="Voice controls"
    >
      <motion.div
        className="flex items-center gap-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1, type: prefersReduced ? 'tween' : 'spring', stiffness: 100, damping: 20 }}
      >
        <motion.button
          className={getMuteButtonClass()}
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
          style={{ transition: prefersReduced ? 'none' : undefined }}
        >
          {isMuted ? (
            <VolumeX className="w-5 h-5" aria-hidden="true" />
          ) : (
            <Volume2 className="w-5 h-5" aria-hidden="true" />
          )}
        </motion.button>

        <motion.button
          className={getPrimaryButtonClass()}
          onClick={handleRecordClick}
          disabled={!isConnected}
          aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          aria-pressed={isRecording}
          variants={buttonTapVariants}
          whileTap="tap"
          whileHover={isConnected && !isRecording ? 'hover' : undefined}
          whileFocus="focus"
          style={{ transition: prefersReduced ? 'none' : undefined }}
        >
          {isRecording && (
            <motion.div
              animate={!prefersReduced ? pulseRingVariants : undefined}
              style={{
                position: 'absolute',
                inset: -4,
                borderRadius: '50%',
                border: '2px solid currentColor',
                pointerEvents: 'none',
              }}
              aria-hidden="true"
            />
          )}
          {isRecording ? (
            <motion.div
              className="w-8 h-8 rounded bg-white"
              animate={{ scale: prefersReduced ? 1 : [1, 0.8, 1] }}
              transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
              aria-hidden="true"
            />
          ) : voiceState === 'processing' || voiceState === 'speaking' ? (
            <motion.div
              className="w-8 h-8"
              animate={{ rotate: prefersReduced ? 0 : 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              aria-hidden="true"
            >
              <svg className="w-full h-full text-current" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                <path d="M12 2a10 10 0 0 1 10 10" strokeLinecap="round" strokeOpacity="1" />
              </svg>
            </motion.div>
          ) : (
            <Mic className="w-8 h-8" aria-hidden="true" />
          )}
        </motion.button>

        <motion.button
          className={getSettingsButtonClass()}
          onClick={onSettings}
          disabled={!isConnected}
          aria-label="Open voice settings"
          variants={settingsButtonVariants}
          whileHover="hover"
          whileTap="tap"
          style={{ transition: prefersReduced ? 'none' : undefined }}
        >
          <Settings className="w-5 h-5" aria-hidden="true" />
        </motion.button>
      </motion.div>

      <motion.p
        className="text-center text-sm text-gray-600 dark:text-gray-400 max-w-md px-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        aria-live="polite"
        aria-atomic="true"
      >
        {!isConnected
          ? 'Voice bridge disconnected. Click connect above to start.'
          : isMuted
          ? 'Microphone muted'
          : isRecording
          ? 'Listening... Speak now'
          : voiceState === 'processing'
          ? 'Processing...'
          : voiceState === 'speaking'
          ? 'Speaking...'
          : voiceState === 'idle'
          ? 'Tap the mic or say "Hey Agentium" to start'
          : 'Ready'}
      </motion.p>
    </div>
  );
}