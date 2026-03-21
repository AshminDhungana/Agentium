import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, Trash, ArrowRight, Save } from "lucide-react";

interface StepConfig {
  step_index: number;
  type: string;
  config: any;
  on_success_step?: number;
  on_failure_step?: number;
}

interface WorkflowTemplate {
  steps: StepConfig[];
}

interface WorkflowBuilderProps {
  initialTemplate?: WorkflowTemplate;
  onSave: (name: string, template: WorkflowTemplate, cron?: string) => void;
}

export const WorkflowBuilder: React.FC<WorkflowBuilderProps> = ({ initialTemplate, onSave }) => {
  const [name, setName] = useState('');
  const [cron, setCron] = useState('');
  const [steps, setSteps] = useState<StepConfig[]>(initialTemplate?.steps || [
    { step_index: 0, type: 'TASK', config: { task_title: 'Step 1', prompt: '' } }
  ]);

  const addStep = () => {
    const nextIdx = steps.length > 0 ? Math.max(...steps.map(s => s.step_index)) + 1 : 0;
    setSteps([...steps, { step_index: nextIdx, type: 'TASK', config: { task_title: `Step ${nextIdx+1}`, prompt: '' } }]);
  };

  const updateStep = (index: number, changes: Partial<StepConfig>) => {
    const newSteps = [...steps];
    newSteps[index] = { ...newSteps[index], ...changes };
    setSteps(newSteps);
  };

  const removeStep = (index: number) => {
    const newSteps = [...steps];
    newSteps.splice(index, 1);
    setSteps(newSteps);
  };

  const handleSave = () => {
    if (!name.trim()) {
      alert("Workflow Name is required");
      return;
    }
    onSave(name, { steps }, cron);
  };

  return (
    <div className="space-y-6">
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-xl font-semibold text-white">Create Workflow</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Workflow Name</label>
              <input 
                type="text" 
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-white" 
                placeholder="e.g. Daily Data Scraper"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">Cron Schedule (Optional)</label>
              <input 
                type="text" 
                className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-white" 
                placeholder="e.g. 0 0 * * *"
                value={cron}
                onChange={e => setCron(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {steps.map((step, idx) => (
          <Card key={idx} className="bg-slate-900 border-slate-800 relative">
            <Button 
              variant="ghost" 
              size="icon" 
              className="absolute top-2 right-2 text-red-400 hover:text-red-300 hover:bg-red-400/10"
              onClick={() => removeStep(idx)}
            >
              <Trash className="w-4 h-4" />
            </Button>
            <CardContent className="pt-6">
              <div className="grid grid-cols-12 gap-4 items-start">
                <div className="col-span-2">
                  <div className="text-sm font-medium text-blue-400 mb-2">Step {step.step_index}</div>
                  <select 
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1 text-white text-sm"
                    value={step.type}
                    onChange={(e) => updateStep(idx, { type: e.target.value })}
                  >
                    <option value="TASK">AI Task</option>
                    <option value="CONDITION">Condition</option>
                    <option value="PARALLEL">Parallel</option>
                    <option value="DELAY">Delay</option>
                    <option value="HUMAN_APPROVAL">Human Approval</option>
                  </select>
                </div>
                
                <div className="col-span-6 space-y-3 border-l border-slate-800 pl-4">
                  {step.type === 'TASK' && (
                    <>
                      <div>
                        <label className="text-xs text-slate-500 mb-1 block">Task Title</label>
                        <input 
                          type="text" 
                          className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-sm"
                          value={step.config.task_title || ''}
                          onChange={e => updateStep(idx, { config: { ...step.config, task_title: e.target.value }})}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-slate-500 mb-1 block">Prompt</label>
                        <textarea 
                          rows={2}
                          className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-sm"
                          value={step.config.prompt || ''}
                          onChange={e => updateStep(idx, { config: { ...step.config, prompt: e.target.value }})}
                        />
                      </div>
                    </>
                  )}
                  {step.type === 'DELAY' && (
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">Delay Seconds</label>
                      <input 
                        type="number" 
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-sm"
                        value={step.config.delay_seconds || 60}
                        onChange={e => updateStep(idx, { config: { ...step.config, delay_seconds: parseInt(e.target.value) }})}
                      />
                    </div>
                  )}
                </div>

                <div className="col-span-4 space-y-3 border-l border-slate-800 pl-4">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">On Success Step Index</label>
                    <input 
                      type="number" 
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-sm"
                      value={step.on_success_step ?? ''}
                      onChange={e => updateStep(idx, { on_success_step: e.target.value ? parseInt(e.target.value) : undefined })}
                    />
                  </div>
                  {(step.type === 'TASK' || step.type === 'CONDITION') && (
                    <div>
                      <label className="text-xs text-slate-500 mb-1 block">On Failure Step Index</label>
                      <input 
                        type="number" 
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-white text-sm"
                        value={step.on_failure_step ?? ''}
                        onChange={e => updateStep(idx, { on_failure_step: e.target.value ? parseInt(e.target.value) : undefined })}
                      />
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        <div className="flex justify-between items-center py-4">
          <Button onClick={addStep} variant="outline" className="border-indigo-500/50 text-indigo-400 hover:bg-indigo-500/10">
            <Plus className="w-4 h-4 mr-2" /> Add Step
          </Button>
          
          <Button onClick={handleSave} className="bg-indigo-500 hover:bg-indigo-600 text-white">
            <Save className="w-4 h-4 mr-2" /> Save Workflow
          </Button>
        </div>
      </div>
    </div>
  );
};
