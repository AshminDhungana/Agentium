import React, { useEffect, useState } from 'react';
import { monitoringService} from '../services/monitoring';
import { MonitoringDashboard, ViolationReport, AgentHealthReport} from '../types';
import { Activity, ShieldCheck, AlertTriangle, Loader2, TrendingUp } from 'lucide-react';

export const MonitoringPage: React.FC = () => {
    const [dashboard, setDashboard] = useState<MonitoringDashboard | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        loadDashboard();
    }, []);

    const loadDashboard = async () => {
        try {
            setIsLoading(true);
            setError(null);
            
            const data = await monitoringService.getDashboard('00001');
            setDashboard(data);
        } catch (err: any) {
            console.error('Monitoring error:', err);
            setError(err.response?.data?.detail || 'Monitoring endpoint not available');
            
            setDashboard({
                system_health: 100,
                active_alerts: 0,
                agent_health_breakdown: {},
                latest_health_reports: [],
                recent_violations: []
            });
        } finally {
            setIsLoading(false);
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">Loading metrics...</span>
                </div>
            </div>
        );
    }

    const systemHealth = dashboard?.system_health ?? 100;
    const activeAlerts = dashboard?.active_alerts || 0;
    const healthReports = dashboard?.latest_health_reports || [];
    const violations = dashboard?.recent_violations || [];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-6 transition-colors duration-200">
            <div className="max-w-7xl mx-auto">

                {/* Header */}
                <div className="mb-8">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center shadow-lg">
                            <Activity className="w-7 h-7 text-white" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                                System Monitoring
                            </h1>
                            <p className="text-gray-500 dark:text-gray-400 text-sm">
                                Real-time oversight of agent operations
                            </p>
                        </div>
                    </div>
                </div>

                {/* Error Notice */}
                {error && (
                    <div className="mb-6 bg-yellow-50 dark:bg-yellow-950/40 border border-yellow-200 dark:border-yellow-800/60 rounded-lg p-4">
                        <div className="flex gap-3">
                            <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <h3 className="text-sm font-semibold text-yellow-900 dark:text-yellow-300 mb-1">
                                    Monitoring System Notice
                                </h3>
                                <p className="text-sm text-yellow-800 dark:text-yellow-400">
                                    {error}. Displaying default values.
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {/* Stats Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">

                    {/* System Health Card */}
                    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">System Health</p>
                                <p className={`text-3xl font-bold ${
                                    systemHealth > 90
                                        ? 'text-green-600 dark:text-green-400'
                                        : 'text-yellow-600 dark:text-yellow-400'
                                }`}>
                                    {systemHealth}%
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    {systemHealth > 90 ? 'Operational' : 'Degraded'}
                                </p>
                            </div>
                            <div className="w-12 h-12 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                                <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400" />
                            </div>
                        </div>
                    </div>

                    {/* Active Alerts Card */}
                    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Active Alerts</p>
                                <p className="text-3xl font-bold text-gray-900 dark:text-white">
                                    {activeAlerts}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    No issues detected
                                </p>
                            </div>
                            <div className="w-12 h-12 rounded-lg bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                                <Activity className="w-6 h-6 text-red-600 dark:text-red-400" />
                            </div>
                        </div>
                    </div>

                    {/* Monitored Agents Card */}
                    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Monitored Agents</p>
                                <p className="text-3xl font-bold text-gray-900 dark:text-white">
                                    {healthReports.length}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    All systems normal
                                </p>
                            </div>
                            <div className="w-12 h-12 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                                <ShieldCheck className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Bottom panels */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                    {/* Recent Violations */}
                    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                        {/* Panel header - visually distinct from card body */}
                        <div className="bg-yellow-50 dark:bg-yellow-950/50 border-b border-yellow-100 dark:border-yellow-900/60 px-6 py-4">
                            <h2 className="text-lg font-bold text-gray-900 dark:text-yellow-100 flex items-center gap-2">
                                <AlertTriangle className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                                Recent Violations
                            </h2>
                        </div>

                        {/* Panel body - diagram/list area with its own distinct background */}
                        <div className="p-6 bg-white dark:bg-gray-900">
                            {violations.length > 0 ? (
                                <div className="space-y-4">
                                    {violations.map((v: ViolationReport) => (
                                        <div
                                            key={v.id}
                                            className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700"
                                        >
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                                                            v.severity === 'critical' || v.severity === 'major'
                                                                ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                                                                : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'
                                                        }`}>
                                                            {v.severity}
                                                        </span>
                                                    </div>
                                                    <p className="text-sm text-gray-900 dark:text-gray-100">
                                                        {v.description}
                                                    </p>
                                                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                                        {v.created_at ? new Date(v.created_at).toLocaleString() : '—'}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-12">
                                    {/* Empty state diagram area */}
                                    <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mx-auto mb-4 border border-gray-200 dark:border-gray-700">
                                        <ShieldCheck className="w-8 h-8 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Violations Detected
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        All agents operating within guidelines
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Agent Health Reports */}
                    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
                        {/* Panel header - visually distinct */}
                        <div className="bg-blue-50 dark:bg-blue-950/50 border-b border-blue-100 dark:border-blue-900/60 px-6 py-4">
                            <h2 className="text-lg font-bold text-gray-900 dark:text-blue-100 flex items-center gap-2">
                                <Activity className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                Agent Health Reports
                            </h2>
                        </div>

                        {/* Panel body - diagram/list area */}
                        <div className="p-6 bg-white dark:bg-gray-900">
                            {healthReports.length > 0 ? (
                                <div className="space-y-3">
                                    {healthReports.map((report: AgentHealthReport) => (
                                        <div
                                            key={report.id}
                                            className="flex items-center justify-between bg-gray-50 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700"
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                                                    report.health_score > 90
                                                        ? 'bg-green-100 dark:bg-green-900/40'
                                                        : 'bg-yellow-100 dark:bg-yellow-900/40'
                                                }`}>
                                                    <span className={`text-sm font-bold ${
                                                        report.health_score > 90
                                                            ? 'text-green-700 dark:text-green-300'
                                                            : 'text-yellow-700 dark:text-yellow-300'
                                                    }`}>
                                                        {report.health_score}
                                                    </span>
                                                </div>
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                                                        Agent #{report.subject}
                                                    </p>
                                                    <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                                                        {report.status}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-xs text-gray-500 dark:text-gray-400">Success Rate</div>
                                                <div className="text-sm font-bold text-green-600 dark:text-green-400">
                                                    {report.metrics.success_rate}%
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-center py-12">
                                    {/* Empty state diagram area */}
                                    <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center mx-auto mb-4 border border-gray-200 dark:border-gray-700">
                                        <Activity className="w-8 h-8 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Health Reports
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Agent monitoring will appear here
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
};
