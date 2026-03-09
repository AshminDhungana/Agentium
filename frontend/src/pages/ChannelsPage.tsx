// src/pages/ChannelsPage.tsx
// ─────────────────────────────────────────────────────────────────────────────
// Improvements applied (all non-breaking):
//
//  #1  Local type duplicates removed — imported from @/types instead.
//  #2  QR polling memory leak fixed — useQRPolling hook with stored handle.
//  #3  N polling intervals fixed — single batched query (30 s) at page level;
//      ChannelMetricsSection now receives data as a prop instead of fetching.
//  #4  Delete confirmation already present (confirm dialog) — preserved as-is.
//  #5  Per-channel test loading state — testingChannelId replaces global flag.
//  #6  staleTime + select on channels query — removes double normalisation.
//  #7  channelTypes/colorMap/statusConfig imported from @/constants/channelTypes.
//  #8  ARIA on all modals — role, aria-modal, aria-labelledby, Escape key.
//  #9  Shared MessageLogViewer imported — inline duplicate removed.
// #10  useReducer consolidates 6 modal-related useState calls.
// #11  whatsappProvider state kept separate (not modal-related) for clarity.
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useReducer, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { channelMetricsApi } from '@/services/channelMetrics';
import { MessageLogViewer } from '@/components/channels/MessageLogViewer';
import { useQRPolling } from '@/hooks/useQRPolling';
import {
    channelTypes,
    colorMap,
    whatsAppCloudFields,
    whatsAppBridgeFields,
    getStatus,
} from '@/constants/channelTypes';
import type {
    Channel,
    ChannelTypeSlug,
    ChannelFormData,
    WhatsAppProvider,
    ChannelMetricsResponse,
} from '@/types';
import {
    MessageCircle,
    Plus,
    RefreshCw,
    Trash2,
    ChevronRight,
    Loader2,
    X,
    Copy,
    CheckCircle,
    Server,
    AlertTriangle,
    XCircle,
    Clock,
    Inbox,
    ArrowUpRight,
    MessageSquare,
    Send,
    QrCode,
} from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { QRCodeSVG } from 'qrcode.react';
import { useNavigate } from 'react-router-dom';

// ═══════════════════════════════════════════════════════════════════════════════
// MODAL STATE — useReducer replaces 6 scattered useState hooks (#10)
// ═══════════════════════════════════════════════════════════════════════════════

interface ModalState {
    showAddModal: boolean;
    selectedType: ChannelTypeSlug | null;
    qrCodeData: string | null;
    qrStep: boolean;
}

type ModalAction =
    | { type: 'OPEN' }
    | { type: 'SELECT_TYPE'; payload: ChannelTypeSlug }
    | { type: 'BACK' }                          // from config step → type picker
    | { type: 'ENTER_QR_STEP' }
    | { type: 'SET_QR_DATA'; payload: string }
    | { type: 'OPEN_QR_FOR_BRIDGE' }            // after switchProvider → web_bridge
    | { type: 'CLOSE' };

const INITIAL_MODAL: ModalState = {
    showAddModal: false,
    selectedType: null,
    qrCodeData: null,
    qrStep: false,
};

