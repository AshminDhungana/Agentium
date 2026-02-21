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
    QrCode,
    Server,
    AlertTriangle,
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
type WhatsAppProvider = 'cloud_api' | 'web_bridge';

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
        provider?: WhatsAppProvider;
        bridge_url?: string;
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
    help?: string;
}

interface ChannelTypeDefinition {
    id: ChannelTypeSlug;
    name: string;
    Icon: React.FC<{ className?: string }>;
    description: string;
    color: ColorKey;
    fields: ChannelField[];
    note?: string;
    providerSelector?: boolean; // For WhatsApp dual-mode
}

// ─── Color palette ────────────────────────────────────────────────────────────

type ColorKey = 'green' | 'purple' | 'blue' | 'red' | 'indigo' | 'gray' | 'cyan' | 'teal' | 'orange' | 'pink' | 'slate';

const colorMap: Record<ColorKey, { bg: string; darkBg: string; text: string; darkText: string }> = {
    green:  { bg: 'bg-green-100',  darkBg: 'dark:bg-green-500/10',  text: 'text-green-600',  darkText: 'dark:text-green-400'  },
    purple: { bg: 'bg-purple-100', darkBg: 'dark:bg-purple-500/10', text: 'text-purple-600', darkText: 'dark:text-purple-400' },
    blue:   { bg: 'bg-blue-100',   darkBg: 'dark:bg-blue-500/10',   text: 'text-blue-600',   darkText: 'dark:text-blue-400'   },
    red:    { bg: 'bg-red-100',    darkBg: 'dark:bg-red-500/10',    text: 'text-red-600',    darkText: 'dark:text-red-400'    },
    indigo: { bg: 'bg-indigo-100', darkBg: 'dark:bg-indigo-500/10', text: 'text-indigo-600', darkText: 'dark:text-indigo-400' },
    gray:   { bg: 'bg-gray-100',   darkBg: 'dark:bg-gray-500/10',   text: 'text-gray-600',   darkText: 'dark:text-gray-400'   },
    cyan:   { bg: 'bg-cyan-100',   darkBg: 'dark:bg-cyan-500/10',   text: 'text-cyan-600',   darkText: 'dark:text-cyan-400'   },
    teal:   { bg: 'bg-teal-100',   darkBg: 'dark:bg-teal-500/10',   text: 'text-teal-600',   darkText: 'dark:text-teal-400'   },
    orange: { bg: 'bg-orange-100', darkBg: 'dark:bg-orange-500/10', text: 'text-orange-600', darkText: 'dark:text-orange-400' },
    pink:   { bg: 'bg-pink-100',   darkBg: 'dark:bg-pink-500/10',   text: 'text-pink-600',   darkText: 'dark:text-pink-400'   },
    slate:  { bg: 'bg-slate-100',  darkBg: 'dark:bg-slate-500/10',  text: 'text-slate-600',  darkText: 'dark:text-slate-400'  },
};

// ─── WhatsApp Provider Fields ────────────────────────────────────────────────

const whatsAppCloudFields: ChannelField[] = [
    { name: 'phone_number_id', label: 'Phone Number ID', type: 'text',     placeholder: '123456789012345', required: true, help: 'From Meta Business Manager' },
    { name: 'access_token',    label: 'Access Token',    type: 'password', placeholder: 'EAAxxxxx...',     required: true, help: 'Permanent token from Meta' },
    { name: 'verify_token',    label: 'Verify Token',    type: 'text',     placeholder: 'my_verify_secret', help: 'Custom secret for webhook verification' },
    { name: 'app_secret',      label: 'App Secret',      type: 'password', placeholder: 'Optional', help: 'For webhook signature verification' },
];

// web_bridge needs no user-supplied fields — bridge_url and bridge_token
// are injected from the backend env (WHATSAPP_BRIDGE_URL / WHATSAPP_BRIDGE_TOKEN).
const whatsAppBridgeFields: ChannelField[] = [];

