// frontend/src/pages/ABTestingPage.tsx
import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  FlaskConical, Plus, X, Play, BarChart3, Clock, DollarSign,
  Trophy, ChevronRight, RefreshCw, Trash2, StopCircle,
  TrendingUp, Zap, CheckCircle2, AlertCircle, Loader2,
  Target, Layers, Activity, Shield, AlertTriangle,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, RadarChart, PolarGrid,
  PolarAngleAxis, Radar,
} from 'recharts';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { api } from '@/services/api';
import {
  abTestingApi,
  ExperimentSummary,
  ExperimentDetail,
  ModelComparison,
  ExperimentStatus,
  PaginatedExperiments,
} from '@/services/abTesting';

// ── Colour palette ────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, {
  bg: string; text: string; dot: string;
  darkBg: string; darkText: string; darkDot: string;
}> = {
  draft:     { bg: 'bg-slate-100',  text: 'text-slate-600',   dot: 'bg-slate-400',           darkBg: 'dark:bg-slate-800',       darkText: 'dark:text-slate-400',   darkDot: 'dark:bg-slate-500' },
  pending:   { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-400',            darkBg: 'dark:bg-amber-500/10',    darkText: 'dark:text-amber-400',   darkDot: 'dark:bg-amber-400' },
  running:   { bg: 'bg-blue-50',    text: 'text-blue-700',    dot: 'bg-blue-500 animate-pulse', darkBg: 'dark:bg-blue-500/10',   darkText: 'dark:text-blue-400',    darkDot: 'dark:bg-blue-400' },
  completed: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500',          darkBg: 'dark:bg-emerald-500/10',  darkText: 'dark:text-emerald-400', darkDot: 'dark:bg-emerald-400' },
  failed:    { bg: 'bg-red-50',     text: 'text-red-700',     dot: 'bg-red-500',              darkBg: 'dark:bg-red-500/10',      darkText: 'dark:text-red-400',     darkDot: 'dark:bg-red-400' },
  cancelled: { bg: 'bg-slate-100',  text: 'text-slate-500',   dot: 'bg-slate-300',            darkBg: 'dark:bg-slate-800',       darkText: 'dark:text-slate-400',   darkDot: 'dark:bg-slate-600' },
};

const MODEL_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#06b6d4'];
const FILTERS: Array<ExperimentStatus | ''> = ['', 'running', 'completed', 'failed', 'pending', 'cancelled'];
const PAGE_SIZE = 18;

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
      ${s.bg} ${s.text} ${s.darkBg} ${s.darkText}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.darkDot}`} />
      {status}
    </span>
  );
}

function ScorePill({ score, label }: { score: number | null | undefined; label?: string }) {
  const v = score ?? 0;
  const color =
    v >= 80 ? 'text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-500/10' :
    v >= 60 ? 'text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-500/10' :
              'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-500/10';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${color}`}>
      {label && <span className="font-normal mr-1">{label}</span>}
      {v.toFixed(1)}
    </span>
  );
}

