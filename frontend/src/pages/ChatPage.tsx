import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketChat } from '@/hooks/useWebSocket';
import {
    Send,
    Crown,
    Bot,
    AlertCircle,
    Loader2,
    Wifi,
    WifiOff,
    CheckCircle
} from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';

interface Message {
    id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    timestamp: Date;
    metadata?: any;
}

export function ChatPage() {
    const [input, setInput] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const { user } = useAuthStore();

    // Use authenticated WebSocket
    const {
        isConnected,
        isConnecting,
        error,
        sendMessage: sendWsMessage
    } = useWebSocketChat((data) => {
        // Handle incoming WebSocket messages
        if (data.type === 'message' || data.type === 'system' || data.type === 'error') {
            const newMessage: Message = {
                id: crypto.randomUUID(),
                role: data.role || (data.type === 'error' ? 'system' : 'head_of_council'),
                content: data.content,
                timestamp: new Date(),
                metadata: data.metadata
            };
            setMessages(prev => [...prev, newMessage]);

            // Show toast for task creation
            if (data.metadata?.task_created) {
                toast.success(`Task ${data.metadata.task_id} created`);
            }
        }
    });

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !isConnected) return;

        // Add user message to UI immediately
        const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'sovereign',
            content: input.trim(),
            timestamp: new Date()
        };
        setMessages(prev => [...prev, userMessage]);

        // Send via WebSocket (authenticated)
        const sent = sendWsMessage(input.trim());

        if (sent) {
            setInput('');
        } else {
            toast.error('Failed to send message');
        }
    };

    const getStatusColor = () => {
        if (isConnected) return 'text-green-500';
        if (isConnecting) return 'text-yellow-500';
        return 'text-red-500';
    };

    const getStatusIcon = () => {
        if (isConnected) return <Wifi className="w-5 h-5" />;
        if (isConnecting) return <Loader2 className="w-5 h-5 animate-spin" />;
        return <WifiOff className="w-5 h-5" />;
    };

    return (
        <div className="h-[calc(100vh-4rem)] flex flex-col max-w-5xl mx-auto">
            {/* Header with Connection Status */}
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white">
                        <Crown className="w-6 h-6" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                            Command Interface
                            <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full font-medium ml-2">
                                00001
                            </span>
                        </h1>
                        <div className="flex items-center gap-2 mt-1">
                            <span className={getStatusColor()}>
                                {getStatusIcon()}
                            </span>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                                {isConnected ? 'Authenticated & Connected' :
                                    isConnecting ? 'Connecting...' :
                                        error || 'Disconnected'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto space-y-6 mb-6 pr-2">
                {messages.length === 0 && isConnected && (
                    <div className="text-center text-gray-500 dark:text-gray-400 mt-20">
                        <Bot className="w-16 h-16 mx-auto mb-4 opacity-50" />
                        <p>Connected to Head of Council</p>
                        <p className="text-sm">Issue your first command</p>
                    </div>
                )}

                {messages.map((message) => (
                    <div
                        key={message.id}
                        className={`flex gap-4 ${message.role === 'sovereign' ? 'flex-row-reverse' : ''}`}
                    >
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                            {message.role === 'sovereign' ?
                                <Crown className="w-5 h-5 text-yellow-600" /> :
                                <Bot className="w-5 h-5 text-blue-600" />
                            }
                        </div>

                        <div className={`flex-1 max-w-3xl ${message.role === 'sovereign' ? 'text-right' : ''}`}>
                            <div className={`inline-block text-left px-4 py-3 rounded-2xl shadow-sm ${message.role === 'sovereign'
                                ? 'bg-blue-600 text-white ml-12'
                                : message.role === 'system'
                                    ? 'bg-red-50 dark:bg-red-900/20 text-red-900 dark:text-red-300 mx-12'
                                    : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 mr-12'
                                }`}>
                                <div className="whitespace-pre-wrap text-sm">{message.content}</div>
                                {message.metadata?.task_created && (
                                    <div className="mt-2 pt-2 border-t border-white/20 text-xs flex items-center gap-1">
                                        <CheckCircle className="w-3 h-3" />
                                        Task {message.metadata.task_id} created
                                    </div>
                                )}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">
                                {format(message.timestamp, 'h:mm a')}
                            </div>
                        </div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                {!isConnected && !isConnecting && (
                    <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" />
                        Not connected. Please check authentication.
                    </div>
                )}

                <form onSubmit={handleSubmit} className="flex gap-2">
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSubmit(e);
                            }
                        }}
                        placeholder={isConnected ? "Issue your command..." : "Connecting..."}
                        disabled={!isConnected}
                        className="flex-1 px-4 py-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl resize-none text-gray-900 dark:text-white disabled:opacity-50"
                        rows={2}
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || !isConnected}
                        className="px-6 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
                    >
                        <Send className="w-5 h-5" />
                    </button>
                </form>
            </div>
        </div>
    );
}