import { useRef, useEffect, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import type { WaveformVisualizerProps } from './types';

const SMOOTHING = 0.85;

export function WaveformVisualizer({
  timeDomainData,
  color = '#3b82f6',
  height = 80,
  width = 600,
  reducedMotion = false,
  className = '',
}: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const prevDataRef = useRef<Uint8Array | null>(null);
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const gradient = useMemo(() => {
    if (!canvasRef.current) return null;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return null;
    const grad = ctx.createLinearGradient(0, 0, 0, height);
    grad.addColorStop(0, color);
    grad.addColorStop(0.5, `${color}80`);
    grad.addColorStop(1, 'transparent');
    return grad;
  }, [color, height]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const centerY = h / 2;

    ctx.clearRect(0, 0, w, h);

    if (!timeDomainData || timeDomainData.length === 0) return;

    const data = timeDomainData;
    const sliceWidth = w / data.length;

    if (prefersReduced) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();

      let x = 0;
      for (let i = 0; i < data.length; i++) {
        const v = data[i] / 128.0;
        const y = v * centerY;
        if (i === 0) {
          ctx.moveTo(x, centerY + y);
        } else {
          ctx.lineTo(x, centerY + y);
        }
        x += sliceWidth;
      }
      ctx.stroke();
      return;
    }

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, color);
    grad.addColorStop(0.5, `${color}80`);
    grad.addColorStop(1, 'transparent');
    ctx.strokeStyle = grad;
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    ctx.beginPath();

    let x = 0;
    let prevSmoothedY = 0;
    for (let i = 0; i < data.length; i++) {
      const v = data[i] / 128.0;
      const y = v * centerY * 0.9;

      const prevData = prevDataRef.current;
      const prevV = prevData ? prevData[i] / 128.0 : v;
      const smoothedV = prevV * SMOOTHING + v * (1 - SMOOTHING);
      const smoothedY = smoothedV * centerY * 0.9;

      if (i === 0) {
        ctx.moveTo(x, centerY + smoothedY);
      } else {
        const xc = x - sliceWidth / 2;
        const yc = (centerY + smoothedY + centerY + prevSmoothedY) / 2;
        ctx.quadraticCurveTo(x - sliceWidth, centerY + prevSmoothedY, xc, yc);
      }

      prevSmoothedY = smoothedY;
      x += sliceWidth;
    }

    ctx.stroke();

    ctx.beginPath();
    x = 0;
    prevSmoothedY = 0;
    for (let i = 0; i < data.length; i++) {
      const v = data[i] / 128.0;
      const y = v * centerY * 0.9;

      const prevData = prevDataRef.current;
      const prevV = prevData ? prevData[i] / 128.0 : v;
      const smoothedV = prevV * SMOOTHING + v * (1 - SMOOTHING);
      const smoothedY = smoothedV * centerY * 0.9;

      if (i === 0) {
        ctx.moveTo(x, centerY - smoothedY);
      } else {
        const xc = x - sliceWidth / 2;
        const yc = (centerY - smoothedY + centerY - prevSmoothedY) / 2;
        ctx.quadraticCurveTo(x - sliceWidth, centerY - prevSmoothedY, xc, yc);
      }

      prevSmoothedY = smoothedY;
      x += sliceWidth;
    }

    ctx.stroke();

    prevDataRef.current = data;

    if (!prefersReduced) {
      animationFrameRef.current = requestAnimationFrame(draw);
    }
  }, [timeDomainData, color, height, prefersReduced]);

  useEffect(() => {
    if (prefersReduced) {
      draw();
    } else {
      const animate = () => {
        draw();
        animationFrameRef.current = requestAnimationFrame(animate);
      };
      animationFrameRef.current = requestAnimationFrame(animate);
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [draw, prefersReduced]);

  return (
    <motion.div
      className={`relative overflow-hidden ${className}`}
      style={{ width, height }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="block"
        aria-hidden="true"
        role="img"
        aria-label={`Audio waveform visualization, ${prefersReduced ? 'reduced motion' : 'animated'} state`}
      />
    </motion.div>
  );
}