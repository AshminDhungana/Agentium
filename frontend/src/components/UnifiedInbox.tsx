import { useState } from 'react';
import { Smartphone, Slack, Mail, MessageCircle, User } from 'lucide-react';
import { format } from 'date-fns';

interface UnifiedMessage {
    id: string;
    channel: 'whatsapp' | 'slack' | 'email' | 'telegram';
    channelName: string;
    sender: string;
    content: string;
    timestamp: Date;
    status: 'pending' | 'processing' | 'responded';
    assignedAgent?: string;
    response?: string;
}

const STATUS_CLASSES: Record<string, string> = {
    pending:    'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20',
    processing: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20',
    responded:  'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20',
};

const FILTER_ACTIVE   = 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20';
const FILTER_INACTIVE = 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-[#1e2535] dark:text-gray-400 dark:border-[#2a3347]';

export function UnifiedInbox() {
    const [messages] = useState<UnifiedMessage[]>([
        {
            id: '1',
            channel: 'whatsapp',
            channelName: 'Support WhatsApp',
            sender: '+1-555-0199',
            content: 'I need help analyzing this dataset',
            timestamp: new Date(),
            status: 'processing',
            assignedAgent: '20001',
        },
    ]);
    const [filter, setFilter] = useState('all');

    const getChannelIcon = (channel: string) => {
        switch (channel) {
            case 'whatsapp': return Smartphone;
            case 'slack':    return Slack;
            case 'email':    return Mail;
            case 'telegram': return MessageCircle;
            default:         return MessageCircle;
        }
    };

    return (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] transition-colors duration-200">

            {/* Header */}
            <div className="p-5 border-b border-gray-100 dark:border-[#1e2535] flex items-center justify-between">
                <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                        <MessageCircle className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    Unified Inbox
                    <span className="text-xs font-normal text-gray-400 dark:text-gray-500">(Cross-Channel)</span>
                </h3>

                <div className="flex gap-1.5">
                    {['all', 'whatsapp', 'slack', 'email'].map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-1 text-xs rounded-full capitalize border transition-colors duration-150 ${
                                filter === f ? FILTER_ACTIVE : FILTER_INACTIVE
                            }`}
                        >
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Message list */}
            <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                {messages.map((msg) => {
                    const Icon = getChannelIcon(msg.channel);
                    return (
                        <div
                            key={msg.id}
                            className="p-4 hover:bg-gray-50 dark:hover:bg-[#0f1117] transition-colors duration-150"
                        >
                            <div className="flex items-start gap-4">
                                <div className="w-10 h-10 rounded-lg bg-gray-100 dark:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] flex items-center justify-center flex-shrink-0">
                                    <Icon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                                </div>

                                <div className="flex-1 min-w-0">
                                    <div className="flex flex-wrap items-center gap-2 mb-1">
                                        <span className="text-sm font-semibold text-gray-900 dark:text-white">
                                            {msg.sender}
                                        </span>
                                        <span className="text-xs text-gray-400 dark:text-gray-500">
                                            via {msg.channelName}
                                        </span>
                                        <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${STATUS_CLASSES[msg.status] || STATUS_CLASSES.pending}`}>
                                            {msg.status}
                                        </span>
                                    </div>

                                    <p className="text-sm text-gray-600 dark:text-gray-300 mb-2 truncate">
                                        {msg.content}
                                    </p>

                                    <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400 dark:text-gray-500">
                                        <span>{format(msg.timestamp, 'h:mm a')}</span>
                                        {msg.assignedAgent && (
                                            <span className="flex items-center gap-1">
                                                <User className="w-3 h-3" />
                                                Agent {msg.assignedAgent}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
