import React, { useState, useEffect } from 'react';
import { api } from '@/services/api';
import { WorkflowBuilder } from './WorkflowBuilder';
import { Button } from "@/components/ui/button";
import { Plus, Play, Info, CheckCircle, Clock, AlertTriangle, XCircle, Search, Power } from 'lucide-react';
import toast from 'react-hot-toast';

export const WorkflowAutomationPanel: React.FC = () => {
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'list' | 'create' | 'executions'>('list');
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<any>(null);

  useEffect(() => {
    let interval: any;
    if (view === 'list') {
      loadWorkflows();
    } else if (view === 'executions' && executionId) {
      const poll = async () => {
        try {
          const res = await api.get(`/api/v1/workflows/executions/${executionId}`);
          setExecutionStatus(res.data);
          if (res.data.status === 'COMPLETED' || res.data.status === 'FAILED') {
            clearInterval(interval);
          }
        } catch (e) {
          console.error('Poll failed', e);
        }
      };
      poll();
      interval = setInterval(poll, 2000);
    }
    return () => clearInterval(interval);
  }, [view, executionId]);

  const loadWorkflows = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/v1/workflows/');
      setWorkflows(res.data);
    } catch (e) {
      toast.error('Failed to load workflows');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (name: string, template: any, cron?: string) => {
    try {
      await api.post('/api/v1/workflows/', {
        name,
        template_json: template,
        schedule_cron: cron || undefined
      });
      toast.success('Workflow created');
      setView('list');
    } catch (e) {
      toast.error('Failed to save workflow');
    }
  };

  const handleExecute = async (id: string) => {
    try {
      const res = await api.post(`/api/v1/workflows/${id}/execute`, { context: {} });
      toast.success('Execution started');
      setSelectedWorkflowId(id);
      setExecutionId(res.data.id);
      setExecutionStatus(res.data);
      setView('executions');
    } catch (e) {
      toast.error('Trigger failed');
    }
  };

  if (view === 'create') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => setView('list')} className="text-gray-400">Back Config</Button>
          <h2 className="text-xl font-bold text-white">New Workflow</h2>
        </div>
        <WorkflowBuilder onSave={handleSave} />
      </div>
    );
  }

  if (view === 'executions' && executionStatus) {
    const isDone = executionStatus.status === 'COMPLETED' || executionStatus.status === 'FAILED';
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setView('list')} className="text-gray-400 px-2 py-1 h-auto text-xs border border-gray-700">Back</Button>
            <h2 className="text-xl font-bold text-white">Live Execution: <span className="text-indigo-400 font-mono text-lg">{executionId?.split('-')[0]}</span></h2>
          </div>
          <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
            executionStatus.status === 'COMPLETED' ? 'bg-green-500/20 text-green-400' : 
            executionStatus.status === 'FAILED' ? 'bg-red-500/20 text-red-400' : 
            'bg-indigo-500/20 text-indigo-400'
          }`}>
            {executionStatus.status}
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 min-h-[300px] text-gray-300 relative overflow-hidden">
          {!isDone && (
            <div className="absolute top-0 left-0 right-0 h-1 bg-indigo-500/20">
              <div className="h-full bg-indigo-500 animate-[pulse_2s_ease-in-out_infinite] w-1/3"></div>
            </div>
          )}
          
          <div className="flex flex-col items-center justify-center py-8">
            {!isDone && <ActivityPulse />}
            {executionStatus.status === 'COMPLETED' && <CheckCircle className="w-16 h-16 text-green-500 mb-4" />}
            {executionStatus.status === 'FAILED' && <XCircle className="w-16 h-16 text-red-500 mb-4" />}
            
            <h3 className="text-2xl font-semibold mt-6">{isDone ? 'Execution ' + executionStatus.status : 'Processing Workflow...'}</h3>
            <p className="text-gray-500 mt-2 font-mono text-sm max-w-sm text-center">
              {isDone 
                ? 'Workflow run has concluded.' 
                : `Currently executing step index ${executionStatus.current_step_index}. The engine is actively orchestrating tasks.`}
            </p>
          </div>

          <div className="mt-8 border-t border-slate-800 pt-6">
            <h4 className="text-sm font-semibold text-gray-500 mb-4 uppercase tracking-wider">Execution Context</h4>
            <pre className="bg-slate-950 p-4 rounded-lg text-xs font-mono text-emerald-400 overflow-x-auto border border-slate-800">
              {JSON.stringify(executionStatus.context_data, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Power className="w-5 h-5 text-indigo-500" /> Workflow Templates
        </h2>
        <Button onClick={() => setView('create')} className="bg-indigo-600 hover:bg-indigo-700 text-white">
          <Plus className="w-4 h-4 mr-2" /> New Workflow
        </Button>
      </div>

      {loading ? (
        <div className="text-gray-500 animate-pulse">Loading...</div>
      ) : workflows.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-8 text-center">
          <p className="text-gray-500 mb-4">No workflows found. Create an automated sequence to save time.</p>
          <Button onClick={() => setView('create')} variant="outline" className="border-indigo-500 text-indigo-400 hover:bg-indigo-500/10">
            <Plus className="w-4 h-4 mr-2" /> Create First Workflow
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workflows.map(wf => (
            <div key={wf.id} className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl p-5 hover:border-gray-300 dark:hover:border-indigo-500/50 transition-all flex flex-col justify-between hidden-card">
              <div>
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-semibold text-gray-900 dark:text-white text-base truncate">{wf.name}</h3>
                  <span className="text-[10px] bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 px-2 py-0.5 rounded font-mono">v{wf.version}</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 line-clamp-2">
                  {wf.description || 'No description provided.'}
                </p>
                <div className="flex items-center gap-4 text-xs text-gray-400 mb-4">
                  <div className="flex items-center gap-1"><Clock className="w-3 h-3"/> {wf.schedule_cron || 'Manual'}</div>
                  <div className="flex items-center gap-1 bg-green-500/10 text-green-400 px-1.5 rounded">Active</div>
                </div>
              </div>
              <div className="flex gap-2 pt-4 border-t border-gray-100 dark:border-[#1e2535]">
                <Button 
                  onClick={() => handleExecute(wf.id)}
                  size="sm" 
                  className="flex-1 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-medium shadow-[0_0_15px_rgba(99,102,241,0.3)] shadow-indigo-500/20"
                >
                  <Play className="w-3.5 h-3.5 mr-1" /> Run Now
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ActivityPulse = () => (
  <div className="relative flex items-center justify-center w-12 h-12">
    <div className="absolute w-full h-full border-4 border-indigo-500 rounded-full animate-ping opacity-20"></div>
    <div className="absolute w-8 h-8 bg-indigo-500 rounded-full"></div>
    <Play className="w-4 h-4 text-white relative z-10 ml-0.5" />
  </div>
);
