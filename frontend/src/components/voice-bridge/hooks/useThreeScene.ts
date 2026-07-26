import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { FXAAPass } from 'three/addons/postprocessing/FXAAPass.js';

interface ThreeSceneReturn {
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  composer: EffectComposer;
  clock: THREE.Clock;
  resize: () => void;
  dispose: () => void;
}

const FRUSTUM_SIZE = 25;

export function useThreeScene(container: HTMLDivElement | null): ThreeSceneReturn | null {
  const [sceneObjects, setSceneObjects] = useState<ThreeSceneReturn | null>(null);
  const animationFrameRef = useRef<number>();
  const containerRef = useRef(container);
  containerRef.current = container;

  useEffect(() => {
    if (!containerRef.current) return;
    const containerEl = containerRef.current;
    const width = containerEl.clientWidth;
    const height = containerEl.clientHeight;

    if (width === 0 || height === 0) return;

    // ── Renderer ──────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.domElement.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;display:block;';
    containerEl.appendChild(renderer.domElement);

    // ── Scene ─────────────────────────────────────────────────
    const scene = new THREE.Scene();

    // ── Camera: Orthographic for consistent sizing ────────────
    const aspect = width / height;
    const camera = new THREE.OrthographicCamera(
      (FRUSTUM_SIZE * aspect) / -2,
      (FRUSTUM_SIZE * aspect) / 2,
      FRUSTUM_SIZE / 2,
      FRUSTUM_SIZE / -2,
      0.1,
      100
    );
    camera.position.set(0, 0, 30);
    camera.lookAt(0, 0, 0);

    // ── Lighting ──────────────────────────────────────────────
    const ambient = new THREE.AmbientLight(0xffffff, 0.35);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0xffffff, 0.7);
    keyLight.position.set(10, 15, 10);
    scene.add(keyLight);

    const stateLight = new THREE.PointLight(0x3b82f6, 1.5, 30);
    stateLight.position.set(0, 0, 0);
    scene.add(stateLight);

    const rimLight = new THREE.DirectionalLight(0x4444ff, 0.3);
    rimLight.position.set(-5, 5, -5);
    scene.add(rimLight);

    // ── Post-Processing ───────────────────────────────────────
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));

    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(width, height),
      0.6, 0.4, 0.85
    );
    composer.addPass(bloomPass);

    const fxaaPass = new FXAAPass();
    composer.addPass(fxaaPass);

    // ── Clock ─────────────────────────────────────────────────
    const clock = new THREE.Clock();

    // ── Resize handler ────────────────────────────────────────
    const resize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      if (w === 0 || h === 0) return;

      const newAspect = w / h;
      camera.left = (FRUSTUM_SIZE * newAspect) / -2;
      camera.right = (FRUSTUM_SIZE * newAspect) / 2;
      camera.top = FRUSTUM_SIZE / 2;
      camera.bottom = FRUSTUM_SIZE / -2;
      camera.updateProjectionMatrix();

      renderer.setSize(w, h);
      composer.setSize(w, h);
      bloomPass.resolution.set(w, h);
    };

    // ── Animation loop ────────────────────────────────────────
    const animate = () => {
      animationFrameRef.current = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      composer.render(delta);
    };
    animate();

    // ── Cleanup ───────────────────────────────────────────────
    const dispose = () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      renderer.dispose();
      composer.dispose();
      bloomPass.dispose();
      fxaaPass.dispose();
      if (renderer.domElement.parentElement) renderer.domElement.parentElement.removeChild(renderer.domElement);
    };

    const returnObj: ThreeSceneReturn = { scene, camera, renderer, composer, clock, resize, dispose };
    setSceneObjects(returnObj);

    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      dispose();
      setSceneObjects(null);
    };
  }, []);

  return sceneObjects;
}