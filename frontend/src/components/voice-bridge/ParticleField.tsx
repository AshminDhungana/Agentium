import { useEffect, useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import particleVertex from './shaders/particleVertex.glsl';
import particleFragment from './shaders/particleFragment.glsl';

const PARTICLE_COUNT = 2000;

interface ParticleFieldProps {
  micLevel: number;
  state: 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
  prefersReduced: boolean;
  color: THREE.Color;
}

export function ParticleField({ micLevel, state, prefersReduced, color }: ParticleFieldProps) {
  const { scene, registerObject, unregisterObject } = useThreeContext();
  const pointsRef = useRef<THREE.Points | null>(null);
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);

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

      // Color variation
      const hue = 0.6 + Math.random() * 0.1;
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
      materialRef.current.uniforms.uTime.value += 1/60;
      materialRef.current.uniforms.uMicLevel.value = micLevel;
      materialRef.current.uniforms.uState.value = stateIndex;
    };

    const id = setInterval(animate, 16);
    return () => clearInterval(id);
  }, [micLevel, stateIndex]);

  // Reduced motion: freeze particle physics
  useEffect(() => {
    if (prefersReduced && materialRef.current) {
      materialRef.current.uniforms.uMicLevel.value = 0;
      materialRef.current.uniforms.uState.value = 0;
    }
  }, [prefersReduced]);

  return null;
}