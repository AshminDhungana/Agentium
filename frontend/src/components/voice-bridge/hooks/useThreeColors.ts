import { useEffect, useState, useCallback, useRef } from 'react';
import * as THREE from 'three';

interface ThreeColors {
  listening: THREE.Color;
  speaking: THREE.Color;
  thinking: THREE.Color;
  processing: THREE.Color;
  error: THREE.Color;
  idle: THREE.Color;
  muted: THREE.Color;
  canvasBg: THREE.Color;
  panelBg: THREE.Color;
  glassBorder: THREE.Color;
}

const DEFAULTS: ThreeColors = {
  listening: new THREE.Color('#3b82f6'),
  speaking: new THREE.Color('#10b981'),
  thinking: new THREE.Color('#8b5cf6'),
  processing: new THREE.Color('#8b5cf6'), // same as thinking
  error: new THREE.Color('#ef4444'),
  idle: new THREE.Color('#64748b'),
  muted: new THREE.Color('#9ca3af'),
  canvasBg: new THREE.Color('#f9fafb'),
  panelBg: new THREE.Color('#ffffff'),
  glassBorder: new THREE.Color('rgba(37, 99, 235, 0.12)'),
};

export function useThreeColors(): ThreeColors & { updateColors: () => void } {
  const [colors, setColors] = useState<ThreeColors>(DEFAULTS);
  const observerRef = useRef<MutationObserver | null>(null);

  const syncColors = useCallback(() => {
    if (typeof document === 'undefined') return;
    const rootStyles = getComputedStyle(document.documentElement);
    const get = (varName: string) => new THREE.Color(rootStyles.getPropertyValue(varName).trim());

    setColors({
      listening: get('--c-voice-listening'),
      speaking: get('--c-voice-speaking'),
      thinking: get('--c-voice-thinking'),
      processing: get('--c-voice-thinking'),
      error: get('--c-voice-error'),
      idle: new THREE.Color('#64748b'),
      muted: new THREE.Color('#9ca3af'),
      canvasBg: get('--c-canvas'),
      panelBg: get('--c-panel'),
      glassBorder: get('--c-glass-border'),
    });
  }, []);

  useEffect(() => {
    syncColors();
    observerRef.current = new MutationObserver(syncColors);
    observerRef.current.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observerRef.current?.disconnect();
  }, [syncColors]);

  return { ...colors, updateColors: syncColors };
}