import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/services/api';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Button } from '@/components/ui/button';
import { Power, Edit, Play, ChevronRight } from 'lucide-react';

interface Workflow {
  id: string;
  name: string;
  description: string | null;
  version: number;
  schedule_cron: string | null;
  is_active: boolean;
}

const WorkflowCard: React.FC<{ workflow: Workflow; onEdit: () => void; onRun: () => void }> = ({
  workflow,
  onEdit,
  onRun,
}) => (
  <div
    className="
      bg-white dark:bg-[#161b27]
      border border-gray-200 dark:border-[#1e2535]
      rounded-xl p-5
      hover:border-gray-300 dark:hover:border-indigo-500/50
      transition-all flex flex-col justify-between
    "
  >
    <div>
      <div className="flex items-start justify-between mb-2">
        <h3 className="font-semibold text-gray-900 dark:text-white text-base truncate pr-2">
          {workflow.name}
        </h3>
        <span className="text-[10px] bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 px-2 py-0.5 rounded font-mono flex-shrink-0">
          v{workflow.version}
        </span>
      </div>
      <p className="text-xs text-gray-600 dark:text-gray-400 mb-4 line-clamp-2">
        {workflow.description || 'No description provided.'}
      </p>
      <div className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 mb-4">
        <div className="flex items-center gap-1">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          {workflow.schedule_cron || 'Manual'}
        </div>
        <div className="flex items-center gap-1 bg-green-500/10 text-green-700 dark:text-green-400 px-1.5 rounded">
          Active
        </div>
      </div>
    </div>

    <div className="flex gap-2 pt-4 border-t border-gray-100 dark:border-[#1e2535]">
      <Button
        onClick={onEdit}
        variant="outline"
        className="flex-1 border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-[#1e2535]"
      >
        <Edit className="w-3.5 h-3.5 mr-1.5" /> Edit
      </Button>
      <Button
        onClick={onRun}
        size="sm"
        className="
          flex-1
          bg-gradient-to-r from-indigo-500 to-purple-600
          hover:from-indigo-600 hover:to-purple-700
          text-white font-medium
          shadow-[0_0_15px_rgba(99,102,241,0.3)]
        "
      >
        <Play className="w-3.5 h-3.5 mr-1" /> Run
      </Button>
    </div>
  </div>
);

export const WorkflowsPage: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const loadWorkflows = async () => {
      try {
        setLoading(true);
        const res = await api.get('/api/v1/workflows/');
        setWorkflows(res.data);
      } catch (e) {
        showToast.error('Failed to load workflows');
      } finally {
        setLoading(false);
      }
    };
    loadWorkflows();
  }, []);

  const handleRun = async (id: string) => {
    try {
      const res = await api.post(`/api/v1/workflows/${id}/execute`, { context: {} });
      showToast.success('Execution started');
      navigate(`/workflows/${id}/executions`);
    } catch (e) {
      showToast.error('Failed to start execution');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-2">
            <Power className="w-6 h-6 text-indigo-600" />
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">Workflows</h2>
          </div>
          <Button
            onClick={() => navigate('/workflows/new')}
            className="bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            <Power className="w-4 h-4 mr-2" /> New Workflow
          </Button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <LoadingSpinner size="lg" label="Loading workflows…" />
          </div>
        ) : workflows.length === 0 ? (
          <div className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl">
            <EmptyState
              illustration="workflows"
              icon={Power}
              title="No workflows yet"
              description="Create an automated sequence to orchestrate multi-step agent tasks."
              action={{ label: 'Create First Workflow', onClick: () => navigate('/workflows/new') }}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflows.map((wf) => (
              <WorkflowCard
                key={wf.id}
                workflow={wf}
                onEdit={() => navigate(`/workflows/${wf.id}`)}
                onRun={() => handleRun(wf.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowsPage;