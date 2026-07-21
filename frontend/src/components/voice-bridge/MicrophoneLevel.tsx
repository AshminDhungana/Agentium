import { motion } from 'framer-motion';
import type { MicrophoneLevelProps, MicrophoneLevelRingProps } from './types';

const SEGMENT_COUNT = 12;

export function MicrophoneLevel({
  level = 0,
  maxLevel = 1,
  segments = SEGMENT_COUNT,
  className = '',
  reducedMotion = false,
}: MicrophoneLevelProps) {
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const activeSegments = Math.ceil((level / maxLevel) * segments);

  const getSegmentColor = (index: number): string => {
    const ratio = index / segments;
    if (ratio < 0.5) return '#22c55e';
    if (ratio < 0.75) return '#f59e0b';
    return '#ef4444';
  };

  const segmentVariants = {
    inactive: {
      scaleY: 0.1,
      backgroundColor: 'rgba(148, 163, 184, 0.15)',
      transition: { duration: prefersReduced ? 0 : 0.15, ease: 'easeOut' as const },
    },
    active: (index: number) => ({
      scaleY: 1,
      backgroundColor: getSegmentColor(index),
      boxShadow: `0 0 8px ${getSegmentColor(index)}`,
      transition: {
        duration: prefersReduced ? 0 : 0.1,
        ease: 'easeOut' as const,
        delay: index * 0.01,
      },
    }),
    peak: (index: number) => ({
      scaleY: 1.2,
      backgroundColor: getSegmentColor(index),
      boxShadow: `0 0 16px ${getSegmentColor(index)}`,
      transition: { duration: 0.05, ease: 'easeOut' as const },
    }),
  };

  return (
    <div
      className={`flex items-end gap-1 ${className}`}
      role="img"
      aria-label={`Microphone input level: ${Math.round((level / maxLevel) * 100)}%`}
      aria-live="polite"
    >
      {Array.from({ length: segments }, (_, i) => {
        const isActive = i < activeSegments;
        const isPeak = isActive && i === activeSegments - 1 && level > 0.8;

        return (
          <motion.div
            key={i}
            className="w-1.5 h-16 rounded-full"
            initial="inactive"
            animate={isActive ? (isPeak ? 'peak' : 'active') : 'inactive'}
            variants={segmentVariants}
            custom={i}
            style={{
              transformOrigin: 'bottom center',
            }}
            aria-hidden="true"
          />
        );
      })}
    </div>
  );
}

export function MicrophoneLevelRing({
  level = 0,
  maxLevel = 1,
  size = 160,
  strokeWidth = 4,
  className = '',
  reducedMotion = false,
}: MicrophoneLevelRingProps) {
  const prefersReduced = reducedMotion || (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - level / maxLevel);

  const getColor = (level: number): string => {
    if (level < 0.5) return '#22c55e';
    if (level < 0.75) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div
      className={`relative flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Microphone input level: ${Math.round((level / maxLevel) * 100)}%`}
      aria-live="polite"
    >
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(148, 163, 184, 0.15)"
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={getColor(level / maxLevel)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={prefersReduced ? offset : undefined}
          strokeLinecap="round"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{
            duration: prefersReduced ? 0 : 0.15,
            ease: 'easeOut',
          }}
          style={{
            filter: `drop-shadow(0 0 4px ${getColor(level / maxLevel)})`,
          }}
        />
      </svg>
      <span className="absolute text-xs font-mono text-white/70" aria-hidden="true">
        {Math.round((level / maxLevel) * 100)}%
      </span>
    </div>
  );
}