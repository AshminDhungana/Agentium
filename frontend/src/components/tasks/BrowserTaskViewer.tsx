import React, { useEffect, useState, useRef } from 'react';
import { useWebSocketStore } from '../../store/websocketStore';
import { browserApi, BrowserFrameResponse } from '../../services/browserApi';
import { Monitor, RefreshCw, AlertCircle, X, Maximize2, Minimize2, Video, Pause, Play } from 'lucide-react';

export interface BrowserTaskViewerProps {
    taskId: string;
    onClose?: () => void;
    mode?: 'tab' | 'modal';
}

export const BrowserTaskViewer: React.FC<BrowserTaskViewerProps> = ({ taskId, onClose, mode = 'modal' }) => {
    const lastMessage = useWebSocketStore(s => s.lastMessage);
    const [latestFrame, setLatestFrame] = useState<BrowserFrameResponse | null>(null);
    const [status, setStatus] = useState<'connecting' | 'live' | 'paused' | 'disconnected'>('connecting');
    const [isFullscreen, setIsFullscreen] = useState(false);
    
    // Fallback polling generic ref
    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Process websocket messages
    useEffect(() => {
        if (lastMessage?.type === 'browser_frame' && (lastMessage as any).task_id === taskId) {
            setLatestFrame(lastMessage as unknown as BrowserFrameResponse);
            setStatus('live');
        }
    }, [lastMessage, taskId]);

    // Handle initial state and fallback stream
    useEffect(() => {
        let mounted = true;
        
        const fetchInitialStream = async () => {
            try {
                const res = await browserApi.getSessionStream(taskId);
                if (mounted) {
                    setLatestFrame(res);
                    setStatus(res.status === 'paused' ? 'paused' : 'connecting'); 
                }
            } catch (e) {
                console.error("No active stream found", e);
                if (mounted) setStatus('disconnected');
            }
        };

        fetchInitialStream();

        // Polling fallback every 5s just in case WebSocket disconnects
        pollingIntervalRef.current = setInterval(async () => {
            if (status !== 'live' && status !== 'disconnected') {
               try {
                   const res = await browserApi.getSessionStream(taskId);
                   if (mounted) {
                       setLatestFrame(res);
                   }
               } catch (e) {
                   if (mounted) setStatus('disconnected');
               }
            }
        }, 5000);

        return () => {
            mounted = false;
            if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);
        };
    }, [taskId, status]);

    const handleTogglePause = async () => {
        const isPaused = status === 'paused';
        try {
            await browserApi.configureSession(taskId, { paused: !isPaused });
            setStatus(isPaused ? 'live' : 'paused');
        } catch (e) {
            console.error("Failed to toggle pause", e);
        }
    };

    const containerClasses = mode === 'modal' 
        ? "fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        : "h-auto border border-gray-200 dark:border-[#1e2535] rounded-xl overflow-hidden bg-white dark:bg-[#161b27] flex flex-col mt-4";

    const contentClasses = mode === 'modal'
        ? `bg-white dark:bg-[#161b27] rounded-xl overflow-hidden shadow-2xl flex flex-col border border-gray-200 dark:border-[#2a3347]
           ${isFullscreen ? 'w-full h-full' : 'max-w-6xl w-full max-h-[90vh]'}`
        : "flex-1 flex flex-col";

    if (status === 'disconnected') {
        return (
            <div className={containerClasses}>
                <div className={contentClasses}>
                    <div className="flex flex-col items-center justify-center p-12 h-64">
                        <Monitor className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Stream Disconnected</h3>
                        <p className="text-sm text-gray-500 max-w-sm text-center mt-2">
                           The browser stream for this task is no longer active, or the task has completed.
                        </p>
                        {mode === 'modal' && onClose && (
                            <button onClick={onClose} className="mt-6 px-4 py-2 border border-gray-200 dark:border-[#2a3347] rounded-lg text-sm bg-gray-50 dark:bg-[#0f1117] hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-700 dark:text-gray-200">
                                Close Viewer
                            </button>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className={containerClasses}>
            <div className={contentClasses}>
                
                {/* Header / Title Bar */}
                <div className="flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-[#0f1117] border-b border-gray-200 dark:border-[#1e2535]">
                    <div className="flex items-center gap-3 w-3/4">
                        <Monitor className="w-5 h-5 text-violet-500" />
                        <div className="flex-1 min-w-0">
                            <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                                {latestFrame?.title || 'Browser Session'}
                            </h3>
                            <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px] text-gray-400 font-mono truncate max-w-md">
                                    {latestFrame?.url || 'Waiting for URL...'}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] uppercase font-bold tracking-wide
                            ${status === 'live' ? 'bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-400' : 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-400'}`}>
                            {status === 'live' && <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />}
                            {status === 'live' ? 'LIVE' : status === 'paused' ? 'PAUSED' : 'CONNECTING...'}
                        </div>
                        
                        <button onClick={handleTogglePause} className="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-500 dark:text-gray-400 transition-colors">
                            {status === 'paused' ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                        </button>

                        {mode === 'modal' && (
                            <>
                                <button onClick={() => setIsFullscreen(!isFullscreen)} className="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-500 dark:text-gray-400 transition-colors">
                                    {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                                </button>
                                {onClose && (
                                    <button onClick={onClose} className="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-500 dark:text-gray-400 transition-colors ml-1">
                                        <X className="w-4 h-4" />
                                    </button>
                                )}
                            </>
                        )}
                    </div>
                </div>

                {/* Main Content Area */}
                <div className={`flex flex-col md:flex-row flex-1 overflow-hidden ${mode === 'modal' ? 'min-h-[500px]' : 'min-h-[400px]'}`}>
                    
                    {/* Viewport (Image) */}
                    <div className="flex-1 bg-black overflow-hidden relative flex items-center justify-center">
                        {status === 'connecting' && !latestFrame?.frame ? (
                             <div className="flex flex-col items-center gap-3">
                                <RefreshCw className="w-6 h-6 animate-spin text-gray-500" />
                                <span className="text-xs text-gray-500">Connecting to browser stream...</span>
                             </div>
                        ) : latestFrame?.frame ? (
                            <img 
                                src={`data:image/jpeg;base64,${latestFrame.frame}`} 
                                alt="Live Browser View"
                                className="object-contain max-w-full max-h-full"
                                style={{ transition: 'opacity 0.1s ease-in-out' }} 
                            />
                        ) : (
                             <div className="text-gray-500 text-sm flex items-center gap-2">
                                <AlertCircle className="w-4 h-4" />
                                No frame data available
                             </div>
                        )}
                        
                        {/* Stream Stats Overlay */}
                        <div className="absolute top-2 right-2 px-2 py-1 bg-black/60 backdrop-blur-sm rounded text-[10px] text-white font-mono flex items-center gap-2">
                             <Video className="w-3 h-3" />
                             <span>Frame {(latestFrame as any)?.frame_number || 0}</span>
                        </div>
                    </div>

                    {/* Action Log Sidebar */}
                    <div className="w-full md:w-64 lg:w-80 bg-gray-50 dark:bg-[#0f1117] border-l border-t md:border-t-0 border-gray-200 dark:border-[#1e2535] flex flex-col font-mono text-xs overflow-hidden">
                        <div className="px-3 py-2 bg-gray-100 dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 font-semibold uppercase tracking-wider text-[10px]">
                            Action Log
                        </div>
                        <div className="flex-1 overflow-y-auto p-3 space-y-3">
                            {(!latestFrame?.action_log || latestFrame.action_log.length === 0) ? (
                                <p className="text-gray-400 italic text-center text-[11px] mt-4 font-sans">
                                    Waiting for actions...
                                    <br/><br/>
                                    Browser interactions performed by the agent will appear here.
                                </p>
                            ) : (
                                [...latestFrame.action_log].reverse().map((entry, i) => (
                                    <div key={i} className="flex flex-col border-l-2 border-violet-400 dark:border-violet-500 pl-2">
                                        <span className="text-[9px] text-gray-400 mb-0.5">
                                            {new Date(entry.timestamp).toLocaleTimeString()}
                                        </span>
                                        <span className="text-gray-800 dark:text-gray-300 leading-snug break-words">
                                            {entry.action}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
};
