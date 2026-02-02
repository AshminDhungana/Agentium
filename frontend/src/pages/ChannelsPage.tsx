import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import {
    Smartphone,
    Slack,
    Mail,
    MessageCircle,
    Plus,
    Settings,
    Copy,
    CheckCircle,
    RefreshCw,
    Trash2,
    ChevronRight,
    Loader2,
    X
} from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { QRCodeSVG } from 'qrcode.react';

interface Channel {
    id: string;
    name: string;
    type: 'whatsapp' | 'slack' | 'telegram' | 'email';
    status: 'pending' | 'active' | 'error' | 'disconnected';
    config: {
        phone_number?: string;
        has_credentials: boolean;
        webhook_url?: string;
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
    type: 'whatsapp' | 'slack' | 'telegram' | 'email';
    config: Record<string, string>;
    default_agent_id?: string;
    auto_create_tasks: boolean;
    require_approval: boolean;
}

// Tailwind color mapping (dynamic classes don't work with purge)
const colorMap = {
    green: { bg: 'bg-green-100', darkBg: 'dark:bg-green-900/30', text: 'text-green-600' },
    purple: { bg: 'bg-purple-100', darkBg: 'dark:bg-purple-900/30', text: 'text-purple-600' },
    blue: { bg: 'bg-blue-100', darkBg: 'dark:bg-blue-900/30', text: 'text-blue-600' },
    red: { bg: 'bg-red-100', darkBg: 'dark:bg-red-900/30', text: 'text-red-600' }
};

export function ChannelsPage() {
    const queryClient = useQueryClient();
    const [showAddModal, setShowAddModal] = useState(false);
    const [selectedType, setSelectedType] = useState<string | null>(null);
    const [qrCodeData, setQrCodeData] = useState<string | null>(null);
    const [pollingChannelId, setPollingChannelId] = useState<string | null>(null);

    // Fetch channels
    const { data: channels = [], isLoading } = useQuery({
        queryKey: ['channels'],
        queryFn: async () => {
            const response = await api.get('/channels/');
            return response.data as Channel[];
        }
    });

    // Create channel mutation
    const createMutation = useMutation({
        mutationFn: async (data: ChannelFormData) => {
            const response = await api.post('/channels/', data);
            return response.data;
        },
        onSuccess: (data: any) => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            toast.success('Channel created successfully');

            if (data.type === 'whatsapp') {
                setPollingChannelId(data.id);
                pollForQR(data.id);
            } else {
                setShowAddModal(false);
                setSelectedType(null);
            }
        },
        onError: (error: any) => {
            toast.error(error.response?.data?.detail || 'Failed to create channel');
        }
    });

