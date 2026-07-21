import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { useEffect, useRef, useCallback, useMemo } from 'react';
import type { VoiceState, VoiceOrbProps } from './types';

const ORB_COLORS: Record<VoiceState, string> = {
  idle: '#64748b',
  listening: '#3b82f6',
  speaking: '#8b5cf6',
  processing: '#f59e0b',
  error: '#ef4444',
  muted: '#9ca3af',
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: 'Idle',
  listening: 'Listening...',
  speaking: 'Speaking...',
  processing: 'Processing...',
  error: 'Error',
  muted: 'Muted',
};

const ORB_SIZES = {
  base: 120,
  max: 200,
  min: 100,
};

export function VoiceOrb({
  size = ORB_SIZES.base,
  state = 'idle',
  micLevel = 0,
  className = '',
  reducedMotion = false,
}: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const timeRef = useRef(0);
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const scale = useMotionValue(1);
  const rotation = useMotionValue(0);
  const glowRadius = useMotionValue(0);
  const pulseScale = useMotionValue(1);

  const springConfig = { stiffness: 300, damping: 30, mass: 1 };
  const springConfigFast = { stiffness: 400, damping: 25, mass: 1 };

  const targetScale = useMemo(() => {
    switch (state) {
      case 'listening':
        return 1 + micLevel * 0.5;
      case 'speaking':
        return 1 + micLevel * 0.3;
      case 'processing':
        return 1.05;
      case 'error':
        return 1;
      case 'muted':
        return 0.9;
      default:
        return 1;
    }
  }, [state, micLevel]);

  const targetGlow = useMemo(() => {
    switch (state) {
      case 'listening':
        return 40 + micLevel * 60;
      case 'speaking':
        return 30 + micLevel * 50;
      case 'processing':
        return 20;
      case 'error':
        return 30;
      default:
        return 0;
    }
  }, [state, micLevel]);

  useEffect(() => {
    scale.set(targetScale);
  }, [targetScale]);

  useEffect(() => {
    glowRadius.set(targetGlow);
  }, [targetGlow]);

  useEffect(() => {
    if (state === 'speaking') {
      const animate = () => {
        rotation.set(rotation.get() + 0.5);
        frameRef.current = requestAnimationFrame(animate);
      };
      frameRef.current = requestAnimationFrame(animate);
      return () => cancelAnimationFrame(frameRef.current);
    }
  }, [state, rotation]);

   useEffect(() => {
     if (state === 'idle' && !prefersReduced) {
       const animate = () => {
         pulseScale.set(pulseScale.get() > 1 ? 0.98 : 1.02);
         frameRef.current = requestAnimationFrame(animate);
       };
       frameRef.current = requestAnimationFrame(animate);
       return () => cancelAnimationFrame(frameRef.current);
     }
   }, [state, prefersReduced]);

  const springScale = useSpring(scale, springConfig);
  const springGlow = useSpring(glowRadius, springConfigFast);
  const springPulse = useSpring(pulseScale, { stiffness: 200, damping: 20 });

  const color = ORB_COLORS[state] || ORB_COLORS.idle;
  const glowColor = useTransform(springGlow, (g) => `${color}${Math.round(Math.min(g, 255)).toString(16).padStart(2, '0')}`);
  const bgColor = useTransform(springScale, (s) => `rgba(${hexToRgb(color)}, ${0.15 * s})`);
  const borderColor = useTransform(springScale, (s) => `${color}${Math.round(0.3 * s * 255).toString(16).padStart(2, '0')}`);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const baseR = size * 0.28;
    const pointCount = 48;

    ctx.clearRect(0, 0, w, h);

    if (prefersReduced) {
      ctx.beginPath();
      ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
      const gradient = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, `${color}66`);
      ctx.fillStyle = gradient;
      ctx.fill();
      return;
    }

    timeRef.current += 0.02;
    const time = timeRef.current;

    const glowGrad = ctx.createRadialGradient(cx, cy, baseR * 0.5, cx, cy, baseR * 1.4 + springGlow.get());
    glowGrad.addColorStop(0, `${color}33`);
    glowGrad.addColorStop(1, `${color}00`);
    ctx.fillStyle = glowGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR * 1.4 + springGlow.get(), 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    for (let i = 0; i <= pointCount; i++) {
      const angle = (i / pointCount) * Math.PI * 2 - Math.PI / 2;
      let noise = 0;

      if (state === 'listening' || state === 'speaking') {
        noise = simplex2D(cx + baseR * Math.cos(angle), cy + baseR * Math.sin(angle), time) * (5 + micLevel * 25);
      } else if (state === 'processing') {
        noise = Math.sin(time * 2 + i * 0.5) * 12;
      } else if (state === 'error') {
        noise = Math.sin(time * 10 + i) * 5;
      }

      const r = baseR + noise;
      const px = cx + Math.cos(angle) * r;
      const py = cy + Math.sin(angle) * r;

      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();

    const grad = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
    grad.addColorStop(0, color);
    grad.addColorStop(0.5, `${color}cc`);
    grad.addColorStop(1, `${color}44`);
    ctx.fillStyle = grad;
    ctx.fill();

    const innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.4);
    innerGlow.addColorStop(0, 'rgba(255,255,255,0.15)');
    innerGlow.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = innerGlow;
    ctx.fill();
  }, [size, state, micLevel, color, springGlow, prefersReduced]);

  useEffect(() => {
    const animate = () => {
      draw();
      frameRef.current = requestAnimationFrame(animate);
    };
    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [draw]);

  const icon = useMemo(() => {
    switch (state) {
      case 'listening':
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="22" />
          </svg>
        );
      case 'speaking':
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.5 8c3 2 3 8 0 10" />
            <path d="M19.5 8c3 2 3 8 0 10" />
          </svg>
        );
      case 'processing':
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="8" />
          </svg>
        );
      case 'error':
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
        );
      case 'muted':
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="1" y1="1" x2="23" y2="23" />
            <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
            <path d="M17 16.95a7 7 0 0 1-5 1.16" />
          </svg>
        );
      default:
        return (
          <svg width={size * 0.35} height={size * 0.35} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="22" />
          </svg>
        );
    }
  }, [state, size]);

  return (
    <motion.div
      className={`relative flex items-center justify-center ${className}`}
      style={{
        width: size,
        height: size,
      }}
      role="img"
      aria-label={STATE_LABELS[state]}
      aria-live="polite"
    >
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="block"
        aria-hidden="true"
      />

      <motion.div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          background: bgColor,
          border: '1px solid',
          borderColor: borderColor,
          boxShadow: `0 0 ${springGlow.get()}px ${springGlow.get() / 3}px ${glowColor}`,
          transform: `scale(${springScale.get() * springPulse.get()})`,
          transition: 'none',
        }}
        aria-hidden="true"
      />

      <motion.div
        style={{
          position: 'absolute',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))',
          transform: state === 'speaking' ? `rotate(${rotation.get()}deg)` : 'none',
        }}
        animate={{ opacity: state === 'speaking' ? 1 : 1 }}
        transition={{ duration: 0.2 }}
      >
        {icon}
      </motion.div>

      {prefersReduced && (
        <span className="absolute bottom-[-20px] text-xs font-semibold text-white/70 text-center w-full" aria-live="polite">
          {STATE_LABELS[state]}
        </span>
      )}
    </motion.div>
  );
}

function simplex2D(x: number, y: number, time: number): number {
  return Math.sin(x * 0.01 + time) * 0.5 + Math.cos(y * 0.015 + time * 0.7) * 0.5;
}

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r}, ${g}, ${b}`;
}