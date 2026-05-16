import React, { useState, useEffect } from 'react';
import { SlideOver } from '@/components/ui/SlideOver';
import { Button } from '@/components/ui/button';
import { Settings, Trash2, Save } from 'lucide-react';
import type { WorkflowNodeData } from './WorkflowStepNode';
import { STEP_TYPE_CONFIG } from './WorkflowStepNode';

// ── Props ───────────────────────────────────────────────────────────────────

interface NodeConfigDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  nodeData: WorkflowNodeData | null;
  onSave: (stepIndex: number, changes: Partial<WorkflowNodeData>) => void;
  onDelete: (stepIndex: number) => void;
  /** All step indexes for routing dropdowns */
  allStepIndexes: number[];
}

// ── Shared input classes ────────────────────────────────────────────────────

const inputCls = `
  w-full bg-gray-50 dark:bg-[#0f1117]
  border border-gray-200 dark:border-[#1e2535]
  rounded-lg px-3 py-2
  text-gray-900 dark:text-white
  placeholder-gray-400 dark:placeholder-gray-500
  text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/40
  transition-colors
`;

const selectCls = `
  w-full bg-gray-50 dark:bg-[#0f1117]
  border border-gray-200 dark:border-[#1e2535]
  rounded-lg px-3 py-2
  text-gray-900 dark:text-white text-sm
  focus:outline-none focus:ring-2 focus:ring-indigo-500/40
  transition-colors
`;

const labelCls = 'text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 block';

// ── Component ───────────────────────────────────────────────────────────────

