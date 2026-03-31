import React, { useEffect, useState } from 'react';
import { Monitor, RefreshCw } from 'lucide-react';
import { browserApi, BrowserSessionInfo } from '../../services/browserApi';
import { Task } from '../../types';

interface BrowserSessionsListProps {
    tasks: Task[];
    onSelectTask: (taskId: string) => void;
}

export const BrowserSessionsList: React.FC<BrowserSessionsListProps> = ({ tasks, onSelectTask }) => {
    const [sessions, setSessions] = useState<BrowserSessionInfo[]>([]);
    const [loading, setLoading] = useState(true);

    const loadSessions = async () => {
        setLoading(true);
        try {
            const res = await browserApi.getSessions();
            setSessions(res.sessions || []);
        } catch (err) {
            console.error('Failed to load browser sessions:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadSessions();
        const interval = setInterval(loadSessions, 10000); // refresh every 10s
        return () => clearInterval(interval);
    }, []);

    if (loading && sessions.length === 0) {
        return (
            <div className="flex justify-center p-8">
                <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
        );
    }

    if (sessions.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center p-12 bg-white dark:bg-[#161b27] rounded-xl border border-dashed border-gray-200 dark:border-[#2a3347]">
                <Monitor className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">No Active Browser Sessions</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center max-w-sm">
                    There are no agents currently interacting with a web browser. Launch a browser-based task to see live streams here.
                </p>
                <button 
                    onClick={loadSessions}
                    className="mt-6 px-4 py-2 bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400 text-xs font-semibold rounded-lg"
                >
                    Refresh List
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Active Browser Sessions</h3>
                <button 
                    onClick={loadSessions}
                    className="p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sessions.map(session => {
                    const task = tasks.find(t => t.id === session.task_id);
                    const taskName = task?.title || `Task ${session.task_id.substring(0, 8)}...`;
                    
                    return (
                        <div 
                            key={session.task_id}
                            onClick={() => onSelectTask(session.task_id)}
                            className="bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl p-4 cursor-pointer hover:border-blue-400 dark:hover:border-blue-500 transition-colors group"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <Monitor className="w-5 h-5 text-violet-500" />
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide
                                    ${session.status === 'active' ? 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400'}`}>
                                    {session.status}
                                </span>
                            </div>
                            <h4 className="text-sm font-semibold text-gray-900 dark:text-white line-clamp-1 mb-1">
                                {taskName}
                            </h4>
                            <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1 mb-3 font-mono">
                                {session.url || 'No URL loaded'}
                            </p>
                            <div className="flex justify-between items-center text-[10px] text-gray-400 dark:text-gray-500">
                                <span>{session.fps} FPS Capture</span>
                                <span>
                                    {session.started_at ? new Date(session.started_at).toLocaleTimeString() : ''}
                                </span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
