import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import { useThreeColors } from './hooks/useThreeColors';
import type { ConnectionStatus } from './types';

// Define color keys
type ThreeColorKey = 'listening' | 'speaking' | 'thinking' | 'processing' | 'error' | 'idle' | 'muted' | 'canvasBg' | 'panelBg' | 'glassBorder';

interface ConnectionStatus3DProps {
  status: ConnectionStatus;
  prefersReduced: boolean;
}

const STATUS_CONFIG: Record<ConnectionStatus, { color: ThreeColorKey; pulse: boolean }> = {
  disconnected: { color: 'idle', pulse: false },
  connecting: { color: 'thinking', pulse: true },
  connected: { color: 'speaking', pulse: false },
  error: { color: 'error', pulse: true },
  reconnecting: { color: 'thinking', pulse: true },
};

export function ConnectionStatus3D({ status, prefersReduced }: ConnectionStatus3DProps) {
  const { scene, registerObject, unregisterObject, clock } = useThreeContext();
  const colors = useThreeColors();
  const sphereRef = useRef<THREE.Mesh | null>(null);
  const materialRef = useRef<THREE.MeshPhysicalMaterial | null>(null);
  const animationRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    const geometry = new THREE.SphereGeometry(0.3, 16, 16);
    const config = STATUS_CONFIG[status];
    const color = colors[config.color];

    const material = new THREE.MeshPhysicalMaterial({
      color,
      transmission: 0.5,
      roughness: 0.1,
      clearcoat: 1.0,
      emissive: color.clone().multiplyScalar(0.3),
      emissiveIntensity: 0.3,
    });
    materialRef.current = material;

    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(0, 10, 0); // Above orb
    sphereRef.current = sphere;

    registerObject(sphere, () => {
      geometry.dispose();
      material.dispose();
    });

    return () => unregisterObject(sphere);
  }, [status, colors, registerObject, unregisterObject]);

  // Pulse animation - respect reduced motion
  useEffect(() => {
    const config = STATUS_CONFIG[status];
    if (!config.pulse || !materialRef.current || prefersReduced) return;

    const animate = () => {
      if (!materialRef.current) return;
      const t = clock.getElapsedTime();
      const pulse = Math.sin(t * 4) * 0.5 + 0.5;
      materialRef.current.emissiveIntensity = 0.3 + pulse * 0.5;
      materialRef.current.needsUpdate = true;
      if (sphereRef.current) sphereRef.current.scale.setScalar(1 + pulse * 0.2);
    };

    animationRef.current = setInterval(animate, 16);
    return () => {
      if (animationRef.current) clearInterval(animationRef.current);
    };
  }, [status, clock, prefersReduced]);

  return null;
}