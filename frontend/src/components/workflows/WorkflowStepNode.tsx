import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import {
  Cpu,
  GitBranch,
  Network,
  Clock,
  UserCheck,
  type LucideIcon,
} from 'lucide-react';

// ── Step type visual config ─────────────────────────────────────────────────

export interface StepTypeConfig {
  label: string;
  icon: LucideIcon;
  accent: string;
  accentDark: string;
  bg: string;
  bgDark: string;
  border: string;
  borderDark: string;
  ring: string;
}

export const STEP_TYPE_CONFIG: Record<string, StepTypeConfig> = {
  TASK: {
    label: 'AI Task',
    icon: Cpu,
    accent: 'text-blue-600',
    accentDark: 'dark:text-blue-400',
    bg: 'bg-blue-50',
    bgDark: 'dark:bg-blue-500/10',
    border: 'border-blue-200',
    borderDark: 'dark:border-blue-500/30',
    ring: 'ring-blue-400/40',
  },
  CONDITION: {
    label: 'Condition',
    icon: GitBranch,
    accent: 'text-purple-600',
    accentDark: 'dark:text-purple-400',
    bg: 'bg-purple-50',
    bgDark: 'dark:bg-purple-500/10',
    border: 'border-purple-200',
    borderDark: 'dark:border-purple-500/30',
    ring: 'ring-purple-400/40',
  },
  PARALLEL: {
    label: 'Parallel',
    icon: Network,
    accent: 'text-amber-600',
    accentDark: 'dark:text-amber-400',
    bg: 'bg-amber-50',
    bgDark: 'dark:bg-amber-500/10',
    border: 'border-amber-200',
    borderDark: 'dark:border-amber-500/30',
    ring: 'ring-amber-400/40',
  },
  DELAY: {
    label: 'Delay',
    icon: Clock,
    accent: 'text-gray-600',
    accentDark: 'dark:text-gray-400',
    bg: 'bg-gray-50',
    bgDark: 'dark:bg-gray-500/10',
    border: 'border-gray-200',
    borderDark: 'dark:border-gray-500/30',
    ring: 'ring-gray-400/40',
  },
  HUMAN_APPROVAL: {
    label: 'Approval',
    icon: UserCheck,
    accent: 'text-emerald-600',
    accentDark: 'dark:text-emerald-400',
    bg: 'bg-emerald-50',
    bgDark: 'dark:bg-emerald-500/10',
    border: 'border-emerald-200',
    borderDark: 'dark:border-emerald-500/30',
    ring: 'ring-emerald-400/40',
  },
};

const DEFAULT_CONFIG = STEP_TYPE_CONFIG.TASK;

// ── Node data shape ─────────────────────────────────────────────────────────

export interface WorkflowNodeData {
  step_index: number;
  type: string;
  config: Record<string, unknown>;
  on_success_step?: number;
  on_failure_step?: number;
  /** True when this node is selected for editing */
  isSelected?: boolean;
  /** Execution status for live monitoring */
  executionStatus?: 'pending' | 'running' | 'completed' | 'failed';
  [key: string]: unknown;
}

// ── Component ───────────────────────────────────────────────────────────────

function WorkflowStepNodeInner({ data, selected }: NodeProps) {
  const nodeData = data as unknown as WorkflowNodeData;
  const cfg = STEP_TYPE_CONFIG[nodeData.type] ?? DEFAULT_CONFIG;
  const Icon = cfg.icon;

  // Build a short config preview
  const preview = getConfigPreview(nodeData.type, nodeData.config);

  // Execution status dot
  const statusDot = nodeData.executionStatus
    ? EXECUTION_DOT[nodeData.executionStatus] ?? ''
    : null;

  return (
    <>
      {/* Target handle (top) */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-gray-300 dark:!bg-gray-600 !border-2 !border-white dark:!border-[#161b27] !-top-1.5"
      />

      <div
        className={`
          group relative min-w-[180px] max-w-[240px]
          rounded-xl border-2 transition-all duration-200
          bg-white ${cfg.bgDark}
          ${cfg.border} ${cfg.borderDark}
          ${selected ? `ring-2 ${cfg.ring} shadow-lg` : 'shadow-sm hover:shadow-md'}
          cursor-pointer
        `}
      >
        {/* Header */}
        <div className={`flex items-center gap-2.5 px-3 py-2.5 rounded-t-[10px] ${cfg.bg} ${cfg.bgDark}`}>
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center bg-white/70 dark:bg-black/20`}>
            <Icon className={`w-4 h-4 ${cfg.accent} ${cfg.accentDark}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono text-gray-400 dark:text-gray-500">
                #{nodeData.step_index}
              </span>
              <span className={`text-xs font-bold uppercase tracking-wider ${cfg.accent} ${cfg.accentDark}`}>
                {cfg.label}
              </span>
            </div>
          </div>
          {statusDot && (
            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusDot}`} />
          )}
        </div>

        {/* Body */}
        <div className="px-3 py-2 border-t border-gray-100 dark:border-[#1e2535]">
          <p className="text-xs text-gray-700 dark:text-gray-300 line-clamp-2 leading-relaxed">
            {preview || 'Click to configure…'}
          </p>
        </div>
      </div>

      {/* Source handle (bottom) — default / success */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="success"
        className="!w-3 !h-3 !bg-green-400 dark:!bg-green-500 !border-2 !border-white dark:!border-[#161b27] !-bottom-1.5"
      />

      {/* Failure handle (right) — only for TASK and CONDITION */}
      {(nodeData.type === 'TASK' || nodeData.type === 'CONDITION') && (
        <Handle
          type="source"
          position={Position.Right}
          id="failure"
          className="!w-3 !h-3 !bg-red-400 dark:!bg-red-500 !border-2 !border-white dark:!border-[#161b27] !-right-1.5"
        />
      )}
    </>
  );
}

export const WorkflowStepNode = memo(WorkflowStepNodeInner);

// ── Helpers ─────────────────────────────────────────────────────────────────

const EXECUTION_DOT: Record<string, string> = {
  pending: 'bg-gray-400',
  running: 'bg-blue-400 animate-pulse',
  completed: 'bg-green-400',
  failed: 'bg-red-400',
};

function getConfigPreview(type: string, config: Record<string, unknown>): string {
  switch (type) {
    case 'TASK':
      return (config.task_title as string) || (config.prompt as string) || '';
    case 'CONDITION':
      return config.field
        ? `${config.field} ${config.operator ?? '=='} ${config.value ?? '?'}`
        : '';
    case 'DELAY':
      return config.delay_seconds ? `Wait ${config.delay_seconds}s` : '';
    case 'HUMAN_APPROVAL':
      return (config.approval_message as string) || 'Requires human approval';
    case 'PARALLEL':
      return 'Parallel execution';
    default:
      return '';
  }
}
