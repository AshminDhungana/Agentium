import React from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react';

/**
 * Custom edge for the workflow designer.
 *
 * - `sourceHandle === 'success'` → solid green edge labeled "✓ True"
 * - `sourceHandle === 'failure'` → dashed red edge labeled "✗ False"
 * - default                      → solid gray edge, no label
 *
 * The `data.animated` flag adds a moving dash animation for live execution.
 */
export function ConditionalEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  sourceHandleId,
  style = {},
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const isSuccess = sourceHandleId === 'success';
  const isFailure = sourceHandleId === 'failure';
  const isAnimated = !!(data as Record<string, unknown>)?.animated;

  // Determine visual style
  let stroke = '#9ca3af'; // gray-400
  let strokeDasharray: string | undefined;
  let label: string | null = null;
  let labelBg = '';
  let labelText = '';

  if (isSuccess) {
    stroke = '#22c55e'; // green-500
    label = '✓ True';
    labelBg = 'bg-green-100 dark:bg-green-500/20';
    labelText = 'text-green-700 dark:text-green-400';
  } else if (isFailure) {
    stroke = '#ef4444'; // red-500
    strokeDasharray = '6 4';
    label = '✗ False';
    labelBg = 'bg-red-100 dark:bg-red-500/20';
    labelText = 'text-red-700 dark:text-red-400';
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          stroke,
          strokeWidth: 2,
          strokeDasharray,
          animation: isAnimated ? 'flowEdge 1s linear infinite' : undefined,
        }}
      />

      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <span
              className={`
                inline-flex items-center px-2 py-0.5 rounded-full
                text-[10px] font-bold tracking-wide
                shadow-sm border border-gray-200 dark:border-[#1e2535]
                ${labelBg} ${labelText}
              `}
            >
              {label}
            </span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
