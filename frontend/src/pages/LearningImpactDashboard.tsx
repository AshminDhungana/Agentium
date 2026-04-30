import { useState, useEffect } from 'react';
import { Sparkles, TrendingUp, AlertTriangle, Cpu, RefreshCw, CheckCircle, Wrench, Search } from 'lucide-react';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { showToast } from '@/hooks/useToast';

interface ImpactStats {
  success_rate_delta: number;
  tools_generated: number;
  anti_patterns_warned: number;
  history: Array<{ date: string; success_rate: number }>;
}

interface Pattern {
  id: string;
  type: string;
  content: string;
  confidence: number;
}

export function LearningImpactDashboard() {
  const [stats, setStats] = useState<ImpactStats | null>(null);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const resStats = await fetch('/api/v1/improvements/impact');
      const dataStats = await resStats.json();
      setStats(dataStats);

      const resPatterns = await fetch('/api/v1/improvements/patterns');
      const dataPatterns = await resPatterns.json();
      setPatterns(dataPatterns.patterns || []);
    } catch (error) {
      console.error('Failed to fetch learning impact data', error);
      showToast.error('Failed to load learning impact data');
    } finally {
      setLoading(false);
    }
  };

  const manuallyConsolidate = async () => {
    setTriggering(true);
    try {
      await fetch('/api/v1/improvements/consolidate', { method: 'POST' });
      showToast.success('Manual knowledge consolidation triggered successfully!');
    } catch (e) {
      console.error(e);
      showToast.error('Error triggering consolidation.');
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64 text-gray-500 dark:text-gray-400">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header section with actions */}
      <div className="flex justify-between items-center bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-500" />
            Continuous Self-Improvement Engine
          </h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
            Real-time learning metrics, anti-pattern detection, and knowledge consolidation.
          </p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={fetchData}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button 
            onClick={manuallyConsolidate}
            disabled={triggering}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <Cpu className="w-4 h-4" />
            {triggering ? 'Consolidating...' : 'Trigger Consolidation'}
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-green-100 dark:bg-green-500/10 rounded-lg">
            <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Success Rate Delta (7d)</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              +{stats?.success_rate_delta?.toFixed?.(1) || '0.0'}%
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-purple-100 dark:bg-purple-500/10 rounded-lg">
            <Wrench className="w-6 h-6 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Auto-Generated Tools</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {stats?.tools_generated || 0}
            </div>
          </div>
        </div>
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-red-100 dark:bg-red-500/10 rounded-lg">
            <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Anti-Patterns Prevented</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {stats?.anti_patterns_warned || 0}
            </div>
          </div>
        </div>
      </div>

      {/* Patterns Discovered */}
      <div className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-[#1e2535]">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Recent Pattern Discoveries</h3>
        </div>
        <div className="divide-y divide-gray-200 dark:divide-[#1e2535]">
          {patterns.map(p => (
            <div key={p.id} className="p-6 flex items-start gap-4">
              {p.type === 'best_practice' ? (
                <CheckCircle className="w-5 h-5 text-green-500 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
                    p.type === 'best_practice' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                  }`}>
                    {p.type === 'best_practice' ? 'BEST PRACTICE' : 'ANTI-PATTERN'}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">ID: {p.id}</span>
                </div>
                <p className="text-gray-900 dark:text-white text-sm">
                  {p.content}
                </p>
              </div>
              <div className="text-right">
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Confidence</div>
                <div className="w-24 bg-gray-200 dark:bg-[#2a3347] rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full ${p.type === 'best_practice' ? 'bg-green-500' : 'bg-red-500'}`} 
                    style={{ width: `${p.confidence * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
          {patterns.length === 0 && (
            <EmptyState
              icon={Search}
              title="No patterns discovered"
              description="No recent patterns discovered."
            />
          )}
        </div>
      </div>
    </div>
  );
}
