import { useMemo, useRef, useEffect, Suspense } from 'react';
import { ThreeProvider } from './ThreeContext';
import { useThreeScene } from './hooks/useThreeScene';
import { useThreeColors } from './hooks/useThreeColors';
import { LivingOrb3D } from './LivingOrb3D';
import { WaveformSurface3D } from './WaveformSurface3D';
import { FrequencyBars3D } from './FrequencyBars3D';
import { ParticleField } from './ParticleField';
import { ConnectionStatus3D } from './ConnectionStatus3D';
import { Canvas2DFallback } from './Canvas2DFallback';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error' | 'reconnecting';

interface ThreeSceneProps {
  voiceState: VoiceState;
  micLevel: number;
  timeDomainData: Uint8Array | null;
  frequencyData: Uint8Array | null;
  status: ConnectionStatus;
  prefersReduced: boolean;
  orbSize?: number;
}

function ThreeSceneInner({
  voiceState,
  micLevel,
  timeDomainData,
  frequencyData,
  status,
  prefersReduced,
  orbSize,
}: ThreeSceneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const colors = useThreeColors();
  const three = useThreeScene(containerRef.current);

  // WebGL not available - fall back to 2D canvas
  if (!three) {
    return (
      <Canvas2DFallback
        voiceState={voiceState}
        micLevel={micLevel}
        timeDomainData={timeDomainData}
        frequencyData={frequencyData}
        status={status}
        orbSize={orbSize}
      />
    );
  }

  // Determine color for waveform and particles based on voice state
  const stateColor = colors[voiceState === 'idle' ? 'idle' : voiceState === 'muted' ? 'muted' : voiceState === 'error' ? 'error' : voiceState === 'processing' ? 'thinking' : voiceState];

  // Mouse parallax effect (disabled in reduced motion)
  const mouseRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (prefersReduced) return;
    const container = containerRef.current;
    if (!container) return;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      mouseRef.current.x = (e.clientX - rect.left) / rect.width - 0.5;
      mouseRef.current.y = (e.clientY - rect.top) / rect.height - 0.5;
    };

    container.addEventListener('mousemove', handleMouseMove);
    return () => container.removeEventListener('mousemove', handleMouseMove);
  }, [prefersReduced]);

  useEffect(() => {
    if (!three || prefersReduced) return;

    const animate = () => {
      requestAnimationFrame(animate);
      // Apply subtle parallax to camera
      const maxOffset = 0.5; // Max 0.5 units offset
      three.camera.position.x = mouseRef.current.x * maxOffset;
      three.camera.position.y = -mouseRef.current.y * maxOffset;
      three.camera.lookAt(0, 0, 0);
    };
    animate();
  }, [three, prefersReduced]);

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', width: '100%', height: '100%', minHeight: 300 }}
      className="three-canvas"
    >
      <ThreeProvider
        scene={three.scene}
        camera={three.camera}
        renderer={three.renderer}
        composer={three.composer}
        clock={three.clock}
      >
        <LivingOrb3D
          size={orbSize ?? 220}
          state={voiceState}
          micLevel={micLevel}
          frequencyData={frequencyData}
          colors={colors}
          prefersReduced={prefersReduced}
        />
        <WaveformSurface3D
          timeDomainData={timeDomainData}
          color={stateColor}
          prefersReduced={prefersReduced}
        />
        <FrequencyBars3D
          frequencyData={frequencyData}
          prefersReduced={prefersReduced}
        />
        <ParticleField
          micLevel={micLevel}
          state={voiceState}
          prefersReduced={prefersReduced}
        />
        <ConnectionStatus3D status={status} prefersReduced={prefersReduced} />
      </ThreeProvider>
    </div>
  );
}

function LoadingFallback() {
  return (
    <div style={{ width: '100%', height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-label="Loading 3D scene" />
    </div>
  );
}

export function ThreeScene({
  voiceState,
  micLevel,
  timeDomainData,
  frequencyData,
  status,
  prefersReduced,
}: ThreeSceneProps) {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ThreeSceneInner
        voiceState={voiceState}
        micLevel={micLevel}
        timeDomainData={timeDomainData}
        frequencyData={frequencyData}
        status={status}
        prefersReduced={prefersReduced}
      />
    </Suspense>
  );
}