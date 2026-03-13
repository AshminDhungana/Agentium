// src/pages/MobilePage.tsx

import { useEffect, useState } from 'react';
import {
    Smartphone,
    Bell,
    Cloud,
    Plus,
    Trash2,
    RefreshCw,
    CheckCircle,
    XCircle,
    AlertTriangle,
    Clock,
    Loader2,
    Shield,
    WifiOff,
    Download,
    Activity,
} from 'lucide-react';
import { api } from '@/services/api';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Device {
    id: string;
    platform: string;
    token: string;
    registered_at: string;
}

interface NotificationPreferences {
    votes_enabled: boolean;
    alerts_enabled: boolean;
    tasks_enabled: boolean;
    constitutional_enabled: boolean;
    quiet_hours_start?: string;
    quiet_hours_end?: string;
}

interface MobileDashboard {
    status: string;
    active_agents: number;
    tasks: {
        pending: number;
        failed: number;
    };
    active_votes: number;
    role: string;
    unread_notifications: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const getPlatformClasses = (platform: string) => {
    switch (platform) {
        case 'ios':
            return 'bg-gray-100 dark:bg-[#1e2535] text-gray-900 dark:text-white border-gray-200 dark:border-[#2a3347]';
        case 'android':
            return 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-500/20';
        default:
            return 'bg-gray-100 dark:bg-[#1e2535] text-gray-700 dark:text-gray-400 border-gray-200 dark:border-[#2a3347]';
    }
};

const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown';
    return new Date(dateString).toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
};

// ── Toggle component ─────────────────────────────────────────────────────────

function Toggle({
    checked,
    onChange,
    label,
    description,
}: {
    checked: boolean;
    onChange: (v: boolean) => void;
    label: string;
    description?: string;
}) {
    return (
        <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
            <div>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{label}</p>
                {description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>
                )}
            </div>
            <button
                type="button"
                onClick={() => onChange(!checked)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-[#161b27] ${
                    checked ? 'bg-emerald-600' : 'bg-gray-200 dark:bg-[#2a3347]'
                }`}
            >
                <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                        checked ? 'translate-x-6' : 'translate-x-1'
                    }`}
                />
            </button>
        </div>
    );
}

// ── Component ───────────────────────────────────────────────────────────────

