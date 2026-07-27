import { useEffect, useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useThreeContext } from './ThreeContext';
import { useThreeColors } from './hooks/useThreeColors';

const BAR_COUNT = 48;

interface FrequencyBars3DProps {
  frequencyData: Uint8Array | null;
  prefersReduced: boolean;
}

export function FrequencyBars3D({ frequencyData, prefersReduced }: FrequencyBars3DProps) {
  const { scene, registerObject, unregisterObject } = useThreeContext();
  const colors = useThreeColors();
  const instancedMeshRef = useRef<THREE.InstancedMesh | null>(null);
  const geometryRef = useRef<THREE.CylinderGeometry | null>(null);
  const materialRef = useRef<THREE.MeshPhysicalMaterial | null>(null);
  const targetHeightsRef = useRef<Float32Array>(new Float32Array(BAR_COUNT));
  const currentHeightsRef = useRef<Float32Array>(new Float32Array(BAR_COUNT).fill(1));
  const dummyRef = useRef<THREE.Object3D>(new THREE.Object3D());
  const animationRef = useRef<ReturnType<typeof setInterval>>();

  // Theme-aware colors from CSS variables
  const barColors = useMemo(() => {
    const c = [];
    for (let i = 0; i < BAR_COUNT; i++) {
      const ratio = i / BAR_COUNT;
      const color = new THREE.Color();
      if (ratio < 0.33) {
        color.setStyle(getComputedStyle(document.documentElement).getPropertyValue('--c-success').trim() || '#10b981');
      } else if (ratio < 0.66) {
        color.setStyle(getComputedStyle(document.documentElement).getPropertyValue('--c-warning').trim() || '#f59e0b');
      } else {
        color.setStyle(getComputedStyle(document.documentElement).getPropertyValue('--c-error').trim() || '#ef4444');
      }
      c.push(color);
    }
    return c;
  }, []);

  // Initialize instanced mesh
  useEffect(() => {
    const geometry = new THREE.CylinderGeometry(0.08, 0.08, 1, 6, 1, true); // open-ended
    geometryRef.current = geometry;

    const material = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.8,
      roughness: 0.3,
      metalness: 0.1,
      clearcoat: 1.0,
      clearcoatRoughness: 0.1,
      side: THREE.DoubleSide,
      vertexColors: true,
    });
    materialRef.current = material;

    const mesh = new THREE.InstancedMesh(geometry, material, BAR_COUNT);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(BAR_COUNT * 3), 3);
    instancedMeshRef.current = mesh;

    // Position in semi-circle around orb
    for (let i = 0; i < BAR_COUNT; i++) {
      const angle = (i / BAR_COUNT) * Math.PI - Math.PI / 2;
      const x = Math.cos(angle) * 12;
      const y = -2 + (i / BAR_COUNT) * 4;
      const z = Math.sin(angle) * 12;

      dummyRef.current.position.set(x, y, z);
      dummyRef.current.scale.set(1, 1, 1);
      dummyRef.current.updateMatrix();
      mesh.setMatrixAt(i, dummyRef.current.matrix);

      // Theme-aware color gradient
      const c = barColors[i];
      mesh.setColorAt(i, c);
    }

    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor!.needsUpdate = true;

    registerObject(mesh, () => {
      geometry.dispose();
      material.dispose();
    });

    return () => unregisterObject(mesh);
  }, [registerObject, unregisterObject, barColors]);

  // Compute target heights from frequencyData
  useEffect(() => {
    if (!frequencyData || frequencyData.length === 0) return;

    const len = frequencyData.length;
    for (let i = 0; i < BAR_COUNT; i++) {
      const idx = Math.floor(i / BAR_COUNT * len);
      targetHeightsRef.current[i] = Math.max(0.1, frequencyData[idx] / 255 * 6);
    }
  }, [frequencyData]);

  // Spring animation with reduced motion support
  useEffect(() => {
    if (!instancedMeshRef.current) return;

    const animate = () => {
      if (prefersReduced) return; // Freeze animation when reduced motion

      const mesh = instancedMeshRef.current!;
      const damping = 0.15;

      for (let i = 0; i < BAR_COUNT; i++) {
        const target = targetHeightsRef.current[i];
        const current = currentHeightsRef.current[i];
        const next = current + (target - current) * damping;
        currentHeightsRef.current[i] = next;

        mesh.getMatrixAt(i, dummyRef.current.matrix);
        dummyRef.current.scale.y = next;
        dummyRef.current.updateMatrix();
        mesh.setMatrixAt(i, dummyRef.current.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    };

    animationRef.current = setInterval(animate, 16);
    return () => {
      if (animationRef.current) clearInterval(animationRef.current);
    };
  }, [prefersReduced]);

  return null;
}