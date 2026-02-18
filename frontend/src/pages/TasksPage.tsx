import React, { useEffect, useState } from 'react';
import { Task } from '../types';
import { tasksService, CreateTaskRequest } from '../services/tasks';
import { TaskCard } from '../components/tasks/TaskCard';
import { CreateTaskModal } from '../components/tasks/CreateTaskModal';
import {
    Plus,
    Filter,
    CheckCircle,
    Clock,
    AlertTriangle,
    ListTodo,
    RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';

const STATUS_FILTERS = [
    { value: '',             label: 'All',          color: 'gray'   },
    { value: 'pending',      label: 'Pending',      color: 'yellow' },
    { value: 'deliberating', label: 'Deliberating', color: 'purple' },
    { value: 'in_progress',  label: 'In Progress',  color: 'blue'   },
    { value: 'completed',    label: 'Completed',    color: 'green'  },
    { value: 'failed',       label: 'Failed',       color: 'red'    },
];

const FILTER_COLORS: Record<string, string> = {
    gray:   'bg-gray-100 text-gray-700 border-gray-200 dark:bg-[#1e2535] dark:text-gray-300 dark:border-[#2a3347]',
    yellow: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
    purple: 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20',
    blue:   'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20',
    green:  'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
    red:    'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20',
};

const FILTER_ACTIVE: Record<string, string> = {
    gray:   'bg-gray-600 text-white border-gray-600 dark:bg-gray-500 dark:border-gray-500',
    yellow: 'bg-yellow-500 text-white border-yellow-500',
    purple: 'bg-purple-600 text-white border-purple-600',
    blue:   'bg-blue-600 text-white border-blue-600',
    green:  'bg-green-600 text-white border-green-600',
    red:    'bg-red-600 text-white border-red-600',
};

export const TasksPage: React.FC = () => {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [filterStatus, setFilterStatus] = useState<string>('');

    useEffect(() => {
        loadTasks();
    }, [filterStatus]);

    const loadTasks = async (silent = false) => {
        try {
            if (!silent) setIsLoading(true);
            else setIsRefreshing(true);
            const data = await tasksService.getTasks({ status: filterStatus || undefined });
            setTasks(data);
        } catch (err) {
            console.error(err);
            toast.error('Failed to load tasks');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    };

    const handleCreateTask = async (data: any) => {
        const requestData: CreateTaskRequest = {
            title: data.title,
            description: data.description,
            priority: data.priority,
            task_type: data.task_type,
        };
        await tasksService.createTask(requestData);
        await loadTasks();
        toast.success('Task created successfully');
    };

    const stats = {
        total:     tasks.length,
        pending:   tasks.filter(t => t.status === 'pending').length,
        active:    tasks.filter(t => ['in_progress', 'deliberating'].includes(t.status)).length,
        completed: tasks.filter(t => t.status === 'completed').length,
    };

    const statCards = [
        {
            label: 'Total Tasks',
            value: stats.total,
            icon: ListTodo,
            bg:   'bg-blue-100 dark:bg-blue-500/10',
            text: 'text-blue-600 dark:text-blue-400',
        },
        {
            label: 'Pending',
            value: stats.pending,
            icon: Clock,
            bg:   'bg-yellow-100 dark:bg-yellow-500/10',
            text: 'text-yellow-600 dark:text-yellow-400',
        },
        {
            label: 'In Progress',
            value: stats.active,
            icon: AlertTriangle,
            bg:   'bg-purple-100 dark:bg-purple-500/10',
            text: 'text-purple-600 dark:text-purple-400',
        },
        {
            label: 'Completed',
            value: stats.completed,
            icon: CheckCircle,
            bg:   'bg-green-100 dark:bg-green-500/10',
            text: 'text-green-600 dark:text-green-400',
        },
    ];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">

            {/* ── Page Header ────────────────────────────────────────────── */}
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        Tasks
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Monitor and manage agent operations.
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={() => loadTasks(true)}
                        disabled={isRefreshing}
                        className="p-2 rounded-lg border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 shadow-sm dark:shadow-[0_2px_8px_rgba(0,0,0,0.2)] disabled:opacity-50"
                        title="Refresh"
                    >
                        <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                    </button>

                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors duration-150 shadow-sm text-sm font-medium"
                    >
                        <Plus className="w-4 h-4" />
                        New Task
                    </button>
                </div>
            </div>

            {/* ── Stats Grid ─────────────────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
                {statCards.map((stat) => (
                    <div
                        key={stat.label}
                        className="bg-white dark:bg-[#161b27] p-6 rounded-xl border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-11 h-11 rounded-lg ${stat.bg} flex items-center justify-center`}>
                                <stat.icon className={`w-5 h-5 ${stat.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {isLoading ? (
                                    <span className="inline-block w-7 h-6 rounded bg-gray-200 dark:bg-[#1e2535] animate-pulse" />
                                ) : (
                                    stat.value
                                )}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            {stat.label}
                        </p>
                    </div>
                ))}
            </div>

            {/* ── Filter + Task List Panel ────────────────────────────────── */}
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

                {/* Panel header with filters */}
                <div className="px-6 py-4 border-b border-gray-100 dark:border-[#1e2535] flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 text-gray-400 dark:text-gray-500">
                        <Filter className="w-4 h-4" />
                        <span className="text-sm font-medium">Filter:</span>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        {STATUS_FILTERS.map(({ value, label, color }) => {
                            const isActive = filterStatus === value;
                            return (
                                <button
                                    key={value}
                                    onClick={() => setFilterStatus(value)}
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${
                                        isActive ? FILTER_ACTIVE[color] : FILTER_COLORS[color]
                                    }`}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>

                    {!isLoading && (
                        <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
                            {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'}
                        </span>
                    )}
                </div>

                {/* Task grid */}
                <div className="p-6">
                    {isLoading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                            {[...Array(8)].map((_, i) => (
                                <div
                                    key={i}
                                    className="h-48 rounded-xl bg-gray-100 dark:bg-[#1e2535] animate-pulse"
                                />
                            ))}
                        </div>
                    ) : tasks.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-center">
                            <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mb-4">
                                <ListTodo className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                            </div>
                            <p className="text-gray-900 dark:text-white font-medium mb-1">
                                {filterStatus ? `No ${filterStatus} tasks` : 'No tasks yet'}
                            </p>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                                {filterStatus
                                    ? 'Try a different filter or create a new task'
                                    : 'Create your first task to get started'}
                            </p>
                            {!filterStatus && (
                                <button
                                    onClick={() => setShowCreateModal(true)}
                                    className="bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors duration-150 text-sm font-medium shadow-sm"
                                >
                                    <Plus className="w-4 h-4" />
                                    New Task
                                </button>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                            {tasks.map(task => (
                                <TaskCard key={task.id} task={task} />
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {showCreateModal && (
                <CreateTaskModal
                    onConfirm={handleCreateTask}
                    onClose={() => setShowCreateModal(false)}
                />
            )}
        </div>
    );
};
