import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import { useThreeColors } from './hooks/useThreeColors';
import type { ConnectionStatus } from './types';

// Define color keys without the updateColors function
type ThreeColorKey = 'listening' | 'speaking' | 'thinking' | 'processing' | 'error' | 'idle' | 'muted' | 'canvasBg' | 'panelBg' | 'glassBorder';

interface ConnectionStatus3DProps {
  status: ConnectionStatus;
  colors: Record<ThreeColorKey, THREE.Color> & { updateColors: () => void };
}

const STATUS_CONFIG: Record<ConnectionStatus, { color: ThreeColorKey; pulse: boolean }> = {
  disconnected: { color: 'idle', pulse: false },
  connecting: { color: 'thinking', pulse: true },
  connected: { color: 'speaking', pulse: false },
  error: { color: 'error', pulse: true },
  reconnecting: { color: 'thinking', pulse: true },
};

export function ConnectionStatus3D({ status, colors }: ConnectionStatus3DProps) {
  const { scene, registerObject, unregisterObject, clock } = useThreeContext();
  const sphereRef = useRef<THREE.Mesh | null>(null);
  const materialRef = useRef<THREE.MeshPhysicalMaterial | null>(null);

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

  // Pulse animation
  useEffect(() => {
    const config = STATUS_CONFIG[status];
    if (!config.pulse || !materialRef.current) return;

    const animate = () => {
      if (!materialRef.current) return;
      const t = clock.getElapsedTime();
      const pulse = Math.sin(t * 4) * 0.5 + 0.5;
      materialRef.current.emissiveIntensity = 0.3 + pulse * 0.5;
      materialRef.current.needsUpdate = true;
      if (sphereRef.current) sphereRef.current.scale.setScalar(1 + pulse * 0.2);
    };

    const id = setInterval(animate, 16);
    return () => clearInterval(id);
  }, [status, clock]);

  return null;
}