import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '@/services/api';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/button';
import { Play, ArrowLeft, RefreshCw } from 'lucide-react';
import { useWebSocketStore } from '@/store/websocketStore';

interface Execution {
  id: string;
  workflow_id: string;
  status: 'COMPLETED' | 'FAILED' | 'RUNNING' | 'PENDING';
  current_step_index: number;
  started_at: string;
  completed_at: string | null;
  context_data: Record<string, unknown>;
}

interface Workflow {
  id: string;
  name: string;
  version: number;
  schedule_cron?: string;
  is_active: boolean;
}

export const WorkflowExecutionsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const lastWorkflowExecution = useWebSocketStore(s => s.lastWorkflowExecution);

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [liveExecution, setLiveExecution] = useState<Execution | null>(null);
  const [polling, setPolling] = useState(false);

  // Load workflow info
  useEffect(() => {
    if (!id) return;
    api.get(`/api/v1/workflows/${id}`)
      .then(res => setWorkflow(res.data))
      .catch(() => showToast.error('Failed to load workflow'))
      .finally(() => setLoading(false));
  }, [id]);

  // Load executions list
  const loadExecutions = useCallback(() => {
    if (!id) return;
    api.get(`/api/v1/workflows/${id}/executions`)
      .then(res => setExecutions(res.data))
      .catch(() => showToast.error('Failed to load executions'));
  }, [id]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  // Sync WebSocket updates for live execution
  useEffect(() => {
    if (lastWorkflowExecution && liveExecution && lastWorkflowExecution.execution_id === liveExecution.id) {
      setLiveExecution(prev => prev ? {
        ...prev,
        status: lastWorkflowExecution.status.toUpperCase() as Execution['status'],
        current_step_index: lastWorkflowExecution.current_step ?? prev.current_step_index,
        completed_at: ['completed', 'failed'].includes(lastWorkflowExecution.status)
          ? lastWorkflowExecution.timestamp
          : prev.completed_at,
      } : null);
    }
  }, [lastWorkflowExecution, liveExecution]);

  // Poll live execution
  useEffect(() => {
    if (!liveExecution || !['RUNNING', 'PENDING'].includes(liveExecution.status)) {
      setPolling(false);
      return;
    }

    setPolling(true);
    const interval = setInterval(() => {
      if (document.hidden) return;
      api.get(`/api/v1/workflows/executions/${liveExecution.id}`)
        .then(res => {
          setLiveExecution(res.data);
          if (res.data.status === 'COMPLETED' || res.data.status === 'FAILED') {
            setPolling(false);
            loadExecutions(); // Refresh list
          }
        })
        .catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [liveExecution, loadExecutions]);

  const handleRunNow = async () => {
    if (!id) return;
    try {
      const res = await api.post(`/api/v1/workflows/${id}/execute`, { context: {} });
      showToast.success('Execution started');
      const newExecution: Execution = res.data;
      setLiveExecution(newExecution);
      setSelectedExecutionId(newExecution.id);
    } catch {
      showToast.error('Failed to start execution');
    }
  };

  const handleViewExecution = (exec: Execution) => {
    setSelectedExecutionId(exec.id);
    setLiveExecution(exec);
  };

  const handleBack = () => navigate(`/workflows/${id}`);
  const handleViewDesigner = () => navigate(`/workflows/${id}`);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (!workflow) return null;

  const isLive = !!liveExecution && ['RUNNING', 'PENDING'].includes(liveExecution.status);
  const isDone = !!liveExecution && ['COMPLETED', 'FAILED'].includes(liveExecution.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" onClick={handleBack} className="text-gray-600 dark:text-gray-400">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Execution History: {workflow.name}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">v{workflow.version}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleViewDesigner} className="text-sm">
            View Designer
          </Button>
          <Button onClick={handleRunNow} className="bg-indigo-600 hover:bg-indigo-700 text-white" disabled={isLive}>
            <Play className="w-4 h-4 mr-2" /> Run Now
          </Button>
        </div>
      </div>

      {/* Live Execution View */}
      {(isLive || isDone) && (
        <div className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Live Execution
              <span className="ml-2 font-mono text-sm text-gray-500">{liveExecution?.id?.split('-')[0]}</span>
            </h3>
            <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
              liveExecution?.status === 'COMPLETED' ? 'bg-green-500/20 text-green-700 dark:text-green-400' :
              liveExecution?.status === 'FAILED' ? 'bg-red-500/20 text-red-700 dark:text-red-400' :
              'bg-indigo-500/20 text-indigo-700 dark:text-indigo-300'
            }`}>
              {liveExecution?.status}
            </div>
          </div>

          <div className="flex flex-col items-center justify-center py-8">
            {isLive && (
              <div className="relative flex items-center justify-center w-12 h-12 mb-4">
                <div className="absolute w-full h-full border-4 border-indigo-500 rounded-full animate-ping opacity-20" />
                <div className="absolute w-8 h-8 bg-indigo-500 rounded-full" />
                <Play className="w-4 h-4 text-white relative z-10 ml-0.5" />
              </div>
            )}
            {liveExecution?.status === 'COMPLETED' && (
              <svg className="w-16 h-16 text-green-700 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
            )}
            {liveExecution?.status === 'FAILED' && (
              <svg className="w-16 h-16 text-red-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            )}
            <h4 className="text-xl font-semibold mt-4 text-gray-900 dark:text-white">
              {isLive ? 'Processing Workflow…' : `Execution ${liveExecution?.status}`}
            </h4>
            <p className="text-gray-600 dark:text-gray-300 mt-2 font-mono text-sm max-w-sm text-center">
              {isLive
                ? `Currently executing step index ${liveExecution?.current_step_index}. The engine is actively orchestrating tasks.`
                : 'Workflow run has concluded.'}
            </p>
          </div>

          <div className="mt-8 border-t border-gray-200 dark:border-[#1e2535] pt-6">
            <h4 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-4 uppercase tracking-wider">
              Execution Context
            </h4>
            <pre className="bg-gray-50 dark:bg-[#0f1117] p-4 rounded-lg text-xs font-mono text-emerald-700 dark:text-emerald-400 overflow-x-auto border border-gray-200 dark:border-[#1e2535]">
              {JSON.stringify(liveExecution?.context_data, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Executions List */}
      <div className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl">
        {executions.length === 0 ? (
          <EmptyState
            illustration="workflows"
            icon={Play}
            title="No executions yet"
            description="Click 'Run Now' to trigger a workflow execution."
            action={{ label: 'Run Now', onClick: handleRunNow }}
          />
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-[#1e2535]">
            {executions.map((exec) => (
              <div key={exec.id} className="p-4 hover:bg-gray-50 dark:hover:bg-[#1e2535] cursor-pointer transition-colors"
                onClick={() => handleViewExecution(exec)}>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                      exec.status === 'COMPLETED' ? 'bg-green-500/20 text-green-700 dark:text-green-400' :
                      exec.status === 'FAILED' ? 'bg-red-500/20 text-red-700 dark:text-red-400' :
                      exec.status === 'RUNNING' ? 'bg-indigo-500/20 text-indigo-700 dark:text-indigo-300' :
                      'bg-gray-500/20 text-gray-700 dark:text-gray-400'
                    }`}>
                      {exec.status}
                    </div>
                    <div className="font-mono text-sm text-gray-500">
                      {exec.id.split('-')[0]}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
                    <span>Step: {exec.current_step_index}</span>
                    <span>Started: {new Date(exec.started_at).toLocaleString()}</span>
                    {exec.completed_at && <span>Completed: {new Date(exec.completed_at).toLocaleString()}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowExecutionsPage;