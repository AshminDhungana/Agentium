import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import {
    Smartphone,
    Slack,
    Mail,
    MessageCircle,
    Plus,
    RefreshCw,
    Trash2,
    ChevronRight,
    Loader2,
    X,
    Copy,
    CheckCircle,
    Radio,
    Hash,
    Globe,
    Users,
    Send,
    Grid,
} from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { QRCodeSVG } from 'qrcode.react';

// ─── Types ───────────────────────────────────────────────────────────────────

type ChannelTypeSlug =
    | 'whatsapp'
    | 'slack'
    | 'telegram'
    | 'email'
    | 'discord'
    | 'signal'
    | 'google_chat'
    | 'teams'
    | 'zalo'
    | 'matrix'
    | 'imessage';

type ChannelStatus = 'pending' | 'active' | 'error' | 'disconnected';

interface Channel {
    id: string;
    name: string;
    type: ChannelTypeSlug;
    status: ChannelStatus;
    config: {
        phone_number?: string;
        has_credentials: boolean;
        webhook_url?: string;
        homeserver_url?: string;
        oa_id?: string;
        backend?: string;
        number?: string;
        bb_url?: string;
    };
    routing: {
        default_agent?: string;
        auto_create_tasks: boolean;
        require_approval: boolean;
    };
    stats: {
        received: number;
        sent: number;
        last_message?: string;
    };
}

interface ChannelFormData {
    name: string;
    type: ChannelTypeSlug;
    config: Record<string, string>;
    default_agent_id?: string;
    auto_create_tasks: boolean;
    require_approval: boolean;
}

interface ChannelField {
    name: string;
    label: string;
    type: string;
    placeholder: string;
    required?: boolean;
}

interface ChannelTypeDefinition {
    id: ChannelTypeSlug;
    name: string;
    Icon: React.FC<{ className?: string }>;
    description: string;
    color: ColorKey;
    fields: ChannelField[];
    note?: string;
}

// ─── Color palette ────────────────────────────────────────────────────────────

type ColorKey = 'green' | 'purple' | 'blue' | 'red' | 'indigo' | 'gray' | 'cyan' | 'teal' | 'orange' | 'pink' | 'slate';

const colorMap: Record<ColorKey, { bg: string; darkBg: string; text: string }> = {
    green:  { bg: 'bg-green-100',  darkBg: 'dark:bg-green-900/30',  text: 'text-green-600'  },
    purple: { bg: 'bg-purple-100', darkBg: 'dark:bg-purple-900/30', text: 'text-purple-600' },
    blue:   { bg: 'bg-blue-100',   darkBg: 'dark:bg-blue-900/30',   text: 'text-blue-600'   },
    red:    { bg: 'bg-red-100',    darkBg: 'dark:bg-red-900/30',    text: 'text-red-600'    },
    indigo: { bg: 'bg-indigo-100', darkBg: 'dark:bg-indigo-900/30', text: 'text-indigo-600' },
    gray:   { bg: 'bg-gray-100',   darkBg: 'dark:bg-gray-700/50',   text: 'text-gray-600'   },
    cyan:   { bg: 'bg-cyan-100',   darkBg: 'dark:bg-cyan-900/30',   text: 'text-cyan-600'   },
    teal:   { bg: 'bg-teal-100',   darkBg: 'dark:bg-teal-900/30',   text: 'text-teal-600'   },
    orange: { bg: 'bg-orange-100', darkBg: 'dark:bg-orange-900/30', text: 'text-orange-600' },
    pink:   { bg: 'bg-pink-100',   darkBg: 'dark:bg-pink-900/30',   text: 'text-pink-600'   },
    slate:  { bg: 'bg-slate-100',  darkBg: 'dark:bg-slate-700/50',  text: 'text-slate-600'  },
};

// ─── Channel type definitions ─────────────────────────────────────────────────