function MetricCard({ icon: Icon, label, value, sub }: {
  icon: React.ElementType; label: string; value: string; sub?: string;
}) {
  return (
    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-slate-100 dark:border-[#1e2535] p-4 flex items-center gap-3 shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)]">
      <div className="w-9 h-9 rounded-lg bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center shrink-0">
        <Icon className="w-4.5 h-4.5 text-indigo-600 dark:text-indigo-400" size={18} />
      </div>
      <div>
        <p className="text-xs text-slate-400 dark:text-slate-500 font-medium">{label}</p>
        <p className="text-lg font-bold text-slate-800 dark:text-white leading-tight">{value}</p>
        {sub && <p className="text-xs text-slate-400 dark:text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

// ── Delete confirm modal (replaces window.confirm) ────────────────────────────

function DeleteConfirmModal({
  name,
  onConfirm,
  onCancel,
}: {
  name: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl border border-slate-100 dark:border-[#1e2535] w-full max-w-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-red-50 dark:bg-red-500/10 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-red-500 dark:text-red-400" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 dark:text-white text-sm">Delete Experiment</h3>
            <p className="text-xs text-slate-400 dark:text-slate-500">This action cannot be undone</p>
          </div>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-5">
          Are you sure you want to delete <span className="font-semibold text-slate-800 dark:text-white">"{name}"</span>?
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ── Experiment Card ───────────────────────────────────────────────────────────

function ExperimentCard({
  experiment,
  onClick,
  onDelete,
}: {
  experiment: ExperimentSummary;
  onClick: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const isDeletable = experiment.status !== 'running' && experiment.status !== 'pending';

  return (
    <>
      <div
        onClick={onClick}
        className="bg-white dark:bg-[#161b27] border border-slate-100 dark:border-[#1e2535] rounded-2xl p-5 cursor-pointer
          hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)] hover:border-indigo-100
          dark:hover:border-indigo-500/30 transition-all group"
      >
        <div className="flex items-start justify-between mb-3">
          <StatusBadge status={experiment.status} />
          {isDeletable && (
            <button
              onClick={e => { e.stopPropagation(); setConfirmDelete(true); }}
              className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all"
            >
              <Trash2 className="w-3.5 h-3.5 text-red-400" />
            </button>
          )}
        </div>

        <h3 className="font-semibold text-slate-900 dark:text-white text-sm leading-tight mb-3">
          {experiment.name}
        </h3>

        <div className="flex items-center gap-4 text-xs text-slate-400 dark:text-slate-500 mb-3">
          <span className="flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" />
            {experiment.models_tested} models
          </span>
          {experiment.created_at && (
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {new Date(experiment.created_at).toLocaleDateString()}
            </span>
          )}
        </div>

        {/* Run counts */}
        {experiment.total_runs > 0 && (
          <div className="flex items-center gap-2 text-xs mb-3">
            <span className="text-emerald-600 dark:text-emerald-400">
              ✓ {experiment.completed_runs}
            </span>
            {experiment.failed_runs > 0 && (
              <span className="text-red-500 dark:text-red-400">
                ✗ {experiment.failed_runs}
              </span>
            )}
            <span className="text-slate-400">/ {experiment.total_runs} runs</span>
          </div>
        )}

        {/* Progress bar */}
        <div>
          <div className="flex justify-between text-xs text-slate-400 dark:text-slate-500 mb-1">
            <span>Progress</span>
            <span>{experiment.progress}%</span>
          </div>
          <div className="h-1.5 bg-slate-100 dark:bg-[#0f1117] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                experiment.status === 'completed' ? 'bg-emerald-400 dark:bg-emerald-500' :
                experiment.status === 'failed'    ? 'bg-red-400 dark:bg-red-500' :
                experiment.status === 'running'   ? 'bg-indigo-500 dark:bg-indigo-400' :
                                                    'bg-slate-300 dark:bg-slate-600'
              }`}
              style={{ width: `${experiment.progress}%` }}
            />
          </div>
        </div>

        <div className="mt-3 flex items-center text-xs text-indigo-500 dark:text-indigo-400 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
          View details <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
        </div>
      </div>

      {confirmDelete && (
        <DeleteConfirmModal
          name={experiment.name}
          onConfirm={() => { setConfirmDelete(false); onDelete(); }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  );
}

// ── Create Experiment Modal ───────────────────────────────────────────────────

function CreateExperimentModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [taskTemplate, setTaskTemplate] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [iterations, setIterations] = useState(1);
  const [selectedConfigs, setSelectedConfigs] = useState<string[]>([]);

  const { data: modelsData } = useQuery({
    queryKey: ['model-configs'],
    queryFn: () => api.get('/api/v1/models/configs').then(r => r.data),
  });
  const models = Array.isArray(modelsData) ? modelsData : [];

  const { mutate: create, isPending, error } = useMutation({
    mutationFn: () => abTestingApi.createExperiment({
      name,
      task_template: taskTemplate,
      config_ids: selectedConfigs,
      description: '',
      system_prompt: systemPrompt || undefined,
      iterations,
    }),
    onSuccess: () => { onCreated(); onClose(); },
    onError: (err: Error) => toast.error(err.message),
  });

  const toggleConfig = (id: string) =>
    setSelectedConfigs(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    );

  const isValid = name.trim() && taskTemplate.trim() && selectedConfigs.length >= 2;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_25px_50px_-12px_rgba(0,0,0,0.5)] w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-slate-100 dark:border-[#1e2535]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100 dark:border-[#1e2535]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 dark:bg-indigo-500 flex items-center justify-center shadow-lg shadow-indigo-500/25">
              <FlaskConical className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">New Experiment</h2>
              <p className="text-xs text-slate-400 dark:text-slate-500">Compare models side-by-side</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-sm text-red-700 dark:text-red-400">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error.message}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Experiment Name <span className="text-red-400">*</span>
            </label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. GPT-4o vs Claude 3.5 — Summarisation"
              className="w-full px-3.5 py-2.5 text-sm bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-xl text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>

          {/* Task template */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              Task / Prompt <span className="text-red-400">*</span>
            </label>
            <textarea
              value={taskTemplate}
              onChange={e => setTaskTemplate(e.target.value)}
              rows={4}
              placeholder="The exact prompt that will be sent to each model..."
              className="w-full px-3.5 py-2.5 text-sm bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-xl text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            />
          </div>

          {/* System prompt */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              System Prompt <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={systemPrompt}
              onChange={e => setSystemPrompt(e.target.value)}
              rows={2}
              placeholder="Override the default system prompt..."
              className="w-full px-3.5 py-2.5 text-sm bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-xl text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            />
          </div>

          {/* Model selection */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Models to compare <span className="text-red-400">*</span>
              <span className="ml-1 text-xs text-slate-400 font-normal">(select at least 2)</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {models.map((m: { id: string; name?: string; default_model?: string }) => {
                const selected = selectedConfigs.includes(m.id);
                return (
                  <button
                    key={m.id}
                    onClick={() => toggleConfig(m.id)}
                    className={`px-3 py-2.5 rounded-xl text-xs font-medium border transition-all text-left ${
                      selected
                        ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
                        : 'border-slate-200 dark:border-[#1e2535] text-slate-600 dark:text-slate-400 hover:border-indigo-300 dark:hover:border-indigo-500/50'
                    }`}
                  >
                    <span className="block font-semibold">{m.name || m.default_model || m.id}</span>
                    {m.default_model && m.name && (
                      <span className="text-slate-400 dark:text-slate-500 font-normal">{m.default_model}</span>
                    )}
                  </button>
                );
              })}
              {models.length === 0 && (
                <p className="col-span-2 text-xs text-slate-400 dark:text-slate-500 py-3 text-center">
                  No model configurations found. Add one in the Models page.
                </p>
              )}
            </div>
          </div>

          {/* Iterations */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              Iterations per model
            </label>
            <div className="flex gap-2">
              {[1, 2, 3, 5].map(n => (
                <button
                  key={n}
                  onClick={() => setIterations(n)}
                  className={`px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
                    iterations === n
                      ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-400'
                      : 'border-slate-200 dark:border-[#1e2535] text-slate-600 dark:text-slate-400 hover:border-indigo-300 dark:hover:border-indigo-500/50'
                  }`}
                >
                  {n}×
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-slate-100 dark:border-[#1e2535]">
          <p className="text-xs text-slate-400 dark:text-slate-500">
            {selectedConfigs.length} model{selectedConfigs.length !== 1 ? 's' : ''} selected
            · {selectedConfigs.length * iterations} total runs
          </p>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={() => create()}
              disabled={!isValid || isPending}
              className="flex items-center gap-2 px-5 py-2 bg-indigo-600 dark:bg-indigo-500 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 dark:hover:bg-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md shadow-indigo-500/25"
            >
              {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {isPending ? 'Starting…' : 'Run Experiment'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ── Quick Test Modal ──────────────────────────────────────────────────────────

function QuickTestModal({ onClose }: { onClose: () => void }) {
  const [task, setTask] = useState('');
  const [selectedConfigs, setSelectedConfigs] = useState<string[]>([]);
  const [launchedId, setLaunchedId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: modelsData } = useQuery({
    queryKey: ['model-configs'],
    queryFn: () => api.get('/api/v1/models/configs').then(r => r.data),
  });
  const models = Array.isArray(modelsData) ? modelsData : [];

  // Poll the experiment detail once we have an ID
  const { data: resultExp } = useQuery({
    queryKey: ['experiment', launchedId],
    queryFn: () => abTestingApi.getExperiment(launchedId!),
    enabled: !!launchedId,
    refetchInterval: query => {
      const d = query.state.data;
      if (!d || d.status === 'running' || d.status === 'pending') return 2000;
      return false;
    },
  });

  const { mutate: runTest, isPending, error } = useMutation({
    mutationFn: () => abTestingApi.quickTest(task, selectedConfigs),
    onSuccess: data => {
      setLaunchedId(data.id);
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const toggleConfig = (id: string) =>
    setSelectedConfigs(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    );

  const isValid = task.trim() && selectedConfigs.length >= 2;
  const isDone = resultExp && resultExp.status !== 'running' && resultExp.status !== 'pending';

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 dark:bg-black/80 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_25px_50px_-12px_rgba(0,0,0,0.5)] w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-slate-100 dark:border-[#1e2535]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100 dark:border-[#1e2535]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/25">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">Quick A/B Test</h2>
              <p className="text-xs text-slate-400 dark:text-slate-500">Fires in background — results shown when ready</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        {launchedId ? (
          <div className="p-6 space-y-4">
            {!isDone ? (
              <div className="flex flex-col items-center py-10 gap-4">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
                <p className="text-sm text-slate-500 dark:text-slate-400">Running experiment…</p>
                <StatusBadge status={resultExp?.status ?? 'pending'} />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-4 h-4" />
                  Experiment completed
                </div>

                {resultExp?.comparison?.winner && (
                  <div className="bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Trophy className="w-4 h-4 text-amber-500" />
                      <span className="text-sm font-semibold text-slate-800 dark:text-white">
                        Winner: {resultExp.comparison.winner.model}
                      </span>
                      <ScorePill score={resultExp.comparison.winner.confidence} label="conf" />
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {resultExp.comparison.winner.reason}
                    </p>
                  </div>
                )}

                {(resultExp?.comparison?.model_comparisons?.models ?? []).length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-[#1e2535]">
                          <th className="text-left py-2 pr-4">Model</th>
                          <th className="text-right pr-4">Quality</th>
                          <th className="text-right pr-4">Success</th>
                          <th className="text-right pr-4">Cost</th>
                          <th className="text-right">Latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {resultExp.comparison!.model_comparisons.models.map(m => (
                          <tr key={m.config_id} className="border-b border-slate-50 dark:border-[#1e2535]">
                            <td className="py-2 pr-4 font-medium text-slate-800 dark:text-white">{m.model_name}</td>
                            <td className="py-2 pr-4 text-right"><ScorePill score={m.avg_quality_score} /></td>
                            <td className="py-2 pr-4 text-right text-slate-500">{m.success_rate.toFixed(0)}%</td>
                            <td className="py-2 pr-4 text-right text-slate-500">${m.avg_cost_usd.toFixed(5)}</td>
                            <td className="py-2 text-right text-slate-500">{m.avg_latency_ms?.toLocaleString() ?? '—'}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => { setLaunchedId(null); setTask(''); setSelectedConfigs([]); }}
                    className="flex items-center gap-2 px-4 py-2 text-sm bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Run Another
                  </button>
                  <button
                    onClick={onClose}
                    className="px-4 py-2 text-sm bg-slate-100 dark:bg-[#1e2535] text-slate-600 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-[#2a3347] transition-colors"
                  >
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="p-6 space-y-5">
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg text-sm text-red-700 dark:text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {(error as Error).message}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Task Prompt</label>
              <textarea
                value={task}
                onChange={e => setTask(e.target.value)}
                rows={3}
                placeholder="Enter the prompt to test across models..."
                className="w-full px-3.5 py-2.5 text-sm bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-xl text-slate-800 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Models <span className="text-xs text-slate-400 font-normal">(select at least 2)</span>
              </label>
              <div className="grid grid-cols-2 gap-2">
                {models.map((m: { id: string; name?: string; default_model?: string }) => {
                  const selected = selectedConfigs.includes(m.id);
                  return (
                    <button
                      key={m.id}
                      onClick={() => toggleConfig(m.id)}
                      className={`px-3 py-2 rounded-xl text-xs font-medium border transition-all text-left ${
                        selected
                          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300'
                          : 'border-slate-200 dark:border-[#1e2535] text-slate-600 dark:text-slate-400 hover:border-indigo-300'
                      }`}
                    >
                      {m.name || m.default_model || m.id}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
                Cancel
              </button>
              <button
                onClick={() => runTest()}
                disabled={!isValid || isPending}
                className="flex items-center gap-2 px-5 py-2 bg-amber-500 text-white text-sm font-medium rounded-lg hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {isPending ? 'Launching…' : 'Run Quick Test'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

// ── Experiment Detail Panel (portal) ─────────────────────────────────────────

function ExperimentDetailPanel({
  experimentId,
  onClose,
}: {
  experimentId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const { data: exp, isLoading, refetch } = useQuery({
    queryKey: ['experiment', experimentId],
    queryFn: () => abTestingApi.getExperiment(experimentId),
    refetchInterval: query => {
      const d = query.state.data;
      if (!d || d.status === 'running' || d.status === 'pending') return 3000;
      return false;
    },
  });

  const { mutate: cancelExp, isPending: isCancelling } = useMutation({
    mutationFn: () => abTestingApi.cancelExperiment(experimentId),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Build radar data from model comparisons
  const models = exp?.comparison?.model_comparisons?.models ?? [];
  const radarData = models.length > 0
    ? [
        { metric: 'Quality',      ...Object.fromEntries(models.map(m => [m.model_name, m.avg_quality_score])) },
        { metric: 'Cost Eff.',    ...Object.fromEntries(models.map(m => [m.model_name, Math.max(0, 100 - m.avg_cost_usd * 10000)])) },
        { metric: 'Speed',        ...Object.fromEntries(models.map(m => [m.model_name, Math.max(0, 100 - m.avg_latency_ms / 100)])) },
        { metric: 'Reliability',  ...Object.fromEntries(models.map(m => [m.model_name, m.success_rate])) },
      ]
    : [];

  const panel = (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 dark:bg-black/80 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#161b27] rounded-t-2xl sm:rounded-2xl shadow-2xl border border-slate-100 dark:border-[#1e2535] w-full sm:max-w-4xl max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-100 dark:border-[#1e2535] shrink-0">
          {isLoading || !exp ? (
            <div className="h-6 w-48 bg-slate-100 dark:bg-[#1e2535] rounded animate-pulse" />
          ) : (
            <div className="flex items-center gap-3">
              <StatusBadge status={exp.status} />
              <h2 className="font-bold text-slate-900 dark:text-white">{exp.name}</h2>
            </div>
          )}
          <div className="flex items-center gap-2">
            {exp && (exp.status === 'running' || exp.status === 'pending') && (
              <button
                onClick={() => cancelExp()}
                disabled={isCancelling}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/30 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50"
              >
                <StopCircle className="w-3.5 h-3.5" />
                Cancel
              </button>
            )}
            <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
              <X className="w-4 h-4 text-slate-400" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 p-6 space-y-6">
          {isLoading || !exp ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            </div>
          ) : (
            <>
              {/* Winner */}
              {exp.comparison?.winner && (
                <div className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-500/10 dark:to-purple-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-2xl p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <Trophy className="w-5 h-5 text-amber-500" />
                    <span className="font-bold text-slate-900 dark:text-white">
                      Winner: {exp.comparison.winner.model}
                    </span>
                    <ScorePill score={exp.comparison.winner.confidence} label="confidence" />
                  </div>
                  <p className="text-sm text-slate-600 dark:text-slate-400">{exp.comparison.winner.reason}</p>
                </div>
              )}

              {/* Radar + bar charts */}
              {models.length > 0 && radarData.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Radar */}
                  <div className="bg-slate-50 dark:bg-[#0f1117] rounded-xl p-4 border border-slate-100 dark:border-[#1e2535]">
                    <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 uppercase tracking-wide">
                      Performance Radar
                    </h3>
                    <ResponsiveContainer width="100%" height={220}>
                      <RadarChart data={radarData}>
                        <PolarGrid stroke="#e2e8f0" />
                        <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                        {models.map((m, i) => (
                          <Radar
                            key={m.config_id}
                            name={m.model_name}
                            dataKey={m.model_name}
                            stroke={MODEL_COLORS[i % MODEL_COLORS.length]}
                            fill={MODEL_COLORS[i % MODEL_COLORS.length]}
                            fillOpacity={0.12}
                          />
                        ))}
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Latency bar */}
                  <div className="bg-slate-50 dark:bg-[#0f1117] rounded-xl p-4 border border-slate-100 dark:border-[#1e2535]">
                    <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3 uppercase tracking-wide">
                      Avg Latency (ms)
                    </h3>
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={models.map((m, i) => ({ name: m.model_name, latency: m.avg_latency_ms, fill: MODEL_COLORS[i % MODEL_COLORS.length] }))}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                        <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
                        <Tooltip
                          contentStyle={{ background: '#1e2535', border: 'none', borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: '#e2e8f0' }}
                        />
                        <Bar dataKey="latency" radius={[4, 4, 0, 0]}>
                          {models.map((_, i) => (
                            <rect key={i} fill={MODEL_COLORS[i % MODEL_COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Comparison table */}
              {models.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-indigo-500" />
                    Model Comparison
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-[#1e2535]">
                          <th className="text-left py-2 pr-4 font-medium">Model</th>
                          <th className="text-right pr-4 font-medium">Quality</th>
                          <th className="text-right pr-4 font-medium">Success</th>
                          <th className="text-right pr-4 font-medium">Tokens</th>
                          <th className="text-right pr-4 font-medium">Cost</th>
                          <th className="text-right font-medium">Latency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {models.map((m, i) => (
                          <tr key={m.config_id} className="border-b border-slate-50 dark:border-[#1e2535] hover:bg-slate-50 dark:hover:bg-[#1e2535]/50">
                            <td className="py-2.5 pr-4">
                              <div className="flex items-center gap-1.5">
                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: MODEL_COLORS[i % MODEL_COLORS.length] }} />
                                <span className="font-medium text-slate-800 dark:text-slate-200">{m.model_name}</span>
                                {exp.comparison?.winner.config_id === m.config_id && (
                                  <Trophy className="w-3 h-3 text-amber-500" />
                                )}
                              </div>
                            </td>
                            <td className="py-2.5 pr-4 text-right"><ScorePill score={m.avg_quality_score} /></td>
                            <td className={`py-2.5 pr-4 text-right font-medium ${m.success_rate >= 80 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                              {m.success_rate.toFixed(0)}%
                            </td>
                            <td className="py-2.5 pr-4 text-right text-slate-500">{m.avg_tokens?.toLocaleString() ?? '—'}</td>
                            <td className="py-2.5 pr-4 text-right text-slate-500">${m.avg_cost_usd?.toFixed(5) ?? '—'}</td>
                            <td className="py-2.5 text-right text-slate-500">{m.avg_latency_ms?.toLocaleString() ?? '—'}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Individual Runs */}
              <div>
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                  <Target className="w-4 h-4 text-indigo-500" />
                  Individual Runs ({exp.runs?.length ?? 0})
                </h3>
                <div className="space-y-2">
                  {exp.runs?.map((run, i) => (
                    <div key={run.id} className="bg-slate-50 dark:bg-[#0f1117] rounded-xl p-4 border border-slate-100 dark:border-[#1e2535]">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: MODEL_COLORS[i % MODEL_COLORS.length] }} />
                        <span className="font-medium text-sm text-slate-800 dark:text-slate-200">{run.model}</span>
                        <StatusBadge status={run.status} />
                        {run.quality_score != null && <ScorePill score={run.quality_score} label="Q" />}
                        {run.latency_ms != null && (
                          <span className="text-xs text-slate-400 dark:text-slate-500">{run.latency_ms.toLocaleString()}ms</span>
                        )}
                        {run.cost_usd != null && (
                          <span className="text-xs text-slate-400 dark:text-slate-500">${run.cost_usd.toFixed(6)}</span>
                        )}
                      </div>
                      {run.output_preview && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 font-mono leading-relaxed bg-white dark:bg-[#161b27] rounded-lg p-2.5 border border-slate-100 dark:border-[#1e2535] line-clamp-3">
                          {run.output_preview}
                        </p>
                      )}
                      {run.error_message && (
                        <p className="text-xs text-red-500 dark:text-red-400 mt-1 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3 shrink-0" />
                          {run.error_message}
                        </p>
                      )}
                    </div>
                  ))}
                  {(!exp.runs || exp.runs.length === 0) && (
                    <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-6">No runs yet.</p>
                  )}
                </div>
              </div>

              {/* Task template */}
              <div>
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Task Template</h3>
                <div className="bg-slate-50 dark:bg-[#0f1117] rounded-xl p-4 text-sm text-slate-600 dark:text-slate-400 font-mono whitespace-pre-wrap border border-slate-100 dark:border-[#1e2535]">
                  {exp.task_template}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(panel, document.body);
}

// ── Recommendations Panel ─────────────────────────────────────────────────────

function RecommendationsPanel() {
  const [taskFilter, setTaskFilter] = useState('');

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['ab-recommendations', taskFilter],
    queryFn: () => abTestingApi.getRecommendations(taskFilter || undefined),
    refetchInterval: 60_000,
  });

  const recommendations = data?.recommendations ?? [];

  return (
    <div className="bg-white dark:bg-[#161b27] rounded-2xl border border-slate-100 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)]">
      <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-[#1e2535]">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
          <h2 className="font-semibold text-slate-800 dark:text-white text-sm">Model Recommendations</h2>
          {data && (
            <span className="text-xs text-slate-400 dark:text-slate-500">{data.total_categories} categories</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            value={taskFilter}
            onChange={e => setTaskFilter(e.target.value)}
            placeholder="Filter by category…"
            className="px-3 py-1.5 text-xs bg-slate-50 dark:bg-[#0f1117] border border-slate-200 dark:border-[#1e2535] rounded-lg text-slate-700 dark:text-slate-300 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 w-40"
          />
          <button onClick={() => refetch()} className="p-1.5 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
        </div>
      ) : recommendations.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <TrendingUp className="w-8 h-8 text-slate-300 dark:text-slate-600 mb-3" />
          <p className="text-sm text-slate-400 dark:text-slate-500">No recommendations yet.</p>
          <p className="text-xs text-slate-300 dark:text-slate-600 mt-1">Complete experiments to generate recommendations.</p>
        </div>
      ) : (
        <div className="divide-y divide-slate-50 dark:divide-[#1e2535]">
          {recommendations.map(rec => (
            <div key={rec.task_category} className="p-5 hover:bg-slate-50 dark:hover:bg-[#0f1117]/50 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-1">
                    {rec.task_category}
                  </p>
                  <div className="flex items-center gap-2">
                    <Trophy className="w-3.5 h-3.5 text-amber-500" />
                    <span className="font-semibold text-sm text-slate-800 dark:text-white">{rec.recommended_model}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right">
                    <p className="text-xs text-slate-400 dark:text-slate-500">Quality</p>
                    <ScorePill score={rec.avg_quality_score} />
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-400 dark:text-slate-500">Success</p>
                    <p className={`text-sm font-bold ${rec.success_rate >= 80 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
                      {rec.success_rate.toFixed(0)}%
                    </p>
                  </div>
                </div>
              </div>
              <div className="mt-2 flex items-center gap-3 text-xs text-slate-400 dark:text-slate-500">
                <span>{rec.avg_latency_ms?.toLocaleString() ?? '—'}ms avg latency</span>
                <span>·</span>
                <span>${rec.avg_cost_usd?.toFixed(5) ?? '—'} avg cost</span>
                <span>·</span>
                <span>{rec.sample_size} samples</span>
                {rec.last_updated && (
                  <>
                    <span>·</span>
                    <span>Updated {new Date(rec.last_updated).toLocaleDateString()}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Access Denied ─────────────────────────────────────────────────────────────

function AccessDenied() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0f1117] flex items-center justify-center p-6">
      <div className="text-center">
        <div className="w-20 h-20 bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-2xl flex items-center justify-center mx-auto mb-5">
          <Shield className="w-9 h-9 text-red-600 dark:text-red-400" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Access Denied</h2>
        <p className="text-slate-500 dark:text-slate-400 text-sm">Only admin users can access A/B Testing.</p>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function ABTestingPage() {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();

  // ── All hooks must be declared before any conditional return ────────────────
  const [showCreate, setShowCreate] = useState(false);
  const [showQuickTest, setShowQuickTest] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ExperimentStatus | ''>('');
  const [activeTab, setActiveTab] = useState<'experiments' | 'recommendations'>('experiments');
  const [page, setPage] = useState(0);

  const isAdmin = user?.isSovereign || user?.is_admin || false;

  // WebSocket-driven cache invalidation (replaces most polling)
  const lastMessage = useWebSocketStore(s => s.lastMessage);
  useEffect(() => {
    if (!lastMessage) return;
    if (
      lastMessage.type === 'ab_test_update' ||
      lastMessage.type === 'experiment_status_changed'
    ) {
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
      queryClient.invalidateQueries({ queryKey: ['ab-stats'] });
      if (lastMessage.metadata?.experiment_id) {
        queryClient.invalidateQueries({
          queryKey: ['experiment', lastMessage.metadata.experiment_id],
        });
      }
    }
  }, [lastMessage, queryClient]);

  const { data: pageData, isLoading, refetch } = useQuery({
    queryKey: ['experiments', statusFilter, page],
    queryFn: () => abTestingApi.listExperiments(statusFilter || undefined, PAGE_SIZE, page * PAGE_SIZE),
    enabled: isAdmin,
    // Only poll as fallback when no WS message arrives; slow interval since WS handles it
    refetchInterval: query => {
      const items = (query.state.data as PaginatedExperiments | undefined)?.items ?? [];
      const hasActive = items.some(e => e.status === 'running' || e.status === 'pending');
      return hasActive ? 8000 : 60_000;
    },
  });

  const experiments = pageData?.items ?? [];
  const totalExperiments = pageData?.total ?? 0;
  const totalPages = Math.ceil(totalExperiments / PAGE_SIZE);

  const { data: statsData } = useQuery({
    queryKey: ['ab-stats'],
    queryFn: () => abTestingApi.getStats(),
    enabled: isAdmin,
    refetchInterval: 60_000,
  });

  const { mutate: deleteExp } = useMutation({
    mutationFn: (id: string) => abTestingApi.deleteExperiment(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] });
      toast.success('Experiment deleted');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Conditional render AFTER all hooks ─────────────────────────────────────
  if (!isAdmin) return <AccessDenied />;

  const stats = statsData ?? null;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0f1117]">
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-indigo-600 dark:bg-indigo-500 flex items-center justify-center shadow-lg shadow-indigo-200 dark:shadow-indigo-500/20">
              <FlaskConical className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">A/B Model Testing</h1>
              <p className="text-sm text-slate-400 dark:text-slate-500">Compare AI models on cost, speed &amp; quality</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowQuickTest(true)}
              className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 text-white text-sm font-medium rounded-xl hover:bg-amber-600 shadow-sm transition-colors shadow-amber-200 dark:shadow-amber-500/20"
            >
              <Zap className="w-4 h-4" />
              Quick Test
            </button>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 dark:bg-indigo-500 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 dark:hover:bg-indigo-400 shadow-sm transition-colors shadow-indigo-200 dark:shadow-indigo-500/20"
            >
              <Plus className="w-4 h-4" />
              New Experiment
            </button>
          </div>
        </div>

        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard icon={FlaskConical}  label="Total Experiments" value={String(stats.total_experiments)} />
            <MetricCard icon={CheckCircle2} label="Completed"          value={String(stats.completed_experiments)} />
            <MetricCard icon={Activity}     label="Model Runs"         value={(stats.total_model_runs ?? 0).toLocaleString()} />
            <MetricCard icon={TrendingUp}   label="Recommendations"    value={String(stats.cached_recommendations)} />
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-[#161b27] rounded-xl p-1 w-fit border border-slate-200 dark:border-[#1e2535]">
          {(['experiments', 'recommendations'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all capitalize ${
                activeTab === tab
                  ? 'bg-white dark:bg-[#0f1117] text-slate-800 dark:text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {activeTab === 'recommendations' ? (
          <RecommendationsPanel />
        ) : (
          <>
            {/* Filters */}
            <div className="flex items-center gap-2 flex-wrap">
              {FILTERS.map(f => (
                <button
                  key={f || 'all'}
                  onClick={() => { setStatusFilter(f); setPage(0); }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize ${
                    statusFilter === f
                      ? 'bg-indigo-600 dark:bg-indigo-500 text-white'
                      : 'bg-white dark:bg-[#161b27] text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-[#1e2535] hover:border-slate-300 dark:hover:border-[#2a3347]'
                  }`}
                >
                  {f || 'All'}
                </button>
              ))}
              <button
                onClick={() => refetch()}
                className="ml-auto p-2 hover:bg-white dark:hover:bg-[#161b27] rounded-lg border border-transparent hover:border-slate-200 dark:hover:border-[#1e2535] transition-all"
              >
                <RefreshCw className="w-4 h-4 text-slate-400 dark:text-slate-500" />
              </button>
            </div>

            {/* Grid */}
            {isLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              </div>
            ) : experiments.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center mb-4">
                  <FlaskConical className="w-7 h-7 text-indigo-400" />
                </div>
                <h3 className="font-semibold text-slate-700 dark:text-slate-300 mb-1">No experiments yet</h3>
                <p className="text-sm text-slate-400 dark:text-slate-500 mb-5">Create your first A/B test to compare models</p>
                <button
                  onClick={() => setShowCreate(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 dark:bg-indigo-500 text-white text-sm rounded-xl hover:bg-indigo-700 dark:hover:bg-indigo-400 transition-colors shadow-md"
                >
                  <Plus className="w-4 h-4" />
                  New Experiment
                </button>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {experiments.map(exp => (
                    <ExperimentCard
                      key={exp.id}
                      experiment={exp}
                      onClick={() => setSelectedId(exp.id)}
                      onDelete={() => deleteExp(exp.id)}
                    />
                  ))}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 pt-2">
                    <button
                      onClick={() => setPage(p => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-[#1e2535] disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-[#1e2535] transition-colors"
                    >
                      ← Prev
                    </button>
                    <span className="text-sm text-slate-500 dark:text-slate-400">
                      Page {page + 1} of {totalPages}
                    </span>
                    <button
                      onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-[#1e2535] disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-[#1e2535] transition-colors"
                    >
                      Next →
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Modals (all portal-mounted inside their own components) */}
      {showQuickTest && <QuickTestModal onClose={() => setShowQuickTest(false)} />}

      {showCreate && (
        <CreateExperimentModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['experiments'] });
            queryClient.invalidateQueries({ queryKey: ['ab-stats'] });
          }}
        />
      )}

      {selectedId && (
        <ExperimentDetailPanel
          experimentId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}

export default ABTestingPage;