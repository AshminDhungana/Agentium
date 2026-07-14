import React, { useState } from 'react';
import {
  Monitor,
  ChevronDown,
  ChevronRight,
  Cpu,
  GitBranch,
  Network,
  Clock,
  UserCheck,
  type LucideIcon,
} from 'lucide-react';

// ── Types ───────────────────────────────────────────────────────────────────

interface StepData {
  step_index: number;
  type: string;
  config: Record<string, unknown>;
  on_success_step?: number;
  on_failure_step?: number;
}

/**
 * @description Mobile-optimized read-only viewer for workflow steps.
 * Renders a collapsible list of steps with type icons and config summary.
 * @example
 * ```tsx
 * import { MobileWorkflowViewer } from '@/components/workflows/MobileWorkflowViewer';
 *
 * <MobileWorkflowViewer workflowName="Data Pipeline" version={2} steps={steps} />
 * ```
 * @param {string} props.workflowName - Display name of the workflow.
 * @param {number} props.version - Workflow version number.
 * @param {StepData[]} props.steps - Array of step definitions to display.
 */
interface MobileWorkflowViewerProps {
  workflowName: string;
  version: number;
  steps: StepData[];
}

// ── Step type config ────────────────────────────────────────────────────────

const MOBILE_STEP_CONFIG: Record<string, {
  label: string;
  icon: LucideIcon;
  accent: string;
  bg: string;
  border: string;
  dot: string;
}> = {
  TASK: {
    label: 'AI Task',
    icon: Cpu,
    accent: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-500/10',
    border: 'border-blue-200 dark:border-blue-500/25',
    dot: 'bg-blue-500',
  },
  CONDITION: {
    label: 'Condition',
    icon: GitBranch,
    accent: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-500/10',
    border: 'border-purple-200 dark:border-purple-500/25',
    dot: 'bg-purple-500',
  },
  PARALLEL: {
    label: 'Parallel',
    icon: Network,
    accent: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-500/10',
    border: 'border-amber-200 dark:border-amber-500/25',
    dot: 'bg-amber-500',
  },
  DELAY: {
    label: 'Delay',
    icon: Clock,
    accent: 'text-gray-600 dark:text-gray-400',
    bg: 'bg-gray-50 dark:bg-gray-500/10',
    border: 'border-gray-200 dark:border-gray-500/25',
    dot: 'bg-gray-500',
  },
  HUMAN_APPROVAL: {
    label: 'Approval',
    icon: UserCheck,
    accent: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-500/10',
    border: 'border-emerald-200 dark:border-emerald-500/25',
    dot: 'bg-emerald-500',
  },
};

const DEFAULT_CFG = MOBILE_STEP_CONFIG.TASK;

// ── Helpers ─────────────────────────────────────────────────────────────────

function getConfigSummary(type: string, config: Record<string, unknown>): string {
  switch (type) {
    case 'TASK':
      return (config.task_title as string) || (config.prompt as string) || 'Unconfigured task';
    case 'CONDITION':
      return config.field
        ? `If ${config.field} ${config.operator ?? '=='} ${config.value ?? '?'}`
        : 'Unconfigured condition';
    case 'DELAY':
      return `Wait ${config.delay_seconds ?? 60} seconds`;
    case 'HUMAN_APPROVAL':
      return (config.approval_message as string) || 'Requires human approval';
    case 'PARALLEL':
      return 'Execute branches in parallel';
    default:
      return 'Unknown step';
  }
}

// ── Component ───────────────────────────────────────────────────────────────

