/**
 * VoiceIndicator.tsx
 * - On login: auto-connects, shows spinner, then updates icon to connected/error
 * - On click when offline/error: retries connection
 * - If retry fails: detects OS, shows a toast-style notification with
 *   the exact install command for their platform
 * - On click when connected: disconnects / disables
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Loader2, X, Terminal, Copy, Check } from 'lucide-react';
import { voiceBridgeService, BridgeStatus } from '@/services/voiceBridge';
import { useAuthStore } from '@/store/authStore';

// ── OS Detection ─────────────────────────────────────────────────────────────

type DetectedOS = 'windows' | 'macos' | 'linux' | 'unknown';

function detectOS(): DetectedOS {
  const ua = navigator.userAgent;
  if (/Win/i.test(ua))     return 'windows';
  if (/Mac/i.test(ua))     return 'macos';
  if (/Linux/i.test(ua))   return 'linux';
  return 'unknown';
}

interface InstallInfo {
  os: DetectedOS;
  label: string;
  commands: { caption: string; cmd: string }[];
}

function getInstallInfo(os: DetectedOS): InstallInfo {
  switch (os) {
    case 'windows':
      return {
        os,
        label: 'Windows',
        commands: [
          {
            caption: 'Run in PowerShell (from your Agentium repo folder)',
            cmd: 'powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"',
          },
          {
            caption: 'Or if Docker is running, it auto-installs — check:',
            cmd: '%USERPROFILE%\\.agentium\\run-prompt.cmd',
          },
        ],
      };
    case 'macos':
      return {
        os,
        label: 'macOS',
        commands: [
          {
            caption: 'Run in Terminal (from your Agentium repo folder)',
            cmd: 'bash voice-bridge/install.sh',
          },
          {
            caption: 'Then check status:',
            cmd: 'launchctl list com.agentium.voice',
          },
        ],
      };
    case 'linux':
      return {
        os,
        label: 'Linux',
        commands: [
          {
            caption: 'Run in Terminal (from your Agentium repo folder)',
            cmd: 'bash voice-bridge/install.sh',
          },
          {
            caption: 'Then check status:',
            cmd: 'systemctl --user status agentium-voice',
          },
        ],
      };
    default:
      return {
        os,
        label: 'your OS',
        commands: [
          {
            caption: 'Run from your Agentium repo folder',
            cmd: 'bash voice-bridge/install.sh',
          },
        ],
      };
  }
}

// ── Install Notification ──────────────────────────────────────────────────────

interface InstallNotificationProps {
  info: InstallInfo;
  onClose: () => void;
}

function InstallNotification({ info, onClose }: InstallNotificationProps) {
  const [copied, setCopied] = useState<number | null>(null);

  const handleCopy = async (cmd: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(idx);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // fallback: select the text
    }
  };

  return (
    <div
      className="
        fixed bottom-20 left-4 z-50 w-[340px]
        bg-white dark:bg-[#0d1117]
        border border-gray-200 dark:border-gray-700
        rounded-xl shadow-lg dark:shadow-2xl
        animate-in slide-in-from-bottom-4 fade-in duration-300
      "
      role="alert"
    >
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-500/20">
            <Terminal className="h-3.5 w-3.5 text-orange-500 dark:text-orange-400" />
          </span>
          <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
            Voice Bridge Not Running
          </p>
        </div>
        <button
          onClick={onClose}
          className="ml-2 mt-0.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors flex-shrink-0"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="px-4 pb-2">
        <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed mb-3">
          The local voice bridge isn't running on your{' '}
          <span className="text-gray-800 dark:text-gray-200 font-medium">{info.label}</span> machine.
          Start it with the command below:
        </p>

        {info.commands.map((item, idx) => (
          <div key={idx} className="mb-2 last:mb-0">
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 uppercase tracking-wide">
              {item.caption}
            </p>
            <div className="group flex items-center gap-2 bg-gray-50 dark:bg-black/50 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2">
              <code className="flex-1 text-[11px] text-green-600 dark:text-green-400 font-mono break-all leading-relaxed">
                {item.cmd}
              </code>
              <button
                onClick={() => handleCopy(item.cmd, idx)}
                className="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:text-gray-600 dark:hover:text-gray-300 transition-colors"
                aria-label="Copy command"
              >
                {copied === idx
                  ? <Check className="h-3.5 w-3.5 text-green-500 dark:text-green-400" />
                  : <Copy className="h-3.5 w-3.5" />
                }
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between">
        <p className="text-[10px] text-gray-400 dark:text-gray-600">
          After running, click the mic icon to reconnect.
        </p>
        <button
          onClick={onClose}
          className="text-[11px] text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors"
        >
          Got it
        </button>
      </div>
    </div>
  );
}

// ── VoiceIndicator ────────────────────────────────────────────────────────────

interface VoiceIndicatorProps {
  iconOnly?: boolean;
}

export function VoiceIndicator({ iconOnly = false }: VoiceIndicatorProps) {
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = user?.isAuthenticated ?? false;

  const [status, setStatus]           = useState<BridgeStatus>(voiceBridgeService.status);
  const [isDisabled, setIsDisabled]   = useState(false);
  const [showNotif, setShowNotif]     = useState(false);
  const [notifInfo, setNotifInfo]     = useState<InstallInfo | null>(null);
  const connectAttempted              = useRef(false);

  // Keep status in sync with the singleton
  useEffect(() => {
    return voiceBridgeService.onStatusChange(setStatus);
  }, []);

  // Auto-connect on login (once)
  useEffect(() => {
    if (!isAuthenticated || connectAttempted.current || isDisabled) return;
    connectAttempted.current = true;
    voiceBridgeService.connect().catch(() => {});
  }, [isAuthenticated, isDisabled]);

  // Show install notification when status goes to error/offline after a connect attempt
  useEffect(() => {
    if (
      connectAttempted.current &&
      !isDisabled &&
      (status === 'error' || status === 'offline') &&
      isAuthenticated
    ) {
      const info = getInstallInfo(detectOS());
      setNotifInfo(info);
      setShowNotif(true);
    } else {
      setShowNotif(false);
    }
  }, [status, isDisabled, isAuthenticated]);

  const handleClick = useCallback(() => {
    if (isDisabled) {
      // Re-enable and try to connect
      setIsDisabled(false);
      setShowNotif(false);
      connectAttempted.current = false;
      setTimeout(() => {
        voiceBridgeService.connect().catch(() => {});
        connectAttempted.current = true;
      }, 50);
      return;
    }

    if (status === 'connected') {
      // Disconnect / disable
      voiceBridgeService.disconnect();
      setIsDisabled(true);
      setShowNotif(false);
      return;
    }

    // Offline or error — retry
    setShowNotif(false);
    voiceBridgeService.connect().catch(() => {});
  }, [status, isDisabled]);

  // Effective display
  const effectiveStatus: BridgeStatus = isDisabled ? 'offline' : status;

  const cfg: Record<BridgeStatus, { label: string; color: string; ring: string }> = {
    offline:    { label: 'Voice offline',  color: 'text-gray-400 dark:text-gray-500',     ring: 'focus:ring-gray-500/30' },
    connecting: { label: 'Connecting…',    color: 'text-amber-500 dark:text-amber-400',   ring: 'focus:ring-amber-500/30' },
    connected:  { label: 'Voice ready',    color: 'text-emerald-500 dark:text-emerald-400', ring: 'focus:ring-emerald-500/30' },
    error:      { label: 'Voice error',    color: 'text-red-500 dark:text-red-400',       ring: 'focus:ring-red-500/30' },
  };

  const { label, color, ring } = cfg[effectiveStatus];

  const ariaLabel = isDisabled
    ? 'Voice disabled — click to retry'
    : effectiveStatus === 'connected'
    ? 'Voice ready — click to disconnect'
    : effectiveStatus === 'connecting'
    ? 'Connecting to voice bridge…'
    : 'Voice offline — click to retry';

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        disabled={effectiveStatus === 'connecting'}
        className={`
          relative flex items-center gap-1.5 text-xs font-medium rounded-lg p-1.5
          transition-all duration-200 select-none
          hover:bg-gray-100 dark:hover:bg-white/10
          focus:outline-none focus:ring-2 ${ring}
          disabled:cursor-default
          ${color}
          ${isDisabled ? 'opacity-40' : 'opacity-100'}
        `}
        title={ariaLabel}
        aria-label={ariaLabel}
        aria-pressed={effectiveStatus === 'connected'}
      >
        {effectiveStatus === 'connecting' ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : effectiveStatus === 'connected' ? (
          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <Mic className="relative w-3.5 h-3.5" />
          </span>
        ) : (
          <MicOff className="w-3.5 h-3.5" />
        )}

        {!iconOnly && (
          <span className="hidden sm:inline whitespace-nowrap">{label}</span>
        )}

        {/* Red dot for error state */}
        {effectiveStatus === 'error' && (
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500 ring-2 ring-white dark:ring-gray-900" />
        )}
      </button>

      {/* Install notification */}
      {showNotif && notifInfo && (
        <InstallNotification
          info={notifInfo}
          onClose={() => setShowNotif(false)}
        />
      )}
    </>
  );
}