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
    XCircle,
    ListTodo,
    RefreshCw
} from 'lucide-react';
import toast from 'react-hot-toast';

const STATUS_FILTERS = [
    { value: '', label: 'All', color: 'gray' },
    { value: 'pending', label: 'Pending', color: 'yellow' },
    { value: 'deliberating', label: 'Deliberating', color: 'purple' },
    { value: 'in_progress', label: 'In Progress', color: 'blue' },
    { value: 'completed', label: 'Completed', color: 'green' },
    { value: 'failed', label: 'Failed', color: 'red' },
];

const FILTER_COLORS: Record<string, string> = {
    gray: 'bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600',
    yellow: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
    purple: 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-800',
    blue: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800',
    green: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
    red: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
};

const FILTER_ACTIVE: Record<string, string> = {
    gray: 'bg-gray-600 text-white border-gray-600',
    yellow: 'bg-yellow-500 text-white border-yellow-500',
    purple: 'bg-purple-600 text-white border-purple-600',
    blue: 'bg-blue-600 text-white border-blue-600',
    green: 'bg-green-600 text-white border-green-600',
    red: 'bg-red-600 text-white border-red-600',
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

    // Compute quick stats from loaded tasks
    const stats = {
        total: tasks.length,
        pending: tasks.filter(t => t.status === 'pending').length,
        active: tasks.filter(t => ['in_progress', 'deliberating'].includes(t.status)).length,
        completed: tasks.filter(t => t.status === 'completed').length,
        failed: tasks.filter(t => t.status === 'failed').length,
    };

    const statCards = [
        { label: 'Total Tasks', value: stats.total, icon: ListTodo, bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-600 dark:text-blue-400' },
        { label: 'Pending', value: stats.pending, icon: Clock, bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-600 dark:text-yellow-400' },
        { label: 'In Progress', value: stats.active, icon: AlertTriangle, bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-600 dark:text-purple-400' },
        { label: 'Completed', value: stats.completed, icon: CheckCircle, bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-600 dark:text-green-400' },
    ];

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">

            {/* Header — matches Dashboard exactly */}
            <div className="mb-8 flex items-start justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                        Tasks
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400">
                        Monitor and manage agent operations
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={() => loadTasks(true)}
                        disabled={isRefreshing}
                        className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                    </button>

                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors shadow-sm"
                    >
                        <Plus className="w-4 h-4" />
                        New Task
                    </button>
                </div>
            </div>

            {/* Stats Grid — same pattern as Dashboard */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                {statCards.map((stat) => (
                    <div
                        key={stat.label}
                        className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className={`w-12 h-12 rounded-lg ${stat.bg} flex items-center justify-center`}>
                                <stat.icon className={`w-6 h-6 ${stat.text}`} />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {isLoading ? '—' : stat.value}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                            {stat.label}
                        </p>
                    </div>
                ))}
            </div>

            {/* Filter + Task List Panel — matches Dashboard card style */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">

                {/* Panel header with filters */}
                <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
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
                                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${isActive
                                            ? FILTER_ACTIVE[color]
                                            : FILTER_COLORS[color]
                                        }`}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>

                    {/* Task count badge */}
                    {!isLoading && (
                        <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
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
                                    className="h-48 rounded-xl bg-gray-100 dark:bg-gray-700/50 animate-pulse"
                                />
                            ))}
                        </div>
                    ) : tasks.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-center">
                            <div className="w-16 h-16 rounded-xl bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
                                <ListTodo className="w-8 h-8 text-gray-400 dark:text-gray-500" />
                            </div>
                            <p className="text-gray-900 dark:text-white font-medium mb-1">
                                {filterStatus ? `No ${filterStatus} tasks` : 'No tasks yet'}
                            </p>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                                {filterStatus
                                    ? `Try a different filter or create a new task`
                                    : 'Create your first task to get started'}
                            </p>
                            {!filterStatus && (
                                <button
                                    onClick={() => setShowCreateModal(true)}
                                    className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors text-sm"
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