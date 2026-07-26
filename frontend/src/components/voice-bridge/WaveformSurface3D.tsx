import { useEffect, useRef, useMemo } from 'react';
import * as THREE from 'three';
import { DataTexture, RedFormat, FloatType } from 'three';
import { useThreeContext } from './ThreeContext';
import waveformVertex from './shaders/waveformVertex.glsl';
import waveformFragment from './shaders/waveformFragment.glsl';

interface WaveformSurface3DProps {
  timeDomainData: Uint8Array | null;
  color: THREE.Color;
  prefersReduced: boolean;
}

export function WaveformSurface3D({ timeDomainData, color, prefersReduced }: WaveformSurface3DProps) {
  const { scene, registerObject, unregisterObject, clock } = useThreeContext();
  const meshRef = useRef<THREE.Mesh | null>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  const textureRef = useRef<DataTexture | null>(null);
  const geometryRef = useRef<THREE.PlaneGeometry | null>(null);

  useEffect(() => {
    // Geometry: 200x40 segments = 8000 vertices
    const geometry = new THREE.PlaneGeometry(20, 4, 200, 40);
    geometryRef.current = geometry;

    // Data texture for waveform (256x1)
    const texWidth = 256;
    const data = new Uint8Array(texWidth);
    const texture = new DataTexture(data, texWidth, 1, RedFormat, FloatType);
    texture.needsUpdate = true;
    textureRef.current = texture;

    const material = new THREE.ShaderMaterial({
      vertexShader: waveformVertex,
      fragmentShader: waveformFragment,
      uniforms: {
        uWaveTexture: { value: texture },
        uWaveAmplitude: { value: 1.5 },
        uColor: { value: color.clone() },
        uTime: { value: 0 },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    materialRef.current = material;

    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(0, -8, 0);
    mesh.rotation.x = -Math.PI / 2;
    meshRef.current = mesh;

    registerObject(mesh, () => {
      geometry.dispose();
      material.dispose();
      texture.dispose();
    });

    return () => unregisterObject(mesh);
  }, [registerObject, unregisterObject, color]);

  // Update texture and uniforms each frame
  useEffect(() => {
    if (!materialRef.current || !textureRef.current) return;

    const animate = () => {
      if (!timeDomainData || timeDomainData.length === 0) return;

      // Copy timeDomainData to texture
      const tex = textureRef.current!;
      const texData = tex.image.data as Uint8Array;
      const srcLen = timeDomainData.length;
      for (let i = 0; i < texData.length; i++) {
        const srcIdx = Math.floor(i / texData.length * srcLen);
        texData[i] = timeDomainData[srcIdx];
      }
      tex.needsUpdate = true;

      if (materialRef.current) {
        materialRef.current.uniforms.uTime.value = clock.getElapsedTime();
        materialRef.current.uniforms.uColor.value.set(color);
      }
    };

    const id = setInterval(animate, 16);
    return () => clearInterval(id);
  }, [timeDomainData, color, clock]);

  return null;
}