export function MobilePage() {
    const { user } = useAuthStore();

    const [devices, setDevices] = useState<Device[]>([]);
    const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
    const [dashboard, setDashboard] = useState<MobileDashboard | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<
        'dashboard' | 'devices' | 'preferences' | 'offline'
    >('dashboard');
    const [showAddDeviceModal, setShowAddDeviceModal] = useState(false);
    const [savingPrefs, setSavingPrefs] = useState(false);

    const [newDevice, setNewDevice] = useState({ platform: 'ios', token: '' });
    const [editingPrefs, setEditingPrefs] = useState<NotificationPreferences>({
        votes_enabled: true,
        alerts_enabled: true,
        tasks_enabled: true,
        constitutional_enabled: true,
        quiet_hours_start: '',
        quiet_hours_end: '',
    });

    // ── Effects ─────────────────────────────────────────────────────────────

    useEffect(() => {
        fetchDashboard();
        fetchDevices();
        fetchPreferences();
    }, []);

    // ── Data fetching ────────────────────────────────────────────────────

    const fetchDashboard = async () => {
        try {
            const response = await api.get('/api/v1/mobile/dashboard');
            setDashboard(response.data);
        } catch (error) {
            console.error('Failed to fetch mobile dashboard:', error);
        }
    };

    const fetchDevices = async () => {
        try {
            const response = await api.get('/api/v1/mobile/devices');
            setDevices(response.data ?? []);
        } catch (error) {
            console.error('Failed to fetch devices:', error);
            setDevices([]);
        }
    };

    const fetchPreferences = async () => {
        try {
            const response = await api.get('/api/v1/mobile/notifications/preferences');
            setPreferences(response.data);
            setEditingPrefs(response.data);
        } catch (error) {
            console.error('Failed to fetch preferences:', error);
        } finally {
            setLoading(false);
        }
    };

    // ── Handlers ─────────────────────────────────────────────────────────

    const handleRegisterDevice = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await api.post('/api/v1/mobile/register-device', {
                platform: newDevice.platform,
                token: newDevice.token,
            });
            toast.success('Device registered successfully');
            setShowAddDeviceModal(false);
            setNewDevice({ platform: 'ios', token: '' });
            fetchDevices();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to register device');
        }
    };

    const handleUnregisterDevice = async (token: string) => {
        if (!confirm('Are you sure you want to unregister this device?')) return;
        try {
            await api.delete(`/api/v1/mobile/register-device/${token}`);
            toast.success('Device unregistered');
            fetchDevices();
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to unregister device');
        }
    };

    const handleSavePreferences = async () => {
        setSavingPrefs(true);
        try {
            await api.put('/api/v1/mobile/notifications/preferences', editingPrefs);
            toast.success('Preferences saved');
            setPreferences(editingPrefs);
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to save preferences');
        } finally {
            setSavingPrefs(false);
        }
    };

    const handleOfflineSync = async (type: 'constitution' | 'task-queue') => {
        try {
            const endpoint =
                type === 'constitution'
                    ? '/api/v1/mobile/offline/constitution'
                    : '/api/v1/mobile/offline/task-queue';
            const response = await api.get(endpoint);
            if (type === 'constitution') {
                toast.success(`Constitution synced: v${response.data.version}`);
            } else {
                toast.success(`${response.data.total_queued} tasks queued for offline`);
            }
        } catch (error: any) {
            toast.error(error.response?.data?.detail || 'Failed to sync');
        }
    };

    const updatePref = (key: keyof NotificationPreferences, value: boolean | string) => {
        setEditingPrefs((prev) => ({ ...prev, [key]: value }));
    };

    // ── Access Check ───────────────────────────────────────────────────

    if (!user) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6 transition-colors duration-200">
                <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-xl dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] border border-gray-200 dark:border-[#1e2535] p-8 text-center max-w-md">
                    <div className="w-16 h-16 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mx-auto mb-5">
                        <Shield className="w-8 h-8 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Please log in to access mobile settings.
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
            <div className="max-w-6xl mx-auto">

                {/* ── Page Header ─────────────────────────────────────────────── */}
                <div className="mb-8">
                    <div className="flex items-center gap-3 mb-1">
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                            Mobile App
                        </h1>
                        <span className="px-2.5 py-0.5 bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 text-xs font-semibold rounded-full border border-emerald-200 dark:border-emerald-500/20">
                            New
                        </span>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Configure mobile app settings, devices, and offline sync.
                    </p>
                </div>

                {/* ── Stats Cards ───────────────────────────────────────────── */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                    {/* Connection status */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                                <Smartphone className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <span
                                className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full border ${
                                    dashboard?.status === 'online'
                                        ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                        : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
                                }`}
                            >
                                {dashboard?.status === 'online' ? (
                                    <CheckCircle className="w-3 h-3" />
                                ) : (
                                    <XCircle className="w-3 h-3" />
                                )}
                                {dashboard?.status ?? 'offline'}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Connection Status
                        </p>
                    </div>

                    {/* Registered devices */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                <Smartphone className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {devices.length}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Registered Devices
                        </p>
                    </div>

                    {/* Pending tasks */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
                                <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {dashboard?.tasks?.pending ?? 0}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Pending Tasks
                        </p>
                    </div>

                    {/* Active votes */}
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] p-6 hover:border-gray-300 dark:hover:border-[#2a3347] hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.35)] transition-all duration-150">
                        <div className="flex items-center justify-between mb-4">
                            <div className="w-11 h-11 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                <Bell className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                            </div>
                            <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                {dashboard?.active_votes ?? 0}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Active Votes
                        </p>
                    </div>
                </div>

                {/* ── Tabs ───────────────────────────────────────────────────── */}
                <div className="flex flex-wrap gap-2 mb-6">
                    {(
                        [
                            { id: 'dashboard', label: 'Dashboard', icon: Activity },
                            { id: 'devices', label: 'Devices', icon: Smartphone },
                            { id: 'preferences', label: 'Notifications', icon: Bell },
                            { id: 'offline', label: 'Offline Sync', icon: Cloud },
                        ] as const
                    ).map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 flex items-center gap-2 ${
                                activeTab === id
                                    ? 'bg-emerald-600 text-white shadow-sm'
                                    : 'bg-white dark:bg-[#161b27] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                            }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </div>

                {/* ── Dashboard Tab ────────────────────────────────────────── */}
                {activeTab === 'dashboard' && (
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                        <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center">
                                    <Smartphone className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <div>
                                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Mobile Summary
                                    </h2>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Optimized data for mobile clients
                                    </p>
                                </div>
                            </div>
                        </div>

                        {loading ? (
                            <div className="p-16 text-center">
                                <Loader2 className="w-8 h-8 animate-spin text-emerald-600 dark:text-emerald-400 mx-auto mb-4" />
                                <p className="text-sm text-gray-500 dark:text-gray-400">Loading...</p>
                            </div>
                        ) : dashboard ? (
                            <div className="p-6">
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                                            Active Agents
                                        </p>
                                        <p className="text-xl font-bold text-gray-900 dark:text-white">
                                            {dashboard.active_agents}
                                        </p>
                                    </div>
                                    <div className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                                            Pending Tasks
                                        </p>
                                        <p className="text-xl font-bold text-yellow-600 dark:text-yellow-400">
                                            {dashboard.tasks.pending}
                                        </p>
                                    </div>
                                    <div className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                                            Failed Tasks
                                        </p>
                                        <p className="text-xl font-bold text-red-600 dark:text-red-400">
                                            {dashboard.tasks.failed}
                                        </p>
                                    </div>
                                    <div className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                                            Active Votes
                                        </p>
                                        <p className="text-xl font-bold text-purple-600 dark:text-purple-400">
                                            {dashboard.active_votes}
                                        </p>
                                    </div>
                                </div>

                                <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center shrink-0">
                                            <Shield className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                Role: {dashboard.role}
                                            </p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                                {dashboard.unread_notifications} unread notification
                                                {dashboard.unread_notifications !== 1 ? 's' : ''}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="p-16 text-center">
                                <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                    <AlertTriangle className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                </div>
                                <p className="text-gray-900 dark:text-white font-medium mb-1">
                                    No Data Available
                                </p>
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                    Could not load mobile dashboard
                                </p>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Devices Tab ──────────────────────────────────────────── */}
                {activeTab === 'devices' && (
                    <div className="space-y-6">
                        <div className="flex justify-end">
                            <button
                                onClick={() => setShowAddDeviceModal(true)}
                                className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 dark:hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm"
                            >
                                <Plus className="w-4 h-4" />
                                Register Device
                            </button>
                        </div>

                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                            <Smartphone className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                                Registered Devices
                                            </h2>
                                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                                {devices.length} device
                                                {devices.length !== 1 ? 's' : ''} registered
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={fetchDevices}
                                        className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors duration-150"
                                        title="Refresh"
                                    >
                                        <RefreshCw className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>

                            {devices.length === 0 ? (
                                <div className="p-16 text-center">
                                    <div className="w-14 h-14 rounded-xl bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center mx-auto mb-4">
                                        <Smartphone className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                    </div>
                                    <p className="text-gray-900 dark:text-white font-medium mb-1">
                                        No Devices Registered
                                    </p>
                                    <p className="text-sm text-gray-500 dark:text-gray-400">
                                        Register a device to receive push notifications
                                    </p>
                                </div>
                            ) : (
                                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                    {devices.map((device) => (
                                        <div
                                            key={device.id}
                                            className="p-5 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                                        <Smartphone className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                                    </div>
                                                    <div>
                                                        <div className="flex items-center gap-2">
                                                            <span
                                                                className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${getPlatformClasses(device.platform)}`}
                                                            >
                                                                {device.platform.toUpperCase()}
                                                            </span>
                                                        </div>
                                                        <p className="text-xs font-mono text-gray-500 dark:text-gray-400 mt-1 truncate max-w-xs">
                                                            {device.token.substring(0, 32)}…
                                                        </p>
                                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                                                            Registered {formatDate(device.registered_at)}
                                                        </p>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={() => handleUnregisterDevice(device.token)}
                                                    className="p-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors duration-150"
                                                    title="Unregister device"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Notification Preferences Tab ─────────────────────────── */}
                {activeTab === 'preferences' && (
                    <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                        <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                    <Bell className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                </div>
                                <div>
                                    <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Notification Preferences
                                    </h2>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Choose which events trigger push notifications
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="p-6 space-y-3">
                            <Toggle
                                checked={editingPrefs.votes_enabled}
                                onChange={(v) => updatePref('votes_enabled', v)}
                                label="Vote Notifications"
                                description="Get notified when a Council vote is initiated"
                            />
                            <Toggle
                                checked={editingPrefs.alerts_enabled}
                                onChange={(v) => updatePref('alerts_enabled', v)}
                                label="System Alerts"
                                description="Critical system alerts and warnings"
                            />
                            <Toggle
                                checked={editingPrefs.tasks_enabled}
                                onChange={(v) => updatePref('tasks_enabled', v)}
                                label="Task Updates"
                                description="Task completion, failure, and escalation events"
                            />
                            <Toggle
                                checked={editingPrefs.constitutional_enabled}
                                onChange={(v) => updatePref('constitutional_enabled', v)}
                                label="Constitutional Events"
                                description="Violations, amendments, and governance decisions"
                            />

                            {/* Quiet hours */}
                            <div className="pt-2">
                                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                                    Quiet Hours
                                    <span className="text-xs font-normal text-gray-400 dark:text-gray-500 ml-1">
                                        (suppress notifications during these hours)
                                    </span>
                                </p>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1.5">
                                            Start
                                        </label>
                                        <input
                                            type="time"
                                            value={editingPrefs.quiet_hours_start ?? ''}
                                            onChange={(e) =>
                                                updatePref('quiet_hours_start', e.target.value)
                                            }
                                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1.5">
                                            End
                                        </label>
                                        <input
                                            type="time"
                                            value={editingPrefs.quiet_hours_end ?? ''}
                                            onChange={(e) =>
                                                updatePref('quiet_hours_end', e.target.value)
                                            }
                                            className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="pt-4">
                                <button
                                    onClick={handleSavePreferences}
                                    disabled={savingPrefs}
                                    className="w-full px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 dark:hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center justify-center gap-2"
                                >
                                    {savingPrefs && <Loader2 className="w-4 h-4 animate-spin" />}
                                    Save Preferences
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Offline Sync Tab ──────────────────────────────────────── */}
                {activeTab === 'offline' && (
                    <div className="space-y-6">
                        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] overflow-hidden transition-colors duration-200">
                            <div className="p-6 border-b border-gray-100 dark:border-[#1e2535]">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                        <Cloud className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                    </div>
                                    <div>
                                        <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                                            Offline Data
                                        </h2>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                            Cache data for offline access
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="p-6 space-y-4">
                                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center">
                                            <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                Constitution
                                            </p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                                Current constitution text for offline viewing
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => handleOfflineSync('constitution')}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shrink-0"
                                    >
                                        <Download className="w-4 h-4" />
                                        Sync
                                    </button>
                                </div>

                                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center">
                                            <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                                                Task Queue
                                            </p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                                Pending tasks for offline viewing
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => handleOfflineSync('task-queue')}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shrink-0"
                                    >
                                        <Download className="w-4 h-4" />
                                        Sync
                                    </button>
                                </div>
                            </div>
                        </div>

                        <div className="bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl p-6">
                            <div className="flex items-start gap-3">
                                <div className="w-10 h-10 rounded-lg bg-yellow-100 dark:bg-yellow-500/10 flex items-center justify-center shrink-0">
                                    <WifiOff className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                                        Offline Mode
                                    </h3>
                                    <p className="text-xs text-gray-600 dark:text-gray-400">
                                        When offline, the mobile app will use cached constitution and
                                        display queued tasks. Task execution requires an active
                                        connection.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* ── Add Device Modal ──────────────────────────────────────────── */}
            {showAddDeviceModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl shadow-2xl dark:shadow-[0_24px_80px_rgba(0,0,0,0.7)] max-w-md w-full border border-gray-200 dark:border-[#1e2535]">
                        <div className="border-b border-gray-100 dark:border-[#1e2535] px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 flex items-center justify-center">
                                    <Plus className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <div>
                                    <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                                        Register Device
                                    </h3>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                                        Add a new mobile device for push notifications
                                    </p>
                                </div>
                            </div>
                        </div>

                        <form onSubmit={handleRegisterDevice} className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Platform
                                </label>
                                <select
                                    value={newDevice.platform}
                                    onChange={(e) =>
                                        setNewDevice({ ...newDevice, platform: e.target.value })
                                    }
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150"
                                >
                                    <option value="ios">iOS (APNs)</option>
                                    <option value="android">Android (FCM)</option>
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                    Device Push Token
                                </label>
                                <input
                                    type="text"
                                    value={newDevice.token}
                                    onChange={(e) =>
                                        setNewDevice({ ...newDevice, token: e.target.value })
                                    }
                                    className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 text-sm transition-colors duration-150 font-mono"
                                    placeholder="Paste device push token here"
                                    required
                                />
                                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
                                    Obtain this from the mobile app's device registration flow.
                                </p>
                            </div>

                            <div className="flex gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setShowAddDeviceModal(false)}
                                    className="flex-1 px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 dark:hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm"
                                >
                                    Register
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

export default MobilePage;