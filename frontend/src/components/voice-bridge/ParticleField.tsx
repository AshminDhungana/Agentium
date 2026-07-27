import { useEffect, useRef, useMemo, useLayoutEffect } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import particleVertex from './shaders/particleVertex.glsl';
import particleFragment from './shaders/particleFragment.glsl';
import { useThreeColors } from './hooks/useThreeColors';

const PARTICLE_COUNT = 2000;

interface ParticleFieldProps {
  micLevel: number;
  state: 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
  prefersReduced: boolean;
}

export function ParticleField({ micLevel, state, prefersReduced }: ParticleFieldProps) {
  const { scene, registerObject, unregisterObject } = useThreeContext();
  const colors = useThreeColors();
  const pointsRef = useRef<THREE.Points | null>(null);
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  const animationRef = useRef<ReturnType<typeof setInterval>>();

  const stateIndex = useMemo(() => {
    switch (state) {
      case 'idle': return 0;
      case 'listening': return 1;
      case 'speaking': return 2;
      case 'processing': return 3;
      case 'error': return 4;
      case 'muted': return 5;
      default: return 0;
    }
  }, [state]);

  // Derive particle hues from CSS variables for theme consistency
  const getBaseHue = () => {
    const style = getComputedStyle(document.documentElement);
    const listeningColor = style.getPropertyValue('--c-voice-listening').trim();
    const speakingColor = style.getPropertyValue('--c-voice-speaking').trim();
    const thinkingColor = style.getPropertyValue('--c-voice-thinking').trim();
    const errorColor = style.getPropertyValue('--c-voice-error').trim();
    const idleColor = style.getPropertyValue('--color-text-muted').trim();

    // Convert hex to approximate hue
    const hexToHue = (hex: string) => {
      const r = parseInt(hex.slice(1, 3), 16) / 255;
      const g = parseInt(hex.slice(3, 5), 16) / 255;
      const b = parseInt(hex.slice(5, 7), 16) / 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      let h = 0;
      if (max !== min) {
        if (max === r) h = (g - b) / (max - min);
        else if (max === g) h = 2 + (b - r) / (max - min);
        else h = 4 + (r - g) / (max - min);
        h *= 60;
        if (h < 0) h += 360;
      }
      return h / 360;
    };

    return { listening: listeningColor ? hexToHue(listeningColor) : 0.58,
             speaking: speakingColor ? hexToHue(speakingColor) : 0.33,
             thinking: thinkingColor ? hexToHue(thinkingColor) : 0.72,
             error: errorColor ? hexToHue(errorColor) : 0.0,
             idle: idleColor ? hexToHue(idleColor) : 0.58 };
  };

  const baseHues = useMemo(getBaseHue, []);

  useEffect(() => {
    const geometry = new THREE.BufferGeometry();
    geometryRef.current = geometry;

    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const velocities = new Float32Array(PARTICLE_COUNT * 3);
    const baseSizes = new Float32Array(PARTICLE_COUNT);
    const baseColors = new Float32Array(PARTICLE_COUNT * 3);
    const phases = new Float32Array(PARTICLE_COUNT);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Spherical distribution
      const r = Math.pow(Math.random(), 1/3) * 15;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);

      // Random velocity
      velocities[i * 3] = (Math.random() - 0.5) * 0.02;
      velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.02;
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.02;

      // Base size
      baseSizes[i] = 0.05 + Math.random() * 0.1;

      // Theme-aware color variation based on CSS variables
      const hue = baseHues.listening + Math.random() * 0.1 - 0.05;
      const sat = 0.5 + Math.random() * 0.3;
      const light = 0.4 + Math.random() * 0.3;
      const c = new THREE.Color().setHSL(hue, sat, light);
      baseColors[i * 3] = c.r;
      baseColors[i * 3 + 1] = c.g;
      baseColors[i * 3 + 2] = c.b;

      phases[i] = Math.random() * Math.PI * 2;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3));
    geometry.setAttribute('baseSize', new THREE.BufferAttribute(baseSizes, 1));
    geometry.setAttribute('baseColor', new THREE.BufferAttribute(baseColors, 3));
    geometry.setAttribute('phase', new THREE.BufferAttribute(phases, 1));

    const material = new THREE.ShaderMaterial({
      vertexShader: particleVertex,
      fragmentShader: particleFragment,
      uniforms: {
        uTime: { value: 0 },
        uDelta: { value: 1/60 },
        uMicLevel: { value: micLevel },
        uState: { value: stateIndex },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    materialRef.current = material;

    const points = new THREE.Points(geometry, material);
    pointsRef.current = points;

    registerObject(points, () => {
      geometry.dispose();
      material.dispose();
    });

    return () => unregisterObject(points);
  }, [registerObject, unregisterObject, stateIndex]);

  // Update uniforms
  useEffect(() => {
    if (!materialRef.current) return;

    const animate = () => {
      if (!materialRef.current) return;
      // Respect reduced motion
      if (prefersReduced) return;

      materialRef.current.uniforms.uTime.value += 1/60;
      materialRef.current.uniforms.uMicLevel.value = micLevel;
      materialRef.current.uniforms.uState.value = stateIndex;
    };

    animationRef.current = setInterval(animate, 16);
    return () => {
      if (animationRef.current) clearInterval(animationRef.current);
    };
  }, [micLevel, stateIndex, prefersReduced]);

  // Reduced motion: freeze particle physics
  useLayoutEffect(() => {
    if (prefersReduced && materialRef.current) {
      materialRef.current.uniforms.uMicLevel.value = 0;
      materialRef.current.uniforms.uState.value = 0;
    }
  }, [prefersReduced]);

  return null;
}