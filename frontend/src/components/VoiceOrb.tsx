import { useRef, useEffect, useCallback } from 'react';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

const ORB_COLORS: Record<VoiceState, string> = {
  idle: '#3b82f6',
  listening: '#3b82f6',
  thinking: '#8b5cf6',
  speaking: '#10b981',
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: 'Idle',
  listening: 'Listening...',
  thinking: 'Thinking...',
  speaking: 'Speaking...',
};

interface VoiceOrbProps {
  size: number;
  voiceState: VoiceState;
  micLevel: number;
  className?: string;
  reducedMotion?: boolean;
}

function simplex2D(x: number, y: number, time: number): number {
  return Math.sin(x * 3.0 + time) * 0.3 + Math.cos(y * 4.0 + time * 0.7) * 0.3;
}

export function VoiceOrb({ size, voiceState, micLevel, className = '', reducedMotion = false }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const timeRef = useRef(0);

  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

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
    const amplitude = voiceState === 'idle' ? 5 : 10 + micLevel * 25;
    const color = ORB_COLORS[voiceState];

    ctx.clearRect(0, 0, w, h);

    if (prefersReduced) {
      ctx.beginPath();
      ctx.arc(cx, cy, baseR, 0, Math.PI * 2);
      const gradient = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, color + '66');
      ctx.fillStyle = gradient;
      ctx.fill();
      return;
    }

    timeRef.current += 0.02;
    const time = timeRef.current;

    // Outer glow
    const glowGradient = ctx.createRadialGradient(cx, cy, baseR * 0.5, cx, cy, baseR * 1.4);
    glowGradient.addColorStop(0, `${color}22`);
    glowGradient.addColorStop(1, `${color}00`);
    ctx.fillStyle = glowGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR * 1.4, 0, Math.PI * 2);
    ctx.fill();

    // Blob path
    ctx.beginPath();
    for (let i = 0; i <= pointCount; i++) {
      const angle = (i / pointCount) * Math.PI * 2 - Math.PI / 2;
      let noise = 0;
      if (voiceState === 'listening' || voiceState === 'speaking') {
        noise = simplex2D(cx + baseR * Math.cos(angle), cy + baseR * Math.sin(angle), time) * amplitude;
      } else if (voiceState === 'thinking') {
        noise = Math.sin(time * 2 + i * 0.5) * 12;
      }
      const r = baseR + noise;
      const px = cx + Math.cos(angle) * r;
      const py = cy + Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();

    const gradient = ctx.createRadialGradient(cx - 10, cy - 10, 5, cx, cy, baseR + 10);
    gradient.addColorStop(0, color);
    gradient.addColorStop(0.5, color + 'cc');
    gradient.addColorStop(1, color + '44');
    ctx.fillStyle = gradient;
    ctx.fill();

    // Inner highlight
    const innerGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.4);
    innerGlow.addColorStop(0, 'rgba(255,255,255,0.15)');
    innerGlow.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = innerGlow;
    ctx.fill();

    frameRef.current = requestAnimationFrame(draw);
  }, [size, voiceState, micLevel, prefersReduced]);

  useEffect(() => {
    draw();
    return () => cancelAnimationFrame(frameRef.current);
  }, [draw]);

  return (
    <div className={`relative flex items-center justify-center ${className}`} style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="block"
        aria-hidden="true"
      />
      {prefersReduced && (
        <span
          className="absolute bottom-4 text-xs font-semibold text-white/70"
          aria-live="polite"
        >
          {STATE_LABELS[voiceState]}
        </span>
      )}
    </div>
  );
}
