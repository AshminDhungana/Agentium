// src/components/FlatMapAuthBackground.tsx
import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { HealthIndicator } from './HealthIndicator';
import earthTextureUrl from '../assets/earth-dark.jpg';

interface FlatMapAuthBackgroundProps {
  variant?: 'login' | 'signup';
}

const citiesData = [
  { lat: 40.7128, lng: -74.0060, name: 'New York', size: 0.9, color: '#D4AF37' },
  { lat: 37.7749, lng: -122.4194, name: 'San Francisco', size: 0.8, color: '#D4AF37' },
  { lat: 34.0522, lng: -118.2437, name: 'Los Angeles', size: 0.8, color: '#D4AF37' },
  { lat: 43.6532, lng: -79.3832, name: 'Toronto', size: 0.8, color: '#D4AF37' },
  { lat: 19.4326, lng: -99.1332, name: 'Mexico City', size: 0.8, color: '#D4AF37' },
  { lat: -23.5505, lng: -46.6333, name: 'Sao Paulo', size: 0.8, color: '#D4AF37' },
  { lat: -34.6037, lng: -58.3816, name: 'Buenos Aires', size: 0.8, color: '#D4AF37' },
  { lat: 51.5074, lng: -0.1278, name: 'London', size: 0.9, color: '#D4AF37' },
  { lat: 52.5200, lng: 13.4050, name: 'Berlin', size: 0.8, color: '#D4AF37' },
  { lat: 48.8566, lng: 2.3522, name: 'Paris', size: 0.9, color: '#D4AF37' },
  { lat: 41.9028, lng: 12.4964, name: 'Rome', size: 0.75, color: '#D4AF37' },
  { lat: 59.9139, lng: 10.7522, name: 'Oslo', size: 0.7, color: '#D4AF37' },
  { lat: 59.3293, lng: 18.0686, name: 'Stockholm', size: 0.7, color: '#D4AF37' },
  { lat: 52.2297, lng: 21.0122, name: 'Warsaw', size: 0.7, color: '#D4AF37' },
  { lat: 41.0082, lng: 28.9784, name: 'Istanbul', size: 0.8, color: '#D4AF37' },
  { lat: 55.7558, lng: 37.6173, name: 'Moscow', size: 0.9, color: '#D4AF37' },
  { lat: 39.9042, lng: 116.4074, name: 'Beijing', size: 0.9, color: '#D4AF37' },
  { lat: 31.2304, lng: 121.4737, name: 'Shanghai', size: 1.0, color: '#D4AF37' },
  { lat: 37.5665, lng: 126.9780, name: 'Seoul', size: 0.9, color: '#D4AF37' },
  { lat: 35.6762, lng: 139.6503, name: 'Tokyo', size: 1.0, color: '#D4AF37' },
  { lat: 25.0330, lng: 121.5654, name: 'Taipei', size: 0.7, color: '#D4AF37' },
  { lat: 13.7563, lng: 100.5018, name: 'Bangkok', size: 0.8, color: '#D4AF37' },
  { lat: 25.7041, lng: 77.1025, name: 'New Delhi', size: 0.8, color: '#D4AF37' },
  { lat: 25.2048, lng: 55.2708, name: 'Dubai', size: 0.8, color: '#D4AF37' },
  { lat: 30.0444, lng: 31.2357, name: 'Cairo', size: 0.8, color: '#D4AF37' },
  { lat: 1.3521, lng: 103.8198, name: 'Singapore', size: 0.75, color: '#D4AF37' },
  { lat: -1.2921, lng: 36.8219, name: 'Nairobi', size: 0.75, color: '#D4AF37' },
  { lat: -33.8688, lng: 151.2093, name: 'Sydney', size: 0.8, color: '#D4AF37' },
  { lat: -37.8136, lng: 144.9631, name: 'Melbourne', size: 0.8, color: '#D4AF37' },
  { lat: 27.7172, lng: 85.3240, name: 'Kathmandu', size: 1.2, color: '#DC2626' },
];

function latLngToXY(lat: number, lng: number, width: number, height: number) {
  const x = ((lng + 180) / 360) * width;
  const y = ((90 - lat) / 180) * height;
  return { 
    x: x - (width / 2), 
    y: (height / 2) - y 
  };
}

