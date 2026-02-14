// src/components/FlatMapAuthBackground.tsx
import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { HealthIndicator } from './HealthIndicator';
import earthTextureUrl from '../assets/earth-dark.jpg';

interface FlatMapAuthBackgroundProps {
  variant?: 'login' | 'signup';
}

const citiesData = [
  { lat: 40.71, lng: -74.00, name: 'New York', size: 1.2, color: '#D4AF37' },
  { lat: 37.77, lng: -122.41, name: 'San Francisco', size: 1.0, color: '#D4AF37' },
  { lat: 34.05, lng: -118.24, name: 'Los Angeles', size: 1.0, color: '#D4AF37' },
  { lat: 43.65, lng: -79.38, name: 'Toronto', size: 1.0, color: '#D4AF37' },
  { lat: 19.43, lng: -99.13, name: 'Mexico City', size: 1.0, color: '#D4AF37' },
  { lat: -23.55, lng: -46.63, name: 'Sao Paulo', size: 1.0, color: '#D4AF37' },
  { lat: -34.60, lng: -58.38, name: 'Buenos Aires', size: 1.0, color: '#D4AF37' },
  { lat: 51.50, lng: -0.12, name: 'London', size: 1.2, color: '#D4AF37' },
  { lat: 52.52, lng: 13.40, name: 'Berlin', size: 1.0, color: '#D4AF37' },
  { lat: 48.85, lng: 2.35, name: 'Paris', size: 1.2, color: '#D4AF37' },
  { lat: 41.90, lng: 12.49, name: 'Rome', size: 0.9, color: '#D4AF37' },
  { lat: 59.91, lng: 10.75, name: 'Oslo', size: 0.8, color: '#D4AF37' },
  { lat: 59.32, lng: 18.06, name: 'Stockholm', size: 0.8, color: '#D4AF37' },
  { lat: 52.22, lng: 21.01, name: 'Warsaw', size: 0.8, color: '#D4AF37' },
  { lat: 41.00, lng: 28.97, name: 'Istanbul', size: 1.0, color: '#D4AF37' },
  { lat: 55.75, lng: 37.61, name: 'Moscow', size: 1.2, color: '#D4AF37' },
  { lat: 39.90, lng: 116.40, name: 'Beijing', size: 1.2, color: '#D4AF37' },
  { lat: 31.23, lng: 121.47, name: 'Shanghai', size: 1.4, color: '#D4AF37' },
  { lat: 37.56, lng: 126.97, name: 'Seoul', size: 1.2, color: '#D4AF37' },
  { lat: 35.67, lng: 139.65, name: 'Tokyo', size: 1.4, color: '#D4AF37' },
  { lat: 25.03, lng: 121.56, name: 'Taipei', size: 0.8, color: '#D4AF37' },
  { lat: 13.75, lng: 100.50, name: 'Bangkok', size: 1.0, color: '#D4AF37' },
  { lat: 28.61, lng: 77.20, name: 'New Delhi', size: 1.2, color: '#D4AF37' },
  { lat: 25.20, lng: 55.27, name: 'Dubai', size: 1.0, color: '#D4AF37' },
  { lat: 30.04, lng: 31.23, name: 'Cairo', size: 1.0, color: '#D4AF37' },
  { lat: 1.35, lng: 103.81, name: 'Singapore', size: 0.9, color: '#D4AF37' },
  { lat: -1.28, lng: 36.82, name: 'Nairobi', size: 0.9, color: '#D4AF37' },
  { lat: -33.86, lng: 151.20, name: 'Sydney', size: 1.0, color: '#D4AF37' },
  { lat: -37.81, lng: 144.96, name: 'Melbourne', size: 1.0, color: '#D4AF37' },
  { lat: 27.71, lng: 85.32, name: 'Kathmandu', size: 2.0, color: '#DC2626' },
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
        return dist < 60;
      });

      nearbyCities.forEach((city, index) => {
        const cityPos = latLngToXY(city.lat, city.lng, mapWidth, mapHeight);
        
        const beamGeometry = new THREE.BufferGeometry();
        const points = [
          new THREE.Vector3(cityPos.x, cityPos.y, 0.05),
          new THREE.Vector3(kathmanduPos.x, kathmanduPos.y, 0.05),
        ];
        beamGeometry.setFromPoints(points);
        
        const beamMaterial = new THREE.LineBasicMaterial({
          color: '#DC2626',
          transparent: true,
          opacity: 0.6,
        });
        
        const beam = new THREE.Line(beamGeometry, beamMaterial);
        beam.userData = { 
          delay: index * 0.5,
          speed: 2,
          material: beamMaterial
        };
        beamsGroup.add(beam);
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
        beamsGroup.children.forEach((beam) => {
          if (beam instanceof THREE.Line) {
            const material = beam.material as THREE.LineBasicMaterial;
            const delay = beam.userData.delay;
            const wave = Math.sin((time + delay) * beam.userData.speed);
            material.opacity = 0.2 + (wave + 1) * 0.3;
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
          <div className="font-semibold">CONSTITUTIONAL NETWORK</div>
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
