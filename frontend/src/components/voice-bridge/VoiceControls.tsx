import { useState, useCallback, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Mic, MicOff, Settings, X, Volume2, VolumeX } from 'lucide-react';
import type { VoiceControlsProps, VoiceState } from './types';

const BUTTON_VARIANTS = {
  primary: {
    base: 'w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300',
    idle: 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/40',
    recording: 'bg-gradient-to-br from-red-500 to-red-600 text-white shadow-lg shadow-red-500/40 animate-pulse-ring',
    processing: 'bg-gradient-to-br from-amber-500 to-amber-600 text-white shadow-lg shadow-amber-500/40 opacity-70',
    disabled: 'bg-gray-800 text-gray-500 cursor-not-allowed',
  },
  secondary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    active: 'bg-white/10 text-white border border-white/20 backdrop-blur-md',
    inactive: 'bg-white/5 text-gray-400 border border-white/10 backdrop-blur-md hover:bg-white/10 hover:text-white hover:border-white/20',
    muted: 'bg-red-500/20 text-red-400 border border-red-500/30',
    disabled: 'bg-white/5 text-gray-600 border border-white/5 cursor-not-allowed',
  },
  tertiary: {
    base: 'w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200',
    default: 'bg-white/5 text-gray-400 border border-white/10 backdrop-blur-md hover:bg-white/10 hover:text-white hover:border-white/20',
    active: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
    disabled: 'bg-white/5 text-gray-600 border border-white/5 cursor-not-allowed',
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
  active: { scale: 1, backgroundColor: 'rgba(255,255,255,0.1)' },
  inactive: { scale: 1, backgroundColor: 'rgba(255,255,255,0.05)' },
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
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isSettingsOpen) {
          setIsSettingsOpen(false);
        } else if (onClose) {
          onClose();
        }
      }
      if (e.key === ' ' || e.key === 'Enter') {
        const target = e.target as HTMLButtonElement;
        if (target.tagName === 'BUTTON' && !target.disabled) {
          target.click();
        }
      }
    },
    [isSettingsOpen, onClose]
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isSettingsOpen) {
        setIsSettingsOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isSettingsOpen]);

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
          <motion.div
            animate={isRecording && !prefersReduced ? pulseRingVariants : undefined}
            style={{
              position: 'absolute',
              inset: -4,
              borderRadius: '50%',
              border: '2px solid currentColor',
              pointerEvents: 'none',
            }}
            aria-hidden="true"
          />
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
          onClick={() => setIsSettingsOpen(true)}
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
        className="text-center text-sm text-gray-400 max-w-md px-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        aria-live="polite"
        aria-atomic="true"
      >
        {!isConnected
          ? 'Voice bridge disconnected. Click to connect.'
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

      {isSettingsOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={() => setIsSettingsOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="voice-settings-title"
        >
          <motion.div
            className="w-full max-w-md bg-slate-900/95 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl overflow-hidden"
            initial={{ opacity: 0, y: '100%' }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: '100%' }}
            transition={{ type: prefersReduced ? 'tween' : 'spring', stiffness: 300, damping: 30, duration: 0.4 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
              <h2 id="voice-settings-title" className="text-lg font-semibold text-white">
                Voice Settings
              </h2>
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Close settings"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
              <div className="space-y-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={isMuted}
                    onChange={onMuteToggle}
                    disabled={!isConnected}
                    className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-white">Mute Microphone</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={voiceState === 'listening'}
                    onChange={() => {}}
                    disabled
                    className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-white">Wake Word Detection</span>
                </label>

                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    defaultChecked
                    className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-white">Auto-stop on Silence</span>
                </label>
              </div>

              <div className="space-y-4 pt-4 border-t border-white/10">
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Voice Output</h3>
                <div className="space-y-2">
                  <label className="block text-sm text-gray-300 mb-1">TTS Voice</label>
                  <select
                    className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
                    defaultValue="af_bella"
                  >
                    <option value="af_bella">Bella (Female)</option>
                    <option value="am_adam">Adam (Male)</option>
                    <option value="bf_emma">Emma (British Female)</option>
                    <option value="bm_george">George (British Male)</option>
                    <option value="af_nicole">Nicole (Female)</option>
                    <option value="af_sarah">Sarah (Female)</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm text-gray-300 mb-1">Speech Rate</label>
                  <input
                    type="range"
                    min="0.5"
                    max="2"
                    step="0.1"
                    defaultValue="1"
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
                  />
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>0.5x</span>
                    <span>1x</span>
                    <span>2x</span>
                  </div>
                </div>
              </div>

              <div className="space-y-4 pt-4 border-t border-white/10">
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Advanced</h3>
                <div className="space-y-2">
                  <label className="block text-sm text-gray-300 mb-1">VAD Sensitivity</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    defaultValue="0.5"
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
                  />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm text-gray-300 mb-1">Auto-stop Delay (ms)</label>
                  <input
                    type="range"
                    min="500"
                    max="3000"
                    step="100"
                    defaultValue="1000"
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="px-6 py-2.5 rounded-xl text-sm font-medium text-white bg-slate-800 border border-white/10 hover:bg-slate-700 transition-colors"
              >
                Done
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}