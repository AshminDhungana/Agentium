import { useState, useLayoutEffect, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Settings2, Maximize2 } from 'lucide-react';
import type { BridgeStatus } from '@/services/voiceBridge';

const stageLabels: Record<string, string> = {
  'token-fetch': 'Token fetch — POST /api/v1/auth/voice-token',
  'socket-open': 'WebSocket connection — ws://127.0.0.1:9999',
  'token-rejected': 'Token rejected by bridge (code 1008)',
  'unknown': 'Unknown error',
};

interface ConnectionError {
  stage: string;
  message: string;
  statusCode?: number;
}

interface VoiceDropdownPanelProps {
  buttonRect: DOMRect | null;
  isConnected: boolean;
  effectiveStatus: BridgeStatus;
  isDisabled: boolean;
  label: string;
  installCommand: string;
  connectionError: ConnectionError | null;
  onClose: () => void;
  onOpenSettings: () => void;
  onOpenVoiceMode: () => void;
}

export function VoiceDropdownPanel({
  buttonRect,
  isConnected,
  effectiveStatus,
  isDisabled,
  label,
  installCommand,
  connectionError,
  onClose,
  onOpenSettings,
  onOpenVoiceMode,
}: VoiceDropdownPanelProps) {
  const [style, setStyle] = useState<React.CSSProperties>({});

  useLayoutEffect(() => {
    if (!buttonRect) return;
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const panelMinHeight = 280;
    const top = spaceBelow >= panelMinHeight
      ? buttonRect.top
      : undefined;
    const bottom = spaceBelow < panelMinHeight
      ? window.innerHeight - buttonRect.bottom
      : undefined;
    setStyle({
      left: `${buttonRect.right + 4}px`,
      top: top !== undefined ? `${top}px` : undefined,
      bottom: bottom !== undefined ? `${bottom}px` : undefined,
    });
  }, [buttonRect]);

  useEffect(() => {
    if (!buttonRect) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [buttonRect, onClose]);

  if (!buttonRect) return null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-45 bg-transparent" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-label="Voice options"
        style={style}
        className="fixed z-50 w-56 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-lg p-2 space-y-1"
      >
        <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-gray-500'}`} />
          {label}
        </div>

        {effectiveStatus === 'offline' && !isDisabled && (
          <div className="px-3 py-2 text-xs text-gray-600 dark:text-gray-500 bg-gray-50 dark:bg-black/30 rounded-lg">
            <p className="mb-1">Bridge not running.</p>
            <div className="flex items-center gap-1">
              <code className="text-[10px] text-green-500 flex-1 truncate">{installCommand}</code>
              <button
                onClick={() => navigator.clipboard.writeText(installCommand)}
                className="text-blue-500 hover:text-blue-400 shrink-0"
                aria-label="Copy install command"
              >
                Copy
              </button>
            </div>
            {connectionError && (
              <details className="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
                <summary className="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
                  Connection details
                </summary>
                <div className="mt-1 space-y-0.5">
                  <p>{stageLabels[connectionError.stage] ?? connectionError.stage}</p>
                  <p>Message: {connectionError.message}</p>
                  {connectionError.statusCode && <p>HTTP {connectionError.statusCode}</p>}
                </div>
              </details>
            )}
          </div>
        )}

        <button
          onClick={() => { onClose(); onOpenSettings(); }}
          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
        >
          <Settings2 className="w-3.5 h-3.5" />
          Voice Settings
        </button>

        {isConnected && (
          <button
            onClick={() => { onClose(); onOpenVoiceMode(); }}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-colors"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            Open Voice Mode
          </button>
        )}
      </div>
    </>,
    document.body
  );
}
