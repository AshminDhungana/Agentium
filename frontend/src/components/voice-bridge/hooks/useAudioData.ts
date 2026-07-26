import { useAudioVisualization } from '../hooks/useAudioVisualization';

export function useAudioData() {
  const { micLevel, timeDomainData, frequencyData } = useAudioVisualization();
  return { micLevel, timeDomainData, frequencyData };
}