// Singleton to track if background is already initialized
let globalSceneInstance: {
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  renderer: THREE.WebGLRenderer;
  mapPlane: THREE.Mesh;
  beamsGroup: THREE.Group;
  particles: THREE.Points;
  kathmanduRing: THREE.Mesh;
  animationId: number;
  time: number;
  lastTime: number;
  isSignup: boolean;
  mapWidth: number;
  mapHeight: number;
} | null = null;

let instanceCount = 0;

/**
 * @description Animated Three.js world map background rendered on the login/signup pages.
 * Displays city lights, particle effects, and optional Kathmandu-to-global beams in signup mode.
 * @example
 * ```tsx
 * import { FlatMapAuthBackground } from '@/components/FlatMapAuthBackground';
 *
 * <FlatMapAuthBackground variant="signup" />
 * ```
 * @param {'login' | 'signup'} [props.variant] - Visual mode: 'login' for standard, 'signup' for animated beams (default: 'login').
 */
export function FlatMapAuthBackground({ variant = 'login' }: FlatMapAuthBackgroundProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isSignup, setIsSignup] = useState(variant === 'signup');
  const instanceId = useRef(++instanceCount);

  // Update beams when variant changes
  useEffect(() => {
    setIsSignup(variant === 'signup');
    
    if (globalSceneInstance) {
      updateBeams(variant === 'signup');
    }
  }, [variant]);

  const updateBeams = useCallback((showBeams: boolean) => {
    if (!globalSceneInstance) return;
    
    const { beamsGroup, mapWidth, mapHeight } = globalSceneInstance;
    
    // Clear existing beams
    while(beamsGroup.children.length > 0) {
      const child = beamsGroup.children[0];
      if (child instanceof THREE.Line) {
        child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach(m => m.dispose());
          } else {
            child.material.dispose();
          }
        }
      }
      beamsGroup.remove(child);
    }

    if (showBeams) {
      const kathmandu = citiesData.find(c => c.name === 'Kathmandu')!;
      const kathmanduPos = latLngToXY(kathmandu.lat, kathmandu.lng, mapWidth, mapHeight);
      
      const nearbyCities = citiesData.filter(c => {
        if (c.name === 'Kathmandu') return false;
        const pos = latLngToXY(c.lat, c.lng, mapWidth, mapHeight);
        const dist = Math.sqrt(Math.pow(pos.x - kathmanduPos.x, 2) + Math.pow(pos.y - kathmanduPos.y, 2));
        return dist < 80;
      });

      const now = performance.now() / 1000;
      const DRAW_DURATION = 0.55;  // seconds each line takes to extend outward
      const STAGGER = 0.12;        // seconds between each beam starting

      nearbyCities.forEach((city, index) => {
        const cityPos = latLngToXY(city.lat, city.lng, mapWidth, mapHeight);
        const drawInDelay = index * STAGGER;

        // Base line — drawn progressively via drawRange, starts invisible
        const basePoints = [
          new THREE.Vector3(kathmanduPos.x, kathmanduPos.y, 0.05),
          new THREE.Vector3(cityPos.x, cityPos.y, 0.05),
        ];
        const baseGeometry = new THREE.BufferGeometry();
        baseGeometry.setFromPoints(basePoints);
        baseGeometry.setDrawRange(0, 0); // start fully hidden
        
        const baseMaterial = new THREE.LineBasicMaterial({
          color: '#DC2626',
          transparent: true,
          opacity: 0,
        });
        
        const baseLine = new THREE.Line(baseGeometry, baseMaterial);
        baseLine.userData = {
          isBaseLine: true,
          drawInStartTime: now,
          drawInDelay,
          drawDuration: DRAW_DURATION,
          drawnIn: false,
        };
        beamsGroup.add(baseLine);
        
        // Pulse segment — stays hidden until draw-in completes for this beam
        const segmentGeometry = new THREE.BufferGeometry();
        segmentGeometry.setFromPoints(basePoints);
        
        const segmentMaterial = new THREE.LineBasicMaterial({
          color: '#FF3344',
          transparent: true,
          opacity: 0,
        });
        
        const segment = new THREE.Line(segmentGeometry, segmentMaterial);
        segment.userData = {
          isBaseLine: false,
          delay: index * 0.25,
          speed: 0.25,
          material: segmentMaterial,
          cityPos,
          kathmanduPos,
          pulseStartTime: now + drawInDelay + DRAW_DURATION + 0.1,
        };
        beamsGroup.add(segment);
      });
    }
    
    globalSceneInstance.isSignup = showBeams;
  }, []);

  useEffect(() => {
    // If scene already exists, just attach to this container
    if (globalSceneInstance) {
      if (containerRef.current && globalSceneInstance.renderer.domElement.parentNode !== containerRef.current) {
        containerRef.current.appendChild(globalSceneInstance.renderer.domElement);
      }
      setIsLoaded(true);
      updateBeams(isSignup);
      return;
    }

    if (!containerRef.current) return;

    // Initialize scene once
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0A0D12');

    const aspect = window.innerWidth / window.innerHeight;
    const mapAspect = 2;
    
    let viewWidth: number;
    let viewHeight: number;
    
    if (aspect > mapAspect) {
      viewWidth = 200;
      viewHeight = viewWidth / aspect;
    } else {
      viewHeight = 100;
      viewWidth = viewHeight * aspect;
    }

    const camera = new THREE.OrthographicCamera(
      -viewWidth / 2,
      viewWidth / 2,
      viewHeight / 2,
      -viewHeight / 2,
      0.1,
      1000
    );
    camera.position.set(0, 0, 100);

    const renderer = new THREE.WebGLRenderer({ 
      antialias: true, 
      alpha: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerRef.current.appendChild(renderer.domElement);

    const mapWidth = viewWidth;
    const mapHeight = mapWidth / 2;

    const textureLoader = new THREE.TextureLoader();
    const mapGeometry = new THREE.PlaneGeometry(mapWidth, mapHeight);
    
    const mapMaterial = new THREE.MeshBasicMaterial({
      map: textureLoader.load(earthTextureUrl),
      transparent: true,
      opacity: 0.5,
    });
    
    const mapPlane = new THREE.Mesh(mapGeometry, mapMaterial);
    mapPlane.position.set(0, 0, 0);
    scene.add(mapPlane);

    const cityLightsGroup = new THREE.Group();
    mapPlane.add(cityLightsGroup);

    citiesData.forEach((city) => {
      const pos = latLngToXY(city.lat, city.lng, mapWidth, mapHeight);
      
      if (Math.abs(pos.x) > mapWidth / 2 || Math.abs(pos.y) > mapHeight / 2) return;
      
      const glowGeometry = new THREE.CircleGeometry(city.size * 2, 32);
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: city.color,
        transparent: true,
        opacity: city.name === 'Kathmandu' ? 0.2 : 0.15,
      });
      const glow = new THREE.Mesh(glowGeometry, glowMaterial);
      glow.position.set(pos.x, pos.y, 0.1);
      cityLightsGroup.add(glow);

      const ringGeometry = new THREE.CircleGeometry(city.size * 0.8, 32);
      const ringMaterial = new THREE.MeshBasicMaterial({
        color: city.color,
        transparent: true,
        opacity: city.name === 'Kathmandu' ? 0.4 : 0.25,
      });
      const ring = new THREE.Mesh(ringGeometry, ringMaterial);
      ring.position.set(pos.x, pos.y, 0.15);
      cityLightsGroup.add(ring);

      const coreGeometry = new THREE.CircleGeometry(city.size * 0.3, 16);
      const coreMaterial = new THREE.MeshBasicMaterial({
        color: city.name === 'Kathmandu' ? '#ff6b6b' : '#fff8dc',
        transparent: true,
        opacity: 0.9,
      });
      const core = new THREE.Mesh(coreGeometry, coreMaterial);
      core.position.set(pos.x, pos.y, 0.2);
      cityLightsGroup.add(core);

      if (city.name === 'Kathmandu') {
        const pulseGeometry = new THREE.RingGeometry(city.size * 1.5, city.size * 1.8, 64);
        const pulseMaterial = new THREE.MeshBasicMaterial({
          color: city.color,
          transparent: true,
          opacity: 0.6,
          side: THREE.DoubleSide,
        });
        const pulseRing = new THREE.Mesh(pulseGeometry, pulseMaterial);
        pulseRing.position.set(pos.x, pos.y, 0.05);
        cityLightsGroup.add(pulseRing);
      }
    });

    const kathmandu = citiesData.find(c => c.name === 'Kathmandu')!;
    const kathmanduPos = latLngToXY(kathmandu.lat, kathmandu.lng, mapWidth, mapHeight);

    // Beams group (initially empty)
    const beamsGroup = new THREE.Group();
    mapPlane.add(beamsGroup);

    const particlesGeometry = new THREE.BufferGeometry();
    const particlesCount = 50;
    const posArray = new Float32Array(particlesCount * 3);

    for (let i = 0; i < particlesCount * 3; i += 3) {
      posArray[i] = (Math.random() - 0.5) * mapWidth;
      posArray[i + 1] = (Math.random() - 0.5) * mapHeight;
      posArray[i + 2] = (Math.random() - 0.5) * 10;
    }

    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    const particlesMaterial = new THREE.PointsMaterial({
      size: 0.4,
      color: '#8B6F47',
      transparent: true,
      opacity: 0.3,
    });
    const particlesMesh = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particlesMesh);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const kathmanduLight = new THREE.PointLight(0xDC2626, 0.8, 40);
    kathmanduLight.position.set(kathmanduPos.x, kathmanduPos.y, 10);
    mapPlane.add(kathmanduLight);

    // Find kathmandu ring for animation
    const kathmanduRing = cityLightsGroup.children.find(
      child => child instanceof THREE.Mesh && child.geometry instanceof THREE.RingGeometry
    ) as THREE.Mesh | undefined;

    let time = 0;
    let lastTime = performance.now();
    let animationId: number = 0; // Initialize with 0

    const animate = () => {
      animationId = requestAnimationFrame(animate);
      
      const currentTime = performance.now();
      const delta = (currentTime - lastTime) / 1000;
      lastTime = currentTime;
      time += delta;

      // Animate Kathmandu ring
      if (kathmanduRing) {
        const scale = 1 + Math.sin(time * 1.5) * 0.2;
        kathmanduRing.scale.set(scale, scale, 1);
        const material = kathmanduRing.material as THREE.MeshBasicMaterial;
        material.opacity = 0.4 + Math.sin(time * 1.5) * 0.2;
      }

      // Animate beams if in signup mode
      if (globalSceneInstance?.isSignup) {
        const nowSec = performance.now() / 1000;

        beamsGroup.children.forEach((beam) => {
          if (!(beam instanceof THREE.Line)) return;
          const ud = beam.userData;

          if (ud.isBaseLine) {
            // ── Phase 1: draw the line outward from Kathmandu ──
            const elapsed = nowSec - ud.drawInStartTime - ud.drawInDelay;
            if (elapsed < 0) {
              // Not started yet
              beam.geometry.setDrawRange(0, 0);
              (beam.material as THREE.LineBasicMaterial).opacity = 0;
            } else if (!ud.drawnIn) {
              const t = Math.min(elapsed / ud.drawDuration, 1); // 0 → 1
              // ease out cubic so it decelerates as it reaches the city
              const eased = 1 - Math.pow(1 - t, 3);
              beam.geometry.setDrawRange(0, Math.ceil(eased * 2)); // 2 points total
              (beam.material as THREE.LineBasicMaterial).opacity = eased * 0.15;
              if (t >= 1) ud.drawnIn = true;
            } else {
              // ── Phase 2: gentle pulse on the base line ──
              beam.geometry.setDrawRange(0, 2);
              (beam.material as THREE.LineBasicMaterial).opacity = 0.12 + Math.sin(time * 0.8) * 0.03;
            }
          } else {
            // ── Pulse segment: only active after draw-in ──
            if (nowSec < ud.pulseStartTime) {
              ud.material.opacity = 0;
              return;
            }
            const pulseTime = nowSec - ud.pulseStartTime;
            const cycle = (pulseTime * ud.speed + ud.delay) % 3;
            if (cycle < 1) {
              const progress = cycle;
              const fadeIn = Math.min(progress * 3, 1);
              const fadeOut = Math.max(1 - (progress - 0.7) * 3, 0);
              ud.material.opacity = 0.7 * fadeIn * fadeOut;
            } else {
              ud.material.opacity = 0;
            }
          }
        });
      }

      particlesMesh.rotation.z = time * 0.01;

      renderer.render(scene, camera);
    };

    animate();

    // Store global instance
    globalSceneInstance = {
      scene,
      camera,
      renderer,
      mapPlane,
      beamsGroup,
      particles: particlesMesh,
      kathmanduRing: kathmanduRing!,
      animationId,
      time,
      lastTime,
      isSignup: false,
      mapWidth,
      mapHeight,
    };

    setIsLoaded(true);

    // Handle resize
    const handleResize = () => {
      if (!globalSceneInstance) return;
      
      const newAspect = window.innerWidth / window.innerHeight;
      
      let newViewWidth: number;
      let newViewHeight: number;
      
      if (newAspect > mapAspect) {
        newViewWidth = 200;
        newViewHeight = newViewWidth / newAspect;
      } else {
        newViewHeight = 100;
        newViewWidth = newViewHeight * newAspect;
      }
      
      camera.left = -newViewWidth / 2;
      camera.right = newViewWidth / 2;
      camera.top = newViewHeight / 2;
      camera.bottom = -newViewHeight / 2;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup only on last instance unmount
    return () => {
      window.removeEventListener('resize', handleResize);
      
      // Only cleanup if this is the last instance
      instanceCount--;
      if (instanceCount === 0 && globalSceneInstance) {
        cancelAnimationFrame(globalSceneInstance.animationId);
        renderer.dispose();
        renderer.forceContextLoss();
        globalSceneInstance = null;
      }
    };
  }, [isSignup, updateBeams]);

  return (
    <div className="fixed inset-0 overflow-hidden z-0">
      {/* Base Constitutional Gradient - transitions smoothly */}
      <div 
        className="absolute inset-0 transition-all duration-700"
        style={{
          background: isSignup
            ? 'linear-gradient(135deg, #0D1117 0%, #1a1f2e 50%, #141A23 100%)'
            : 'linear-gradient(135deg, #0A0D12 0%, #141A23 50%, #1a1f2e 100%)'
        }}
      />

      {/* Three.js Flat Map Container - persistent */}
      <div 
        ref={containerRef} 
        className="absolute inset-0"
        style={{ opacity: isLoaded ? 0.95 : 0, transition: 'opacity 0.5s ease' }}
      />

      {/* Constitutional Grid Overlay */}
      <div className="absolute inset-0 opacity-[0.02] pointer-events-none">
        <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="constitutionalGrid" width="120" height="120" patternUnits="userSpaceOnUse">
              <path d="M 120 0 L 0 0 0 120" fill="none" stroke="#8B6F47" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#constitutionalGrid)" />
        </svg>
      </div>

      {/* Vignette Overlay */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `
            radial-gradient(ellipse at 50% 50%, transparent 0%, transparent 50%, rgba(10, 13, 18, 0.6) 100%),
            linear-gradient(180deg, rgba(10, 13, 18, 0.4) 0%, transparent 20%, transparent 80%, rgba(10, 13, 18, 0.4) 100%)
          `
        }}
      />

      {/* Federal Constitutional Network Text with HealthIndicator - color transitions */}
      <div className="absolute top-6 right-8 pointer-events-none z-10">
        <div 
          className="text-[10px] tracking-[0.3em] text-right transition-colors duration-700"
          style={{ color: isSignup ? 'rgba(255, 255, 255, 0.6)' : 'rgba(139, 111, 71, 0.5)' }}
        >
          <div className="font-semibold">AGENTIC NETWORK</div>
          <div 
            className="mt-1 text-[9px] tracking-[0.2em] flex items-center justify-end gap-2 transition-colors duration-700" 
            style={{ color: isSignup ? 'rgba(255, 255, 255, 0.4)' : 'rgba(139, 111, 71, 0.35)' }}
          >
            <span>Command Center</span>
            <HealthIndicator />
          </div>
        </div>
      </div>

      {/* Decorative corner elements - color transitions */}
      <div className="absolute top-6 left-6 pointer-events-none">
        <div 
          className="w-16 h-16 border-l border-t opacity-20 transition-colors duration-700" 
          style={{ borderColor: isSignup ? 'rgba(255, 255, 255, 0.3)' : '#8B6F47' }} 
        />
      </div>
      <div className="absolute bottom-6 right-6 pointer-events-none">
        <div 
          className="w-16 h-16 border-r border-b opacity-20 transition-colors duration-700" 
          style={{ borderColor: isSignup ? 'rgba(255, 255, 255, 0.3)' : '#8B6F47' }} 
        />
      </div>

      {/* Bottom line - color transitions */}
      <div 
        className="absolute bottom-0 left-0 right-0 h-px transition-all duration-700"
        style={{
          background: isSignup 
            ? 'linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.2) 50%, transparent 100%)'
            : 'linear-gradient(90deg, transparent 0%, rgba(139, 111, 71, 0.3) 50%, transparent 100%)'
        }}
      />
    </div>
  );
}