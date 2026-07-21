import { useRef, useEffect, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import type { FrequencyBarsProps } from './types';

const BAR_COUNT = 48;

export function FrequencyBars({
  frequencyData,
  color = '#8b5cf6',
  height = 100,
  width = 600,
  reducedMotion = false,
  className = '',
}: FrequencyBarsProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const barHeightsRef = useRef<number[]>(new Array(BAR_COUNT).fill(0));
  const targetHeightsRef = useRef<number[]>(new Array(BAR_COUNT).fill(0));
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const gradient = useMemo(() => {
    if (!canvasRef.current) return null;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return null;
    const grad = ctx.createLinearGradient(0, height, 0, 0);
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

    ctx.clearRect(0, 0, w, h);

    if (!frequencyData || frequencyData.length === 0) {
      if (!prefersReduced) {
        animationFrameRef.current = requestAnimationFrame(draw);
      }
      return;
    }

    const data = frequencyData;
    const binCount = Math.min(data.length, BAR_COUNT);
    const barWidth = (w - (BAR_COUNT - 1) * 2) / BAR_COUNT;

    ctx.fillStyle = gradient || color;

    for (let i = 0; i < BAR_COUNT; i++) {
      let targetHeight = 0;
      if (i < binCount) {
        targetHeight = (data[i] / 255) * h * 0.9;
      }
      targetHeightsRef.current[i] = targetHeight;

      if (prefersReduced) {
        barHeightsRef.current[i] = targetHeight;
      } else {
        barHeightsRef.current[i] += (targetHeight - barHeightsRef.current[i]) * 0.3;
      }

      const barHeight = Math.max(barHeightsRef.current[i], 0.5);
      const x = i * (barWidth + 2);
      const y = h - barHeight;
      const radius = Math.min(barWidth / 2, 3);

      ctx.beginPath();
      ctx.roundRect(x, y, barWidth, barHeight, radius);
      ctx.fill();
    }

    if (!prefersReduced) {
      animationFrameRef.current = requestAnimationFrame(draw);
    }
  }, [frequencyData, color, height, prefersReduced, gradient]);

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
        aria-label={`Frequency bars visualization, ${prefersReduced ? 'reduced motion' : 'animated'} state`}
      />
    </motion.div>
  );
}