const channelTypes: ChannelTypeDefinition[] = [
    {
        id: 'whatsapp',
        name: 'WhatsApp Business',
        Icon: Smartphone,
        description: 'Meta Cloud API integration',
        color: 'green',
        fields: [
            { name: 'phone_number_id', label: 'Phone Number ID', type: 'text',     placeholder: '123456789012345', required: true },
            { name: 'access_token',    label: 'Access Token',    type: 'password', placeholder: 'EAAxxxxx...',     required: true },
            { name: 'verify_token',    label: 'Verify Token',    type: 'text',     placeholder: 'my_verify_secret' },
        ],
    },
    {
        id: 'slack',
        name: 'Slack',
        Icon: Slack,
        description: 'Slack Bot API integration',
        color: 'purple',
        fields: [
            { name: 'bot_token',      label: 'Bot Token',      type: 'password', placeholder: 'xoxb-...', required: true },
            { name: 'signing_secret', label: 'Signing Secret', type: 'password', placeholder: 'abc123...' },
        ],
    },
    {
        id: 'telegram',
        name: 'Telegram',
        Icon: Send,
        description: 'Telegram Bot API',
        color: 'blue',
        fields: [
            { name: 'bot_token', label: 'Bot Token', type: 'password', placeholder: '123456789:ABC-DEF...', required: true },
        ],
    },
    {
        id: 'email',
        name: 'Email (SMTP)',
        Icon: Mail,
        description: 'SMTP send / IMAP receive',
        color: 'red',
        fields: [
            { name: 'smtp_host',   label: 'SMTP Host',  type: 'text',     placeholder: 'smtp.gmail.com', required: true },
            { name: 'smtp_port',   label: 'Port',       type: 'number',   placeholder: '587' },
            { name: 'smtp_user',   label: 'Username',   type: 'email',    placeholder: 'user@domain.com', required: true },
            { name: 'smtp_pass',   label: 'Password',   type: 'password', placeholder: '••••••••',        required: true },
            { name: 'from_email',  label: 'From Email', type: 'email',    placeholder: 'noreply@domain.com' },
        ],
    },
    {
        id: 'discord',
        name: 'Discord',
        Icon: Hash,
        description: 'Discord Bot API',
        color: 'indigo',
        fields: [
            { name: 'bot_token',       label: 'Bot Token',        type: 'password', placeholder: 'MTIz...', required: true },
            { name: 'application_id',  label: 'Application ID',   type: 'text',     placeholder: '123456789012345678' },
        ],
    },
    {
        id: 'signal',
        name: 'Signal',
        Icon: Radio,
        description: 'signal-cli JSON-RPC daemon',
        color: 'gray',
        note: 'Requires signal-cli installed and registered on the server.',
        fields: [
            { name: 'number',    label: 'Registered Number', type: 'tel',  placeholder: '+14155552671', required: true },
            { name: 'rpc_host', label: 'RPC Host',           type: 'text', placeholder: '127.0.0.1' },
            { name: 'rpc_port', label: 'RPC Port',           type: 'number', placeholder: '7583' },
        ],
    },
    {
        id: 'google_chat',
        name: 'Google Chat',
        Icon: MessageCircle,
        description: 'Google Chat Bot API',
        color: 'cyan',
        fields: [
            { name: 'webhook_url', label: 'Incoming Webhook URL (simple)', type: 'text', placeholder: 'https://chat.googleapis.com/v1/spaces/...' },
            { name: 'room_id',     label: 'Default Space/Room ID',         type: 'text', placeholder: 'spaces/AAAAxxxxxxx' },
        ],
        note: 'For full two-way: paste Service Account JSON in config after creation.',
    },
    {
        id: 'teams',
        name: 'Microsoft Teams',
        Icon: Users,
        description: 'Teams Incoming Webhook or Bot Framework',
        color: 'teal',
        fields: [
            { name: 'webhook_url',   label: 'Incoming Webhook URL', type: 'text', placeholder: 'https://xxxxx.webhook.office.com/webhookb2/...' },
            { name: 'tenant_id',     label: 'Tenant ID (Bot only)', type: 'text', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
            { name: 'client_id',     label: 'Client ID (Bot only)', type: 'text', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
            { name: 'client_secret', label: 'Client Secret (Bot only)', type: 'password', placeholder: '••••••••' },
        ],
    },
    {
        id: 'zalo',
        name: 'Zalo',
        Icon: Globe,
        description: 'Zalo Official Account API',
        color: 'orange',
        fields: [
            { name: 'access_token', label: 'OA Access Token', type: 'password', placeholder: 'zalotoken...', required: true },
            { name: 'oa_id',        label: 'OA ID',           type: 'text',     placeholder: '1234567890' },
        ],
    },
    {
        id: 'matrix',
        name: 'Matrix',
        Icon: Grid,
        description: 'Matrix Client-Server API',
        color: 'pink',
        fields: [
            { name: 'homeserver_url', label: 'Homeserver URL',  type: 'text',     placeholder: 'https://matrix.org', required: true },
            { name: 'access_token',   label: 'Access Token',    type: 'password', placeholder: 'syt_...', required: true },
            { name: 'room_id',        label: 'Default Room ID', type: 'text',     placeholder: '!abcdef:matrix.org' },
        ],
    },
    {
        id: 'imessage',
        name: 'iMessage',
        Icon: MessageCircle,
        description: 'macOS only — AppleScript or BlueBubbles',
        color: 'slate',
        note: '⚠️ Requires macOS server with Messages.app (AppleScript) or BlueBubbles.',
        fields: [
            { name: 'backend',     label: 'Backend',           type: 'text',     placeholder: 'applescript  or  bluebubbles' },
            { name: 'bb_url',      label: 'BlueBubbles URL',   type: 'text',     placeholder: 'http://localhost:1234' },
            { name: 'bb_password', label: 'BlueBubbles Pass',  type: 'password', placeholder: '••••••••' },
        ],
    },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const getStatusColor = (s: string) =>
    ({ active: 'bg-green-500', connected: 'bg-green-500', disconnected: 'bg-gray-400', error: 'bg-red-500', pending: 'bg-yellow-500' }[s] ?? 'bg-gray-400');

const getStatusLabel = (s: string) =>
    ({ active: 'Active', connected: 'Connected', disconnected: 'Disconnected', error: 'Error', pending: 'Pending' }[s] ?? s);

// ─── Component ────────────────────────────────────────────────────────────────

export function ChannelsPage() {
    const queryClient = useQueryClient();
    const [showAddModal, setShowAddModal]   = useState(false);
    const [selectedType, setSelectedType]   = useState<ChannelTypeSlug | null>(null);
    const [qrCodeData, setQrCodeData]       = useState<string | null>(null);
    const [pollingChannelId, setPollingChannelId] = useState<string | null>(null);

    // ── fetch ─────────────────────────────────────────────────────────────────
    const { data: channelsData, isLoading, error } = useQuery({
        queryKey: ['channels'],
        queryFn: async () => {
            try {
                const response = await api.get('/api/v1/channels/');
                let data = response.data;
                if (!data) return [] as Channel[];
                if (typeof data === 'object' && !Array.isArray(data) && data.channels) data = data.channels;
                if (!Array.isArray(data)) return [] as Channel[];
                return data as Channel[];
            } catch {
                toast.error('Failed to load channels');
                return [] as Channel[];
            }
        },
        initialData: [] as Channel[],
        refetchOnWindowFocus: true,
    });

    const channels: Channel[] = Array.isArray(channelsData) ? channelsData : [];

    // ── mutations ─────────────────────────────────────────────────────────────
    const createMutation = useMutation({
        mutationFn: (data: ChannelFormData) => api.post('/api/v1/channels/', data).then(r => r.data),
        onSuccess: (data: Channel & { webhook_url?: string }) => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            toast.success('Channel created successfully');
            if (data.type === 'whatsapp') {
                setPollingChannelId(data.id);
                pollForQR(data.id);
            } else {
                closeModal();
            }
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to create channel'),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => api.delete(`/api/v1/channels/${id}`),
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['channels'] }); toast.success('Channel deleted'); },
    });

    const testMutation = useMutation({
        mutationFn: (id: string) => api.post(`/api/v1/channels/${id}/test`).then(r => r.data),
        onSuccess: (data: any) => {
            if (data.success) toast.success('Connection successful!');
            else toast.error(`Connection failed: ${data.error ?? 'Unknown error'}`);
            queryClient.invalidateQueries({ queryKey: ['channels'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Test failed'),
    });

    // ── QR polling (WhatsApp) ─────────────────────────────────────────────────
    const pollForQR = async (channelId: string) => {
        try {
            const response = await api.get(`/api/v1/channels/${channelId}/qr`);
            if (response.data.qr_code) {
                setQrCodeData(response.data.qr_code);
            } else if (response.data.status === 'active') {
                toast.success('WhatsApp connected successfully!');
                closeModal();
                queryClient.invalidateQueries({ queryKey: ['channels'] });
                return;
            }
            if (pollingChannelId === channelId) {
                setTimeout(() => pollForQR(channelId), 3000);
            }
        } catch (err) {
            console.error('QR polling error:', err);
        }
    };

    useEffect(() => () => setPollingChannelId(null), []);

    const closeModal = () => {
        setShowAddModal(false);
        setSelectedType(null);
        setQrCodeData(null);
        setPollingChannelId(null);
    };

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (!selectedType) return;
        const formEl = e.target as HTMLFormElement;
        const fd = new FormData(formEl);
        const typeDef = channelTypes.find(t => t.id === selectedType)!;
        const config: Record<string, string> = {};
        typeDef.fields.forEach(f => {
            const val = (fd.get(f.name) || '').toString();
            if (val) config[f.name] = val;
        });
        createMutation.mutate({
            name: fd.get('name') as string,
            type: selectedType,
            config,
            auto_create_tasks: true,
            require_approval: false,
        });
    };

    const handleCopyWebhook = (url: string) => {
        navigator.clipboard.writeText(url);
        toast.success('Webhook URL copied');
    };

    // ── stats ─────────────────────────────────────────────────────────────────
    const activeCount   = channels.filter(c => c.status === 'active').length;
    const totalReceived = channels.reduce((a, c) => a + (c.stats?.received || 0), 0);
    const totalSent     = channels.reduce((a, c) => a + (c.stats?.sent || 0), 0);

    // ─── Render ───────────────────────────────────────────────────────────────
    return (
        <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">

            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                        Communication Channels
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400">
                        Connect external platforms to your AI agents
                    </p>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                >
                    <Plus className="w-5 h-5" /> Add Channel
                </button>
            </div>

            {/* Error banner */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl">
                    <p className="text-red-700 dark:text-red-400">
                        Error loading channels. Please try refreshing the page.
                    </p>
                </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {[
                    { label: 'Total',    value: channels.length, color: 'text-gray-900 dark:text-white' },
                    { label: 'Active',   value: activeCount,     color: 'text-green-600' },
                    { label: 'Received', value: totalReceived,   color: 'text-blue-600' },
                    { label: 'Sent',     value: totalSent,       color: 'text-purple-600' },
                ].map(stat => (
                    <div key={stat.label} className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                        <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">{stat.label}</div>
                    </div>
                ))}
            </div>

            {/* Channel grid */}
            {isLoading ? (
                <div className="flex items-center justify-center h-64">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                </div>
            ) : channels.length === 0 ? (
                <div className="text-center py-16 bg-gray-50 dark:bg-gray-800/50 rounded-2xl border border-dashed border-gray-300 dark:border-gray-700">
                    <div className="w-16 h-16 mx-auto rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mb-4">
                        <Plus className="w-8 h-8 text-blue-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                        No channels connected
                    </h3>
                    <p className="text-gray-500 dark:text-gray-400 mb-4">
                        Connect WhatsApp, Slack, Discord, Signal and more
                    </p>
                    <button
                        onClick={() => setShowAddModal(true)}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
                    >
                        Add Your First Channel
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {channels.map(channel => {
                        const typeDef = channelTypes.find(t => t.id === channel.type);
                        const colors  = colorMap[typeDef?.color ?? 'blue'];
                        const Icon    = typeDef?.Icon ?? MessageCircle;

                        return (
                            <div key={channel.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                                {/* Card header */}
                                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-4">
                                            <div className={`w-12 h-12 rounded-xl ${colors.bg} ${colors.darkBg} flex items-center justify-center`}>
                                                <Icon className={`w-6 h-6 ${colors.text}`} />
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                                                    {channel.name}
                                                    <span className={`w-2 h-2 rounded-full ${getStatusColor(channel.status)}`} />
                                                </h3>
                                                <p className="text-sm text-gray-500 dark:text-gray-400 capitalize">
                                                    {typeDef?.name ?? channel.type} • {getStatusLabel(channel.status)}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => testMutation.mutate(channel.id)}
                                                disabled={testMutation.isPending}
                                                title="Test connection"
                                                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                                            >
                                                <RefreshCw className={`w-5 h-5 ${testMutation.isPending ? 'animate-spin' : ''}`} />
                                            </button>
                                            <button
                                                onClick={() => { if (confirm(`Delete "${channel.name}"?`)) deleteMutation.mutate(channel.id); }}
                                                title="Delete channel"
                                                className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                            >
                                                <Trash2 className="w-5 h-5" />
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* Card body */}
                                <div className="p-6 space-y-4">
                                    {/* Credentials badge */}
                                    <div className="flex items-center gap-2">
                                        {channel.config?.has_credentials ? (
                                            <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full">
                                                <CheckCircle className="w-3 h-3" /> Credentials configured
                                            </span>
                                        ) : (
                                            <span className="text-xs px-2 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded-full">
                                                ⚠ No credentials
                                            </span>
                                        )}
                                        {channel.routing?.require_approval && (
                                            <span className="text-xs px-2 py-1 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400 rounded-full">
                                                Requires approval
                                            </span>
                                        )}
                                    </div>

                                    {/* Webhook URL */}
                                    {channel.config?.webhook_url && (
                                        <div>
                                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                                                Webhook URL
                                            </label>
                                            <div className="flex gap-2">
                                                <code className="flex-1 text-xs bg-gray-100 dark:bg-gray-900 px-3 py-2 rounded-lg text-gray-600 dark:text-gray-400 truncate font-mono">
                                                    {channel.config.webhook_url}
                                                </code>
                                                <button
                                                    onClick={() => handleCopyWebhook(channel.config.webhook_url!)}
                                                    className="px-3 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                                                >
                                                    <Copy className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Extra info for specific channel types */}
                                    {channel.type === 'signal' && channel.config?.number && (
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            Number: <span className="font-mono">{channel.config.number}</span>
                                        </p>
                                    )}
                                    {channel.type === 'matrix' && channel.config?.homeserver_url && (
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            Homeserver: <span className="font-mono">{channel.config.homeserver_url}</span>
                                        </p>
                                    )}
                                    {channel.type === 'imessage' && (
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            Backend: <span className="font-mono">{channel.config?.backend ?? 'applescript'}</span>
                                            {channel.config?.bb_url && ` · ${channel.config.bb_url}`}
                                        </p>
                                    )}

                                    {/* Stats */}
                                    <div className="flex items-center gap-6 pt-4 border-t border-gray-100 dark:border-gray-700">
                                        <div className="text-sm">
                                            <span className="text-gray-500 dark:text-gray-400">Received: </span>
                                            <span className="font-semibold text-gray-900 dark:text-white">{channel.stats?.received ?? 0}</span>
                                        </div>
                                        <div className="text-sm">
                                            <span className="text-gray-500 dark:text-gray-400">Sent: </span>
                                            <span className="font-semibold text-gray-900 dark:text-white">{channel.stats?.sent ?? 0}</span>
                                        </div>
                                        {channel.stats?.last_message && (
                                            <div className="text-sm text-gray-500 dark:text-gray-400 ml-auto">
                                                {format(new Date(channel.stats.last_message), 'MMM d, h:mm a')}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Add Channel Modal */}
            {showAddModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
                    <div className="bg-white dark:bg-gray-800 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl">

                        {/* Modal header */}
                        <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between sticky top-0 bg-white dark:bg-gray-800 z-10">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                {selectedType
                                    ? `Configure ${channelTypes.find(t => t.id === selectedType)?.name}`
                                    : 'Add Channel'}
                            </h2>
                            <button onClick={closeModal} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                                <X className="w-5 h-5 text-gray-500" />
                            </button>
                        </div>

                        <div className="p-6">
                            {/* Step 1: pick type */}
                            {!selectedType ? (
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {channelTypes.map(type => {
                                        const colors = colorMap[type.color];
                                        return (
                                            <button
                                                key={type.id}
                                                onClick={() => setSelectedType(type.id)}
                                                className="flex items-center gap-4 p-4 border-2 border-gray-200 dark:border-gray-700 rounded-xl transition-all text-left hover:border-blue-500 hover:shadow-md"
                                            >
                                                <div className={`w-10 h-10 rounded-lg ${colors.bg} ${colors.darkBg} flex items-center justify-center flex-shrink-0`}>
                                                    <type.Icon className={`w-5 h-5 ${colors.text}`} />
                                                </div>
                                                <div className="min-w-0">
                                                    <h3 className="font-semibold text-gray-900 dark:text-white text-sm truncate">{type.name}</h3>
                                                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{type.description}</p>
                                                </div>
                                            </button>
                                        );
                                    })}
                                </div>
                            ) : (
                                /* Step 2: configure */
                                <div className="space-y-6">
                                    <button
                                        onClick={() => { setSelectedType(null); setQrCodeData(null); }}
                                        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                                    >
                                        <ChevronRight className="w-4 h-4 rotate-180" /> Back
                                    </button>

                                    {/* Channel note */}
                                    {channelTypes.find(t => t.id === selectedType)?.note && (
                                        <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg text-sm text-amber-700 dark:text-amber-400">
                                            {channelTypes.find(t => t.id === selectedType)!.note}
                                        </div>
                                    )}

                                    {/* WhatsApp QR code display */}
                                    {selectedType === 'whatsapp' && qrCodeData && (
                                        <div className="text-center space-y-4 p-6 bg-green-50 dark:bg-green-900/20 rounded-xl">
                                            <div className="inline-block p-4 bg-white rounded-xl shadow-lg">
                                                <QRCodeSVG value={qrCodeData} size={256} level="H" />
                                            </div>
                                            <p className="text-green-700 dark:text-green-400 text-sm">
                                                Scan with WhatsApp to connect
                                            </p>
                                        </div>
                                    )}

                                    <form onSubmit={handleSubmit} className="space-y-4">
                                        {/* Channel name */}
                                        <div>
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                Channel Name <span className="text-red-500">*</span>
                                            </label>
                                            <input
                                                name="name"
                                                type="text"
                                                required
                                                placeholder={`e.g. "Support ${channelTypes.find(t => t.id === selectedType)?.name}"`}
                                                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                            />
                                        </div>

                                        {/* Channel-specific fields */}
                                        {channelTypes
                                            .find(t => t.id === selectedType)
                                            ?.fields.map(field => (
                                                <div key={field.name}>
                                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                        {field.label}
                                                        {field.required && <span className="text-red-500 ml-1">*</span>}
                                                    </label>
                                                    <input
                                                        name={field.name}
                                                        type={field.type}
                                                        required={field.required}
                                                        placeholder={field.placeholder}
                                                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                    />
                                                </div>
                                            ))}

                                        {/* Actions */}
                                        <div className="flex gap-3 pt-4">
                                            <button
                                                type="button"
                                                onClick={closeModal}
                                                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="submit"
                                                disabled={createMutation.isPending}
                                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors"
                                            >
                                                {createMutation.isPending ? (
                                                    <><Loader2 className="w-4 h-4 animate-spin" /> Connecting...</>
                                                ) : (
                                                    <><CheckCircle className="w-4 h-4" /> Connect</>
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
        </div>
    );
}