export const MobileWorkflowViewer: React.FC<MobileWorkflowViewerProps> = ({
  workflowName,
  version,
  steps,
}) => {
  const [expandedStep, setExpandedStep] = useState<number | null>(null);

  const toggleStep = (idx: number) => {
    setExpandedStep(prev => (prev === idx ? null : idx));
  };

  return (
    <div className="min-h-screen bg-white dark:bg-[#0f1117]">
      {/* Desktop edit banner */}
      <div className="
        flex items-center gap-2.5 px-4 py-3
        bg-indigo-50 dark:bg-indigo-500/10
        border-b border-indigo-200 dark:border-indigo-500/20
      ">
        <Monitor className="w-4 h-4 text-indigo-600 flex-shrink-0" />
        <p className="text-xs text-indigo-700 dark:text-indigo-300 font-medium">
          Open on a larger screen to edit this workflow
        </p>
      </div>

      {/* Header */}
      <div className="px-4 py-5 border-b border-gray-100 dark:border-[#1e2535]">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white truncate">
          {workflowName}
        </h1>
        <div className="flex items-center gap-3 mt-1.5">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-gray-100 text-gray-600 dark:bg-[#1e2535] dark:text-gray-400">
            v{version}
          </span>
          <span className="text-xs text-gray-600 dark:text-gray-500">
            {steps.length} step{steps.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Step list */}
      <div className="px-4 py-4">
        <div className="relative">
          {/* Connector line */}
          <div className="absolute left-[19px] top-6 bottom-6 w-0.5 bg-gray-200 dark:bg-[#1e2535]" />

          <div className="space-y-0">
            {steps.map((step, i) => {
              const cfg = MOBILE_STEP_CONFIG[step.type] ?? DEFAULT_CFG;
              const Icon = cfg.icon;
              const isOpen = expandedStep === step.step_index;
              const isLast = i === steps.length - 1;
              const hasFailureBranch = step.on_failure_step !== undefined;

              return (
                <div key={step.step_index} className="relative">
                  {/* Step card */}
                  <button
                    onClick={() => toggleStep(step.step_index)}
                    className="
                      w-full flex items-start gap-3 py-3 text-left
                      transition-colors active:bg-gray-50 dark:active:bg-[#161b27]
                    "
                  >
                    {/* Timeline dot */}
                    <div className={`
                      relative z-10 w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0
                      ${cfg.bg} border ${cfg.border}
                    `}>
                      <Icon className={`w-4.5 h-4.5 ${cfg.accent}`} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0 pt-0.5">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-gray-600 dark:text-gray-500">
                          #{step.step_index}
                        </span>
                        <span className={`text-xs font-bold uppercase tracking-wider ${cfg.accent}`}>
                          {cfg.label}
                        </span>
                        {isOpen
                          ? <ChevronDown className="w-3 h-3 text-gray-600 dark:text-gray-400 ml-auto" />
                          : <ChevronRight className="w-3 h-3 text-gray-600 dark:text-gray-400 ml-auto" />
                        }
                      </div>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5 line-clamp-1">
                        {getConfigSummary(step.type, step.config)}
                      </p>
                    </div>
                  </button>

                  {/* Expanded config */}
                  {isOpen && (
                    <div className="ml-[52px] mb-3 p-3 rounded-xl bg-gray-50 dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535]">
                      <pre className="
                        text-[11px] font-mono text-gray-600 dark:text-gray-400
                        whitespace-pre-wrap break-words
                      ">
                        {JSON.stringify(step.config, null, 2)}
                      </pre>

                      {/* Routing info */}
                      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-[#1e2535] space-y-1">
                        {step.on_success_step !== undefined && (
                          <div className="flex items-center gap-1.5 text-xs">
                            <span className="w-2 h-2 rounded-full bg-green-400 flex-shrink-0" />
                            <span className="text-gray-600 dark:text-gray-400">
                              On success → Step #{step.on_success_step}
                            </span>
                          </div>
                        )}
                        {step.on_failure_step !== undefined && (
                          <div className="flex items-center gap-1.5 text-xs">
                            <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" />
                            <span className="text-gray-600 dark:text-gray-400">
                              On failure → Step #{step.on_failure_step}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Conditional fork indicator */}
                  {hasFailureBranch && !isLast && (
                    <div className="ml-[52px] mb-2 flex items-center gap-2 text-[10px]">
                      <span className="px-1.5 py-0.5 rounded bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400 font-bold">
                        ✓ True
                      </span>
                      <span className="text-gray-300 dark:text-gray-600">/</span>
                      <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400 font-bold">
                        ✗ False → #{step.on_failure_step}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
