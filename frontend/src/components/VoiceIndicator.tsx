/**
 * VoiceIndicator.tsx — Compact status badge shown in MainLayout's sidebar footer.
 * Reflects the current voice bridge connection state.
 */

import { Mic, MicOff, Loader2 } from 'lucide-react';
import { useVoiceBridge } from '@/hooks/useVoiceBridge';
import { BridgeStatus } from '@/services/voiceBridge';

const STATUS_CONFIG: Record<BridgeStatus, { label: string; color: string; pulse: boolean }> = {
  offline:    { label: 'Voice offline',   color: 'text-gray-400 dark:text-gray-500',  pulse: false },
  connecting: { label: 'Connecting…',     color: 'text-yellow-500 dark:text-yellow-400', pulse: true  },
  connected:  { label: 'Voice ready',     color: 'text-green-500 dark:text-green-400',  pulse: false },
  error:      { label: 'Voice error',     color: 'text-red-500 dark:text-red-400',      pulse: false },
};

export function VoiceIndicator() {
  const { status } = useVoiceBridge();
  const cfg = STATUS_CONFIG[status];

  return (
    <div
      className={`flex items-center gap-1.5 text-xs font-medium ${cfg.color}`}
      title={`Voice bridge: ${cfg.label}`}
    >
      {status === 'connecting' ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : status === 'offline' || status === 'error' ? (
        <MicOff className="w-3.5 h-3.5" />
      ) : (
        <span className="relative flex h-2 w-2 items-center">
          {cfg.pulse && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
          )}
          <Mic className="w-3.5 h-3.5" />
        </span>
      )}
      <span className="hidden sm:inline">{cfg.label}</span>
    </div>
  );
}