/**
 * @description Palette of draggable step types for the workflow designer canvas.
 * Provides tiles for TASK, CONDITION, PARALLEL, HUMAN_APPROVAL, and DELAY steps.
 * @example
 * ```tsx
 * import { StepPalette } from '@/components/workflows/StepPalette';
 *
 * <StepPalette onStepAdd={addStep} />
 * ```
 * @param {(type: string, defaultConfig: Record<string, unknown>) => void} props.onStepAdd - Callback when a step type is selected.
 */
import React, { useRef, useCallback } from 'react';
import { useReactFlow } from '@xyflow/react';
import {
  Cpu,
  GitBranch,
  Network,
  Clock,
  UserCheck,
  GripVertical,
  type LucideIcon,
} from 'lucide-react';

// ── Step definitions ────────────────────────────────────────────────────────

interface StepDef {
  type: string;
  label: string;
  icon: LucideIcon;
  colorCls: string;
  iconCls: string;
  defaultConfig: Record<string, unknown>;
}

const STEP_DEFS: StepDef[] = [
  {
    type: 'TASK',
    label: 'AI Task',
    icon: Cpu,
    colorCls: 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/25 hover:border-blue-400 dark:hover:border-blue-500/50',
    iconCls: 'text-blue-600 dark:text-blue-400',
    defaultConfig: { task_title: '', prompt: '' },
  },
  {
    type: 'CONDITION',
    label: 'Condition',
    icon: GitBranch,
    colorCls: 'bg-purple-50 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/25 hover:border-purple-400 dark:hover:border-purple-500/50',
    iconCls: 'text-purple-600 dark:text-purple-400',
    defaultConfig: { field: '', operator: 'eq', value: '' },
  },
  {
    type: 'PARALLEL',
    label: 'Parallel',
    icon: Network,
    colorCls: 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/25 hover:border-amber-400 dark:hover:border-amber-500/50',
    iconCls: 'text-amber-600 dark:text-amber-400',
    defaultConfig: { sub_steps: [] },
  },
  {
    type: 'DELAY',
    label: 'Delay',
    icon: Clock,
    colorCls: 'bg-gray-50 dark:bg-gray-500/10 border-gray-200 dark:border-gray-500/25 hover:border-gray-400 dark:hover:border-gray-500/50',
    iconCls: 'text-gray-600 dark:text-gray-400',
    defaultConfig: { delay_seconds: 60 },
  },
  {
    type: 'HUMAN_APPROVAL',
    label: 'Approval',
    icon: UserCheck,
    colorCls: 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/25 hover:border-emerald-400 dark:hover:border-emerald-500/50',
    iconCls: 'text-emerald-600 dark:text-emerald-400',
    defaultConfig: { approval_message: '', timeout_seconds: 3600 },
  },
];

// ── Props ───────────────────────────────────────────────────────────────────

interface StepPaletteProps {
  /** Callback to add a new node at a canvas position */
  onAddNode: (type: string, config: Record<string, unknown>, position: { x: number; y: number }) => void;
  /** Layout mode */
  variant: 'sidebar' | 'bottom-sheet';
}

// ── Ghost element utils ─────────────────────────────────────────────────────

function createGhostElement(def: StepDef): HTMLDivElement {
  const ghost = document.createElement('div');
  ghost.className = `
    fixed z-[9999] pointer-events-none
    flex items-center gap-2 px-3 py-2 rounded-xl
    bg-white dark:bg-[#161b27] border-2 border-indigo-400
    shadow-2xl shadow-indigo-500/30
    opacity-90 transition-none
  `;
  ghost.style.width = '140px';
  ghost.innerHTML = `
    <span class="text-sm font-semibold text-gray-900 dark:text-white">${def.label}</span>
  `;
  return ghost;
}

// ── Component ───────────────────────────────────────────────────────────────

export const StepPalette: React.FC<StepPaletteProps> = ({ onAddNode, variant }) => {
  const reactFlowInstance = useReactFlow();
  const ghostRef = useRef<{ element: HTMLDivElement; def: StepDef } | null>(null);

  // ── HTML5 drag (desktop) ──────────────────────────────────────────────────

  const handleDragStart = useCallback(
    (e: React.DragEvent, def: StepDef) => {
      e.dataTransfer.setData('application/agentium-step', JSON.stringify({
        type: def.type,
        config: def.defaultConfig,
      }));
      e.dataTransfer.effectAllowed = 'move';
    },
    [],
  );

  // ── Touch drag (tablet) ───────────────────────────────────────────────────

  const handleTouchStart = useCallback(
    (e: React.TouchEvent, def: StepDef) => {
      const touch = e.touches[0];
      const ghost = createGhostElement(def);
      ghost.style.left = `${touch.clientX - 70}px`;
      ghost.style.top = `${touch.clientY - 20}px`;
      document.body.appendChild(ghost);
      ghostRef.current = { element: ghost, def };
    },
    [],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      // Prevent page scroll while dragging a tile
      e.preventDefault();
      const touch = e.touches[0];
      if (ghostRef.current) {
        ghostRef.current.element.style.left = `${touch.clientX - 70}px`;
        ghostRef.current.element.style.top = `${touch.clientY - 20}px`;
      }
    },
    [],
  );

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!ghostRef.current) return;

      const touch = e.changedTouches[0];
      const dropPosition = reactFlowInstance.screenToFlowPosition({
        x: touch.clientX,
        y: touch.clientY,
      });

      onAddNode(ghostRef.current.def.type, ghostRef.current.def.defaultConfig, dropPosition);

      // Clean up ghost
      ghostRef.current.element.remove();
      ghostRef.current = null;
    },
    [reactFlowInstance, onAddNode],
  );

  // ── Render ────────────────────────────────────────────────────────────────

  const isSidebar = variant === 'sidebar';

  return (
    <div
      className={`
        ${isSidebar
          ? 'w-56 flex-shrink-0 border-r border-gray-200 dark:border-[#1e2535] bg-gray-50/50 dark:bg-[#0f1117]/50 p-4 overflow-y-auto'
          : 'flex gap-2 p-3 overflow-x-auto bg-gray-50/80 dark:bg-[#0f1117]/80 backdrop-blur-sm border-t border-gray-200 dark:border-[#1e2535]'
        }
      `}
    >
      {isSidebar && (
        <h3 className="text-xs font-bold text-gray-600 dark:text-gray-500 uppercase tracking-widest mb-3 px-1">
          Step Types
        </h3>
      )}

      <div className={isSidebar ? 'space-y-2' : 'flex gap-2'}>
        {STEP_DEFS.map((def) => {
          const Icon = def.icon;
          return (
            <div
              key={def.type}
              draggable
              onDragStart={(e) => handleDragStart(e, def)}
              onTouchStart={(e) => handleTouchStart(e, def)}
              onTouchMove={(e) => handleTouchMove(e)}
              onTouchEnd={(e) => handleTouchEnd(e)}
              className={`
                flex items-center gap-2.5 px-3 py-2.5
                rounded-xl border cursor-grab active:cursor-grabbing
                transition-all duration-200
                select-none touch-none
                ${def.colorCls}
                ${isSidebar ? '' : 'min-w-[120px] flex-shrink-0'}
              `}
            >
              <GripVertical className="w-3.5 h-3.5 text-gray-300 dark:text-gray-600 flex-shrink-0" />
              <Icon className={`w-4 h-4 flex-shrink-0 ${def.iconCls}`} />
              <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap">
                {def.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
