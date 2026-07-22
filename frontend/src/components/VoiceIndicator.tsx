import { useState, useEffect, useRef, useCallback, useMemo, useReducer } from 'react';
import { createPortal } from 'react-dom';
import { Mic, MicOff, ChevronDown } from 'lucide-react';
import { VoiceDropdownPanel } from './VoiceDropdownPanel';
import { voiceBridgeService, BridgeStatus, VoiceState } from '@/services/voiceBridge';
import { useAuthStore } from '@/store/authStore';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

const STATUS_CFG: Record<BridgeStatus, { label: string; color: string; ringColor: string }> = {
  offline:    { label: 'Voice offline',  color: 'text-gray-500', ringColor: 'border-gray-500/30' },
  connecting: { label: 'Connecting\u2026',    color: 'text-amber-400', ringColor: 'border-amber-400/50' },
  connected:  { label: 'Voice ready',    color: 'text-emerald-400', ringColor: 'border-emerald-400/50' },
  error:      { label: 'Voice error',    color: 'text-red-400', ringColor: 'border-red-400/50' },
};

const VOICE_STATE_RING: Record<string, string> = {
  idle: 'border-blue-500/20',
  listening: 'border-blue-500/60',
  thinking: 'border-purple-500/60',
  speaking: 'border-emerald-500/60',
  interrupted: 'border-amber-500/60',
};

type Platform = 'windows' | 'macos' | 'linux' | 'unknown';

function getPlatform(): Platform {
  const p = navigator.platform;
  if (p.includes('Win')) return 'windows';
  if (p.includes('Mac')) return 'macos';
  if (p.includes('Linux')) return 'linux';
  return 'unknown';
}

function getInstallCommand(os: Platform): string {
  switch (os) {
    case 'windows':
      return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
    case 'macos':
    case 'linux':
      return './scripts/install-voice-bridge.sh';
    default:
      return 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"';
  }
}

const stageLabels: Record<string, string> = {
  'token-fetch': 'Token fetch — POST /api/v1/auth/voice-token',
  'socket-open': 'WebSocket connection — ws://127.0.0.1:9999',
  'token-rejected': 'Token rejected by bridge (code 1008)',
  'unknown': 'Unknown error',
};

interface VoiceIndicatorProps {
  iconOnly?: boolean;
}

export function VoiceIndicator({ iconOnly = false }: VoiceIndicatorProps) {
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = user?.isAuthenticated ?? false;

  const [status, setStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [isDisabled, setIsDisabled] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const connectAttempted = useRef(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const [, forceUpdate] = useReducer((x: number) => x + 1, 0);

  useEffect(() => {
    return voiceBridgeService.onStatusChange(setStatus);
  }, []);

  useEffect(() => {
    return voiceBridgeService.onStateChange((s) => {
      if (s) setVoiceState(s);
    });
  }, []);

  useEffect(() => {
    return voiceBridgeService.onErrorChange(() => forceUpdate());
  }, []);

  useEffect(() => {
    if (!isAuthenticated || connectAttempted.current || isDisabled) return;
    connectAttempted.current = true;
    voiceBridgeService.connect().catch(() => {});
  }, [isAuthenticated, isDisabled]);

  const effectiveStatus: BridgeStatus = isDisabled ? 'offline' : status;
  const { label, color, ringColor } = STATUS_CFG[effectiveStatus];

  const effectiveRing = effectiveStatus === 'connected'
    ? VOICE_STATE_RING[voiceState]
    : ringColor;

  const handleToggle = useCallback(() => {
    if (isDisabled) {
      setIsDisabled(false);
      connectAttempted.current = false;
      setTimeout(() => voiceBridgeService.connect(), 50);
      return;
    }
    if (status === 'connected') {
      voiceBridgeService.disconnect();
      setIsDisabled(true);
      return;
    }
    voiceBridgeService.connect().catch(() => {});
  }, [status, isDisabled]);

  const isConnecting = effectiveStatus === 'connecting';
  const isConnected = effectiveStatus === 'connected';
  const platform = useMemo(() => getPlatform(), []);
  const installCommand = useMemo(() => getInstallCommand(platform), [platform]);
  const connectionError = voiceBridgeService.connectionError;

  return (
    <div ref={triggerRef} className="relative flex items-center gap-0.5">
      <button
        type="button"
        onClick={handleToggle}
        disabled={isConnecting}
        className={`
          relative flex items-center gap-1.5 text-xs font-medium rounded-lg p-1.5
          transition-all duration-200 select-none
          hover:bg-gray-100 dark:hover:bg-white/10
          focus:outline-none focus:ring-2 focus:ring-blue-500/30
          disabled:cursor-default
          ${color}
          ${isDisabled ? 'opacity-40' : 'opacity-100'}
        `}
        title={label}
        aria-label={label}
        aria-pressed={isConnected}
      >
        <span
          className={`absolute inset-0 rounded-lg border-2 transition-colors duration-300 ${effectiveRing}`}
        />

        {isConnecting ? (
          <LoadingSpinner size="xs" />
        ) : isConnected ? (
          <Mic className="relative w-3.5 h-3.5" />
        ) : (
          <MicOff className="relative w-3.5 h-3.5" />
        )}

        {!iconOnly && <span className="hidden sm:inline whitespace-nowrap">{label}</span>}

        {effectiveStatus === 'error' && (
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white dark:ring-gray-900" />
        )}
      </button>

      {(isConnected || effectiveStatus === 'offline') && (
        <button
          type="button"
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label="Voice options"
        >
          <ChevronDown className="w-3 h-3" />
        </button>
      )}

      {dropdownOpen && triggerRef.current && (
        <VoiceDropdownPanel
          buttonRect={triggerRef.current.getBoundingClientRect()}
          isConnected={isConnected}
          effectiveStatus={effectiveStatus}
          isDisabled={isDisabled}
          label={label}
          installCommand={installCommand}
          connectionError={connectionError}
          onClose={() => setDropdownOpen(false)}
          onOpenSettings={() => window.dispatchEvent(new CustomEvent('open-voice-settings'))}
          onOpenVoiceMode={() => window.dispatchEvent(new CustomEvent('open-voice-mode'))}
        />
      )}
    </div>
  );
}
