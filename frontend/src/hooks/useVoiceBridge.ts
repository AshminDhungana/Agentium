/**
 * useVoiceBridge.ts — React hook that connects to the host-native voice bridge.
 *
 * Connects on mount (when the user is authenticated), disconnects on unmount.
 * Exposes bridge status and the last interaction event.
 *
 * Usage:
 *   const { status } = useVoiceBridge(handleVoiceInteraction);
 */

import { useEffect, useRef, useState } from 'react';
import { voiceBridgeService, BridgeStatus, VoiceInteractionEvent } from '@/services/voiceBridge';
import { useAuthStore } from '@/store/authStore';

const STATUS_MESSAGES: Record<BridgeStatus, string> = {
  offline:    'Voice bridge not running',
  connecting: 'Connecting to voice bridge...',
  connected:  'Voice bridge active',
  error:      'Voice bridge unavailable',
};

export function useVoiceBridge(
  onInteraction?: (event: VoiceInteractionEvent) => void,
): { status: BridgeStatus; statusMessage: string } {
  const [status, setStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = user?.isAuthenticated ?? false;

  // Keep a stable ref so the effect doesn't re-run when the callback identity changes
  const onInteractionRef = useRef(onInteraction);
  useEffect(() => { onInteractionRef.current = onInteraction; }, [onInteraction]);

  useEffect(() => {
    if (!isAuthenticated) return;

    // Subscribe to status changes
    const unsubStatus = voiceBridgeService.onStatusChange(setStatus);

    // Subscribe to voice interaction events
    const unsubInteraction = voiceBridgeService.onInteraction((event) => {
      try {
        onInteractionRef.current?.(event);
      } catch (err) {
        console.warn('[useVoiceBridge] onInteraction callback threw:', err);
      }
    });

    // Connect (no-op if already connected)
    voiceBridgeService.connect().catch((err) => {
      console.warn('[useVoiceBridge] connect() error:', err);
    });

    return () => {
      unsubStatus();
      unsubInteraction();
      // Do NOT disconnect on unmount — the singleton stays alive across page changes
    };
  }, [isAuthenticated]);

  return { status, statusMessage: STATUS_MESSAGES[status] };
}