    // Delete channel mutation
    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/channels/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['channels'] });
            toast.success('Channel deleted');
        }
    });

    // Test connection mutation
    const testMutation = useMutation({
        mutationFn: async (id: string) => {
            const response = await api.post(`/channels/${id}/test`);
            return response.data;
        },
        onSuccess: (data: any) => {
            if (data.success) {
                toast.success('Connection successful!');
            } else {
                toast.error(`Connection failed: ${data.error}`);
            }
            queryClient.invalidateQueries({ queryKey: ['channels'] });
        }
    });

    // Poll for QR code (WhatsApp)
    const pollForQR = async (channelId: string) => {
        try {
            const response = await api.get(`/channels/${channelId}/qr`);
            if (response.data.qr_code) {
                setQrCodeData(response.data.qr_code);
            } else if (response.data.status === 'active') {
                toast.success('WhatsApp connected successfully!');
                setShowAddModal(false);
                setSelectedType(null);
                setQrCodeData(null);
                setPollingChannelId(null);
                queryClient.invalidateQueries({ queryKey: ['channels'] });
                return;
            }

            if (pollingChannelId === channelId) {
                setTimeout(() => pollForQR(channelId), 3000);
            }
        } catch (error) {
            console.error('QR polling error:', error);
        }
    };

    // Cleanup polling
    useEffect(() => {
        return () => setPollingChannelId(null);
    }, []);

    const channelTypes = [
        {
            id: 'whatsapp',
            name: 'WhatsApp Business',
            Icon: Smartphone,
            description: 'Connect via WhatsApp Business API',
            color: 'green' as const,
            fields: [{ name: 'phone_number', label: 'Phone Number', type: 'tel', placeholder: '+1234567890' }]
        },
        {
            id: 'slack',
            name: 'Slack',
            Icon: Slack,
            description: 'Slack Bot integration',
            color: 'purple' as const,
            fields: [
                { name: 'bot_token', label: 'Bot Token', type: 'password', placeholder: 'xoxb-...' },
                { name: 'signing_secret', label: 'Signing Secret', type: 'password', placeholder: 'Optional' }
            ]
        },
        {
            id: 'telegram',
            name: 'Telegram',
            Icon: MessageCircle,
            description: 'Telegram Bot API',
            color: 'blue' as const,
            fields: [{ name: 'bot_token', label: 'Bot Token', type: 'password', placeholder: '123456789:ABC...' }]
        },
        {
            id: 'email',
            name: 'Email (SMTP)',
            Icon: Mail,
            description: 'SMTP/IMAP integration',
            color: 'red' as const,
            fields: [
                { name: 'smtp_host', label: 'SMTP Host', type: 'text', placeholder: 'smtp.gmail.com' },
                { name: 'smtp_port', label: 'Port', type: 'number', placeholder: '587' },
                { name: 'smtp_user', label: 'Username', type: 'email', placeholder: 'user@domain.com' },
                { name: 'smtp_pass', label: 'Password', type: 'password', placeholder: 'password' }
            ]
        }
    ];

    const handleCopyWebhook = (url: string) => {
        navigator.clipboard.writeText(url);
        toast.success('Webhook URL copied');
    };

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            active: 'bg-green-500',
            connected: 'bg-green-500',
            disconnected: 'bg-gray-400',
            error: 'bg-red-500',
            pending: 'bg-yellow-500'
        };
        return colors[status] || 'bg-gray-400';
    };

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
                    <Plus className="w-5 h-5" />
                    Add Channel
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                        {channels.length}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Total</div>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="text-2xl font-bold text-green-600">
                        {channels.filter((c: Channel) => c.status === 'active').length}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Active</div>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="text-2xl font-bold text-blue-600">
                        {channels.reduce((acc: number, c: Channel) => acc + (c.stats?.received || 0), 0)}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Received</div>
                </div>
                <div className="bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
                    <div className="text-2xl font-bold text-purple-600">
                        {channels.reduce((acc: number, c: Channel) => acc + (c.stats?.sent || 0), 0)}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Sent</div>
                </div>
            </div>

            {/* Channels Grid */}
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
                    <button
                        onClick={() => setShowAddModal(true)}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
                    >
                        Add Your First Channel
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {channels.map((channel: Channel) => {
                        const typeInfo = channelTypes.find(t => t.id === channel.type);
                        const colors = colorMap[typeInfo?.color || 'blue'];
                        const Icon = typeInfo?.Icon || MessageCircle;

                        return (
                            <div
                                key={channel.id}
                                className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
                            >
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
                                                    {channel.type} • {channel.status}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => testMutation.mutate(channel.id)}
                                                disabled={testMutation.isPending}
                                                className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg"
                                            >
                                                <RefreshCw className={`w-5 h-5 ${testMutation.isPending ? 'animate-spin' : ''}`} />
                                            </button>
                                            <button
                                                onClick={() => {
                                                    if (confirm('Delete this channel?')) {
                                                        deleteMutation.mutate(channel.id);
                                                    }
                                                }}
                                                className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                                            >
                                                <Trash2 className="w-5 h-5" />
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <div className="p-6 space-y-4">
                                    {channel.config?.webhook_url && (
                                        <div>
                                            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1.5">
                                                Webhook URL
                                            </label>
                                            <div className="flex gap-2">
                                                <code className="flex-1 text-xs bg-gray-100 dark:bg-gray-900 px-3 py-2 rounded-lg text-gray-600 dark:text-gray-400 truncate font-mono">
                                                    {channel.config.webhook_url}
                                                </code>
                                                <button
                                                    onClick={() => handleCopyWebhook(channel.config.webhook_url!)}
                                                    className="px-3 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg"
                                                >
                                                    <Copy className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    <div className="flex items-center gap-6 pt-4 border-t border-gray-100 dark:border-gray-700">
                                        <div className="text-sm">
                                            <span className="text-gray-500 dark:text-gray-400">Received: </span>
                                            <span className="font-semibold text-gray-900 dark:text-white">
                                                {channel.stats?.received || 0}
                                            </span>
                                        </div>
                                        <div className="text-sm">
                                            <span className="text-gray-500 dark:text-gray-400">Sent: </span>
                                            <span className="font-semibold text-gray-900 dark:text-white">
                                                {channel.stats?.sent || 0}
                                            </span>
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
                        <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between sticky top-0 bg-white dark:bg-gray-800">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                Add Channel
                            </h2>
                            <button
                                onClick={() => {
                                    setShowAddModal(false);
                                    setSelectedType(null);
                                    setQrCodeData(null);
                                    setPollingChannelId(null);
                                }}
                                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5 text-gray-500" />
                            </button>
                        </div>

                        <div className="p-6">
                            {!selectedType ? (
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    {channelTypes.map((type) => (
                                        <button
                                            key={type.id}
                                            onClick={() => setSelectedType(type.id)}
                                            className="flex items-center gap-4 p-4 border-2 border-gray-200 dark:border-gray-700 rounded-xl transition-all text-left hover:border-blue-500 hover:shadow-md"
                                        >
                                            <div className={`w-12 h-12 rounded-lg ${colorMap[type.color].bg} ${colorMap[type.color].darkBg} flex items-center justify-center`}>
                                                <type.Icon className={`w-6 h-6 ${colorMap[type.color].text}`} />
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-900 dark:text-white">
                                                    {type.name}
                                                </h3>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                                    {type.description}
                                                </p>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            ) : (
                                <div className="space-y-6">
                                    <button
                                        onClick={() => setSelectedType(null)}
                                        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 mb-4"
                                    >
                                        <ChevronRight className="w-4 h-4 rotate-180" />
                                        Back
                                    </button>

                                    {selectedType === 'whatsapp' && qrCodeData && (
                                        <div className="text-center space-y-4 p-6 bg-green-50 dark:bg-green-900/20 rounded-xl">
                                            <div className="inline-block p-4 bg-white rounded-xl shadow-lg">
                                                <QRCodeSVG value={qrCodeData} size={256} level="H" />
                                            </div>
                                            <p className="text-green-700 dark:text-green-400">
                                                Scan with WhatsApp to connect
                                            </p>
                                        </div>
                                    )}

                                    <form onSubmit={(e) => {
                                        e.preventDefault();
                                        const formEl = e.target as HTMLFormElement;
                                        const formData = new FormData(formEl);
                                        createMutation.mutate({
                                            name: formData.get('name') as string,
                                            type: selectedType as any,
                                            config: Object.fromEntries(
                                                channelTypes.find(t => t.id === selectedType)?.fields.map(f => [f.name, formData.get(f.name) || '']) || []
                                            ),
                                            auto_create_tasks: true,
                                            require_approval: false
                                        });
                                    }} className="space-y-4">
                                        <div>
                                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                Channel Name
                                            </label>
                                            <input
                                                name="name"
                                                type="text"
                                                required
                                                className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                            />
                                        </div>

                                        {channelTypes.find(t => t.id === selectedType)?.fields.map((field) => (
                                            <div key={field.name}>
                                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                                    {field.label}
                                                </label>
                                                <input
                                                    name={field.name}
                                                    type={field.type}
                                                    placeholder={field.placeholder}
                                                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                                />
                                            </div>
                                        ))}

                                        <div className="flex gap-3 pt-4">
                                            <button
                                                type="button"
                                                onClick={() => setShowAddModal(false)}
                                                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="submit"
                                                disabled={createMutation.isPending}
                                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg"
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