export const NodeConfigDrawer: React.FC<NodeConfigDrawerProps> = ({
  isOpen,
  onClose,
  nodeData,
  onSave,
  onDelete,
  allStepIndexes,
}) => {
  const [type, setType] = useState('TASK');
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [onSuccessStep, setOnSuccessStep] = useState<number | undefined>();
  const [onFailureStep, setOnFailureStep] = useState<number | undefined>();

  // Sync local state when nodeData changes
  useEffect(() => {
    if (nodeData) {
      setType(nodeData.type);
      setConfig({ ...nodeData.config });
      setOnSuccessStep(nodeData.on_success_step);
      setOnFailureStep(nodeData.on_failure_step);
    }
  }, [nodeData]);

  if (!nodeData) return null;

  const cfg = STEP_TYPE_CONFIG[type] ?? STEP_TYPE_CONFIG.TASK;
  const Icon = cfg.icon;

  const updateConfig = (key: string, value: unknown) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    onSave(nodeData.step_index, {
      type,
      config,
      on_success_step: onSuccessStep,
      on_failure_step: onFailureStep,
    });
    onClose();
  };

  const handleDelete = () => {
    if (window.confirm(`Delete step #${nodeData.step_index}?`)) {
      onDelete(nodeData.step_index);
      onClose();
    }
  };

  return (
    <SlideOver
      isOpen={isOpen}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <Icon className={`w-5 h-5 ${cfg.accent} ${cfg.accentDark}`} />
          Step #{nodeData.step_index} — {cfg.label}
        </span>
      }
      icon={Settings}
      subtitle="Configure step behavior and routing"
    >
      <div className="p-6 space-y-6">
        {/* Step Type */}
        <div>
          <label className={labelCls}>Step Type</label>
          <select className={selectCls} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="TASK">AI Task</option>
            <option value="CONDITION">Condition</option>
            <option value="PARALLEL">Parallel</option>
            <option value="DELAY">Delay</option>
            <option value="HUMAN_APPROVAL">Human Approval</option>
          </select>
        </div>

        {/* Divider */}
        <div className="border-t border-gray-100 dark:border-[#1e2535]" />

        {/* Type-specific config */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
            Configuration
          </h4>

          {type === 'TASK' && (
            <>
              <div>
                <label className={labelCls}>Task Title</label>
                <input
                  type="text"
                  className={inputCls}
                  placeholder="e.g. Analyze customer data"
                  value={(config.task_title as string) ?? ''}
                  onChange={(e) => updateConfig('task_title', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Prompt</label>
                <textarea
                  rows={4}
                  className={inputCls}
                  placeholder="Instructions for the agent…"
                  value={(config.prompt as string) ?? ''}
                  onChange={(e) => updateConfig('prompt', e.target.value)}
                />
              </div>
            </>
          )}

          {type === 'CONDITION' && (
            <>
              <div>
                <label className={labelCls}>Field Path</label>
                <input
                  type="text"
                  className={inputCls}
                  placeholder="e.g. last_task_output.status"
                  value={(config.field as string) ?? ''}
                  onChange={(e) => updateConfig('field', e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Operator</label>
                  <select
                    className={selectCls}
                    value={(config.operator as string) ?? 'eq'}
                    onChange={(e) => updateConfig('operator', e.target.value)}
                  >
                    <option value="eq">Equals</option>
                    <option value="neq">Not Equals</option>
                    <option value="gt">Greater Than</option>
                    <option value="lt">Less Than</option>
                    <option value="contains">Contains</option>
                  </select>
                </div>
                <div>
                  <label className={labelCls}>Value</label>
                  <input
                    type="text"
                    className={inputCls}
                    placeholder="e.g. success"
                    value={(config.value as string) ?? ''}
                    onChange={(e) => updateConfig('value', e.target.value)}
                  />
                </div>
              </div>
            </>
          )}

          {type === 'DELAY' && (
            <div>
              <label className={labelCls}>Delay (seconds)</label>
              <input
                type="number"
                className={inputCls}
                min={1}
                value={(config.delay_seconds as number) ?? 60}
                onChange={(e) => updateConfig('delay_seconds', parseInt(e.target.value) || 60)}
              />
            </div>
          )}

          {type === 'HUMAN_APPROVAL' && (
            <>
              <div>
                <label className={labelCls}>Approval Message</label>
                <textarea
                  rows={3}
                  className={inputCls}
                  placeholder="Message shown to the approver…"
                  value={(config.approval_message as string) ?? ''}
                  onChange={(e) => updateConfig('approval_message', e.target.value)}
                />
              </div>
              <div>
                <label className={labelCls}>Timeout (seconds)</label>
                <input
                  type="number"
                  className={inputCls}
                  min={60}
                  value={(config.timeout_seconds as number) ?? 3600}
                  onChange={(e) => updateConfig('timeout_seconds', parseInt(e.target.value) || 3600)}
                />
              </div>
            </>
          )}

          {type === 'PARALLEL' && (
            <p className="text-xs text-gray-400 dark:text-gray-500 italic">
              Parallel steps automatically fork execution. Connect multiple outgoing edges to define parallel branches.
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-gray-100 dark:border-[#1e2535]" />

        {/* Routing */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
            Routing
          </h4>
          <div>
            <label className={labelCls}>On Success → Step</label>
            <select
              className={selectCls}
              value={onSuccessStep ?? ''}
              onChange={(e) => setOnSuccessStep(e.target.value ? parseInt(e.target.value) : undefined)}
            >
              <option value="">— End / Auto —</option>
              {allStepIndexes
                .filter(i => i !== nodeData.step_index)
                .map(i => (
                  <option key={i} value={i}>Step #{i}</option>
                ))
              }
            </select>
          </div>

          {(type === 'TASK' || type === 'CONDITION') && (
            <div>
              <label className={labelCls}>On Failure → Step</label>
              <select
                className={selectCls}
                value={onFailureStep ?? ''}
                onChange={(e) => setOnFailureStep(e.target.value ? parseInt(e.target.value) : undefined)}
              >
                <option value="">— End / Auto —</option>
                {allStepIndexes
                  .filter(i => i !== nodeData.step_index)
                  .map(i => (
                    <option key={i} value={i}>Step #{i}</option>
                  ))
                }
              </select>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-100 dark:border-[#1e2535]">
          <Button
            variant="ghost"
            onClick={handleDelete}
            className="text-red-500 hover:text-red-400 hover:bg-red-500/10"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Delete Step
          </Button>
          <Button
            onClick={handleSave}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            <Save className="w-4 h-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </div>
    </SlideOver>
  );
};
