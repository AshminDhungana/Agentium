import { useEffect, useRef, useState, useCallback } from 'react';
import type { UseAudioVisualizationReturn } from '../types';

export function useAudioVisualization(): UseAudioVisualizationReturn {
  const [timeDomainData, setTimeDomainData] = useState<Uint8Array>(new Uint8Array(128));
  const [frequencyData, setFrequencyData] = useState<Uint8Array>(new Uint8Array(64));
  const [micLevel, setMicLevel] = useState(0);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const updateVisualization = useCallback(() => {
    if (!analyserRef.current) return;

    const tdData = new Uint8Array(analyserRef.current.frequencyBinCount);
    const fdData = new Uint8Array(analyserRef.current.frequencyBinCount);

    analyserRef.current.getByteTimeDomainData(tdData);
    analyserRef.current.getByteFrequencyData(fdData);

    setTimeDomainData(tdData);
    setFrequencyData(fdData.slice(0, 64));

    let sum = 0;
    for (let i = 0; i < tdData.length; i++) {
      const val = (tdData[i] - 128) / 128;
      sum += val * val;
    }
    const rms = Math.sqrt(sum / tdData.length);
    setMicLevel(Math.min(rms * 2, 1));

    animationFrameRef.current = requestAnimationFrame(updateVisualization);
  }, []);

  const start = useCallback(async (stream: MediaStream) => {
    if (audioContextRef.current) return;

    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;

      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      analyserRef.current = analyser;

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      source.connect(analyser);

      streamRef.current = stream;

      updateVisualization();
    } catch (error) {
      console.warn('[useAudioVisualization] Failed to start:', error);
    }
  }, [updateVisualization]);

  const stop = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    streamRef.current = null;

    setTimeDomainData(new Uint8Array(128));
    setFrequencyData(new Uint8Array(64));
    setMicLevel(0);
  }, []);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    timeDomainData,
    frequencyData,
    micLevel,
    start,
    stop,
  };
}