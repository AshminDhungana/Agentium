import { useEffect, useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import orbVertex from './shaders/orbVertex.glsl';
import orbFragment from './shaders/orbFragment.glsl';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';

interface VoiceOrb3DProps {
  size: number;
  state: VoiceState;
  micLevel: number;
  frequencyData: Uint8Array | null;
  colors: {
    listening: THREE.Color;
    speaking: THREE.Color;
    thinking: THREE.Color;
    processing: THREE.Color;
    error: THREE.Color;
    idle: THREE.Color;
    muted: THREE.Color;
  };
  prefersReduced: boolean;
}

const STATE_MAP: Record<VoiceState, number> = {
  idle: 0, listening: 1, speaking: 2, processing: 3, error: 4, muted: 5,
};

const STATE_CONFIG: Record<VoiceState, {
  transmission: number; roughness: number; clearcoat: number;
  emissiveIntensity: number; rotationSpeed: number;
}> = {
  idle: { transmission: 0, roughness: 0.35, clearcoat: 1.0, emissiveIntensity: 0.0, rotationSpeed: 0.03 },
  listening: { transmission: 0.1, roughness: 0.15, clearcoat: 1.0, emissiveIntensity: 0.3, rotationSpeed: 0.05 },
  speaking: { transmission: 0.2, roughness: 0.08, clearcoat: 1.0, emissiveIntensity: 0.5, rotationSpeed: 0.12 },
  processing: { transmission: 0.05, roughness: 0.2, clearcoat: 0.8, emissiveIntensity: 0.4, rotationSpeed: 0.02 },
  error: { transmission: 0, roughness: 0.5, clearcoat: 0.0, emissiveIntensity: 0.6, rotationSpeed: 0.15 },
  muted: { transmission: 0, roughness: 0.8, clearcoat: 0.0, emissiveIntensity: 0.0, rotationSpeed: 0.01 },
};

export function VoiceOrb3D({
  size,
  state,
  micLevel,
  frequencyData,
  colors,
  prefersReduced,
}: VoiceOrb3DProps) {
  const { scene, registerObject, unregisterObject, clock } = useThreeContext();
  const outerMeshRef = useRef<THREE.Mesh | null>(null);
  const innerMeshRef = useRef<THREE.Mesh | null>(null);
  const wireMaterialRef = useRef<THREE.ShaderMaterial | null>(null);
  const coreMaterialRef = useRef<THREE.MeshPhysicalMaterial | null>(null);
  const geometryRef = useRef<{ outer: THREE.BufferGeometry; inner: THREE.BufferGeometry } | null>(null);

  // Compute frequency bands
  const { uBass, uMid, uTreble, uPulsePhase } = useMemo(() => {
    let bass = 0.1, mid = 0.1, treble = 0.05, pulsePhase = 0;

    if (frequencyData && frequencyData.length > 0) {
      const len = frequencyData.length;
      const bassEnd = Math.floor(len * 0.1);
      const midEnd = Math.floor(len * 0.5);

      let bassSum = 0, midSum = 0, trebleSum = 0;
      for (let i = 0; i < bassEnd; i++) bassSum += frequencyData[i];
      for (let i = bassEnd; i < midEnd; i++) midSum += frequencyData[i];
      for (let i = midEnd; i < len; i++) trebleSum += frequencyData[i];

      bass = (state === 'speaking' || state === 'listening') ? (bassSum / (bassEnd * 255)) * (state === 'speaking' ? 1.0 : 0.8) : micLevel * 0.8;
      mid = (state === 'speaking' || state === 'listening') ? (midSum / ((midEnd - bassEnd) * 255)) * (state === 'speaking' ? 1.0 : 0.6) : micLevel * 0.6;
      treble = (state === 'speaking' || state === 'listening') ? (trebleSum / ((len - midEnd) * 255)) * (state === 'speaking' ? 1.0 : 0.4) : micLevel * 0.4;
    } else {
      bass = micLevel * 0.8;
      mid = micLevel * 0.6;
      treble = micLevel * 0.4;
    }
    pulsePhase = bass * 10;

    return { uBass: bass, uMid: mid, uTreble: treble, uPulsePhase: pulsePhase };
  }, [state, micLevel, frequencyData]);

  // Create/destroy meshes
  useEffect(() => {
    const radius = size / 50; // px to Three units
    const outerGeo = new THREE.IcosahedronGeometry(radius * 1.06, 2);
    const innerGeo = new THREE.IcosahedronGeometry(radius, 2);
    geometryRef.current = { outer: outerGeo, inner: innerGeo };

    // Wireframe shader material (outer)
    const wireMaterial = new THREE.ShaderMaterial({
      vertexShader: orbVertex,
      fragmentShader: orbFragment,
      uniforms: {
        uTime: { value: 0 },
        uBass: { value: uBass },
        uMid: { value: uMid },
        uTreble: { value: uTreble },
        uPulsePhase: { value: uPulsePhase },
        uState: { value: STATE_MAP[state] },
        uCoreColor: { value: colors[state === 'idle' ? 'idle' : state === 'muted' ? 'muted' : state === 'error' ? 'error' : state === 'processing' ? 'thinking' : state] },
        uGlowColor: { value: colors[state === 'idle' ? 'idle' : state === 'muted' ? 'muted' : state === 'error' ? 'error' : state === 'processing' ? 'thinking' : state] },
        uEmissiveIntensity: { value: STATE_CONFIG[state].emissiveIntensity },
      },
      transparent: true,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    wireMaterialRef.current = wireMaterial;

    // Core physical material (inner)
    const config = STATE_CONFIG[state];
    const coreColor = colors[state === 'idle' ? 'idle' : state === 'muted' ? 'muted' : state === 'error' ? 'error' : state === 'processing' ? 'thinking' : state];
    const coreMaterial = new THREE.MeshPhysicalMaterial({
      color: coreColor,
      transmission: config.transmission,
      roughness: config.roughness,
      clearcoat: config.clearcoat,
      clearcoatRoughness: 0.1,
      emissive: coreColor.clone().multiplyScalar(config.emissiveIntensity),
      emissiveIntensity: config.emissiveIntensity,
      metalness: 0.1,
      reflectivity: 0.5,
    });
    coreMaterialRef.current = coreMaterial;

    const outerMesh = new THREE.Mesh(outerGeo, wireMaterial);
    const innerMesh = new THREE.Mesh(innerGeo, coreMaterial);

    outerMeshRef.current = outerMesh;
    innerMeshRef.current = innerMesh;

    registerObject(outerMesh, () => { outerGeo.dispose(); wireMaterial.dispose(); });
    registerObject(innerMesh, () => { innerGeo.dispose(); coreMaterial.dispose(); });

    return () => {
      unregisterObject(outerMesh);
      unregisterObject(innerMesh);
      geometryRef.current = null;
    };
  }, [size, state, colors, registerObject, unregisterObject]);

  // Animation loop - update uniforms
  useEffect(() => {
    if (!wireMaterialRef.current || !coreMaterialRef.current) return;

    const animate = () => {
      const elapsed = clock.getElapsedTime();
      const config = STATE_CONFIG[state];
      const coreColor = colors[state === 'idle' ? 'idle' : state === 'muted' ? 'muted' : state === 'error' ? 'error' : state === 'processing' ? 'thinking' : state];

      // Update wireframe uniforms
      wireMaterialRef.current!.uniforms.uTime.value = elapsed;
      wireMaterialRef.current!.uniforms.uBass.value = uBass;
      wireMaterialRef.current!.uniforms.uMid.value = uMid;
      wireMaterialRef.current!.uniforms.uTreble.value = uTreble;
      wireMaterialRef.current!.uniforms.uPulsePhase.value = uPulsePhase;
      wireMaterialRef.current!.uniforms.uState.value = STATE_MAP[state];
      wireMaterialRef.current!.uniforms.uCoreColor.value.set(coreColor);
      wireMaterialRef.current!.uniforms.uGlowColor.value.set(coreColor);
      wireMaterialRef.current!.uniforms.uEmissiveIntensity.value = config.emissiveIntensity;

      // Update core material
      coreMaterialRef.current!.color.set(coreColor);
      coreMaterialRef.current!.transmission = config.transmission;
      coreMaterialRef.current!.roughness = config.roughness;
      coreMaterialRef.current!.clearcoat = config.clearcoat;
      coreMaterialRef.current!.emissive.set(coreColor).multiplyScalar(config.emissiveIntensity);
      coreMaterialRef.current!.emissiveIntensity = config.emissiveIntensity;
      coreMaterialRef.current!.needsUpdate = true;

      // Rotation
      if (!prefersReduced && config.rotationSpeed > 0) {
        outerMeshRef.current!.rotation.y += config.rotationSpeed * 0.016;
        innerMeshRef.current!.rotation.y += config.rotationSpeed * 0.016;
        outerMeshRef.current!.rotation.x += config.rotationSpeed * 0.008;
        innerMeshRef.current!.rotation.x += config.rotationSpeed * 0.008;
      }

      // Audio-reactive scale pulse
      if (!prefersReduced && (state === 'listening' || state === 'speaking')) {
        const pulseScale = 1 + uBass * 0.03;
        outerMeshRef.current!.scale.setScalar(pulseScale);
        innerMeshRef.current!.scale.setScalar(pulseScale);
      } else {
        outerMeshRef.current!.scale.setScalar(1);
        innerMeshRef.current!.scale.setScalar(1);
      }
    };

    const interval = setInterval(animate, 16); // ~60fps
    return () => clearInterval(interval);
  }, [state, uBass, uMid, uTreble, uPulsePhase, colors, prefersReduced, clock]);

  // Reduced motion: freeze
  useEffect(() => {
    if (prefersReduced && wireMaterialRef.current) {
      wireMaterialRef.current.uniforms.uBass.value = 0;
      wireMaterialRef.current.uniforms.uMid.value = 0;
      wireMaterialRef.current.uniforms.uTreble.value = 0;
      if (outerMeshRef.current) outerMeshRef.current.rotation.set(0, 0, 0);
      if (innerMeshRef.current) innerMeshRef.current.rotation.set(0, 0, 0);
    }
  }, [prefersReduced]);

  return null; // Renders via Three.js scene
}