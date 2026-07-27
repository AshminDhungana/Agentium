// frontend/src/components/voice-bridge/Canvas2DFallback.tsx — COMPLETE REPLACEMENT
import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useReducedMotion } from './hooks/useReducedMotion';

type VoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';
type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error' | 'reconnecting';

interface Canvas2DFallbackProps {
  voiceState: VoiceState;
  micLevel: number;
  timeDomainData: Uint8Array | null;
  frequencyData: Uint8Array | null;
  status: ConnectionStatus;
  prefersReduced?: boolean;
  orbSize?: number;
}

const BAR_COUNT = 48;
const PARTICLE_COUNT = 12;
const ORB_BASE_RADIUS = 80;

export function Canvas2DFallback({
  voiceState,
  micLevel,
  timeDomainData,
  frequencyData,
  status,
  prefersReduced: prefersReducedProp = false,
  orbSize = 320,
}: Canvas2DFallbackProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const timeRef = useRef(0);
  const barHeightsRef = useRef<number[]>(Array(BAR_COUNT).fill(0));
  const particlesRef = useRef<Particle[]>([]);
  const { prefersReduced: prefersReducedHook } = useReducedMotion();
  const prefersReduced = prefersReducedProp || prefersReducedHook;

  // Initialize particles
  useEffect(() => {
    if (particlesRef.current.length === 0) {
      const effectiveOrbRadius = Math.max(orbSize / 4, 60);
      particlesRef.current = Array.from({ length: PARTICLE_COUNT }, () => ({
        angle: Math.random() * Math.PI * 2,
        radius: effectiveOrbRadius * 1.3 + Math.random() * effectiveOrbRadius * 0.8,
        speed: 0.005 + Math.random() * 0.015,
        size: 1.5 + Math.random() * 3,
        opacity: 0.3 + Math.random() * 0.5,
        phase: Math.random() * Math.PI * 2,
      }));
    }
  }, [orbSize]);

  // Get CSS custom properties for design system consistency
  const getDesignTokens = useCallback(() => {
    const style = getComputedStyle(document.documentElement);
    return {
      canvasBg: style.getPropertyValue('--c-canvas').trim() || '#0f172a',
      panelBg: style.getPropertyValue('--c-panel').trim() || '#1e293b',
      glassBg: style.getPropertyValue('--c-glass-bg').trim() || 'rgba(30, 41, 59, 0.7)',
      glassBorder: style.getPropertyValue('--c-glass-border').trim() || 'rgba(148, 163, 184, 0.2)',
      brand: style.getPropertyValue('--c-brand').trim() || '#3b82f6',
      brandHover: style.getPropertyValue('--c-brand-hover').trim() || '#2563eb',
      brand2: style.getPropertyValue('--c-brand-2').trim() || '#8b5cf6',
      success: style.getPropertyValue('--c-success').trim() || '#10b981',
      warning: style.getPropertyValue('--c-warning').trim() || '#f59e0b',
      error: style.getPropertyValue('--c-error').trim() || '#ef4444',
      voiceListening: style.getPropertyValue('--c-voice-listening').trim() || '#3b82f6',
      voiceSpeaking: style.getPropertyValue('--c-voice-speaking').trim() || '#059669',
      voiceThinking: style.getPropertyValue('--c-voice-thinking').trim() || '#7c3aed',
      voiceError: style.getPropertyValue('--c-voice-error').trim() || '#ef4444',
      voiceGlow: style.getPropertyValue('--c-voice-glow').trim() || 'rgba(59, 130, 246, 0.4)',
      textPrimary: style.getPropertyValue('--color-text-primary').trim() || '#f1f5f9',
      textSecondary: style.getPropertyValue('--color-text-secondary').trim() || '#94a3b8',
      textMuted: style.getPropertyValue('--color-text-muted').trim() || '#64748b',
      hairline: style.getPropertyValue('--c-hairline').trim() || 'rgba(148, 163, 184, 0.15)',
    };
  }, []);

  // State-specific color palette with CSS variable overrides
  const stateColors = useMemo(() => {
    const tokens = getDesignTokens();
    return {
      listening: {
        primary: tokens.voiceListening,
        glow: tokens.voiceListening,
        gradient: [tokens.voiceListening, tokens.brand],
      },
      speaking: {
        primary: tokens.voiceSpeaking,
        glow: tokens.voiceSpeaking,
        gradient: [tokens.voiceSpeaking, tokens.success],
      },
      processing: {
        primary: tokens.voiceThinking,
        glow: tokens.voiceThinking,
        gradient: [tokens.voiceThinking, tokens.brand2],
      },
      error: {
        primary: tokens.voiceError,
        glow: tokens.voiceError,
        gradient: [tokens.voiceError, tokens.error],
      },
      muted: {
        primary: tokens.textMuted,
        glow: tokens.textMuted,
        gradient: [tokens.textMuted, tokens.hairline],
      },
      idle: {
        primary: tokens.textSecondary,
        glow: tokens.hairline,
        gradient: [tokens.textSecondary, tokens.hairline],
      },
    };
  }, [getDesignTokens]);

  // Status color
  const getStatusColor = useCallback((status: ConnectionStatus) => {
    const tokens = getDesignTokens();
    switch (status) {
      case 'connected': return tokens.success;
      case 'connecting':
      case 'reconnecting': return tokens.warning;
      case 'error': return tokens.error;
      default: return tokens.textMuted;
    }
  }, [getDesignTokens]);

  // Spring physics for bars (critically damped)
  const springDamping = 0.15;
  const springStiffness = 180;

  // Orb pulse scale with spring-like easing
  const getOrbPulseScale = useCallback((state: VoiceState, level: number, time: number): number => {
    if (prefersReduced) return 1;
    const basePulse = Math.sin(time * 2.5) * 0.03;
    const levelInfluence = level * 0.35;
    const stateMultiplier = state === 'listening' ? 1.2 : state === 'speaking' ? 1.0 : 0.8;
    return 1 + basePulse + levelInfluence * stateMultiplier;
  }, [prefersReduced]);

  // Draw helper: rounded rectangle
  const roundRect = useCallback((
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    w: number,
    h: number,
    r: number
  ) => {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }, []);

  // Main render loop
  const render = useCallback((timestamp: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!ctx) return;

    const dt = prefersReduced ? 0 : Math.min((timestamp - timeRef.current) / 1000, 1/30);
    timeRef.current = timestamp;

    const { width, height } = canvas;
    const cx = width / 2;
    const cy = height / 2;
    const colors = stateColors[voiceState];
    const statusColor = getStatusColor(status);
    const tokens = getDesignTokens();

    // Clear with canvas background
    ctx.fillStyle = tokens.canvasBg;
    ctx.fillRect(0, 0, width, height);

    // ============================================
    // DEPTH LAYER 1: Subtle background atmosphere
    // ============================================
    // Radial glow behind orb (matches voice state)
    const glowRadius = Math.max(width, height) * 0.6;
    const glowGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowRadius);
    const glowOpacity = voiceState === 'idle' ? 0.08 : voiceState === 'muted' ? 0.06 : 0.18;
    glowGradient.addColorStop(0, `${colors.glow}${Math.round(glowOpacity * 255).toString(16).padStart(2, '0')}`);
    glowGradient.addColorStop(0.5, `${colors.glow}10`);
    glowGradient.addColorStop(1, 'transparent');
    ctx.fillStyle = glowGradient;
    ctx.fillRect(0, 0, width, height);

    // Subtle grid pattern (matches AgentsPage aesthetic)
    ctx.save();
    ctx.globalAlpha = 0.03;
    ctx.strokeStyle = tokens.hairline;
    ctx.lineWidth = 1;
    const gridSize = 40;
    for (let x = 0; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();

    // ============================================
    // DEPTH LAYER 2: Orbital particles
    // ============================================
    if (!prefersReduced) {
      ctx.save();
      particlesRef.current.forEach((p) => {
        // Orbital motion influenced by mic level
        const speedMod = 1 + micLevel * 3;
        p.angle += p.speed * speedMod * dt * 60;
        p.phase += 0.02 * dt * 60;

        const radius = p.radius + Math.sin(p.phase) * 8;
        const x = cx + Math.cos(p.angle) * radius;
        const y = cy + Math.sin(p.angle * 0.7) * radius * 0.6;

        // Size pulse with audio
        const size = p.size * (1 + micLevel * 0.5);

        // Gradient particle
        const particleGradient = ctx.createRadialGradient(x, y, 0, x, y, size * 2);
        particleGradient.addColorStop(0, `${colors.primary}${Math.round(p.opacity * 255).toString(16).padStart(2, '0')}`);
        particleGradient.addColorStop(1, 'transparent');

        ctx.fillStyle = particleGradient;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();
    }

    // ============================================
    // DEPTH LAYER 3: The Premium Orb (3-ring gradient system)
    // ============================================
    const pulseScale = getOrbPulseScale(voiceState, micLevel, timeRef.current / 1000);
    const baseOrbRadius = Math.max(orbSize / 2, 60);
    const orbRadius = baseOrbRadius * pulseScale;

    // Ring 1: Outer glow ring (largest, most transparent)
    const outerRingRadius = orbRadius * 1.45;
    const outerGradient = ctx.createRadialGradient(cx, cy, outerRingRadius * 0.3, cx, cy, outerRingRadius);
    outerGradient.addColorStop(0, 'transparent');
    outerGradient.addColorStop(0.6, `${colors.glow}08`);
    outerGradient.addColorStop(1, `${colors.primary}15`);
    ctx.fillStyle = outerGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, outerRingRadius, 0, Math.PI * 2);
    ctx.fill();

    // Ring 2: Mid glow ring (core visual identity)
    const midRingRadius = orbRadius * 1.15;
    const midGradient = ctx.createRadialGradient(cx, cy, midRingRadius * 0.4, cx, cy, midRingRadius);
    midGradient.addColorStop(0, `${colors.primary}10`);
    midGradient.addColorStop(0.5, `${colors.primary}25`);
    midGradient.addColorStop(0.8, `${colors.glow}40`);
    midGradient.addColorStop(1, `${colors.primary}60`);
    ctx.fillStyle = midGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, midRingRadius, 0, Math.PI * 2);
    ctx.fill();

    // Ring 3: Inner core ring (sharp, defined)
    const innerRingRadius = orbRadius * 0.85;
    const innerGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, innerRingRadius);
    innerGradient.addColorStop(0, colors.gradient[0]);
    innerGradient.addColorStop(0.5, colors.gradient[1]);
    innerGradient.addColorStop(1, `${colors.primary}DD`);
    ctx.fillStyle = innerGradient;
    ctx.beginPath();
    ctx.arc(cx, cy, innerRingRadius, 0, Math.PI * 2);
    ctx.fill();

    // Core highlight (specular)
    if (voiceState !== 'muted' && voiceState !== 'idle') {
      const highlightRadius = innerRingRadius * 0.4;
      const highlightGradient = ctx.createRadialGradient(
        cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, 0,
        cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, highlightRadius
      );
      highlightGradient.addColorStop(0, 'rgba(255,255,255,0.4)');
      highlightGradient.addColorStop(1, 'transparent');
      ctx.fillStyle = highlightGradient;
      ctx.beginPath();
      ctx.arc(cx - highlightRadius * 0.3, cy - highlightRadius * 0.3, highlightRadius, 0, Math.PI * 2);
      ctx.fill();
    }

    // ============================================
    // DEPTH LAYER 4: Frequency bars (spring-damped, gradient)
    // ============================================
    if (frequencyData && frequencyData.length > 0) {
      const barWidth = (width * 0.85) / BAR_COUNT;
      const barGap = barWidth * 0.15;
      const maxBarHeight = height * 0.28;
      const startX = (width - (BAR_COUNT * barWidth + (BAR_COUNT - 1) * barGap)) / 2;
      const baseY = cy + orbRadius * 1.6;

      ctx.save();

      frequencyData.forEach((value, i) => {
        if (i >= BAR_COUNT) return;

        // Map frequency index to usable range (skip very low/high)
        const freqIndex = Math.floor((i / BAR_COUNT) * (frequencyData.length * 0.75));
        const magnitude = frequencyData[freqIndex] / 255;

        // Spring physics: target height with damping
        const targetHeight = magnitude * maxBarHeight;
        const currentHeight = barHeightsRef.current[i];
        const velocity = (targetHeight - currentHeight) * springStiffness;
        const dampingForce = -velocity * springDamping;
        const acceleration = velocity + dampingForce;

        barHeightsRef.current[i] = currentHeight + acceleration * dt;
        const height = Math.max(2, barHeightsRef.current[i]);
        const x = startX + i * (barWidth + barGap);
        const y = baseY - height;

        // Color gradient based on frequency band (bass=green, mid=amber, treble=red/pink)
        const freqRatio = i / BAR_COUNT;
        let barColor: string;
        let barGlow: string;
        if (freqRatio < 0.33) {
          // Bass - green/cyan
          barColor = tokens.success;
          barGlow = tokens.success;
        } else if (freqRatio < 0.66) {
          // Mid - amber/gold
          barColor = tokens.warning;
          barGlow = tokens.warning;
        } else {
          // Treble - pink/red
          barColor = '#f472b6';
          barGlow = '#f472b6';
        }

        // Bar gradient (bottom to top)
        const barGradient = ctx.createLinearGradient(x, baseY, x, y);
        barGradient.addColorStop(0, `${barColor}DD`);
        barGradient.addColorStop(0.5, barColor);
        barGradient.addColorStop(1, `${barColor}80`);

        ctx.fillStyle = barGradient;
        roundRect(ctx, x, y, barWidth, height, barWidth / 2);
        ctx.fill();

        // Glow on active bars
        if (height > maxBarHeight * 0.3) {
          ctx.shadowColor = barGlow;
          ctx.shadowBlur = 8;
          roundRect(ctx, x, y, barWidth, height, barWidth / 2);
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      });

      ctx.restore();
    }

    // ============================================
    // DEPTH LAYER 5: Waveform with mirror reflection
    // ============================================
    if (timeDomainData && timeDomainData.length > 0) {
      const waveWidth = width * 0.75;
      const waveHeight = 60;
      const waveX = (width - waveWidth) / 2;
      const waveY = cy + orbRadius * 2.2;
      const sampleCount = Math.min(256, timeDomainData.length);

      ctx.save();

      // Main waveform gradient
      const waveGradient = ctx.createLinearGradient(waveX, waveY - waveHeight, waveX, waveY + waveHeight);
      waveGradient.addColorStop(0, `${colors.primary}00`);
      waveGradient.addColorStop(0.3, `${colors.primary}40`);
      waveGradient.addColorStop(0.5, `${colors.primary}FF`);
      waveGradient.addColorStop(0.7, `${colors.primary}40`);
      waveGradient.addColorStop(1, `${colors.primary}00`);

      // Draw upper waveform
      ctx.strokeStyle = waveGradient;
      ctx.lineWidth = 2.5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();

      const stepX = waveWidth / (sampleCount - 1);
      timeDomainData.slice(0, sampleCount).forEach((value, i) => {
        const x = waveX + i * stepX;
        const normalized = (value - 128) / 128;
        const y = waveY + normalized * waveHeight * 0.5;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      // Mirror reflection (faded, inverted)
      const reflectionGradient = ctx.createLinearGradient(waveX, waveY, waveX, waveY + waveHeight);
      reflectionGradient.addColorStop(0, `${colors.primary}30`);
      reflectionGradient.addColorStop(0.5, `${colors.primary}10`);
      reflectionGradient.addColorStop(1, `${colors.primary}00`);

      ctx.strokeStyle = reflectionGradient;
      ctx.lineWidth = 1.5;
      ctx.globalAlpha = 0.4;
      ctx.beginPath();

      timeDomainData.slice(0, sampleCount).forEach((value, i) => {
        const x = waveX + i * stepX;
        const normalized = (value - 128) / 128;
        const y = waveY - normalized * waveHeight * 0.35; // Inverted, smaller
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.restore();
    }

    // ============================================
    // DEPTH LAYER 6: Connection status indicator
    // ============================================
    if (status !== 'disconnected') {
      const dotSize = 10;
      const dotX = width - 32;
      const dotY = 32;

      ctx.save();
      // Pulsing ring
      if (!prefersReduced && (status === 'connecting' || status === 'reconnecting' || status === 'connected')) {
        const pulse = (Math.sin(timeRef.current / 200) + 1) / 2;
        const ringRadius = dotSize + pulse * 8;
        const ringAlpha = (1 - pulse) * 0.5;
        ctx.strokeStyle = `${statusColor}${Math.round(ringAlpha * 255).toString(16).padStart(2, '0')}`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(dotX, dotY, ringRadius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Core dot
      ctx.fillStyle = statusColor;
      ctx.shadowColor = statusColor;
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.arc(dotX, dotY, dotSize / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.restore();
    }

    // ============================================
    // DEPTH LAYER 7: State label (text)
    // ============================================
    const stateLabels: Record<VoiceState, string> = {
      idle: 'Ready',
      listening: 'Listening...',
      speaking: 'Speaking',
      processing: 'Thinking...',
      error: 'Error',
      muted: 'Muted',
    };

    ctx.font = '500 13px ui-sans-serif, system-ui';
    ctx.fillStyle = tokens.textSecondary;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const label = stateLabels[voiceState];
    const labelX = cx;
    const labelY = cy + orbRadius * 2.8;
    ctx.fillText(label, labelX, labelY);

    // Schedule next frame
    if (!prefersReduced) {
      animationRef.current = requestAnimationFrame(render);
    }
  }, [
    voiceState,
    micLevel,
    frequencyData,
    timeDomainData,
    status,
    prefersReduced,
    stateColors,
    getStatusColor,
    getDesignTokens,
    getOrbPulseScale,
    roundRect,
  ]);

  // Start/stop animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Handle resize
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = Math.floor(rect.width * dpr);
        canvas.height = Math.floor(rect.height * dpr);
        canvas.style.width = `${rect.width}px`;
        canvas.style.height = `${rect.height}px`;
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.scale(dpr, dpr);
      }
    };

    resize();
    window.addEventListener('resize', resize);
    animationRef.current = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', resize);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [render, prefersReduced]);

  // Reduced motion: single static frame
  useEffect(() => {
    if (prefersReduced && canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) {
        timeRef.current = performance.now();
        render(timeRef.current);
      }
    }
  }, [prefersReduced, render, voiceState, micLevel, status]);

  return (
    <div className="relative w-full h-full" style={{ minHeight: 320 }}>
      <canvas
        ref={canvasRef}
        className="w-full h-full block"
        aria-hidden="true"
        role="img"
        aria-label={`Voice visualization: ${voiceState}, microphone level ${Math.round(micLevel * 100)}%`}
      />
    </div>
  );
}

interface Particle {
  angle: number;
  radius: number;
  speed: number;
  size: number;
  opacity: number;
  phase: number;
}