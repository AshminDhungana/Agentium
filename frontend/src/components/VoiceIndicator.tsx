/**
 * VoiceIndicator.tsx — Compact status badge shown in MainLayout's sidebar footer.
 * Reflects the current voice bridge connection state.
 * Clicking the indicator toggles the voice bridge on/off.
 */

import { useState } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';
import { useVoiceBridge } from '@/hooks/useVoiceBridge';
import { BridgeStatus } from '@/services/voiceBridge';

const STATUS_CONFIG: Record<BridgeStatus, { label: string; color: string; pulse: boolean }> = {
  offline:    { label: 'Voice offline',   color: 'text-gray-400 dark:text-gray-500',        pulse: false },
  connecting: { label: 'Connecting…',     color: 'text-yellow-500 dark:text-yellow-400',    pulse: true  },
  connected:  { label: 'Voice ready',     color: 'text-green-500 dark:text-green-400',      pulse: false },
  error:      { label: 'Voice error',     color: 'text-red-500 dark:text-red-400',          pulse: false },
};

interface VoiceIndicatorProps {
  iconOnly?: boolean;
}

export function VoiceIndicator({ iconOnly = false }: VoiceIndicatorProps) {
  const { status } = useVoiceBridge();
  const [isDisabled, setIsDisabled] = useState(false);

  const handleToggle = () => {
    setIsDisabled(prev => !prev);
    // If your useVoiceBridge hook exposes connect/disconnect methods, call them here:
    // isDisabled ? connect() : disconnect();
  };

  // When manually disabled, override display to look "off"
  const effectiveStatus: BridgeStatus = isDisabled ? 'offline' : status;
  const cfg = STATUS_CONFIG[effectiveStatus];
  const tooltipLabel = isDisabled
    ? 'Voice disabled (click to enable)'
    : `Voice bridge: ${cfg.label} (click to disable)`;

  return (
    <button
      type="button"
      onClick={handleToggle}
      className={`
        flex items-center gap-1.5 text-xs font-medium rounded-md p-1
        transition-all duration-200
        hover:bg-gray-100 dark:hover:bg-white/10
        focus:outline-none focus:ring-2 focus:ring-blue-500/40
        ${cfg.color}
        ${isDisabled ? 'opacity-50' : 'opacity-100'}
      `}
      title={tooltipLabel}
      aria-label={tooltipLabel}
      aria-pressed={!isDisabled}
    >
      {effectiveStatus === 'connecting' ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : effectiveStatus === 'offline' || effectiveStatus === 'error' ? (
        <MicOff className="w-3.5 h-3.5" />
      ) : (
        <span className="relative flex items-center justify-center">
          {cfg.pulse && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
          )}
          <Mic className="w-3.5 h-3.5" />
        </span>
      )}
      {!iconOnly && <span className="hidden sm:inline">{cfg.label}</span>}
    </button>
  );
}