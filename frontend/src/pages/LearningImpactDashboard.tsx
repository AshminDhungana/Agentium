import { useState, useEffect } from 'react';
import { 
  Sparkles, TrendingUp, AlertTriangle, Cpu, RefreshCw, 
  CheckCircle, Wrench, Search, ClipboardCheck, AlertCircle 
} from 'lucide-react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { showToast } from '@/hooks/useToast';
import { improvementsApi } from '@/services/improvements';
import { useAuthStore } from '@/store/authStore';

interface ImpactStats {
  success_rate_delta: number;
  tools_generated: number;
  anti_patterns_warned: number;
  total_reviews_processed?: number;
  history: Array<{ date: string; success_rate: number }>;
}

interface Pattern {
  id: string;
  type: string;
  content: string;
  confidence: number;
}

export function LearningImpactDashboard() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<ImpactStats | null>(null);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [isDark, setIsDark] = useState(() => 
    typeof document !== 'undefined' ? document.documentElement.classList.contains('dark') : false
  );

  const canConsolidate = Boolean(
    user?.is_admin ||
    user?.is_sovereign ||
    user?.isSovereign ||
    user?.role === 'admin' ||
    user?.role === 'primary_sovereign' ||
    user?.role === 'deputy_sovereign'
  );

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [dataStats, dataPatterns] = await Promise.all([
        improvementsApi.getImpactStats(),
        improvementsApi.getPatterns(),
      ]);
      setStats(dataStats);
      setPatterns(dataPatterns.patterns || []);
    } catch (err: any) {
      console.error('Failed to fetch learning impact data', err);
      const msg = err?.message || 'Failed to load learning impact data';
      setError(msg);
      showToast.error('Failed to load learning impact data');
    } finally {
      setLoading(false);
    }
  };

  const manuallyConsolidate = async () => {
    if (!canConsolidate) {
      showToast.error('Admin permissions required to trigger consolidation.');
      return;
    }
    setTriggering(true);
    try {
      await improvementsApi.triggerConsolidation();
      showToast.success('Manual knowledge consolidation triggered successfully!');
      await fetchData();
    } catch (e: any) {
      console.error(e);
      showToast.error('Error triggering consolidation.');
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64 text-gray-600 dark:text-gray-400">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Error Banner */}
      {error && !stats && (
        <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl flex items-center justify-between text-red-700 dark:text-red-400">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <p className="text-sm font-medium">{error}</p>
          </div>
          <button
            onClick={fetchData}
            className="px-3 py-1.5 text-xs font-semibold bg-red-100 hover:bg-red-200 dark:bg-red-900/50 dark:hover:bg-red-900 text-red-800 dark:text-red-200 rounded-lg transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Header section with actions */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-600" />
            Continuous Self-Improvement Engine
          </h2>
          <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
            Real-time learning metrics, anti-pattern detection, and knowledge consolidation.
          </p>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <button 
            onClick={fetchData}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 border border-gray-200 dark:border-[#1e2535] rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button 
            onClick={manuallyConsolidate}
            disabled={triggering || !canConsolidate}
            title={!canConsolidate ? 'Admin or Sovereign role required' : 'Trigger autonomous learning review and knowledge extraction'}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Cpu className="w-4 h-4" />
            {triggering ? 'Consolidating...' : 'Trigger Consolidation'}
          </button>
        </div>
      </div>

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-green-100 dark:bg-green-500/10 rounded-lg">
            <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Success Rate Delta (7d)</p>
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
            <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Auto-Generated Tools</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {stats?.tools_generated ?? 0}
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-red-100 dark:bg-red-500/10 rounded-lg">
            <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Anti-Patterns Prevented</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {stats?.anti_patterns_warned ?? 0}
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm flex items-start gap-4">
          <div className="p-3 bg-blue-100 dark:bg-blue-500/10 rounded-lg">
            <ClipboardCheck className="w-6 h-6 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">Total Reviews Processed</p>
            <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
              {stats?.total_reviews_processed ?? 0}
            </div>
          </div>
        </div>
      </div>

      {/* Success Rate Trend Chart */}
      <div className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-purple-600" />
          Success Rate Trend (7-Day History)
        </h3>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart 
              data={stats?.history || []} 
              margin={{ top: 10, right: 20, bottom: 5, left: -10 }}
            >
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
              <XAxis 
                dataKey="date" 
                stroke={isDark ? '#9ca3af' : '#6b7280'} 
                fontSize={12}
                tickFormatter={(val) => {
                  try {
                    const parts = val.split('-');
                    return parts.length >= 3 ? `${parts[1]}/${parts[2]}` : val;
                  } catch {
                    return val;
                  }
                }}
              />
              <YAxis 
                stroke={isDark ? '#9ca3af' : '#6b7280'} 
                fontSize={12}
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: isDark ? '#1f2937' : '#ffffff',
                  borderColor: isDark ? '#374151' : '#e5e7eb',
                  color: isDark ? '#f9fafb' : '#111827',
                  borderRadius: '0.5rem',
                  boxShadow: isDark
                    ? '0 4px 6px rgba(0,0,0,0.4)'
                    : '0 4px 6px rgba(0,0,0,0.08)',
                }}
                formatter={(value: any) => [`${value}%`, 'Success Rate']}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <Line 
                type="monotone" 
                dataKey="success_rate" 
                stroke="#8b5cf6" 
                strokeWidth={3} 
                dot={{ r: 4, fill: '#8b5cf6' }}
                activeDot={{ r: 7 }} 
                name="Success Rate"
              />
            </LineChart>
          </ResponsiveContainer>
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
                <CheckCircle className="w-5 h-5 text-green-700 dark:text-green-400 shrink-0 mt-0.5" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
                    p.type === 'best_practice' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                  }`}>
                    {p.type === 'best_practice' ? 'BEST PRACTICE' : 'ANTI-PATTERN'}
                  </span>
                  <span className="text-xs text-gray-600 dark:text-gray-400 font-mono">ID: {p.id}</span>
                </div>
                <p className="text-gray-900 dark:text-white text-sm">
                  {p.content}
                </p>
              </div>
              <div className="text-right">
                <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Confidence</div>
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
