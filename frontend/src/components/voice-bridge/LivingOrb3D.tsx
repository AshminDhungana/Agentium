import { useEffect, useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import orbSurfaceVertex from './shaders/orbSurfaceVertex.glsl';
import orbSurfaceFragment from './shaders/orbSurface.glsl';
import orbMidRingVertex from './shaders/orbMidRingVertex.glsl';
import orbMidRingFragment from './shaders/orbMidRing.glsl';
import particleFieldVertex from './shaders/particleField.glsl';
import particleFieldFragment from './shaders/particleFieldFragment.glsl';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';

interface LivingOrb3DProps {
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

// State configuration matching Canvas2DFallback design
const STATE_CONFIG: Record<VoiceState, {
  apertureIdle: number;
  ringSpeed: number;        // Revolutions per second
  blobAmount: number;
  pulseMin: number;
  pulseMax: number;
}> = {
  idle:       { apertureIdle: 0.15, ringSpeed: 1/30, blobAmount: 0.06, pulseMin: 1.0,  pulseMax: 1.02 },
  listening:  { apertureIdle: 0.15, ringSpeed: 1/8,  blobAmount: 0.06, pulseMin: 1.0,  pulseMax: 1.35 },
  speaking:   { apertureIdle: 0.15, ringSpeed: 1/4,  blobAmount: 0.08, pulseMin: 1.0,  pulseMax: 1.20 },
  processing: { apertureIdle: 0.15, ringSpeed: 1/2,  blobAmount: 0.04, pulseMin: 0.95, pulseMax: 1.00 },
  error:      { apertureIdle: 0.15, ringSpeed: 0,    blobAmount: 0.02, pulseMin: 1.0,  pulseMax: 1.00 },
  muted:      { apertureIdle: 0.00, ringSpeed: 0,    blobAmount: 0.00, pulseMin: 1.0,  pulseMax: 1.00 },
};

const PARTICLE_COUNT = 400;
const PARTICLE_RADIUS_MIN = 1.3;
const PARTICLE_RADIUS_MAX = 2.1;

// Target aperture values per state
const TARGET_APERTURE: Record<VoiceState, number> = {
  idle: 0.15, listening: 0.85, speaking: 0.90, processing: 0.05, error: 0.15, muted: 0.00,
};

export function LivingOrb3D({
  size,
  state,
  micLevel,
  frequencyData,
  colors,
  prefersReduced,
}: LivingOrb3DProps) {
  const { scene, registerObject, unregisterObject, clock } = useThreeContext();

  const coreMeshRef = useRef<THREE.Mesh | null>(null);
  const midRingMeshRef = useRef<THREE.Mesh | null>(null);
  const particleSystemRef = useRef<THREE.Points | null>(null);

  const coreMaterialRef = useRef<THREE.ShaderMaterial | null>(null);
  const midRingMaterialRef = useRef<THREE.ShaderMaterial | null>(null);
  const particleMaterialRef = useRef<THREE.ShaderMaterial | null>(null);

  const geometryRef = useRef<{ core: THREE.BufferGeometry; midRing: THREE.BufferGeometry; particles: THREE.BufferGeometry } | null>(null);

  // Animation refs
  const apertureRef = useRef(0.15);
  const ringRotationRef = useRef(0);
  const noiseOffsetRef = useRef({ x: 0, y: 0 });
  const pulseScaleRef = useRef(1.0);
  const lastTimeRef = useRef(0);
  const animationIntervalRef = useRef<ReturnType<typeof setInterval>>();

  // Compute frequency bands
  const { uBass, uMid, uTreble } = useMemo(() => {
    let bass = 0.1, mid = 0.1, treble = 0.05;

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

    return { uBass: bass, uMid: mid, uTreble: treble };
  }, [state, micLevel, frequencyData]);

  // Get current state color
  const currentColor = useMemo(() => {
    if (state === 'idle') return colors.idle;
    if (state === 'muted') return colors.muted;
    if (state === 'error') return colors.error;
    if (state === 'processing') return colors.thinking;
    return colors[state];
  }, [state, colors]);

  // Brand colors for conic gradient
  const brandColor = useMemo(() => new THREE.Color('#3b82f6'), []);
  const accentColor = useMemo(() => new THREE.Color('#8b5cf6'), []);

  const config = STATE_CONFIG[state];
  const targetAperture = TARGET_APERTURE[state];

  // Create/destroy meshes
  useEffect(() => {
    const radius = size / 50; // Convert px to Three units

    // === CORE GEOMETRY (Icosahedron for organic feel) ===
    const coreGeo = new THREE.IcosahedronGeometry(radius, 4);

    // === MID RING GEOMETRY (Custom ring with UVs for conic gradient) ===
    const midRingGeo = new THREE.BufferGeometry();
    const ringSegments = 128;
    const radialSegments = 4;

    const ringPositions = [];
    const ringUvs = [];
    const ringIndices = [];

    for (let r = 0; r < radialSegments; r++) {
      const innerR = radius * 1.05 + (r / (radialSegments - 1)) * (radius * 0.2);
      const outerR = radius * 1.05 + ((r + 1) / (radialSegments - 1)) * (radius * 0.2);

      for (let i = 0; i <= ringSegments; i++) {
        const angle = (i / ringSegments) * Math.PI * 2;
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);

        // Inner ring vertices
        ringPositions.push(cos * innerR, 0, sin * innerR);
        ringUvs.push(i / ringSegments, r / (radialSegments - 1));

        // Outer ring vertices
        ringPositions.push(cos * outerR, 0, sin * outerR);
        ringUvs.push(i / ringSegments, (r + 1) / (radialSegments - 1));
      }
    }

    // Generate indices for triangles
    for (let r = 0; r < radialSegments - 1; r++) {
      for (let i = 0; i < ringSegments; i++) {
        const a = r * (ringSegments + 1) * 2 + i * 2;
        const b = a + 1;
        const c = a + 2;
        const d = a + 3;

        // Two triangles per quad
        ringIndices.push(a, c, b);
        ringIndices.push(b, c, d);
      }
    }

    midRingGeo.setAttribute('position', new THREE.Float32BufferAttribute(ringPositions, 3));
    midRingGeo.setAttribute('uv', new THREE.Float32BufferAttribute(ringUvs, 2));
    midRingGeo.setIndex(ringIndices);
    midRingGeo.computeVertexNormals();

    // === PARTICLE GEOMETRY ===
    const particleGeo = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
    const particleAngles = new Float32Array(PARTICLE_COUNT);
    const particleRadii = new Float32Array(PARTICLE_COUNT);
    const particleSpeeds = new Float32Array(PARTICLE_COUNT);
    const particleSizes = new Float32Array(PARTICLE_COUNT);
    const particleOpacities = new Float32Array(PARTICLE_COUNT);
    const particlePhases = new Float32Array(PARTICLE_COUNT);
    const particleInclinations = new Float32Array(PARTICLE_COUNT);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const radius = PARTICLE_RADIUS_MIN + Math.random() * (PARTICLE_RADIUS_MAX - PARTICLE_RADIUS_MIN);
      const speed = 0.005 + Math.random() * 0.02;
      const size = 1.5 + Math.random() * 3.0;
      const opacity = 0.3 + Math.random() * 0.5;
      const phase = Math.random() * Math.PI * 2;
      const inclination = Math.acos(2 * Math.random() - 1); // Uniform spherical distribution

      particlePositions[i * 3] = Math.cos(angle) * radius;
      particlePositions[i * 3 + 1] = Math.sin(angle * 0.7) * radius * 0.6;
      particlePositions[i * 3 + 2] = Math.sin(angle) * radius;

      particleAngles[i] = angle;
      particleRadii[i] = radius;
      particleSpeeds[i] = speed;
      particleSizes[i] = size;
      particleOpacities[i] = opacity;
      particlePhases[i] = phase;
      particleInclinations[i] = inclination;
    }

    particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    particleGeo.setAttribute('aAngle', new THREE.BufferAttribute(particleAngles, 1));
    particleGeo.setAttribute('aRadius', new THREE.BufferAttribute(particleRadii, 1));
    particleGeo.setAttribute('aSpeed', new THREE.BufferAttribute(particleSpeeds, 1));
    particleGeo.setAttribute('aSize', new THREE.BufferAttribute(particleSizes, 1));
    particleGeo.setAttribute('aOpacity', new THREE.BufferAttribute(particleOpacities, 1));
    particleGeo.setAttribute('aPhase', new THREE.BufferAttribute(particlePhases, 1));
    particleGeo.setAttribute('aInclination', new THREE.BufferAttribute(particleInclinations, 1));

    geometryRef.current = { core: coreGeo, midRing: midRingGeo, particles: particleGeo };

    // === CORE MATERIAL (ShaderMaterial with orbSurface shaders) ===
    const coreMaterial = new THREE.ShaderMaterial({
      vertexShader: orbSurfaceVertex,
      fragmentShader: orbSurfaceFragment,
      uniforms: {
        uTime: { value: 0 },
        uMicLevel: { value: micLevel },
        uStateColor: { value: currentColor.clone() },
        uStateGlow: { value: currentColor.clone().multiplyScalar(0.6) },
        uAccentColor: { value: accentColor.clone() },
        uAperture: { value: targetAperture },
        uNoiseOffset: { value: new THREE.Vector2(0, 0) },
        uPulseScale: { value: 1.0 },
        uState: { value: STATE_MAP[state] },
      },
      transparent: true,
      side: THREE.DoubleSide,
      depthWrite: true,
      blending: THREE.NormalBlending,
    });
    coreMaterialRef.current = coreMaterial;

    // === MID RING MATERIAL ===
    const midRingMaterial = new THREE.ShaderMaterial({
      vertexShader: orbMidRingVertex,
      fragmentShader: orbMidRingFragment,
      uniforms: {
        uTime: { value: 0 },
        uMicLevel: { value: micLevel },
        uStateColor: { value: currentColor.clone() },
        uBrandColor: { value: brandColor.clone() },
        uAccentColor: { value: accentColor.clone() },
        uRingRotation: { value: 0 },
        uBlobAmount: { value: config.blobAmount },
        uPulseScale: { value: 1.0 },
        uState: { value: STATE_MAP[state] },
      },
      transparent: true,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    midRingMaterialRef.current = midRingMaterial;

    // === PARTICLE MATERIAL ===
    const particleMaterial = new THREE.ShaderMaterial({
      vertexShader: particleFieldVertex,
      fragmentShader: particleFieldFragment,
      uniforms: {
        uTime: { value: 0 },
        uMicLevel: { value: micLevel },
        uStateColor: { value: currentColor.clone() },
        uPulseScale: { value: 1.0 },
        uState: { value: STATE_MAP[state] },
      },
      transparent: true,
      vertexColors: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    particleMaterialRef.current = particleMaterial;

    // Create meshes
    const coreMesh = new THREE.Mesh(coreGeo, coreMaterial);
    const midRingMesh = new THREE.Mesh(midRingGeo, midRingMaterial);
    const particleSystem = new THREE.Points(particleGeo, particleMaterial);

    coreMeshRef.current = coreMesh;
    midRingMeshRef.current = midRingMesh;
    particleSystemRef.current = particleSystem;

    // Register for cleanup
    registerObject(coreMesh, () => { coreGeo.dispose(); coreMaterial.dispose(); });
    registerObject(midRingMesh, () => { midRingGeo.dispose(); midRingMaterial.dispose(); });
    registerObject(particleSystem, () => { particleGeo.dispose(); particleMaterial.dispose(); });

    scene.add(coreMesh);
    scene.add(midRingMesh);
    scene.add(particleSystem);

    return () => {
      scene.remove(coreMesh);
      scene.remove(midRingMesh);
      scene.remove(particleSystem);
      unregisterObject(coreMesh);
      unregisterObject(midRingMesh);
      unregisterObject(particleSystem);
      geometryRef.current = null;
    };
  }, [size, state, colors, registerObject, unregisterObject, scene]);

  // Animation loop - update uniforms
  useEffect(() => {
    if (!coreMaterialRef.current || !midRingMaterialRef.current || !particleMaterialRef.current) return;

    const animate = () => {
      const elapsed = clock.getElapsedTime();
      const dt = elapsed - lastTimeRef.current;
      lastTimeRef.current = elapsed;

      if (prefersReduced) return;

      // Update aperture (spring toward target)
      const apertureDiff = targetAperture - apertureRef.current;
      apertureRef.current += apertureDiff * 0.15; // Spring factor

      // Update ring rotation
      ringRotationRef.current += config.ringSpeed * Math.PI * 2 * dt;

      // Update noise offset
      noiseOffsetRef.current.x += dt * 0.1;
      noiseOffsetRef.current.y += dt * 0.05;

      // Update pulse scale (spring toward target based on mic level)
      const pulseTarget = config.pulseMin + micLevel * (config.pulseMax - config.pulseMin);
      const pulseDiff = pulseTarget - pulseScaleRef.current;
      pulseScaleRef.current += pulseDiff * 0.2;

      // === Update CORE MATERIAL ===
      coreMaterialRef.current!.uniforms.uTime.value = elapsed;
      coreMaterialRef.current!.uniforms.uMicLevel.value = micLevel;
      coreMaterialRef.current!.uniforms.uStateColor.value.set(currentColor);
      coreMaterialRef.current!.uniforms.uStateGlow.value.set(currentColor).multiplyScalar(0.6);
      coreMaterialRef.current!.uniforms.uAccentColor.value.set(accentColor);
      coreMaterialRef.current!.uniforms.uAperture.value = apertureRef.current;
      coreMaterialRef.current!.uniforms.uNoiseOffset.value.set(noiseOffsetRef.current.x, noiseOffsetRef.current.y);
      coreMaterialRef.current!.uniforms.uPulseScale.value = pulseScaleRef.current;
      coreMaterialRef.current!.uniforms.uState.value = STATE_MAP[state];

      // === Update MID RING MATERIAL ===
      midRingMaterialRef.current!.uniforms.uTime.value = elapsed;
      midRingMaterialRef.current!.uniforms.uMicLevel.value = micLevel;
      midRingMaterialRef.current!.uniforms.uStateColor.value.set(currentColor);
      midRingMaterialRef.current!.uniforms.uBrandColor.value.set(brandColor);
      midRingMaterialRef.current!.uniforms.uAccentColor.value.set(accentColor);
      midRingMaterialRef.current!.uniforms.uRingRotation.value = ringRotationRef.current;
      midRingMaterialRef.current!.uniforms.uPulseScale.value = pulseScaleRef.current;
      midRingMaterialRef.current!.uniforms.uState.value = STATE_MAP[state];

      // === Update PARTICLE MATERIAL ===
      particleMaterialRef.current!.uniforms.uTime.value = elapsed;
      particleMaterialRef.current!.uniforms.uMicLevel.value = micLevel;
      particleMaterialRef.current!.uniforms.uStateColor.value.set(currentColor);
      particleMaterialRef.current!.uniforms.uPulseScale.value = pulseScaleRef.current;
      particleMaterialRef.current!.uniforms.uState.value = STATE_MAP[state];
    };

    animationIntervalRef.current = setInterval(animate, 16); // ~60fps
    return () => {
      if (animationIntervalRef.current) clearInterval(animationIntervalRef.current);
    };
  }, [state, micLevel, uBass, uMid, uTreble, currentColor, prefersReduced, config, targetAperture, ringRotationRef, pulseScaleRef, clock]);

  // Reduced motion: freeze animations
  useEffect(() => {
    if (prefersReduced) {
      if (coreMaterialRef.current) {
        coreMaterialRef.current.uniforms.uMicLevel.value = 0;
        coreMaterialRef.current.uniforms.uAperture.value = targetAperture;
      }
      if (midRingMaterialRef.current) {
        midRingMaterialRef.current.uniforms.uMicLevel.value = 0;
        midRingMaterialRef.current.uniforms.uRingRotation.value = 0;
      }
      if (particleMaterialRef.current) {
        particleMaterialRef.current.uniforms.uMicLevel.value = 0;
      }
      if (coreMeshRef.current) coreMeshRef.current.rotation.set(0, 0, 0);
      if (midRingMeshRef.current) midRingMeshRef.current.rotation.set(0, 0, 0);
      if (particleSystemRef.current) particleSystemRef.current.rotation.set(0, 0, 0);
    }
  }, [prefersReduced, targetAperture]);

  return null; // Renders via Three.js scene
}