function modalReducer(state: ModalState, action: ModalAction): ModalState {
    switch (action.type) {
        case 'OPEN':           return { ...INITIAL_MODAL, showAddModal: true };
        case 'SELECT_TYPE':    return { ...state, selectedType: action.payload };
        case 'BACK':           return { ...state, selectedType: null, qrCodeData: null };
        case 'ENTER_QR_STEP':  return { ...state, qrStep: true };
        case 'SET_QR_DATA':    return { ...state, qrCodeData: action.payload, qrStep: true };
        case 'OPEN_QR_FOR_BRIDGE':
            return { showAddModal: true, selectedType: 'whatsapp', qrCodeData: null, qrStep: true };
        case 'CLOSE':          return { ...INITIAL_MODAL };
        default:               return state;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHANNEL METRICS SECTION
// Props-driven instead of self-fetching — batched query lives in the page (#3)
// ═══════════════════════════════════════════════════════════════════════════════

interface ChannelMetricsSectionProps {
    channelId: string;
    metricsData: ChannelMetricsResponse | undefined;
    isLoading: boolean;
}

function ChannelMetricsSection({ channelId, metricsData, isLoading }: ChannelMetricsSectionProps) {
    const [showLogs, setShowLogs] = useState(false);
    const queryClient = useQueryClient();

    const resetMutation = useMutation({
        mutationFn: () => channelMetricsApi.resetChannel(channelId),
        onSuccess: () => {
            toast.success('Channel reset successfully');
            // Invalidate the shared batched query, not the old per-channel key
            queryClient.invalidateQueries({ queryKey: ['all-channel-metrics'] });
        },
        onError: () => toast.error('Failed to reset channel'),
    });

    if (isLoading) {
        return (
            <div className="pt-4 border-t border-gray-100 dark:border-[#1e2535]">
                <div className="flex items-center gap-2 text-sm text-gray-500">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Loading health metrics...
                </div>
            </div>
        );
    }

    if (!metricsData) return null;

    const { metrics, health_status } = metricsData;

    const getHealthColors = () => {
        switch (health_status) {
            case 'healthy':  return { bg: 'bg-green-50 dark:bg-green-500/10',   border: 'border-green-200 dark:border-green-500/20',   text: 'text-green-700 dark:text-green-400',   indicator: 'bg-green-500'  };
            case 'warning':  return { bg: 'bg-yellow-50 dark:bg-yellow-500/10', border: 'border-yellow-200 dark:border-yellow-500/20', text: 'text-yellow-700 dark:text-yellow-400', indicator: 'bg-yellow-500' };
            case 'critical': return { bg: 'bg-red-50 dark:bg-red-500/10',       border: 'border-red-200 dark:border-red-500/20',       text: 'text-red-700 dark:text-red-400',       indicator: 'bg-red-500'    };
        }
    };

    const getCircuitColors = () => {
        switch (metrics.circuit_breaker_state) {
            case 'closed':    return 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400 border-green-200 dark:border-green-500/20';
            case 'half_open': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400 border-yellow-200 dark:border-yellow-500/20';
            case 'open':      return 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/20 animate-pulse';
        }
    };

    const colors = getHealthColors();

    return (
        <div className="pt-4 border-t border-gray-100 dark:border-[#1e2535] space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${colors.indicator}`} />
                    <span className="text-sm font-semibold text-gray-900 dark:text-white">Health Metrics</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${colors.bg} ${colors.border} ${colors.text} uppercase font-medium`}>
                        {health_status}
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-1 rounded-full border font-semibold ${getCircuitColors()}`}>
                        Circuit: {metrics.circuit_breaker_state.toUpperCase()}
                    </span>
                    {metrics.circuit_breaker_state === 'open' && (
                        <button
                            onClick={() => resetMutation.mutate()}
                            disabled={resetMutation.isPending}
                            className="p-1.5 bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-500/20 transition-colors"
                            title="Reset circuit breaker"
                        >
                            <RefreshCw className={`w-3 h-3 ${resetMutation.isPending ? 'animate-spin' : ''}`} />
                        </button>
                    )}
                </div>
            </div>

            {/* Metrics grid */}
            <div className={`grid grid-cols-4 gap-3 p-3 rounded-xl border ${colors.bg} ${colors.border}`}>
                <div className="text-center">
                    <div className={`text-lg font-bold ${colors.text}`}>{metrics.success_rate.toFixed(1)}%</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Success</div>
                </div>
                <div className="text-center">
                    <div className={`text-lg font-bold ${metrics.failed_requests > 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}`}>
                        {metrics.failed_requests}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Failures</div>
                </div>
                <div className="text-center">
                    <div className={`text-lg font-bold ${metrics.rate_limit_hits > 0 ? 'text-yellow-600 dark:text-yellow-400' : 'text-gray-700 dark:text-gray-300'}`}>
                        {metrics.rate_limit_hits}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Rate Limits</div>
                </div>
                <div className="text-center">
                    <div className={`text-lg font-bold ${metrics.consecutive_failures > 2 ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}`}>
                        {metrics.consecutive_failures}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">Consecutive</div>
                </div>
            </div>

            {/* Toggle logs */}
            <button
                onClick={() => setShowLogs(v => !v)}
                className="flex items-center gap-2 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
            >
                {showLogs ? 'Hide' : 'Show'} Message Logs
                <ChevronRight className={`w-4 h-4 transition-transform ${showLogs ? 'rotate-90' : ''}`} />
            </button>

            {/* Shared component — no duplicate inline definition (#9) */}
            {showLogs && <MessageLogViewer channelId={channelId} />}
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEST MESSAGE MODAL — ARIA added (#8)
// ═══════════════════════════════════════════════════════════════════════════════

interface TestModalProps {
    channel: Channel;
    onClose: () => void;
}

function TestMessageModal({ channel, onClose }: TestModalProps) {
    const [recipient, setRecipient] = useState('');
    const [content, setContent]     = useState('Hello from Agentium! 👋');
    const [sending, setSending]     = useState(false);

    const typeDef = channelTypes.find(t => t.id === channel.type);
    const Icon    = typeDef?.Icon ?? MessageCircle;
    const colors  = colorMap[typeDef?.color ?? 'blue'];

    const handleSend = async () => {
        if (!recipient.trim()) { toast.error('Recipient required'); return; }
        setSending(true);
        try {
            await api.post(`/api/v1/channels/${channel.id}/send`, { recipient, content });
            toast.success('Test message sent!');
            onClose();
        } catch (err: any) {
            toast.error(err?.response?.data?.detail ?? 'Send failed');
        } finally {
            setSending(false);
        }
    };

    return (
        <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="test-msg-modal-title"
            onKeyDown={e => e.key === 'Escape' && onClose()}
            className="fixed inset-0 bg-black/60 dark:bg-black/75 flex items-center justify-center p-4 z-50 backdrop-blur-sm"
        >
            <div className="bg-white dark:bg-[#161b27] rounded-2xl max-w-md w-full shadow-2xl border border-gray-200 dark:border-[#1e2535]">
                <div className="p-6 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg ${colors.bg} ${colors.darkBg} flex items-center justify-center`}>
                            <Icon className={`w-5 h-5 ${colors.text} ${colors.darkText}`} />
                        </div>
                        <div>
                            <h2 id="test-msg-modal-title" className="text-base font-semibold text-gray-900 dark:text-white">
                                Send Test Message
                            </h2>
                            <p className="text-xs text-gray-500 dark:text-gray-400">{channel.name}</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                    >
                        <X className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                    </button>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Recipient</label>
                        <input
                            type="text"
                            value={recipient}
                            onChange={e => setRecipient(e.target.value)}
                            placeholder="Phone number, chat ID, email…"
                            className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Message</label>
                        <textarea
                            value={content}
                            onChange={e => setContent(e.target.value)}
                            rows={3}
                            className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none text-sm resize-none"
                        />
                    </div>
                </div>
                <div className="p-6 border-t border-gray-200 dark:border-[#1e2535] flex justify-end gap-3">
                    <button onClick={onClose} className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors">
                        Cancel
                    </button>
                    <button
                        onClick={handleSend}
                        disabled={sending}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                    >
                        {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                        Send Message
                    </button>
                </div>
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export function ChannelsPage() {
    const navigate    = useNavigate();
    const queryClient = useQueryClient();

    // ── Modal state (#10) ──────────────────────────────────────────────────────
    const [modalState, dispatchModal] = useReducer(modalReducer, INITIAL_MODAL);
    const { showAddModal, selectedType, qrCodeData, qrStep } = modalState;

    // ── Non-modal state (kept as useState — each is independent) ──────────────
    const [whatsappProvider,  setWhatsappProvider]  = useState<WhatsAppProvider>('cloud_api');
    const [showProviderSwitch, setShowProviderSwitch] = useState<string | null>(null);
    const [editingSenders,    setEditingSenders]    = useState<string | null>(null);
    const [senderInput,       setSenderInput]       = useState('');
    const [testChannel,       setTestChannel]       = useState<Channel | null>(null);
    // Per-channel loading flag for the test button (#5)
    const [testingChannelId,  setTestingChannelId]  = useState<string | null>(null);

    // ── QR polling hook (#2) ───────────────────────────────────────────────────
    const { startPolling, stopPolling } = useQRPolling({
        onAuthenticated: useCallback(() => {
            toast.success('WhatsApp connected successfully!');
            dispatchModal({ type: 'CLOSE' });
            queryClient.invalidateQueries({ queryKey: ['channels'] });
        }, [queryClient]),
        onQRCode: useCallback((qrData: string) => {
            dispatchModal({ type: 'SET_QR_DATA', payload: qrData });
        }, []),
        onError: useCallback((err: unknown) => {
            console.error('[ChannelsPage] QR polling error:', err);
        }, []),
    });

    const closeModal = useCallback(() => {
        stopPolling();
        dispatchModal({ type: 'CLOSE' });
        setWhatsappProvider('cloud_api');
    }, [stopPolling]);

    // ── Channels query (#6 — staleTime + select normalisation) ────────────────
    const { data: channels = [], isLoading, error } = useQuery({
        queryKey: ['channels'],
        queryFn: async () => {
            const response = await api.get<{ channels: Channel[] }>('/api/v1/channels/');
            return response.data;
        },
        // select centralises normalisation — removes double Array.isArray guard
        select: (data): Channel[] => data?.channels ?? [],
        staleTime: 30_000,
        refetchOnWindowFocus: true,
    });

    // ── Batched metrics query (#3 — one query for all cards, 30 s interval) ───
    const { data: allMetrics, isLoading: metricsLoading } = useQuery({
        queryKey: ['all-channel-metrics'],
        queryFn: () => channelMetricsApi.getAllChannelsMetrics(),
        refetchInterval: 30_000,
        staleTime: 15_000,
        enabled: channels.length > 0,
    });

    // ── Mutations ─────────────────────────────────────────────────────────────

    const createMutation = useMutation({
        mutationFn: (data: ChannelFormData) =>
            api.post('/api/v1/channels/', data).then(r => r.data),
        onSuccess: (data: Channel & { webhook_url?: string }) => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            toast.success('Channel created successfully');
            if (data.type === 'whatsapp' && data.config?.provider === 'web_bridge') {
                dispatchModal({ type: 'ENTER_QR_STEP' });
                startPolling(data.id);
            } else {
                closeModal();
            }
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to create channel'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.delete(`/api/v1/channels/${id}`),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            toast.success('Channel deleted');
        },
    });

    const updateSendersMutation = useMutation({
        mutationFn: ({ id, senders }: { id: string; senders: string[] }) =>
            api.put(`/api/v1/channels/${id}`, { config: { allowed_senders: senders } }).then(r => r.data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            setEditingSenders(null);
            setSenderInput('');
            toast.success('Allowed senders updated');
        },
        onError: () => toast.error('Failed to update allowed senders'),
    });

    // Fix #5: scoped loading — only the button on the tested card spins
    const testMutation = useMutation({
        mutationFn: (id: string) => {
            setTestingChannelId(id);
            return api.post(`/api/v1/channels/${id}/test`).then(r => r.data);
        },
        onSuccess: (data: any) => {
            if (data.success) toast.success('Connection successful!');
            else toast.error(`Connection failed: ${data.error ?? 'Unknown error'}`);
            queryClient.invalidateQueries({ queryKey: ['channels'] });
        },
        onError:   (err: any) => toast.error(err.response?.data?.detail || 'Test failed'),
        onSettled: () => setTestingChannelId(null),
    });

    const switchProviderMutation = useMutation({
        mutationFn: ({ id, provider }: { id: string; provider: WhatsAppProvider }) =>
            api.post(`/api/v1/channels/${id}/whatsapp/switch-provider?new_provider=${provider}`).then(r => r.data),
        onSuccess: (data) => {
            toast.success(`Switched to ${data.provider === 'cloud_api' ? 'Cloud API' : 'Web Bridge'}`);
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            setShowProviderSwitch(null);
            if (data.provider === 'web_bridge' && data.channel_id) {
                dispatchModal({ type: 'OPEN_QR_FOR_BRIDGE' });
                setWhatsappProvider('web_bridge');
                startPolling(data.channel_id);
            }
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to switch provider'),
    });

    // ── Form submit ────────────────────────────────────────────────────────────
    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (!selectedType) return;

        const fd = new FormData(e.target as HTMLFormElement);

        const fields =
            selectedType === 'whatsapp'
                ? (whatsappProvider === 'cloud_api' ? whatsAppCloudFields : whatsAppBridgeFields)
                : (channelTypes.find(t => t.id === selectedType)?.fields ?? []);

        const config: Record<string, string> = {};
        if (selectedType === 'whatsapp') {
            config.provider = whatsappProvider;
            if (whatsappProvider === 'web_bridge') {
                config.bridge_url   = 'env://whatsapp-bridge';
                config.bridge_token = 'env://WHATSAPP_BRIDGE_TOKEN';
            }
        }
        fields.forEach(f => {
            const val = (fd.get(f.name) || '').toString();
            if (val) config[f.name] = val;
        });

        createMutation.mutate({
            name:              fd.get('name') as string,
            type:              selectedType,
            config,
            auto_create_tasks: true,
            require_approval:  false,
        });
    };

    const handleCopyWebhook = (url: string) => {
        navigator.clipboard.writeText(url);
        toast.success('Webhook URL copied');
    };

    const handleViewLog = (channelId: string) =>
        navigate(`/message-log?channel_id=${channelId}`);

    // ── Summary stats ──────────────────────────────────────────────────────────
    const activeCount   = channels.filter(c => c.status === 'active').length;
    const totalReceived = channels.reduce((a, c) => a + (c.stats?.received || 0), 0);
    const totalSent     = channels.reduce((a, c) => a + (c.stats?.sent    || 0), 0);

    // ─── Render ───────────────────────────────────────────────────────────────
    return (
        <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 transition-colors duration-200">

            {/* ── Page header ─────────────────────────────────────────────── */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        Communication Channels
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Connect external platforms to your AI agents
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => navigate('/message-log')}
                        className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg transition-colors duration-150"
                    >
                        <Inbox className="w-4 h-4" /> All Logs
                    </button>
                    <button
                        onClick={() => dispatchModal({ type: 'OPEN' })}
                        className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm dark:shadow-blue-900/30"
                    >
                        <Plus className="w-4 h-4" /> Add Channel
                    </button>
                </div>
            </div>

            {/* ── Error banner ─────────────────────────────────────────────── */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                    <p className="text-red-700 dark:text-red-400 text-sm">
                        Error loading channels. Please try refreshing the page.
                    </p>
                </div>
            )}

            {/* ── Stats ────────────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {[
                    { label: 'Total Channels', value: channels.length,  valueClass: 'text-gray-900 dark:text-white'          },
                    { label: 'Active',          value: activeCount,      valueClass: 'text-green-600 dark:text-green-400'     },
                    { label: 'Received',        value: totalReceived,    valueClass: 'text-blue-600 dark:text-blue-400'       },
                    { label: 'Sent',            value: totalSent,        valueClass: 'text-purple-600 dark:text-purple-400'   },
                ].map(stat => (
                    <div
                        key={stat.label}
                        className="bg-white dark:bg-[#161b27] p-5 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none transition-colors duration-200"
                    >
                        <div className={`text-2xl font-bold ${stat.valueClass}`}>{stat.value}</div>
                        <div className="text-xs font-medium text-gray-500 dark:text-gray-500 mt-0.5 uppercase tracking-wide">
                            {stat.label}
                        </div>
                    </div>
                ))}
            </div>

            {/* ── Channel grid ─────────────────────────────────────────────── */}
            {isLoading ? (
                <div className="flex items-center justify-center h-64">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                </div>

            ) : channels.length === 0 ? (
                <div className="text-center py-16 bg-gray-50 dark:bg-[#161b27] rounded-2xl border border-dashed border-gray-300 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="w-16 h-16 mx-auto rounded-full bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center mb-4">
                        <Plus className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No channels connected</h3>
                    <p className="text-gray-500 dark:text-gray-400 text-sm mb-5">
                        Connect WhatsApp, Slack, Discord, Signal and more
                    </p>
                    <button
                        onClick={() => dispatchModal({ type: 'OPEN' })}
                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150"
                    >
                        Add Your First Channel
                    </button>
                </div>

            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {channels.map(channel => {
                        const typeDef   = channelTypes.find(t => t.id === channel.type);
                        const colors    = colorMap[typeDef?.color ?? 'blue'];
                        const Icon      = typeDef?.Icon ?? MessageCircle;
                        const status    = getStatus(channel.status);
                        const isWhatsApp = channel.type === 'whatsapp';
                        const provider   = channel.config?.provider || 'cloud_api';
                        const isBridge   = provider === 'web_bridge';
                        // Per-card metrics slice from the single batched query (#3)
                        const channelMetrics = allMetrics?.channels.find(m => m.channel_id === channel.id);

                        return (
                            <div
                                key={channel.id}
                                className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                            >
                                {/* Card header */}
                                <div className="p-5 border-b border-gray-100 dark:border-[#1e2535]">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-11 h-11 rounded-xl ${colors.bg} ${colors.darkBg} flex items-center justify-center flex-shrink-0`}>
                                                <Icon className={`w-5 h-5 ${colors.text} ${colors.darkText}`} />
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-900 dark:text-gray-100 leading-snug">
                                                    {channel.name}
                                                </h3>
                                                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                                                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${status.dot}`} />
                                                    <p className="text-xs text-gray-500 dark:text-gray-400">
                                                        {typeDef?.name ?? channel.type} · {status.label}
                                                    </p>
                                                    {isWhatsApp && (
                                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                                                            isBridge
                                                                ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400'
                                                                : 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'
                                                        }`}>
                                                            {isBridge ? 'Bridge' : 'Cloud API'}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Action buttons */}
                                        <div className="flex gap-1">
                                            <button
                                                onClick={() => handleViewLog(channel.id)}
                                                title="View message log"
                                                className="p-2 text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-all duration-150"
                                            >
                                                <Inbox className="w-4 h-4" />
                                            </button>
                                            {isWhatsApp && (
                                                <button
                                                    onClick={() => setShowProviderSwitch(channel.id)}
                                                    title="Switch provider"
                                                    className="p-2 text-gray-400 dark:text-gray-500 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10 rounded-lg transition-all duration-150"
                                                >
                                                    <Server className="w-4 h-4" />
                                                </button>
                                            )}
                                            {/* Fix #5: spinner scoped to this channel only */}
                                            <button
                                                onClick={() => testMutation.mutate(channel.id)}
                                                disabled={testingChannelId === channel.id}
                                                title="Test connection"
                                                className="p-2 text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-all duration-150"
                                            >
                                                <RefreshCw className={`w-4 h-4 ${testingChannelId === channel.id ? 'animate-spin' : ''}`} />
                                            </button>
                                            <button
                                                onClick={() => {
                                                    if (confirm(`Delete "${channel.name}"?\n\nThis cannot be undone.`))
                                                        deleteMutation.mutate(channel.id);
                                                }}
                                                title="Delete channel"
                                                className="p-2 text-gray-400 dark:text-gray-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-all duration-150"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* Card body */}
                                <div className="p-5 space-y-4 bg-white dark:bg-[#161b27]">
                                    {/* Status badges */}
                                    <div className="flex flex-wrap items-center gap-2">
                                        {channel.config?.has_credentials ? (
                                            <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-500/20 rounded-full font-medium">
                                                <CheckCircle className="w-3 h-3" /> Credentials configured
                                            </span>
                                        ) : (
                                            <span className="text-xs px-2.5 py-1 bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border border-yellow-200 dark:border-yellow-500/20 rounded-full font-medium">
                                                ⚠ No credentials
                                            </span>
                                        )}
                                        {channel.routing?.require_approval && (
                                            <span className="text-xs px-2.5 py-1 bg-orange-100 dark:bg-orange-500/10 text-orange-700 dark:text-orange-400 border border-orange-200 dark:border-orange-500/20 rounded-full font-medium">
                                                Requires approval
                                            </span>
                                        )}
                                        {isWhatsApp && isBridge && channel.status === 'pending' && (
                                            <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-purple-100 dark:bg-purple-500/10 text-purple-700 dark:text-purple-400 border border-purple-200 dark:border-purple-500/20 rounded-full font-medium">
                                                <QrCode className="w-3 h-3" /> QR Required
                                            </span>
                                        )}
                                    </div>

                                    {/* WhatsApp provider info */}
                                    {isWhatsApp && (
                                        <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#1e2535]">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Provider</span>
                                                <span className={`text-xs font-semibold ${isBridge ? 'text-orange-600 dark:text-orange-400' : 'text-blue-600 dark:text-blue-400'}`}>
                                                    {isBridge ? 'Web Bridge (QR)' : 'Cloud API (Meta)'}
                                                </span>
                                            </div>
                                            <p className="text-xs text-gray-500 dark:text-gray-500">
                                                {isBridge
                                                    ? 'Uses WebSocket bridge with QR authentication. Good for personal use.'
                                                    : 'Official Meta Business API. Required for production/business use.'}
                                            </p>
                                        </div>
                                    )}

                                    {/* Webhook URL */}
                                    {channel.config?.webhook_url && (
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
                                                Webhook URL
                                            </label>
                                            <div className="flex gap-2">
                                                <code className="flex-1 text-xs bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] px-3 py-2 rounded-lg text-gray-600 dark:text-gray-400 truncate font-mono">
                                                    {channel.config.webhook_url}
                                                </code>
                                                <button
                                                    onClick={() => handleCopyWebhook(channel.config.webhook_url!)}
                                                    title="Copy webhook URL"
                                                    className="px-3 py-2 bg-gray-100 dark:bg-[#1e2535] hover:bg-gray-200 dark:hover:bg-[#2a3347] border border-gray-200 dark:border-[#1e2535] rounded-lg transition-all duration-150"
                                                >
                                                    <Copy className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Type-specific info */}
                                    {channel.type === 'signal' && channel.config?.number && (
                                        <p className="text-xs text-gray-500 dark:text-gray-500">
                                            Number: <span className="font-mono text-gray-700 dark:text-gray-300">{channel.config.number}</span>
                                        </p>
                                    )}
                                    {channel.type === 'matrix' && channel.config?.homeserver_url && (
                                        <p className="text-xs text-gray-500 dark:text-gray-500">
                                            Homeserver: <span className="font-mono text-gray-700 dark:text-gray-300">{channel.config.homeserver_url}</span>
                                        </p>
                                    )}
                                    {channel.type === 'imessage' && (
                                        <p className="text-xs text-gray-500 dark:text-gray-500">
                                            Backend: <span className="font-mono text-gray-700 dark:text-gray-300">{channel.config?.backend ?? 'applescript'}</span>
                                            {channel.config?.bb_url && <span className="text-gray-400 dark:text-gray-600"> · {channel.config.bb_url}</span>}
                                        </p>
                                    )}

                                    {/* Action buttons */}
                                    <div className="flex flex-wrap gap-2 pt-2">
                                        <button
                                            onClick={() => setTestChannel(channel)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/10 border border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-medium hover:bg-blue-600/20 transition-colors"
                                        >
                                            <MessageSquare className="w-3.5 h-3.5" /> Send Test
                                        </button>
                                        <button
                                            onClick={() => handleViewLog(channel.id)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] text-gray-600 dark:text-gray-400 text-xs font-medium hover:bg-gray-200 dark:hover:bg-[#2a3347] transition-colors"
                                        >
                                            <ArrowUpRight className="w-3.5 h-3.5" /> View Logs
                                        </button>
                                    </div>

                                    {/* Allowed senders (WhatsApp only) */}
                                    {isWhatsApp && (
                                        <div className="pt-3 border-t border-gray-100 dark:border-[#1e2535]">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Allowed Senders</span>
                                                <button
                                                    onClick={() => { setEditingSenders(channel.id); setSenderInput(''); }}
                                                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                                                >
                                                    {editingSenders === channel.id ? 'Cancel' : 'Edit'}
                                                </button>
                                            </div>
                                            {editingSenders === channel.id ? (
                                                <div className="space-y-2">
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {(channel.config?.allowed_senders || []).map(num => (
                                                            <span key={num} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 rounded-full text-xs font-mono">
                                                                {num}
                                                                <button
                                                                    onClick={() => updateSendersMutation.mutate({ id: channel.id, senders: (channel.config?.allowed_senders || []).filter(s => s !== num) })}
                                                                    className="hover:text-red-500 ml-0.5"
                                                                >×</button>
                                                            </span>
                                                        ))}
                                                    </div>
                                                    <div className="flex gap-2">
                                                        <input
                                                            value={senderInput}
                                                            onChange={e => setSenderInput(e.target.value)}
                                                            onKeyDown={e => {
                                                                if (e.key === 'Enter' && senderInput.trim()) {
                                                                    const updated = [...(channel.config?.allowed_senders || []), senderInput.trim()];
                                                                    updateSendersMutation.mutate({ id: channel.id, senders: updated });
                                                                    setSenderInput('');
                                                                }
                                                            }}
                                                            placeholder="+1234567890 (Enter to add)"
                                                            className="flex-1 px-2 py-1 text-xs border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-1 focus:ring-blue-500 outline-none"
                                                        />
                                                        <button
                                                            onClick={() => updateSendersMutation.mutate({ id: channel.id, senders: channel.config?.allowed_senders || [] })}
                                                            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
                                                        >
                                                            Save
                                                        </button>
                                                    </div>
                                                    <p className="text-xs text-gray-400 dark:text-gray-500">
                                                        Leave empty to accept messages from everyone. Add your number to only accept your own messages.
                                                    </p>
                                                </div>
                                            ) : (
                                                <div className="flex flex-wrap gap-1.5">
                                                    {(channel.config?.allowed_senders || []).length === 0 ? (
                                                        <span className="text-xs text-amber-600 dark:text-amber-400">⚠ Everyone can trigger this channel</span>
                                                    ) : (
                                                        (channel.config.allowed_senders || []).map(num => (
                                                            <span key={num} className="px-2 py-0.5 bg-green-100 dark:bg-green-500/15 text-green-700 dark:text-green-300 rounded-full text-xs font-mono">{num}</span>
                                                        ))
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Stats row */}
                                    <div className="flex items-center gap-5 pt-3 border-t border-gray-100 dark:border-[#1e2535]">
                                        <div className="text-sm">
                                            <span className="text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wide font-medium">Received </span>
                                            <span className="font-semibold text-gray-900 dark:text-gray-100">{channel.stats?.received ?? 0}</span>
                                        </div>
                                        <div className="text-sm">
                                            <span className="text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wide font-medium">Sent </span>
                                            <span className="font-semibold text-gray-900 dark:text-gray-100">{channel.stats?.sent ?? 0}</span>
                                        </div>
                                        {channel.stats?.last_message && (
                                            <div className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                                                {format(new Date(channel.stats.last_message), 'MMM d, h:mm a')}
                                            </div>
                                        )}
                                    </div>

                                    {/* Health metrics (prop-driven — no per-card polling) (#3) */}
                                    <ChannelMetricsSection
                                        channelId={channel.id}
                                        metricsData={channelMetrics}
                                        isLoading={metricsLoading && !channelMetrics}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── Add Channel Modal (#8 ARIA) ───────────────────────────────── */}
            {showAddModal && (
                <div
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="add-channel-title"
                    onKeyDown={e => e.key === 'Escape' && closeModal()}
                    className="fixed inset-0 bg-black/60 dark:bg-black/75 flex items-center justify-center p-4 z-50 backdrop-blur-sm"
                >
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl dark:shadow-[0_24px_64px_rgba(0,0,0,0.6)] border border-gray-200 dark:border-[#1e2535]">

                        {/* Modal header */}
                        <div className="p-6 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between sticky top-0 bg-white dark:bg-[#161b27] z-10 rounded-t-2xl">
                            <h2 id="add-channel-title" className="text-lg font-bold text-gray-900 dark:text-white">
                                {qrStep
                                    ? 'Scan QR Code'
                                    : selectedType
                                        ? `Configure ${channelTypes.find(t => t.id === selectedType)?.name}`
                                        : 'Add Channel'}
                            </h2>
                            <button
                                aria-label="Close"
                                onClick={closeModal}
                                className="p-2 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors duration-150"
                            >
                                <X className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                            </button>
                        </div>

                        <div className="p-6">
                            {/* Step 3: QR code */}
                            {qrStep ? (
                                <div className="flex flex-col items-center gap-6 py-4">
                                    <div className="text-center">
                                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                            Scan this QR code with your WhatsApp app to link the account.
                                        </p>
                                    </div>

                                    {qrCodeData ? (
                                        <div className="p-5 bg-white rounded-2xl shadow-lg border border-orange-200 dark:border-orange-500/30">
                                            <QRCodeSVG value={qrCodeData} size={240} level="H" includeMargin />
                                        </div>
                                    ) : (
                                        <div className="w-[250px] h-[250px] rounded-2xl bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] flex flex-col items-center justify-center gap-3">
                                            <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
                                            <p className="text-xs text-gray-500 dark:text-gray-400">Waiting for QR code…</p>
                                        </div>
                                    )}

                                    <ol className="text-sm text-gray-600 dark:text-gray-400 space-y-1.5 text-left w-full max-w-xs list-decimal list-inside">
                                        <li>Open <strong className="text-gray-800 dark:text-gray-200">WhatsApp</strong> on your phone</li>
                                        <li>Go to <strong className="text-gray-800 dark:text-gray-200">Settings → Linked Devices</strong></li>
                                        <li>Tap <strong className="text-gray-800 dark:text-gray-200">Link a Device</strong></li>
                                        <li>Scan the QR code above</li>
                                    </ol>

                                    <div className="flex items-center gap-2 text-xs text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 rounded-lg px-3 py-2 w-full max-w-xs">
                                        <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
                                        Waiting for scan… refreshes every 10 s
                                    </div>

                                    <button
                                        type="button"
                                        onClick={closeModal}
                                        className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                                    >
                                        Cancel
                                    </button>
                                </div>

                            ) : !selectedType ? (
                                /* Step 1: type picker */
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                    {channelTypes.map(type => {
                                        const c = colorMap[type.color];
                                        return (
                                            <button
                                                key={type.id}
                                                onClick={() => dispatchModal({ type: 'SELECT_TYPE', payload: type.id })}
                                                className="flex items-center gap-3 p-4 border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] hover:border-blue-400 dark:hover:border-blue-500/50 hover:bg-blue-50/30 dark:hover:bg-blue-500/5 rounded-xl transition-all duration-150 text-left group"
                                            >
                                                <div className={`w-10 h-10 rounded-lg ${c.bg} ${c.darkBg} flex items-center justify-center flex-shrink-0`}>
                                                    <type.Icon className={`w-5 h-5 ${c.text} ${c.darkText}`} />
                                                </div>
                                                <div className="min-w-0">
                                                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-sm truncate">{type.name}</h3>
                                                    <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{type.description}</p>
                                                </div>
                                            </button>
                                        );
                                    })}
                                </div>

                            ) : (
                                /* Step 2: configuration form */
                                <div className="space-y-5">
                                    <button
                                        onClick={() => dispatchModal({ type: 'BACK' })}
                                        className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors duration-150"
                                    >
                                        <ChevronRight className="w-4 h-4 rotate-180" /> Back
                                    </button>

                                    {/* Channel note */}
                                    {channelTypes.find(t => t.id === selectedType)?.note && (
                                        <div className="p-3.5 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg text-sm text-amber-700 dark:text-amber-400">
                                            {channelTypes.find(t => t.id === selectedType)!.note}
                                        </div>
                                    )}

                                    {/* WhatsApp provider selector */}
                                    {selectedType === 'whatsapp' && (
                                        <div className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535]">
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                                                Select Provider <span className="text-red-500">*</span>
                                            </label>
                                            <div className="grid grid-cols-2 gap-3">
                                                <button
                                                    type="button"
                                                    onClick={() => setWhatsappProvider('cloud_api')}
                                                    className={`p-3 rounded-lg border-2 text-left transition-all ${
                                                        whatsappProvider === 'cloud_api'
                                                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
                                                            : 'border-gray-200 dark:border-[#1e2535] hover:border-gray-300'
                                                    }`}
                                                >
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <Server className={`w-4 h-4 ${whatsappProvider === 'cloud_api' ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500'}`} />
                                                        <span className={`font-medium text-sm ${whatsappProvider === 'cloud_api' ? 'text-blue-900 dark:text-blue-100' : 'text-gray-700 dark:text-gray-300'}`}>
                                                            Cloud API
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-gray-500 dark:text-gray-500">Official Meta API for business use</p>
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => setWhatsappProvider('web_bridge')}
                                                    className={`p-3 rounded-lg border-2 text-left transition-all ${
                                                        whatsappProvider === 'web_bridge'
                                                            ? 'border-orange-500 bg-orange-50 dark:bg-orange-500/10'
                                                            : 'border-gray-200 dark:border-[#1e2535] hover:border-gray-300'
                                                    }`}
                                                >
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <QrCode className={`w-4 h-4 ${whatsappProvider === 'web_bridge' ? 'text-orange-600 dark:text-orange-400' : 'text-gray-500'}`} />
                                                        <span className={`font-medium text-sm ${whatsappProvider === 'web_bridge' ? 'text-orange-900 dark:text-orange-100' : 'text-gray-700 dark:text-gray-300'}`}>
                                                            Web Bridge
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-gray-500 dark:text-gray-500">QR-based for personal/development</p>
                                                </button>
                                            </div>

                                            {whatsappProvider === 'web_bridge' && (
                                                <div className="mt-3 space-y-2">
                                                    <div className="p-2.5 bg-green-50 dark:bg-green-500/5 border border-green-200 dark:border-green-500/20 rounded-lg flex items-start gap-2">
                                                        <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                                                        <p className="text-xs text-green-700 dark:text-green-400">
                                                            Bridge is running in Docker. Just give this channel a name and click Connect — a QR code will appear instantly.
                                                        </p>
                                                    </div>
                                                    <div className="p-2.5 bg-orange-50 dark:bg-orange-500/5 border border-orange-200 dark:border-orange-500/20 rounded-lg flex items-start gap-2">
                                                        <AlertTriangle className="w-4 h-4 text-orange-500 dark:text-orange-400 flex-shrink-0 mt-0.5" />
                                                        <p className="text-xs text-orange-700 dark:text-orange-400">
                                                            Web Bridge uses unofficial methods. Use only for personal accounts, not business.
                                                        </p>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    <form onSubmit={handleSubmit} className="space-y-4">
                                        {/* Channel name */}
                                        <div>
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                                Channel Name <span className="text-red-500">*</span>
                                            </label>
                                            <input
                                                name="name"
                                                type="text"
                                                required
                                                placeholder={`e.g. "Support ${channelTypes.find(t => t.id === selectedType)?.name}"`}
                                                className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-500/50 focus:border-transparent outline-none transition-all duration-150 text-sm"
                                            />
                                        </div>

                                        {/* Dynamic fields */}
                                        {selectedType === 'whatsapp' ? (
                                            (whatsappProvider === 'cloud_api' ? whatsAppCloudFields : whatsAppBridgeFields).map(field => (
                                                <div key={field.name}>
                                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                                        {field.label}{field.required && <span className="text-red-500 ml-1">*</span>}
                                                    </label>
                                                    <input
                                                        name={field.name}
                                                        type={field.type}
                                                        required={field.required}
                                                        placeholder={field.placeholder}
                                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-500/50 focus:border-transparent outline-none transition-all duration-150 text-sm"
                                                    />
                                                    {field.help && <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">{field.help}</p>}
                                                </div>
                                            ))
                                        ) : (
                                            channelTypes.find(t => t.id === selectedType)?.fields.map(field => (
                                                <div key={field.name}>
                                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                                        {field.label}{field.required && <span className="text-red-500 ml-1">*</span>}
                                                    </label>
                                                    <input
                                                        name={field.name}
                                                        type={field.type}
                                                        required={field.required}
                                                        placeholder={field.placeholder}
                                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-500/50 focus:border-transparent outline-none transition-all duration-150 text-sm"
                                                    />
                                                </div>
                                            ))
                                        )}

                                        {/* Actions */}
                                        <div className="flex gap-3 pt-2">
                                            <button
                                                type="button"
                                                onClick={closeModal}
                                                className="px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 text-sm font-medium"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="submit"
                                                disabled={createMutation.isPending}
                                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-all duration-150 text-sm font-medium shadow-sm dark:shadow-blue-900/30"
                                            >
                                                {createMutation.isPending ? (
                                                    <><Loader2 className="w-4 h-4 animate-spin" /> {whatsappProvider === 'web_bridge' && selectedType === 'whatsapp' ? 'Generating QR…' : 'Connecting…'}</>
                                                ) : (
                                                    <><CheckCircle className="w-4 h-4" /> {whatsappProvider === 'web_bridge' && selectedType === 'whatsapp' ? 'Connect & Show QR' : 'Connect'}</>
                                                )}
                                            </button>
                                        </div>
                                    </form>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Provider Switch Modal (#8 ARIA) ───────────────────────────── */}
            {showProviderSwitch && (
                <div
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="provider-switch-title"
                    onKeyDown={e => e.key === 'Escape' && setShowProviderSwitch(null)}
                    className="fixed inset-0 bg-black/60 dark:bg-black/75 flex items-center justify-center p-4 z-50 backdrop-blur-sm"
                >
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl max-w-md w-full shadow-2xl border border-gray-200 dark:border-[#1e2535]">
                        <div className="p-6 border-b border-gray-200 dark:border-[#1e2535]">
                            <h3 id="provider-switch-title" className="text-lg font-bold text-gray-900 dark:text-white">
                                Switch WhatsApp Provider
                            </h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                This will disconnect the current session and switch authentication methods.
                            </p>
                        </div>
                        <div className="p-6 space-y-3">
                            <button
                                onClick={() => switchProviderMutation.mutate({ id: showProviderSwitch, provider: 'cloud_api' })}
                                disabled={switchProviderMutation.isPending}
                                className="w-full p-4 border-2 border-blue-200 dark:border-blue-500/30 hover:border-blue-500 dark:hover:border-blue-400 rounded-xl text-left transition-all group"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400">Switch to Cloud API</span>
                                    <Server className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400">Official Meta Business API. Best for production use.</p>
                            </button>

                            <button
                                onClick={() => switchProviderMutation.mutate({ id: showProviderSwitch, provider: 'web_bridge' })}
                                disabled={switchProviderMutation.isPending}
                                className="w-full p-4 border-2 border-orange-200 dark:border-orange-500/30 hover:border-orange-500 dark:hover:border-orange-400 rounded-xl text-left transition-all group"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="font-semibold text-gray-900 dark:text-white group-hover:text-orange-600 dark:group-hover:text-orange-400">Switch to Web Bridge</span>
                                    <QrCode className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400">QR-based authentication. For personal/development use.</p>
                            </button>

                            <button
                                onClick={() => setShowProviderSwitch(null)}
                                className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-[#1e2535] transition-all duration-150 text-sm font-medium"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Test Message Modal ────────────────────────────────────────── */}
            {testChannel && (
                <TestMessageModal
                    channel={testChannel}
                    onClose={() => setTestChannel(null)}
                />
            )}
        </div>
    );
}
