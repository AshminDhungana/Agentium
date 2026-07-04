import React from 'react';

/**
 * @description SVG-based circular progress indicator used to visualize
 * an agent's health score (0–100) as a partially-filled ring.
 * @example
 * ```tsx
 * import { HealthRing } from '@/components/ui/HealthRing';
 *
 * <HealthRing score={85} size={36} />
 * ```
 * @param {number} props.score - Health value (0–100).
 * @param {number} [props.size] - Diameter in pixels (default: 36).
 */
interface HealthRingProps {
  score: number;
  size?: number;
}

export const HealthRing: React.FC<HealthRingProps> = ({ score, size = 36 }) => {
  const radius = (size / 2) - 4;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.max(0, Math.min(100, score)) / 100) * circumference;
  const color = score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444';

  const center = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-label={`Health: ${score}%`}>
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        strokeWidth="3"
        className="stroke-slate-200 dark:stroke-slate-700"
      />
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        strokeWidth="3"
        stroke={color}
        strokeDasharray={`${filled} ${circumference}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${center} ${center})`}
        style={{ transition: 'stroke-dasharray 0.5s ease' }}
      />
      <text
        x={center}
        y={center + 4}
        textAnchor="middle"
        fontSize="8"
        fontWeight="700"
        fill={color}
      >
        {score}
      </text>
    </svg>
  );
};
