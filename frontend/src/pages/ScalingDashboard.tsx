import React, { useEffect, useState } from 'react';
import { api } from '@/services/api';
import { 
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { 
    Activity, Cpu, Zap, Settings, TrendingUp, AlertCircle, PlayCircle, StopCircle 
} from 'lucide-react';
import { showToast } from '@/hooks/useToast';
import { useAuthStore } from '@/store/authStore';
import { EmptyState } from '@/components/ui/EmptyState';
import { History } from 'lucide-react';

// WebSocket subscription placeholder, relying on polling instead
// import { useWebSocket } from '@/contexts/WebSocketContext';

interface Predictions {
    next_1h: number;
    next_6h: number;
    next_24h: number;
    current_capacity: number;
    recommendation: string;
}

interface ScalingEvent {
    id: string;
    action: string;
    description: string;
    created_at: string;
    status: string;
    level: string;
}

export const ScalingDashboard: React.FC = () => {
    const { user } = useAuthStore();
    const isAdmin = user?.role === 'admin' || user?.role === 'primary_sovereign';

    // Detect dark mode for chart tooltip theming
    const [isDark, setIsDark] = useState(
        typeof window !== 'undefined' && document.documentElement.classList.contains('dark')
    );
    useEffect(() => {
        const observer = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'));
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, []);
    
    const [predictions, setPredictions] = useState<Predictions | null>(null);
    const [history, setHistory] = useState<ScalingEvent[]>([]);
    
    // For manual override
    const [overrideCount, setOverrideCount] = useState(1);
    const [overrideTier, setOverrideTier] = useState(3);
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const fetchData = async () => {
        try {
            const [predRes, histRes] = await Promise.all([
                api.get('/api/v1/scaling/predictions/load'),
                api.get('/api/v1/scaling/history')
            ]);
            setPredictions(predRes.data);
            setHistory(histRes.data.history || []);
        } catch (error) {
            console.error('Failed to fetch scaling data', error);
        }
    };

    const handleOverride = async (action: 'spawn' | 'liquidate') => {
        if (!isAdmin) {
            showToast.error("Admin permissions required.");
            return;
        }
        setIsSubmitting(true);
        try {
            await api.post('/api/v1/scaling/override', {
                action,
                count: overrideCount,
                tier: overrideTier
            });
            showToast.success(`Manual ${action} initiated successfully.`);
            fetchData();
        } catch (error) {
            showToast.error(`Failed to execute ${action} override`);
        } finally {
            setIsSubmitting(false);
        }
    };

    const chartData = predictions ? [
        { time: 'Now', capacity: predictions.current_capacity, predicted: predictions.current_capacity },
        { time: '+1h', capacity: null, predicted: predictions.next_1h },
        { time: '+6h', capacity: null, predicted: predictions.next_6h },
        { time: '+24h', capacity: null, predicted: predictions.next_24h },
    ] : [];

    // Mock Budget Gauge properties
    const BUDGET_LIMIT = 10.00;
    // We would fetch actual token spend, but mock for display if not available from prediction endpoints directly right now.
    // In actual implementation, we'd query the Token Optimizer status via another endpoint.
    const tokenSpend = 0.00; // placeholder
    const budgetPercentage = Math.min((tokenSpend / BUDGET_LIMIT) * 100, 100);

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        <TrendingUp className="text-blue-500" />
                        Predictive Auto-Scaling
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">
                        AI-driven capacity planning and proactive agent orchestration.
                    </p>
                </div>
                {predictions && predictions.recommendation !== 'neutral' && (
                    <div className="px-4 py-2 rounded-full text-sm font-medium border flex items-center gap-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800">
                        <AlertCircle className="w-4 h-4" />
                        System Recommendation: {predictions.recommendation.toUpperCase()}
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-4 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/50 rounded-lg">
                            <Cpu className="text-blue-600 dark:text-blue-400 w-5 h-5" />
                        </div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Active Agents</span>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">
                        {predictions?.current_capacity ?? '-'}
                    </div>
                </div>

                <div className="p-4 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="p-2 bg-purple-100 dark:bg-purple-900/50 rounded-lg">
                            <Activity className="text-purple-600 dark:text-purple-400 w-5 h-5" />
                        </div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Predicted (1h)</span>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">
                        {predictions?.next_1h ?? '-'}
                    </div>
                </div>

                <div className="p-4 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="p-2 bg-yellow-100 dark:bg-yellow-900/50 rounded-lg">
                            <Zap className="text-yellow-600 dark:text-yellow-400 w-5 h-5" />
                        </div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Token Budget</span>
                    </div>
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">
                        ${tokenSpend.toFixed(2)}
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-[#1e2535] rounded-full h-1.5 mt-2">
                        <div 
                            className={`h-1.5 rounded-full ${budgetPercentage > 80 ? 'bg-red-500' : 'bg-green-500'}`} 
                            style={{ width: `${budgetPercentage}%` }}
                        ></div>
                    </div>
                </div>

                <div className="p-4 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="p-2 bg-green-100 dark:bg-green-900/50 rounded-lg">
                            <Settings className="text-green-600 dark:text-green-400 w-5 h-5" />
                        </div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">System Mode</span>
                    </div>
                    <div className="text-xl font-bold text-green-500 mt-1">
                        Auto-Scaling Active
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Chart */}
                <div className="lg:col-span-2 p-6 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <h2 className="text-lg font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
                        Load Prediction Forward-Look
                    </h2>
                    <div className="h-72 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                                <XAxis dataKey="time" stroke="#888888" />
                                <YAxis stroke="#888888" />
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
                                />
                                <Line 
                                    type="monotone" 
                                    dataKey="predicted" 
                                    stroke="#8b5cf6" 
                                    strokeWidth={3} 
                                    name="Predicted Need"
                                    activeDot={{ r: 8 }} 
                                />
                                <Line 
                                    type="monotone" 
                                    dataKey="capacity" 
                                    stroke="#10b981" 
                                    strokeWidth={3} 
                                    name="Actual Capacity"
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Manual Override Panel */}
                <div className="p-6 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                    <h2 className="text-lg font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
                        Manual Override
                    </h2>
                    {!isAdmin ? (
                        <div className="text-gray-500 dark:text-gray-400 text-sm">
                            You must be an Administrator or Sovereign to use manual overrides.
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Agent Count
                                </label>
                                <input 
                                    type="number" 
                                    min="1" 
                                    max="20"
                                    value={overrideCount}
                                    onChange={(e) => setOverrideCount(Number(e.target.value))}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-300 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500/40 text-gray-900 dark:text-white transition-colors duration-200 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Agent Tier Target
                                </label>
                                <select 
                                    value={overrideTier}
                                    onChange={(e) => setOverrideTier(Number(e.target.value))}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-300 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-blue-500/40 text-gray-900 dark:text-white transition-colors duration-200 focus:outline-none"
                                >
                                    <option value={1}>Tier 1 (Critical)</option>
                                    <option value={2}>Tier 2 (High)</option>
                                    <option value={3}>Tier 3 (Standard)</option>
                                </select>
                            </div>
                            
                            <div className="pt-4 grid grid-cols-2 gap-3 border-t border-gray-100 dark:border-[#1e2535]">
                                <button
                                    onClick={() => handleOverride('spawn')}
                                    disabled={isSubmitting}
                                    className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50"
                                >
                                    <PlayCircle size={16} /> Spawn
                                </button>
                                <button
                                    onClick={() => handleOverride('liquidate')}
                                    disabled={isSubmitting}
                                    className="flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                                >
                                    <StopCircle size={16} /> Liquidate
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* History Timeline */}
            <div className="p-6 bg-white dark:bg-[#161b27] rounded-xl shadow-sm border border-gray-100 dark:border-[#1e2535] transition-colors duration-200">
                <h2 className="text-lg font-bold mb-4 text-gray-900 dark:text-white flex items-center gap-2">
                    Scaling Activity Log
                </h2>
                {history.length === 0 ? (
                    <EmptyState
                        icon={History}
                        title="No scaling history"
                        description="No recent scaling events recorded."
                    />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-gray-500 uppercase bg-gray-50 dark:bg-[#0f1117]/50 dark:text-gray-400">
                                <tr>
                                    <th className="px-4 py-3 rounded-tl-lg">Time</th>
                                    <th className="px-4 py-3">Action</th>
                                    <th className="px-4 py-3">Description</th>
                                    <th className="px-4 py-3 rounded-tr-lg">Level</th>
                                </tr>
                            </thead>
                            <tbody>
                                {history.map((event, i) => (
                                    <tr key={i} className="border-b border-gray-100 dark:border-[#1e2535] last:border-0 hover:bg-gray-50 dark:hover:bg-[#1e2535]/50 transition-colors">
                                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                                            {new Date(event.created_at).toLocaleString()}
                                        </td>
                                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                            {event.action}
                                        </td>
                                        <td className="px-4 py-3 text-gray-700 dark:text-gray-300">
                                            {event.description}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                                                event.level?.toLowerCase() === 'info' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' :
                                                event.level?.toLowerCase() === 'warning' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300' :
                                                'bg-gray-100 text-gray-800 dark:bg-[#1e2535] dark:text-gray-300'
                                            }`}>
                                                {event.level?.toUpperCase() || 'INFO'}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};