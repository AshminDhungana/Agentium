import { useState, useEffect, useRef } from 'react';
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
    CheckCircle,
    RefreshCw,
    Paperclip,
    Image as ImageIcon,
    File,
    X,
    Mic,
    MicOff,
    Pause,
    Download,
    Copy,
    Sparkles,
    Code,
    FileText,
    Video,
    Music,
    Archive,
    Maximize2,
    MoreHorizontal,
    Smile,
    Plus
} from 'lucide-react';
import { format, isToday, isYesterday } from 'date-fns';
import toast from 'react-hot-toast';
import { fileApi, UploadedFile as ApiUploadedFile } from '@/services/fileApi';
import { voiceApi } from '@/services/voiceApi';
import { chatApi } from '@/services/chatApi';

interface UploadedFile {
    id: string;
    file: File;
    preview?: string;
    apiFile?: ApiUploadedFile;
    isUploading?: boolean;
    uploadError?: string;
}

export interface Attachment {
    name: string;
    type: string;
    size: number;
    url?: string;
    data?: string;
    category?: string;
}

interface Message {
    id: string;
    role: 'sovereign' | 'head_of_council' | 'system';
    content: string;
    timestamp: Date;
    metadata?: any;
    attachments?: Attachment[];
}

export function ChatPage() {
    const [input, setInput] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
    const [isRecording, setIsRecording] = useState(false);
    const [isPaused, setIsPaused] = useState(false);
    const [recordingTime, setRecordingTime] = useState(0);
    const [showFileMenu, setShowFileMenu] = useState(false);
    const [imagePreview, setImagePreview] = useState<{ url: string; name: string } | null>(null);
    const [voiceAvailable, setVoiceAvailable] = useState<boolean | null>(null);
    const [showVoiceTooltip, setShowVoiceTooltip] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
    const [audioStream, setAudioStream] = useState<MediaStream | null>(null);

    const user = useAuthStore(state => state.user);
    const isAuthenticated = user?.isAuthenticated ?? false;

    const {
        isConnected,
        isConnecting,
        error,
        sendMessage: sendWsMessage,
        reconnect,
        connectionStats
    } = useWebSocketChat((data) => {
        if (data.type === 'message' || data.type === 'system' || data.type === 'error') {
            const newMessage: Message = {
                id: crypto.randomUUID(),
                role: data.role || (data.type === 'error' ? 'system' : 'head_of_council'),
                content: data.content,
                timestamp: new Date(),
                metadata: data.metadata
            };
            setMessages(prev => [...prev, newMessage]);

            if (data.metadata?.task_created) {
                toast.success(`Task ${data.metadata.task_id} created`);
            }
        }
    });

    useEffect(() => {
        if (isAuthenticated) {
            loadChatHistory();
        }
    }, [isAuthenticated]);

    useEffect(() => {
        if (isConnected) {
            checkVoiceAvailability();
        }
    }, [isConnected]);

    const checkVoiceAvailability = async () => {
        const status = await voiceApi.checkStatus();
        setVoiceAvailable(status.available);
    };

    const loadChatHistory = async () => {
        try {
            const history = await chatApi.getHistory(50);
            const formattedMessages: Message[] = history.messages.map(msg => ({
                id: msg.id,
                role: msg.role,
                content: msg.content,
                timestamp: new Date(msg.created_at),
                metadata: msg.metadata,
                attachments: msg.attachments
            }));
            setMessages(formattedMessages);
        } catch (error) {
            console.error('Failed to load chat history:', error);
        }
    };

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
        }
    }, [input]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() && uploadedFiles.length === 0) return;

        const attachments = uploadedFiles
            .filter(f => f.apiFile && !f.uploadError)
            .map(f => ({
                name: f.apiFile!.original_name,
                type: f.apiFile!.type,
                size: f.apiFile!.size,
                url: f.apiFile!.url,
                category: f.apiFile!.category
            }));

        const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'sovereign',
            content: input.trim() || '(file attachment)',
            timestamp: new Date(),
            attachments: attachments.length > 0 ? attachments : undefined
        };
        setMessages(prev => [...prev, userMessage]);

        const sent = sendWsMessage(JSON.stringify({
            content: input.trim(),
            attachments: attachments
        }));

        if (!sent) {
            toast.error('Failed to send message - not connected');
        }

        setInput('');
        setUploadedFiles([]);
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;

        const newFiles: UploadedFile[] = files.map(file => ({
            id: crypto.randomUUID(),
            file,
            isUploading: true
        }));

        setUploadedFiles(prev => [...prev, ...newFiles]);
        setShowFileMenu(false);

        try {
            const response = await fileApi.uploadFiles(files);

            setUploadedFiles(prev => {
                const updated = [...prev];
                response.files.forEach((apiFile, index) => {
                    const localIndex = updated.findIndex(f => f.id === newFiles[index]?.id);
                    if (localIndex !== -1) {
                        updated[localIndex] = {
                            ...updated[localIndex],
                            apiFile,
                            isUploading: false
                        };

                        if (apiFile.category === 'image' && files[index]) {
                            const reader = new FileReader();
                            reader.onload = (e) => {
                                setUploadedFiles(current =>
                                    current.map(f =>
                                        f.id === updated[localIndex].id
                                            ? { ...f, preview: e.target?.result as string }
                                            : f
                                    )
                                );
                            };
                            reader.readAsDataURL(files[index]);
                        }
                    }
                });
                return updated;
            });

            toast.success(`${response.total_uploaded} file(s) uploaded`);
        } catch (error: any) {
            setUploadedFiles(prev =>
                prev.map(f =>
                    newFiles.find(nf => nf.id === f.id)
                        ? { ...f, isUploading: false, uploadError: error.message }
                        : f
                )
            );
            toast.error(`Upload failed: ${error.message}`);
        }
    };

    const removeFile = (id: string) => {
        setUploadedFiles(prev => prev.filter(f => f.id !== id));
    };

    const downloadFile = async (attachment: Attachment) => {
        try {
            if (attachment.data) {
                const a = document.createElement('a');
                a.href = attachment.data;
                a.download = attachment.name;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                toast.success('Downloaded');
            } else if (attachment.url) {
                const response = await fetch(attachment.url);
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = attachment.name;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                toast.success('Downloaded');
            }
        } catch (error) {
            toast.error('Download failed');
        }
    };

    const handleVoiceButtonClick = async () => {
        if (isRecording) {
            stopRecording();
            return;
        }

        const isAvailable = await voiceApi.checkAvailability();
        if (!isAvailable) return;

        startRecording();
    };

    const startRecording = async () => {
        try {
            const { recorder, stream } = await voiceApi.startRecording();
            const chunks: BlobPart[] = [];

            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };

            recorder.onstop = async () => {
                const audioBlob = new Blob(chunks, { type: recorder.mimeType });
                stream.getTracks().forEach(track => track.stop());

                toast.loading('Transcribing voice...', { id: 'transcribing' });

                try {
                    const result = await voiceApi.transcribe(audioBlob);
                    setInput(prev => {
                        const separator = prev && !prev.endsWith(' ') ? ' ' : '';
                        return prev + separator + result.text;
                    });
                    toast.success('Voice transcribed', { id: 'transcribing' });
                } catch (error: any) {
                    if (!error.message?.includes('OpenAI provider')) {
                        toast.error(`Transcription failed: ${error.message}`, { id: 'transcribing' });
                    }
                }

                setIsRecording(false);
                setRecordingTime(0);
            };

            recorder.onerror = () => {
                toast.error('Recording error');
                setIsRecording(false);
                stream.getTracks().forEach(track => track.stop());
            };

            recorder.start();
            setMediaRecorder(recorder);
            setAudioStream(stream);
            setIsRecording(true);
            setRecordingTime(0);

            recordingIntervalRef.current = setInterval(() => {
                setRecordingTime(prev => prev + 1);
            }, 1000);

            toast.success('Recording started');
        } catch (error: any) {
            toast.error(`Microphone access denied: ${error.message}`);
        }
    };

    const stopRecording = () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
        if (audioStream) audioStream.getTracks().forEach(track => track.stop());
        if (recordingIntervalRef.current) clearInterval(recordingIntervalRef.current);
        setMediaRecorder(null);
        setAudioStream(null);
    };

    const copyMessage = (content: string) => {
        navigator.clipboard.writeText(content);
        toast.success('Copied');
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    const formatRecordingTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const formatMessageTime = (date: Date) => {
        if (isToday(date)) return format(date, 'h:mm a');
        if (isYesterday(date)) return 'Yesterday ' + format(date, 'h:mm a');
        return format(date, 'MMM d, h:mm a');
    };

    const getFileIcon = (type: string) => {
        if (type.startsWith('image/')) return <ImageIcon className="w-4 h-4" />;
        if (type.startsWith('video/')) return <Video className="w-4 h-4" />;
        if (type.startsWith('audio/')) return <Music className="w-4 h-4" />;
        if (type === 'application/pdf') return <FileText className="w-4 h-4" />;
        if (type.startsWith('text/')) return <Code className="w-4 h-4" />;
        if (type.includes('zip')) return <Archive className="w-4 h-4" />;
        return <File className="w-4 h-4" />;
    };

    const renderAttachment = (attachment: Attachment, isUser: boolean) => {
        const isImage = attachment.type?.startsWith('image/') || attachment.category === 'image';
        const isVideo = attachment.type?.startsWith('video/') || attachment.category === 'video';

        if (isImage) {
            const imageUrl = attachment.url || attachment.data;
            if (!imageUrl) return null;
            return (
                <div className="mt-2 relative group/img">
                    <img
                        src={imageUrl}
                        alt={attachment.name}
                        className="rounded-2xl max-w-sm max-h-80 object-cover cursor-pointer shadow-sm hover:shadow-md transition-shadow"
                        onClick={() => setImagePreview({ url: imageUrl, name: attachment.name })}
                    />
                    <button aria-label="Download File"
                        onClick={(e) => { e.stopPropagation(); downloadFile(attachment); }}
                        className="absolute top-2 right-2 p-2 bg-black/50 hover:bg-black/70 text-white rounded-lg opacity-0 group-hover/img:opacity-100 transition-opacity backdrop-blur-sm"
                    >
                        <Download className="w-4 h-4" />
                    </button>
                </div>
            );
        }

        if (isVideo) {
            return (
                <div className="mt-2">
                    <video controls className="rounded-2xl max-w-sm max-h-80 shadow-sm" preload="metadata">
                        <source src={attachment.url || attachment.data} type={attachment.type} />
                    </video>
                </div>
            );
        }

        return (
            <div className="mt-2">
                <div className={`flex items-center gap-3 p-3 rounded-xl max-w-sm ${
                    isUser ? 'bg-white/10' : 'bg-gray-100 dark:bg-[#1e2535]'
                }`}>
                    <div className={`p-2 rounded-lg ${isUser ? 'bg-white/20' : 'bg-gray-200 dark:bg-[#2a3347]'}`}>
                        {getFileIcon(attachment.type || '')}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium truncate ${isUser ? 'text-white' : 'text-gray-900 dark:text-gray-100'}`}>
                            {attachment.name}
                        </div>
                        <div className={`text-xs ${isUser ? 'text-white/70' : 'text-gray-500 dark:text-gray-400'}`}>
                            {formatFileSize(attachment.size || 0)}
                        </div>
                    </div>
                    <button aria-label="Download File"
                        onClick={() => downloadFile(attachment)}
                        className={`p-1.5 rounded-lg transition-colors ${isUser ? 'hover:bg-white/20' : 'hover:bg-gray-200 dark:hover:bg-[#2a3347]'}`}
                    >
                        <Download className="w-4 h-4" />
                    </button>
                </div>
            </div>
        );
    };

    if (!isAuthenticated) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6 transition-colors duration-200">
                <div className="text-center max-w-md">
                    <div className="w-20 h-20 bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6">
                        <AlertCircle className="w-10 h-10 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                        Authentication Required
                    </h2>
                    <p className="text-gray-500 dark:text-gray-400">
                        Please log in to access the Command Interface
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full bg-gray-50 dark:bg-[#0f1117] flex flex-col overflow-hidden transition-colors duration-200">
            <div className="w-full h-full flex flex-col">

                {/* ── Header ─────────────────────────────────────────────────── */}
                <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none">
                    <div className="px-6 py-4 max-w-6xl mx-auto">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <div className="relative">
                                    <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/25 dark:shadow-blue-900/40">
                                        <Crown className="w-5 h-5 text-white" />
                                    </div>
                                    {/* Connection status dot */}
                                    <div className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-[#161b27] transition-colors duration-300 ${
                                        isConnected ? 'bg-green-500' : 'bg-gray-400 dark:bg-gray-600'
                                    }`} />
                                </div>
                                <div>
                                    <h1 className="text-base font-semibold text-gray-900 dark:text-white leading-tight">
                                        Head of Council
                                    </h1>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                                        {isConnected ? (
                                            <span className="text-green-600 dark:text-green-400 font-medium">Active now</span>
                                        ) : isConnecting ? (
                                            'Connecting...'
                                        ) : (
                                            <span className="text-gray-400 dark:text-gray-500">Offline</span>
                                        )}
                                        {connectionStats.latencyMs && isConnected && (
                                            <span className="text-green-600 dark:text-green-500">· {connectionStats.latencyMs}ms</span>
                                        )}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                {error && (
                                    <span className="text-sm text-red-600 dark:text-red-400 max-w-xs truncate hidden sm:block">
                                        {error}
                                    </span>
                                )}
                                {!isConnected && !isConnecting && (
                                    <button
                                        onClick={reconnect}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-xl transition-all duration-150 flex items-center gap-2 shadow-sm dark:shadow-blue-900/30"
                                    >
                                        <RefreshCw className="w-4 h-4" />
                                        Reconnect
                                    </button>
                                )}
                                {isConnecting && (
                                    <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-gray-500">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Connecting...
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── Messages Area ──────────────────────────────────────────── */}
                <div className="flex-1 overflow-y-auto min-h-0 bg-gray-50 dark:bg-[#0f1117]">
                    <div className="px-6 py-6 max-w-6xl mx-auto">

                        {/* Empty state */}
                        {messages.length === 0 && (
                            <div className="flex items-center justify-center h-full min-h-[400px]">
                                <div className="text-center max-w-md">
                                    <div className="w-16 h-16 bg-gradient-to-br from-blue-50 to-purple-50 dark:from-blue-500/10 dark:to-purple-500/10 border border-blue-100 dark:border-blue-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-sm">
                                        <Sparkles className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                                    </div>
                                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                                        Start a Conversation
                                    </h2>
                                    <p className="text-gray-500 dark:text-gray-400 text-sm mb-8">
                                        Chat with the AI to manage tasks, spawn agents, and control your system
                                    </p>
                                    <div className="flex flex-wrap gap-2 justify-center">
                                        {['System status', 'Create task', 'List agents', 'Help'].map((suggestion) => (
                                            <button
                                                key={suggestion}
                                                onClick={() => setInput(suggestion)}
                                                className="px-4 py-2 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] hover:border-blue-300 dark:hover:border-blue-500/50 hover:bg-blue-50/30 dark:hover:bg-blue-500/5 rounded-xl text-sm text-gray-700 dark:text-gray-300 transition-all duration-150 shadow-sm dark:shadow-none"
                                            >
                                                {suggestion}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Messages */}
                        <div className="space-y-6 max-w-4xl mx-auto">
                            {messages.map((message, index) => {
                                const isUser = message.role === 'sovereign';
                                const showAvatar = index === 0 || messages[index - 1].role !== message.role;

                                return (
                                    <div key={message.id} className="group">
                                        <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>

                                            {/* Avatar */}
                                            <div className={`flex-shrink-0 ${showAvatar ? 'visible' : 'invisible'}`}>
                                                <div className={`w-9 h-9 rounded-2xl flex items-center justify-center shadow-sm ${
                                                    isUser
                                                        ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-500/25 dark:shadow-blue-900/40'
                                                        : message.role === 'system'
                                                        ? 'bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20'
                                                        : 'bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20'
                                                }`}>
                                                    {isUser ? (
                                                        <Crown className="w-4 h-4 text-white" />
                                                    ) : message.role === 'system' ? (
                                                        <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                                                    ) : (
                                                        <Bot className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                                    )}
                                                </div>
                                            </div>

                                            {/* Bubble */}
                                            <div className={`flex-1 ${isUser ? 'flex justify-end' : ''}`}>
                                                <div className={`inline-block max-w-xl ${isUser ? 'ml-12' : 'mr-12'}`}>
                                                    <div className={`px-4 py-3 rounded-2xl ${
                                                        isUser
                                                            ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/40'
                                                            : message.role === 'system'
                                                            ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-900 dark:text-red-300'
                                                            : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]'
                                                    }`}>
                                                        <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                                                            {message.content}
                                                        </p>

                                                        {message.attachments?.map((attachment, i) => (
                                                            <div key={i}>{renderAttachment(attachment, isUser)}</div>
                                                        ))}

                                                        {message.metadata?.task_created && (
                                                            <div className="mt-3 pt-3 border-t border-white/20 flex items-center gap-2 text-xs">
                                                                <CheckCircle className="w-3.5 h-3.5" />
                                                                Task {message.metadata.task_id} created
                                                            </div>
                                                        )}
                                                    </div>

                                                    {/* Timestamp & copy */}
                                                    <div className={`flex items-center gap-2 mt-1.5 px-1 ${isUser ? 'justify-end' : ''}`}>
                                                        <span className="text-xs text-gray-400 dark:text-gray-500">
                                                            {formatMessageTime(message.timestamp)}
                                                        </span>
                                                        {message.role !== 'system' && (
                                                            <button aria-label="Copy Message"
                                                                onClick={() => copyMessage(message.content)}
                                                                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-[#1e2535] rounded-lg transition-all duration-150"
                                                            >
                                                                <Copy className="w-3 h-3 text-gray-400 dark:text-gray-500" />
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {/* ── Input Area ─────────────────────────────────────────────── */}
                <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_-4px_20px_rgba(0,0,0,0.2)]">
                    <div className="px-6 py-4 max-w-6xl mx-auto">

                        {/* Connection error banner */}
                        {error && !isConnected && (
                            <div className="mb-3 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-center justify-between">
                                <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
                                    <WifiOff className="w-4 h-4 flex-shrink-0" />
                                    <span>{error}</span>
                                </div>
                                <button
                                    onClick={reconnect}
                                    className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 font-medium transition-colors"
                                >
                                    Try Again
                                </button>
                            </div>
                        )}

                        {/* File attachments preview */}
                        {uploadedFiles.length > 0 && (
                            <div className="mb-3 flex flex-wrap gap-2">
                                {uploadedFiles.map((file) => (
                                    <div key={file.id} className="relative group/file">
                                        <div className="flex items-center gap-2 pl-3 pr-2 py-2 bg-gray-100 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl">
                                            {file.preview && file.file.type.startsWith('image/') ? (
                                                <img src={file.preview} alt="" className="w-8 h-8 rounded-lg object-cover" />
                                            ) : (
                                                <div className="w-8 h-8 rounded-lg bg-gray-200 dark:bg-[#1e2535] flex items-center justify-center text-gray-500 dark:text-gray-400">
                                                    {getFileIcon(file.file.type)}
                                                </div>
                                            )}
                                            <span className="text-sm text-gray-700 dark:text-gray-300 max-w-[120px] truncate">
                                                {file.file.name}
                                            </span>
                                            {file.isUploading && (
                                                <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                                            )}
                                            <button aria-label="Remove File"
                                                onClick={() => removeFile(file.id)}
                                                className="p-1 hover:bg-gray-200 dark:hover:bg-[#1e2535] rounded-lg transition-colors text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                                            >
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Recording indicator */}
                        {isRecording && (
                            <div className="mb-3 flex items-center justify-between p-3 bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-500/10 dark:to-orange-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                                <div className="flex items-center gap-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                                        <span className="text-sm font-medium text-red-900 dark:text-red-400">
                                            Recording
                                        </span>
                                    </div>
                                    <span className="text-sm font-mono font-semibold text-red-900 dark:text-red-400">
                                        {formatRecordingTime(recordingTime)}
                                    </span>
                                </div>
                                <button
                                    onClick={stopRecording}
                                    className="px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors"
                                >
                                    Stop
                                </button>
                            </div>
                        )}

                        {/* Input row */}
                        <div className="flex items-end gap-2">

                            {/* Attach button */}
                            <div className="relative">
                                <button aria-label="Attach Files"
                                    type="button"
                                    onClick={() => setShowFileMenu(!showFileMenu)}
                                    disabled={isRecording || !isConnected}
                                    className="p-2.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-xl transition-all duration-150 disabled:opacity-40"
                                >
                                    <Plus className="w-5 h-5" />
                                </button>
                                {showFileMenu && (
                                    <>
                                        <div className="fixed inset-0 z-10" onClick={() => setShowFileMenu(false)} />
                                        <div className="absolute bottom-full left-0 mb-2 w-48 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-lg dark:shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden z-20">
                                            <button
                                                onClick={() => { fileInputRef.current?.click(); setShowFileMenu(false); }}
                                                className="w-full px-4 py-3 text-left text-sm hover:bg-gray-50 dark:hover:bg-[#1e2535] flex items-center gap-3 transition-colors duration-150"
                                            >
                                                <ImageIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                                                <span className="text-gray-700 dark:text-gray-300">Upload Files</span>
                                            </button>
                                        </div>
                                    </>
                                )}
                                <input aria-label="Upload Files" ref={fileInputRef} type="file" multiple onChange={handleFileSelect} className="hidden" accept="image/*,.pdf,.doc,.docx,.txt,.mp4,.mp3" />
                            </div>

                            {/* Text input */}
                            <div className="flex-1 bg-gray-100 dark:bg-[#0f1117] rounded-2xl border border-transparent dark:border-[#1e2535] focus-within:border-blue-500 dark:focus-within:border-blue-500/60 focus-within:bg-white dark:focus-within:bg-[#161b27] transition-all duration-150 shadow-none focus-within:shadow-sm dark:focus-within:shadow-[0_0_0_1px_rgba(59,130,246,0.15)]">
                                <textarea aria-label="Message" ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSubmit(e);
                                        }
                                    }}
                                    placeholder={isConnected ? 'Type a message...' : 'Reconnecting...'}
                                    disabled={isRecording || !isConnected}
                                    className="w-full px-4 py-3 bg-transparent border-0 resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none disabled:opacity-50 text-[15px]"
                                    rows={1}
                                    style={{ maxHeight: '150px' }}
                                />
                            </div>

                            {/* Voice button */}
                            <div className="relative">
                                <button
                                    type="button"
                                    onClick={handleVoiceButtonClick}
                                    disabled={!isConnected}
                                    onMouseEnter={() => voiceAvailable === false && setShowVoiceTooltip(true)}
                                    onMouseLeave={() => setShowVoiceTooltip(false)}
                                    className={`p-2.5 rounded-xl transition-all duration-150 disabled:opacity-40 ${
                                        isRecording
                                            ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/30'
                                            : voiceAvailable === false
                                            ? 'text-orange-500 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-500/10'
                                            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535]'
                                    }`}
                                >
                                    {isRecording ? <MicOff className="w-5 h-5" /> :
                                     voiceAvailable === false ? <AlertCircle className="w-5 h-5" /> :
                                     <Mic className="w-5 h-5" />}
                                </button>

                                {/* Voice unavailable tooltip */}
                                {showVoiceTooltip && voiceAvailable === false && (
                                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2.5 bg-gray-900 dark:bg-[#0f1117] border border-transparent dark:border-[#1e2535] text-white text-xs rounded-xl whitespace-nowrap z-50 shadow-xl">
                                        <div className="font-medium mb-0.5">Voice features unavailable</div>
                                        <div className="text-gray-300 dark:text-gray-400">Add OpenAI provider in Models page</div>
                                        <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-[#0f1117]" />
                                    </div>
                                )}
                            </div>

                            {/* Send button */}
                            <button aria-label="Send" 
                                onClick={handleSubmit}
                                disabled={(!input.trim() && uploadedFiles.length === 0) || isRecording || !isConnected}
                                className="p-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:bg-gray-200 dark:disabled:bg-[#1e2535] disabled:cursor-not-allowed text-white disabled:text-gray-400 dark:disabled:text-gray-600 rounded-xl transition-all duration-150 shadow-md shadow-blue-500/25 dark:shadow-blue-900/30 disabled:shadow-none"
                            >
                                <Send className="w-5 h-5" />
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Image Preview Modal ─────────────────────────────────────── */}
            {imagePreview && (
                <div
                    className="fixed inset-0 bg-black/90 dark:bg-black/95 z-50 flex items-center justify-center p-6 backdrop-blur-sm"
                    onClick={() => setImagePreview(null)}
                >
                    <button aria-label="Preview" onClick={() => setImagePreview(null)}
                        className="absolute top-6 right-6 p-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors"
                    >
                        <X className="w-6 h-6" />
                    </button>
                    <div className="max-w-7xl max-h-full" onClick={(e) => e.stopPropagation()}>
                        <img
                            src={imagePreview.url}
                            alt={imagePreview.name}
                            className="max-w-full max-h-[90vh] object-contain rounded-2xl shadow-2xl"
                        />
                        <div className="mt-4 text-center">
                            <p className="text-white/80 text-sm mb-3">{imagePreview.name}</p>
                            <button
                                onClick={() => {
                                    const a = document.createElement('a');
                                    a.href = imagePreview.url;
                                    a.download = imagePreview.name;
                                    a.click();
                                }}
                                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm rounded-xl transition-colors border border-white/10"
                            >
                                Download
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
