import { useMemo, Suspense, lazy } from 'react';
import { ThreeProvider } from './ThreeContext';
import { useThreeScene } from './hooks/useThreeScene';
import { useThreeColors } from './hooks/useThreeColors';
import { useReducedMotion } from './hooks/useReducedMotion';
import { VoiceOrb3D } from './VoiceOrb3D';
import { WaveformSurface3D } from './WaveformSurface3D';
import { FrequencyBars3D } from './FrequencyBars3D';
import { ParticleField } from './ParticleField';
import { ConnectionStatus3D } from './ConnectionStatus3D';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error' | 'reconnecting';

interface ThreeSceneProps {
  voiceState: VoiceState;
  micLevel: number;
  timeDomainData: Uint8Array | null;
  frequencyData: Uint8Array | null;
  status: ConnectionStatus;
  prefersReduced: boolean;
}

function ThreeSceneInner({
  voiceState,
  micLevel,
  timeDomainData,
  frequencyData,
  status,
  prefersReduced,
}: ThreeSceneProps) {
  const containerRef = useMemo(() => ({ current: null as HTMLDivElement | null }), []);
  const colors = useThreeColors();
  const three = useThreeScene(containerRef.current);

  if (!three) return <LoadingFallback />;

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
        <VoiceOrb3D
          size={220}
          state={voiceState}
          micLevel={micLevel}
          frequencyData={frequencyData}
          colors={colors}
          prefersReduced={prefersReduced}
        />
        <WaveformSurface3D
          timeDomainData={timeDomainData}
          color={colors[voiceState === 'idle' ? 'idle' : voiceState]}
          prefersReduced={prefersReduced}
        />
        <FrequencyBars3D
          frequencyData={frequencyData}
          color={colors[voiceState === 'idle' ? 'idle' : voiceState]}
          prefersReduced={prefersReduced}
        />
        <ParticleField
          micLevel={micLevel}
          state={voiceState}
          prefersReduced={prefersReduced}
          color={colors[voiceState === 'idle' ? 'idle' : voiceState]}
        />
        <ConnectionStatus3D status={status} colors={colors} />
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