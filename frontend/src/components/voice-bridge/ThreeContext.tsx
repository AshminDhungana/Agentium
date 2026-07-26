import { createContext, useContext, useEffect, ReactNode } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';

interface ThreeContextValue {
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  composer: EffectComposer;
  clock: THREE.Clock;
  registerObject: (object: THREE.Object3D, cleanup?: () => void) => void;
  unregisterObject: (object: THREE.Object3D) => void;
}

const ThreeContext = createContext<ThreeContextValue | null>(null);

export function ThreeProvider({
  children,
  scene,
  camera,
  renderer,
  composer,
  clock,
}: {
  children: ReactNode;
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  composer: EffectComposer;
  clock: THREE.Clock;
}) {
  const registered = new Map<THREE.Object3D, () => void>();

  const registerObject = (object: THREE.Object3D, cleanup?: () => void) => {
    scene.add(object);
    if (cleanup) registered.set(object, cleanup);
  };

  const unregisterObject = (object: THREE.Object3D) => {
    scene.remove(object);
    const cleanup = registered.get(object);
    if (cleanup) cleanup();
    registered.delete(object);
  };

  return (
    <ThreeContext.Provider value={{ scene, camera, renderer, composer, clock, registerObject, unregisterObject }}>
      {children}
    </ThreeContext.Provider>
  );
}

export function useThreeContext(): ThreeContextValue {
  const ctx = useContext(ThreeContext);
  if (!ctx) throw new Error('useThreeContext must be used within ThreeProvider');
  return ctx;
}