import React, { useState, useEffect, useCallback } from 'react';
import {
    Terminal,
    Activity,
    Container,
    FileText,
    Shield,
    AlertTriangle,
    Play,
    Square,
    RotateCcw,
    Trash2,
    Eye,
    Lock,
    Unlock,
    Cpu,
    HardDrive,
    Network,
    Server
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { hostAccessApi } from '../services/hostAccessApi';
import type {
    HostSystemStatus,
    ContainerInfo,
    HostCommand,
    AuditLog,
    SovereignCommand
} from '../types/hostAccess';

export const SovereignDashboard: React.FC = () => {
    const [systemStatus, setSystemStatus] = useState<HostSystemStatus | null>(null);
    const [containers, setContainers] = useState<ContainerInfo[]>([]);
    const [commands, setCommands] = useState<HostCommand[]>([]);
    const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
    const [selectedTab, setSelectedTab] = useState<'overview' | 'containers' | 'commands' | 'files' | 'logs'>('overview');
    const [isLoading, setIsLoading] = useState(true);
    const [sovereignCommand, setSovereignCommand] = useState('');
    const [commandOutput, setCommandOutput] = useState<string>('');

    // Real-time updates
    useEffect(() => {
        const fetchData = async () => {
            try {
                const [status, conts, cmds, logs] = await Promise.all([
                    hostAccessApi.getSystemStatus(),
                    hostAccessApi.getContainers(),
                    hostAccessApi.getCommandHistory(20),
                    hostAccessApi.getAuditLogs({ limit: 50 })
                ]);
                setSystemStatus(status);
                setContainers(conts);
                setCommands(cmds);
                setAuditLogs(logs);
            } catch (error) {
                console.error('Failed to fetch data:', error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds

        return () => clearInterval(interval);
    }, []);

    // WebSocket for real-time logs
    useEffect(() => {
        const cleanup = hostAccessApi.streamLogs((log) => {
            setAuditLogs(prev => [log, ...prev].slice(0, 100));
        });
        return cleanup;
    }, []);

    const executeSovereignCommand = async () => {
        if (!sovereignCommand.trim()) return;

        setCommandOutput('Executing...\n');
        try {
            const result = await hostAccessApi.executeSovereignCommand({
                command: sovereignCommand,
                target: 'head_of_council',
                params: { command: sovereignCommand.split(' ') },
                requireApproval: false,
                timeout: 300
            });

            setCommandOutput(prev => prev + `\n$ ${sovereignCommand}\n`);
            if (result.result?.stdout) {
                setCommandOutput(prev => prev + result.result.stdout);
            }
            if (result.result?.stderr) {
                setCommandOutput(prev => prev + '\n[stderr] ' + result.result.stderr);
            }
        } catch (error) {
            setCommandOutput(prev => prev + `\nError: ${error}`);
        }
    };

    const getAgentColor = (agentType: string) => {
        switch (agentType) {
            case 'head_of_council': return 'text-red-500 bg-red-500/10';
            case 'council_member': return 'text-purple-500 bg-purple-500/10';
            case 'lead_agent': return 'text-blue-500 bg-blue-500/10';
            case 'task_agent': return 'text-green-500 bg-green-500/10';
            default: return 'text-gray-500 bg-gray-500/10';
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-900 flex items-center justify-center">
                <Activity className="w-8 h-8 animate-spin text-blue-500" />
                <span className="ml-2 text-white">Initializing Sovereign Dashboard...</span>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-900 text-white">
            {/* Header */}
            <header className="bg-gray-800 border-b border-gray-700 px-6 py-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <Shield className="w-8 h-8 text-yellow-500" />
                        <div>
                            <h1 className="text-2xl font-bold">Agentium Sovereign Dashboard</h1>
                            <p className="text-sm text-gray-400">Override Authority: Human-in-the-Loop Control</p>
                        </div>
                    </div>
                    <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2 text-sm">
                            <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                            <span className="text-green-400">Head of Council Active</span>
                        </div>
                        <button
                            className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-semibold flex items-center space-x-2"
                            onClick={() => hostAccessApi.blockAgent('00001', 'Sovereign emergency stop')}
                        >
                            <AlertTriangle className="w-4 h-4" />
                            <span>EMERGENCY STOP</span>
                        </button>
                    </div>
                </div>
            </header>

            {/* Navigation */}
            <nav className="bg-gray-800 border-b border-gray-700 px-6 py-2">
                <div className="flex space-x-1">
                    {[
                        { id: 'overview', label: 'System Overview', icon: Activity },
                        { id: 'containers', label: 'Agent Containers', icon: Container },
                        { id: 'commands', label: 'Command Terminal', icon: Terminal },
                        { id: 'files', label: 'File System', icon: FileText },
                        { id: 'logs', label: 'Audit Logs', icon: Eye },
                    ].map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setSelectedTab(id as any)}
                            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${selectedTab === id
                                    ? 'bg-blue-600 text-white'
                                    : 'text-gray-400 hover:text-white hover:bg-gray-700'
                                }`}
                        >
                            <Icon className="w-4 h-4" />
                            <span>{label}</span>
                        </button>
                    ))}
                </div>
            </nav>

            {/* Main Content */}
            <main className="p-6">
                {selectedTab === 'overview' && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {/* CPU Card */}
                        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold flex items-center">
                                    <Cpu className="w-5 h-5 mr-2 text-blue-500" />
                                    CPU Usage
                                </h3>
                                <span className="text-2xl font-bold text-blue-400">
                                    {systemStatus?.cpu.usage.toFixed(1)}%
                                </span>
                            </div>
                            <div className="h-32">
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={[{ time: '1', value: systemStatus?.cpu.usage || 0 }]}>
                                        <Line type="monotone" dataKey="value" stroke="#3B82F6" strokeWidth={2} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                            <p className="text-sm text-gray-400 mt-2">
                                {systemStatus?.cpu.cores} Cores • Load: {systemStatus?.cpu.load[0].toFixed(2)}
                            </p>
                        </div>

                        {/* Memory Card */}
                        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold flex items-center">
                                    <Server className="w-5 h-5 mr-2 text-green-500" />
                                    Memory
                                </h3>
                                <span className="text-2xl font-bold text-green-400">
                                    {systemStatus?.memory.percentage.toFixed(0)}%
                                </span>
                            </div>
                            <div className="space-y-2">
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-400">Used</span>
                                    <span>{(systemStatus?.memory.used || 0 / 1024 / 1024 / 1024).toFixed(1)} GB</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-400">Total</span>
                                    <span>{(systemStatus?.memory.total || 0 / 1024 / 1024 / 1024).toFixed(1)} GB</span>
                                </div>
                            </div>
                            <div className="mt-4 h-2 bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-green-500 transition-all"
                                    style={{ width: `${systemStatus?.memory.percentage || 0}%` }}
                                />
                            </div>
                        </div>

                        {/* Disk Card */}
                        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold flex items-center">
                                    <HardDrive className="w-5 h-5 mr-2 text-yellow-500" />
                                    Disk Usage
                                </h3>
                                <span className="text-2xl font-bold text-yellow-400">
                                    {systemStatus?.disk.percentage.toFixed(0)}%
                                </span>
                            </div>
                            <div className="space-y-2 text-sm">
                                {systemStatus?.disk.mounts.slice(0, 2).map((mount, idx) => (
                                    <div key={idx} className="flex justify-between">
                                        <span className="text-gray-400 truncate">{mount.mountpoint}</span>
                                        <span>{((mount.used / mount.total) * 100).toFixed(0)}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Network Card */}
                        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold flex items-center">
                                    <Network className="w-5 h-5 mr-2 text-purple-500" />
                                    Network
                                </h3>
                                <span className="text-sm text-purple-400">
                                    {systemStatus?.network.interfaces.filter(i => i.status === 'up').length} Active
                                </span>
                            </div>
                            <div className="space-y-2 text-sm">
                                {systemStatus?.network.interfaces.slice(0, 3).map((iface, idx) => (
                                    <div key={idx} className="flex justify-between items-center">
                                        <span className="text-gray-400">{iface.name}</span>
                                        <span className={`text-xs ${iface.status === 'up' ? 'text-green-400' : 'text-red-400'}`}>
                                            {iface.ip || 'No IP'}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Recent Commands */}
                        <div className="col-span-full bg-gray-800 rounded-lg p-6 border border-gray-700">
                            <h3 className="text-lg font-semibold mb-4">Recent Agent Activity</h3>
                            <div className="space-y-2 max-h-64 overflow-y-auto">
                                {commands.slice(0, 10).map((cmd) => (
                                    <div key={cmd.id} className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
                                        <div className="flex items-center space-x-3">
                                            <span className={`px-2 py-1 rounded text-xs font-medium ${getAgentColor(cmd.agentType)}`}>
                                                {cmd.agentiumId}
                                            </span>
                                            <span className="text-gray-300">{cmd.action}</span>
                                            <span className="text-gray-500 text-sm">{cmd.target}</span>
                                        </div>
                                        <div className="flex items-center space-x-2">
                                            <span className={`text-xs ${cmd.status === 'completed' ? 'text-green-400' :
                                                    cmd.status === 'failed' ? 'text-red-400' :
                                                        cmd.status === 'running' ? 'text-blue-400 animate-pulse' :
                                                            'text-yellow-400'
                                                }`}>
                                                {cmd.status}
                                            </span>
                                            <span className="text-xs text-gray-500">
                                                {new Date(cmd.requestedAt).toLocaleTimeString()}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {selectedTab === 'containers' && (
                    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-700">
                            <h2 className="text-xl font-semibold">Agent Containers</h2>
                            <p className="text-sm text-gray-400">Manage AI agent containers running on host system</p>
                        </div>
                        <table className="w-full">
                            <thead className="bg-gray-900">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Agent ID</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Type</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Container</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Status</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-700">
                                {containers.map((container) => (
                                    <tr key={container.id} className="hover:bg-gray-750">
                                        <td className="px-6 py-4">
                                            <span className={`px-2 py-1 rounded text-xs font-medium ${getAgentColor(container.agentType || 'unknown')}`}>
                                                {container.agentiumId || 'N/A'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-sm capitalize">{container.agentType || 'Unknown'}</td>
                                        <td className="px-6 py-4 text-sm font-mono text-gray-400">{container.name}</td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${container.status === 'running' ? 'bg-green-100 text-green-800' :
                                                    container.status === 'exited' ? 'bg-red-100 text-red-800' :
                                                        'bg-yellow-100 text-yellow-800'
                                                }`}>
                                                {container.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex space-x-2">
                                                {container.status !== 'running' && (
                                                    <button
                                                        onClick={() => hostAccessApi.manageContainer(container.id, 'start')}
                                                        className="p-1 hover:bg-green-500/20 text-green-400 rounded"
                                                        title="Start"
                                                    >
                                                        <Play className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {container.status === 'running' && (
                                                    <button
                                                        onClick={() => hostAccessApi.manageContainer(container.id, 'stop')}
                                                        className="p-1 hover:bg-red-500/20 text-red-400 rounded"
                                                        title="Stop"
                                                    >
                                                        <Square className="w-4 h-4" />
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => hostAccessApi.manageContainer(container.id, 'restart')}
                                                    className="p-1 hover:bg-blue-500/20 text-blue-400 rounded"
                                                    title="Restart"
                                                >
                                                    <RotateCcw className="w-4 h-4" />
                                                </button>
                                                <button
                                                    onClick={() => hostAccessApi.manageContainer(container.id, 'remove')}
                                                    className="p-1 hover:bg-red-500/20 text-red-400 rounded"
                                                    title="Remove"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {selectedTab === 'commands' && (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-250px)]">
                        <div className="bg-gray-800 rounded-lg border border-gray-700 flex flex-col">
                            <div className="px-6 py-4 border-b border-gray-700">
                                <h2 className="text-xl font-semibold">Sovereign Terminal</h2>
                                <p className="text-sm text-gray-400">Execute commands as root (bypasses Head of Council)</p>
                            </div>
                            <div className="flex-1 p-4 overflow-auto">
                                <pre className="font-mono text-sm text-green-400 whitespace-pre-wrap">
                                    {commandOutput || 'Ready for command...'}
                                </pre>
                            </div>
                            <div className="p-4 border-t border-gray-700">
                                <div className="flex space-x-2">
                                    <span className="text-green-500 font-mono py-2">root@agentium#</span>
                                    <input
                                        type="text"
                                        value={sovereignCommand}
                                        onChange={(e) => setSovereignCommand(e.target.value)}
                                        onKeyPress={(e) => e.key === 'Enter' && executeSovereignCommand()}
                                        className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-white font-mono focus:outline-none focus:border-blue-500"
                                        placeholder="Enter command..."
                                    />
                                    <button
                                        onClick={executeSovereignCommand}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium"
                                    >
                                        Execute
                                    </button>
                                </div>
                            </div>
                        </div>

                        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                            <div className="px-6 py-4 border-b border-gray-700">
                                <h2 className="text-xl font-semibold">Active Operations</h2>
                            </div>
                            <div className="p-4 space-y-3 overflow-auto max-h-full">
                                {commands.filter(c => c.status === 'running').map((cmd) => (
                                    <div key={cmd.id} className="p-4 bg-gray-900 rounded-lg border-l-4 border-blue-500">
                                        <div className="flex justify-between items-start mb-2">
                                            <span className={`px-2 py-1 rounded text-xs ${getAgentColor(cmd.agentType)}`}>
                                                {cmd.agentiumId}
                                            </span>
                                            <span className="text-xs text-blue-400 animate-pulse">RUNNING</span>
                                        </div>
                                        <p className="text-sm font-mono text-gray-300 mb-1">{cmd.action}</p>
                                        <p className="text-xs text-gray-500">{cmd.target}</p>
                                        <div className="mt-2 flex space-x-2">
                                            <button className="text-xs px-2 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30">
                                                Kill Process
                                            </button>
                                            <button className="text-xs px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded hover:bg-yellow-500/30">
                                                Review
                                            </button>
                                        </div>
                                    </div>
                                ))}
                                {commands.filter(c => c.status === 'running').length === 0 && (
                                    <p className="text-gray-500 text-center py-8">No active operations</p>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {selectedTab === 'files' && (
                    <FileSystemExplorer />
                )}

                {selectedTab === 'logs' && (
                    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-700 flex justify-between items-center">
                            <div>
                                <h2 className="text-xl font-semibold">Audit Logs</h2>
                                <p className="text-sm text-gray-400">Real-time security audit trail</p>
                            </div>
                            <div className="flex space-x-2">
                                <select className="bg-gray-900 border border-gray-600 rounded px-3 py-1 text-sm">
                                    <option>All Levels</option>
                                    <option>Info</option>
                                    <option>Warning</option>
                                    <option>Error</option>
                                    <option>Critical</option>
                                </select>
                                <button className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">
                                    Export
                                </button>
                            </div>
                        </div>
                        <div className="max-h-[calc(100vh-300px)] overflow-auto">
                            <table className="w-full">
                                <thead className="bg-gray-900 sticky top-0">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Time</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Agent</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Action</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Target</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Level</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase">Status</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-700">
                                    {auditLogs.map((log, idx) => (
                                        <tr key={idx} className="hover:bg-gray-750">
                                            <td className="px-6 py-4 text-sm text-gray-400">
                                                {new Date(log.timestamp).toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2 py-1 rounded text-xs ${getAgentColor(log.agentType)}`}>
                                                    {log.agentiumId}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-sm">{log.action}</td>
                                            <td className="px-6 py-4 text-sm text-gray-400 font-mono">{log.target}</td>
                                            <td className="px-6 py-4">
                                                <span className={`px-2 py-1 rounded text-xs ${log.level === 'critical' ? 'bg-red-500/20 text-red-400' :
                                                        log.level === 'error' ? 'bg-red-400/20 text-red-300' :
                                                            log.level === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                                                                'bg-blue-500/20 text-blue-400'
                                                    }`}>
                                                    {log.level}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4">
                                                {log.blocked ? (
                                                    <span className="flex items-center text-red-400 text-sm">
                                                        <Lock className="w-4 h-4 mr-1" />
                                                        Blocked
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center text-green-400 text-sm">
                                                        <Unlock className="w-4 h-4 mr-1" />
                                                        Allowed
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

// File System Explorer Component
const FileSystemExplorer: React.FC = () => {
    const [currentPath, setCurrentPath] = useState('/');
    const [files, setFiles] = useState<string[]>([]);
    const [fileContent, setFileContent] = useState<string>('');

    useEffect(() => {
        loadDirectory(currentPath);
    }, [currentPath]);

    const loadDirectory = async (path: string) => {
        try {
            const result = await hostAccessApi.listDirectory(path);
            setFiles(result.listing);
        } catch (error) {
            console.error('Failed to load directory:', error);
        }
    };

    const loadFile = async (path: string) => {
        try {
            const result = await hostAccessApi.readFile(path);
            setFileContent(result.content);
        } catch (error) {
            console.error('Failed to load file:', error);
        }
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-250px)]">
            <div className="lg:col-span-1 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden flex flex-col">
                <div className="px-4 py-3 border-b border-gray-700 bg-gray-900">
                    <div className="flex items-center space-x-2">
                        <button onClick={() => setCurrentPath('/')} className="text-blue-400 hover:text-blue-300">/</button>
                        <span className="text-gray-500">/</span>
                        <span className="text-sm text-gray-300 truncate">{currentPath}</span>
                    </div>
                </div>
                <div className="flex-1 overflow-auto p-2">
                    {files.map((file, idx) => (
                        <button
                            key={idx}
                            onClick={() => {
                                const newPath = `${currentPath}/${file}`.replace(/\/+/g, '/');
                                if (file.endsWith('/')) {
                                    setCurrentPath(newPath);
                                } else {
                                    loadFile(newPath);
                                }
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-gray-700 rounded text-sm flex items-center space-x-2"
                        >
                            <span className={file.endsWith('/') ? 'text-yellow-400' : 'text-gray-400'}>
                                {file.endsWith('/') ? '📁' : '📄'}
                            </span>
                            <span className="truncate">{file.replace(/\/$/, '')}</span>
                        </button>
                    ))}
                </div>
            </div>

            <div className="lg:col-span-2 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden flex flex-col">
                <div className="px-4 py-3 border-b border-gray-700 bg-gray-900 flex justify-between items-center">
                    <span className="text-sm font-mono text-gray-400">File Viewer</span>
                    <div className="space-x-2">
                        <button className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs">Save</button>
                        <button className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-xs">Delete</button>
                    </div>
                </div>
                <textarea
                    value={fileContent}
                    onChange={(e) => setFileContent(e.target.value)}
                    className="flex-1 bg-gray-900 p-4 font-mono text-sm text-gray-300 resize-none focus:outline-none"
                    placeholder="Select a file to view/edit..."
                />
            </div>
        </div>
    );
};

export default SovereignDashboard;