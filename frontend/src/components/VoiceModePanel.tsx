import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { X, Mic, MicOff, Settings2 } from 'lucide-react';
import { voiceBridgeService, BridgeStatus, VoiceState as ServiceVoiceState, TranscriptEvent } from '@/services/voiceBridge';

type ComponentVoiceState = 'idle' | 'listening' | 'speaking' | 'processing' | 'error' | 'muted';

const ORB_COLORS: Record<ComponentVoiceState, string> = {
  idle: '#64748b',
  listening: '#3b82f6',
  speaking: '#8b5cf6',
  processing: '#f59e0b',
  error: '#ef4444',
  muted: '#9ca3af',
};

const STATE_LABELS: Record<ComponentVoiceState, string> = {
  idle: 'Idle',
  listening: 'Listening...',
  speaking: 'Speaking...',
  processing: 'Processing...',
  error: 'Error',
  muted: 'Muted',
};

function VoiceOrb({
  size = 120,
  state = 'idle',
  micLevel = 0,
  className = '',
  reducedMotion = false,
}: { size?: number; state?: ComponentVoiceState; micLevel?: number; className?: string; reducedMotion?: boolean }) {
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
      data-testid="voice-orb"
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

const mapServiceStateToComponentState = (serviceState: ServiceVoiceState): ComponentVoiceState => {
  switch (serviceState) {
    case 'idle':
      return 'idle';
    case 'listening':
      return 'listening';
    case 'thinking':
      return 'processing';
    case 'speaking':
      return 'speaking';
    case 'interrupted':
      return 'error';
    default:
      return 'idle';
  }
};

interface VoiceModePanelProps {
  onClose: () => void;
}

const STATE_LABELS_SERVICE: Record<string, string> = {
  idle: 'Voice Ready',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
  interrupted: 'Interrupted',
};

const STATE_COLORS: Record<string, string> = {
  idle: 'text-gray-400',
  listening: 'text-blue-400',
  thinking: 'text-purple-400',
  speaking: 'text-emerald-400',
  interrupted: 'text-amber-400',
};

export function VoiceModePanel({ onClose }: VoiceModePanelProps) {
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [serviceVoiceState, setServiceVoiceState] = useState<ServiceVoiceState>('idle');
  const [transcripts, setTranscripts] = useState<TranscriptEvent[]>([]);
  const [isMuted, setIsMuted] = useState(false);

  const componentVoiceState: ComponentVoiceState = mapServiceStateToComponentState(serviceVoiceState);

  useEffect(() => {
    return voiceBridgeService.onStatusChange(setBridgeStatus);
  }, []);

  useEffect(() => {
    return voiceBridgeService.onStateChange((s) => {
      if (s) setServiceVoiceState(s);
    });
  }, []);

  useEffect(() => {
    return voiceBridgeService.onTranscript((event: TranscriptEvent) => {
      setTranscripts((prev) => [...prev.slice(-49), event]);
    });
  }, []);

  const handleSettings = useCallback(() => {
    window.dispatchEvent(new CustomEvent('open-voice-settings'));
  }, []);

  const handleToggleMute = useCallback(() => {
    setIsMuted((prev) => !prev);
    if (voiceBridgeService.status === 'connected') {
      if (isMuted) {
        voiceBridgeService.connect();
      } else {
        voiceBridgeService.disconnect();
      }
    }
  }, [isMuted]);

  const isActive = bridgeStatus === 'connected';

  return (
    <div className="fixed inset-0 z-50 bg-[#0a0c12] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4">
        <button
          onClick={handleSettings}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <Settings2 className="w-4 h-4" />
          Voice Settings
        </button>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${STATE_COLORS[serviceVoiceState]}`}>
            {STATE_LABELS_SERVICE[serviceVoiceState]}
          </span>
          <span className={`w-2 h-2 rounded-full ${
            bridgeStatus === 'connected' ? 'bg-emerald-500'
            : bridgeStatus === 'connecting' ? 'bg-amber-400'
            : 'bg-gray-500'
          }`} />
        </div>

        <button
          onClick={onClose}
          className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          aria-label="Close voice mode"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Center: Orb */}
      <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6">
        <div className="relative">
           <VoiceOrb size={240} state={isActive ? componentVoiceState : 'idle'} micLevel={0} />

          {/* Connecting overlay */}
          {bridgeStatus === 'connecting' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-16 h-16 rounded-full border-4 border-blue-500/30 border-t-blue-500 animate-spin" />
            </div>
          )}

          {/* Offline overlay */}
          {bridgeStatus === 'offline' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="bg-[#0a0c12]/80 rounded-full p-6">
                <MicOff className="w-12 h-12 text-gray-600" />
              </div>
            </div>
          )}
        </div>

        {/* State label */}
        <div className="text-center">
          <p className={`text-lg font-semibold ${STATE_COLORS[serviceVoiceState]} transition-colors duration-500`}>
            {isActive ? STATE_LABELS_SERVICE[serviceVoiceState] : 'Voice Bridge Offline'}
          </p>
          <p className="text-sm text-gray-500 mt-1">
            {!isActive ? 'Run the voice bridge to start speaking'
            : serviceVoiceState === 'idle' ? 'Say "Hey Agentium" or tap the mic'
            : ''}
          </p>
        </div>

        {/* Big mic button */}
        <button
          onClick={handleToggleMute}
          className={`w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300 ${
            isMuted || !isActive
              ? 'bg-gray-800 text-gray-500 hover:bg-gray-700'
              : serviceVoiceState === 'listening'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/40 scale-110'
                : 'bg-gray-800 text-white hover:bg-gray-700'
          }`}
          aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
        >
          {isMuted || !isActive ? (
            <MicOff className="w-8 h-8" />
          ) : (
            <Mic className="w-8 h-8" />
          )}
        </button>

        {/* Transcripts */}
          {transcripts.length > 0 && (
            <div className="w-full max-w-lg max-h-40 overflow-y-auto space-y-2 px-4">
              {transcripts.slice(-5).map((t, i) => (
                <div
                  key={`${t.ts}-${i}`}
                  className={`px-4 py-2 rounded-xl text-sm ${
                    t.role === 'user'
                      ? 'bg-blue-500/10 text-blue-300 ml-12'
                      : 'bg-gray-800/50 text-gray-300 mr-12'
                  }`}
                >
                  <span className="text-xs font-medium opacity-60 mr-2">
                    {t.role === 'user' ? 'You' : 'Agentium'}
                  </span>
                  {t.text}
                </div>
              ))}
            </div>
          )}
      </div>

      {/* Bottom bar */}
      <div className="flex items-center justify-center gap-4 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className={`w-1.5 h-1.5 rounded-full ${
            isActive ? 'bg-emerald-500' : 'bg-gray-600'
          }`} />
          {bridgeStatus === 'connected' ? 'Bridge connected'
          : bridgeStatus === 'connecting' ? 'Connecting…'
          : 'Bridge offline'}
        </div>
        <span className="text-gray-700">·</span>
         <span className="text-xs text-gray-500">
           {isActive
             ? serviceVoiceState === 'idle' ? 'Tap mic to speak'
               : serviceVoiceState === 'listening' ? 'Speak now'
               : serviceVoiceState === 'thinking' ? 'Processing…'
               : serviceVoiceState === 'speaking' ? 'Agentium is speaking'
               : ''
             : 'Connect the voice bridge'}
         </span>
      </div>
    </div>
  );
}