// ─── Channel type definitions ─────────────────────────────────────────────────

const channelTypes: ChannelTypeDefinition[] = [
    {
        id: 'whatsapp',
        name: 'WhatsApp',
        Icon: Smartphone,
        description: 'Cloud API or Web Bridge (QR)',
        color: 'green',
        providerSelector: true,
        fields: [], // Dynamic based on provider selection
        note: 'Choose between official Meta Cloud API (business) or Web Bridge (personal/development)',
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
            { name: 'number',    label: 'Registered Number', type: 'tel',    placeholder: '+14155552671', required: true },
            { name: 'rpc_host', label: 'RPC Host',           type: 'text',   placeholder: '127.0.0.1' },
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
            { name: 'webhook_url',   label: 'Incoming Webhook URL',      type: 'text',     placeholder: 'https://xxxxx.webhook.office.com/webhookb2/...' },
            { name: 'tenant_id',     label: 'Tenant ID (Bot only)',      type: 'text',     placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
            { name: 'client_id',     label: 'Client ID (Bot only)',      type: 'text',     placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
            { name: 'client_secret', label: 'Client Secret (Bot only)',  type: 'password', placeholder: '••••••••' },
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
            { name: 'backend',     label: 'Backend',          type: 'text',     placeholder: 'applescript  or  bluebubbles' },
            { name: 'bb_url',      label: 'BlueBubbles URL',  type: 'text',     placeholder: 'http://localhost:1234' },
            { name: 'bb_password', label: 'BlueBubbles Pass', type: 'password', placeholder: '••••••••' },
        ],
    },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const statusConfig: Record<string, { dot: string; badge: string; label: string }> = {
    active:       { dot: 'bg-green-500',  badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',       label: 'Active'       },
    connected:    { dot: 'bg-green-500',  badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',       label: 'Connected'    },
    disconnected: { dot: 'bg-gray-400',   badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',           label: 'Disconnected' },
    error:        { dot: 'bg-red-500',    badge: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',               label: 'Error'        },
    pending:      { dot: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400',   label: 'Pending'      },
};

const getStatus = (s: string) => statusConfig[s] ?? { dot: 'bg-gray-400', badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400', label: s };

// ─── Component ────────────────────────────────────────────────────────────────

export function ChannelsPage() {
    const queryClient = useQueryClient();
    const [showAddModal, setShowAddModal]         = useState(false);
    const [selectedType, setSelectedType]         = useState<ChannelTypeSlug | null>(null);
    const [whatsappProvider, setWhatsappProvider] = useState<WhatsAppProvider>('cloud_api');
    const [qrCodeData, setQrCodeData]             = useState<string | null>(null);
    const [pollingChannelId, setPollingChannelId] = useState<string | null>(null);
    const [showProviderSwitch, setShowProviderSwitch] = useState<string | null>(null);
    const [qrStep, setQrStep]                             = useState(false);   // true = show QR screen

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
            
            // If WhatsApp Web Bridge, start polling for QR
            if (data.type === 'whatsapp' && data.config?.provider === 'web_bridge') {
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

    const switchProviderMutation = useMutation({
        mutationFn: ({ id, provider }: { id: string; provider: WhatsAppProvider }) => 
            api.post(`/api/v1/channels/${id}/whatsapp/switch-provider?new_provider=${provider}`).then(r => r.data),
        onSuccess: (data) => {
            toast.success(`Switched to ${data.provider === 'cloud_api' ? 'Cloud API' : 'Web Bridge'}`);
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            setShowProviderSwitch(null);
            // If switched to web_bridge, open the QR modal for this channel
            if (data.provider === 'web_bridge' && data.channel_id) {
                setShowAddModal(true);
                setSelectedType('whatsapp');
                setWhatsappProvider('web_bridge');
                setPollingChannelId(data.channel_id);
                pollForQR(data.channel_id);
            }
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to switch provider'),
    });

    // ── QR polling (WhatsApp Web Bridge) ─────────────────────────────────────
    const pollForQR = async (channelId: string) => {
        try {
            const response = await api.get(`/api/v1/channels/${channelId}/qr`);
            const data = response.data;

            if (data.authenticated || data.connected || data.status === 'active') {
                toast.success('WhatsApp connected successfully!');
                closeModal();
                queryClient.invalidateQueries({ queryKey: ['channels'] });
                return;
            }

            if (data.qr_code) {
                setQrCodeData(data.qr_code);
                setQrStep(true);   // transition to QR screen
            }

            // Keep polling while channel is pending and not yet authenticated
            if (pollingChannelId === channelId) {
                setTimeout(() => pollForQR(channelId), 3000);
            }
        } catch (err) {
            console.error('QR polling error:', err);
            // Retry on error — bridge may not have the QR ready yet
            if (pollingChannelId === channelId) {
                setTimeout(() => pollForQR(channelId), 4000);
            }
        }
    };

    useEffect(() => () => setPollingChannelId(null), []);

    const closeModal = () => {
        setShowAddModal(false);
        setSelectedType(null);
        setQrCodeData(null);
        setPollingChannelId(null);
        setWhatsappProvider('cloud_api');
        setQrStep(false);
    };

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (!selectedType) return;
        
        const formEl = e.target as HTMLFormElement;
        const fd = new FormData(formEl);
        
        // Get fields based on type
        let fields: ChannelField[] = [];
        if (selectedType === 'whatsapp') {
            fields = whatsappProvider === 'cloud_api' ? whatsAppCloudFields : whatsAppBridgeFields;
        } else {
            const typeDef = channelTypes.find(t => t.id === selectedType);
            fields = typeDef?.fields || [];
        }
        
        const config: Record<string, string> = {};
        
        // Add provider for WhatsApp
        if (selectedType === 'whatsapp') {
            config.provider = whatsappProvider;
            if (whatsappProvider === 'web_bridge') {
                // bridge_url & bridge_token come from backend env vars —
                // signal the backend to use its defaults by passing the sentinel.
                config.bridge_url   = 'env://whatsapp-bridge';
                config.bridge_token = 'env://WHATSAPP_BRIDGE_TOKEN';
            }
        }

        fields.forEach(f => {
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
        <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 transition-colors duration-200">

            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
                        Communication Channels
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm">
                        Connect external platforms to your AI agents
                    </p>
                </div>
                <button
                    onClick={() => setShowAddModal(true)}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm dark:shadow-blue-900/30"
                >
                    <Plus className="w-4 h-4" /> Add Channel
                </button>
            </div>

            {/* Error banner */}
            {error && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                    <p className="text-red-700 dark:text-red-400 text-sm">
                        Error loading channels. Please try refreshing the page.
                    </p>
                </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {[
                    { label: 'Total Channels', value: channels.length,  valueClass: 'text-gray-900 dark:text-white'    },
                    { label: 'Active',          value: activeCount,      valueClass: 'text-green-600 dark:text-green-400' },
                    { label: 'Received',        value: totalReceived,    valueClass: 'text-blue-600 dark:text-blue-400'   },
                    { label: 'Sent',            value: totalSent,        valueClass: 'text-purple-600 dark:text-purple-400' },
                ].map(stat => (
                    <div
                        key={stat.label}
                        className="bg-white dark:bg-[#161b27] p-5 rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none transition-colors duration-200"
                    >
                        <div className={`text-2xl font-bold ${stat.valueClass}`}>{stat.value}</div>
                        <div className="text-xs font-medium text-gray-500 dark:text-gray-500 mt-0.5 uppercase tracking-wide">{stat.label}</div>
                    </div>
                ))}
            </div>

            {/* Channel grid */}
            {isLoading ? (
                <div className="flex items-center justify-center h-64">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-blue-400" />
                </div>

            ) : channels.length === 0 ? (
                <div className="text-center py-16 bg-gray-50 dark:bg-[#161b27] rounded-2xl border border-dashed border-gray-300 dark:border-[#1e2535] transition-colors duration-200">
                    <div className="w-16 h-16 mx-auto rounded-full bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 flex items-center justify-center mb-4">
                        <Plus className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                        No channels connected
                    </h3>
                    <p className="text-gray-500 dark:text-gray-400 text-sm mb-5">
                        Connect WhatsApp, Slack, Discord, Signal and more
                    </p>
                    <button
                        onClick={() => setShowAddModal(true)}
                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors duration-150"
                    >
                        Add Your First Channel
                    </button>
                </div>

            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {channels.map(channel => {
                        const typeDef = channelTypes.find(t => t.id === channel.type);
                        const colors  = colorMap[typeDef?.color ?? 'blue'];
                        const Icon    = typeDef?.Icon ?? MessageCircle;
                        const status  = getStatus(channel.status);
                        
                        // WhatsApp provider badge
                        const isWhatsApp = channel.type === 'whatsapp';
                        const provider = channel.config?.provider || 'cloud_api';
                        const isBridge = provider === 'web_bridge';

                        return (
                            <div
                                key={channel.id}
                                className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] overflow-hidden shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150"
                            >
                                {/* Card header */}
                                <div className="p-5 border-b border-gray-100 dark:border-[#1e2535]">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-3">
                                            {/* Icon */}
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
                                            {isWhatsApp && (
                                                <button
                                                    onClick={() => setShowProviderSwitch(channel.id)}
                                                    title="Switch provider"
                                                    className="p-2 text-gray-400 dark:text-gray-500 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10 rounded-lg transition-all duration-150"
                                                >
                                                    <Server className="w-4 h-4" />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => testMutation.mutate(channel.id)}
                                                disabled={testMutation.isPending}
                                                title="Test connection"
                                                className="p-2 text-gray-400 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-all duration-150"
                                            >
                                                <RefreshCw className={`w-4 h-4 ${testMutation.isPending ? 'animate-spin' : ''}`} />
                                            </button>
                                            <button
                                                onClick={() => { if (confirm(`Delete "${channel.name}"?`)) deleteMutation.mutate(channel.id); }}
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
                                    {/* Badges */}
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

                                    {/* Provider-specific info */}
                                    {isWhatsApp && (
                                        <div className="p-3 bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#1e2535]">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                                                    Provider
                                                </span>
                                                <span className={`text-xs font-semibold ${
                                                    isBridge ? 'text-orange-600 dark:text-orange-400' : 'text-blue-600 dark:text-blue-400'
                                                }`}>
                                                    {isBridge ? 'Web Bridge (QR)' : 'Cloud API (Meta)'}
                                                </span>
                                            </div>
                                            {isBridge ? (
                                                <p className="text-xs text-gray-500 dark:text-gray-500">
                                                    Uses WebSocket bridge with QR authentication. Good for personal use.
                                                </p>
                                            ) : (
                                                <p className="text-xs text-gray-500 dark:text-gray-500">
                                                    Official Meta Business API. Required for production/business use.
                                                </p>
                                            )}
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

                                    {/* Extra info */}
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

                                    {/* Stats */}
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
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── Add Channel Modal ─────────────────────────────────────────── */}
            {showAddModal && (
                <div className="fixed inset-0 bg-black/60 dark:bg-black/75 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl dark:shadow-[0_24px_64px_rgba(0,0,0,0.6)] border border-gray-200 dark:border-[#1e2535]">

                        {/* Modal header */}
                        <div className="p-6 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between sticky top-0 bg-white dark:bg-[#161b27] z-10 rounded-t-2xl">
                            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                                {qrStep
                                    ? 'Scan QR Code'
                                    : selectedType
                                        ? `Configure ${channelTypes.find(t => t.id === selectedType)?.name}`
                                        : 'Add Channel'}
                            </h2>
                            <button aria-label="Close" onClick={closeModal}
                                className="p-2 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors duration-150"
                            >
                                <X className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                            </button>
                        </div>

                        <div className="p-6">
                            {/* Step 3: QR Code — shown after form submit for web_bridge */}
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
                                        Waiting for scan… refreshes every 3 s
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
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                    {channelTypes.map(type => {
                                        const colors = colorMap[type.color];
                                        return (
                                            <button
                                                key={type.id}
                                                onClick={() => setSelectedType(type.id)}
                                                className="flex items-center gap-3 p-4 border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#0f1117] hover:border-blue-400 dark:hover:border-blue-500/50 hover:bg-blue-50/30 dark:hover:bg-blue-500/5 rounded-xl transition-all duration-150 text-left group"
                                            >
                                                <div className={`w-10 h-10 rounded-lg ${colors.bg} ${colors.darkBg} flex items-center justify-center flex-shrink-0`}>
                                                    <type.Icon className={`w-5 h-5 ${colors.text} ${colors.darkText}`} />
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
                                /* Step 2: configure */
                                <div className="space-y-5">
                                    <button
                                        onClick={() => { setSelectedType(null); setQrCodeData(null); }}
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

                                    {/* WhatsApp Provider Selector */}
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
                                                    <p className="text-xs text-gray-500 dark:text-gray-500">
                                                        Official Meta API for business use
                                                    </p>
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
                                                    <p className="text-xs text-gray-500 dark:text-gray-500">
                                                        QR-based for personal/development
                                                    </p>
                                                </button>
                                            </div>
                                            
                                            {/* web_bridge info */}
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

                                        {/* Dynamic fields based on type/provider */}
                                        {selectedType === 'whatsapp' ? (
                                            // WhatsApp fields based on provider
                                            (whatsappProvider === 'cloud_api' ? whatsAppCloudFields : whatsAppBridgeFields).map(field => (
                                                <div key={field.name}>
                                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                                        {field.label}
                                                        {field.required && <span className="text-red-500 ml-1">*</span>}
                                                    </label>
                                                    <input
                                                        name={field.name}
                                                        type={field.type}
                                                        required={field.required}
                                                        placeholder={field.placeholder}
                                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-[#1e2535] rounded-lg bg-white dark:bg-[#0f1117] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-500/50 focus:border-transparent outline-none transition-all duration-150 text-sm"
                                                    />
                                                    {field.help && (
                                                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">{field.help}</p>
                                                    )}
                                                </div>
                                            ))
                                        ) : (
                                            // Other channel types
                                            channelTypes
                                                .find(t => t.id === selectedType)
                                                ?.fields.map(field => (
                                                    <div key={field.name}>
                                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                                            {field.label}
                                                            {field.required && <span className="text-red-500 ml-1">*</span>}
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

            {/* ── Provider Switch Modal ─────────────────────────────────────── */}
            {showProviderSwitch && (
                <div className="fixed inset-0 bg-black/60 dark:bg-black/75 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
                    <div className="bg-white dark:bg-[#161b27] rounded-2xl max-w-md w-full shadow-2xl border border-gray-200 dark:border-[#1e2535]">
                        <div className="p-6 border-b border-gray-200 dark:border-[#1e2535]">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
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
                                    <span className="font-semibold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400">
                                        Switch to Cloud API
                                    </span>
                                    <Server className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    Official Meta Business API. Best for production use.
                                </p>
                            </button>
                            
                            <button
                                onClick={() => switchProviderMutation.mutate({ id: showProviderSwitch, provider: 'web_bridge' })}
                                disabled={switchProviderMutation.isPending}
                                className="w-full p-4 border-2 border-orange-200 dark:border-orange-500/30 hover:border-orange-500 dark:hover:border-orange-400 rounded-xl text-left transition-all group"
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="font-semibold text-gray-900 dark:text-white group-hover:text-orange-600 dark:group-hover:text-orange-400">
                                        Switch to Web Bridge
                                    </span>
                                    <QrCode className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                                </div>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                    QR-based authentication. For personal/development use.
                                </p>
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
        </div>
    );
}