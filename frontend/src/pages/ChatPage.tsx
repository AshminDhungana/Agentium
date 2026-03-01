import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { inboxApi, UnifiedConversation, UnifiedMessage } from '@/services/inboxApi';
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
    Plus,
    MessageCircle,
    Smartphone,
    Slack,
    Mail,
    Inbox,
    Volume2,
    VolumeX,
    Settings2,
    ChevronDown,
    Globe,
    FolderOpen,
    Trash2,
    Eye,
    UploadCloud,
    HardDrive,
    Search,
    Filter,
} from 'lucide-react';
import { format, isToday, isYesterday } from 'date-fns';
import toast from 'react-hot-toast';
import { fileApi, UploadedFile as ApiUploadedFile } from '@/services/fileApi';
import { voiceApi } from '@/services/voiceApi';
import { chatApi } from '@/services/chatApi';
import { localVoice } from '@/services/localVoice';
// ── Voice Bridge additions ────────────────────────────────────────────────────
import { useVoiceBridge } from '@/hooks/useVoiceBridge';
import { VoiceInteractionEvent } from '@/services/voiceBridge';

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

type ActiveTab = 'ai' | 'inbox' | 'files';

// File browser types
interface BrowserFile {
    filename: string;
    stored_name: string;
    url: string;
    size: number;
    category: string;
    uploaded_at: string;
}

export function ChatPage() {
    // ── Tab state ──────────────────────────────────────────────────────────────
    const [activeTab, setActiveTab] = useState<ActiveTab>('ai');

    // ── AI Chat state ──────────────────────────────────────────────────────────
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
    const [isLocalMode, setIsLocalMode] = useState(false);
    const [interimTranscript, setInterimTranscript] = useState('');
    // Voice settings state
    const [showVoiceSettings, setShowVoiceSettings] = useState(false);
    const [selectedVoice, setSelectedVoice] = useState('alloy');
    const [selectedLanguage, setSelectedLanguage] = useState('');
    const [availableVoices, setAvailableVoices] = useState<{ id: string; name: string; description: string }[]>([]);
    const [availableLanguages, setAvailableLanguages] = useState<{ code: string; name: string }[]>([]);
    const [isSpeaking, setIsSpeaking] = useState<string | null>(null); // message id being spoken
    const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
    const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
    const processedMessageIds = useRef<Set<string>>(new Set());

    // ── Inbox state ────────────────────────────────────────────────────────────
    const [conversations, setConversations] = useState<UnifiedConversation[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [inboxLoading, setInboxLoading] = useState(false);
    const [replyContent, setReplyContent] = useState('');
    const [isSending, setIsSending] = useState(false);
    const inboxMessagesEndRef = useRef<HTMLDivElement>(null);

    // ── File Browser state ─────────────────────────────────────────────────────
    const [browserFiles, setBrowserFiles] = useState<BrowserFile[]>([]);
    const [browserLoading, setBrowserLoading] = useState(false);
    const [browserSearch, setBrowserSearch] = useState('');
    const [browserCategory, setBrowserCategory] = useState('all');
    const [browserStats, setBrowserStats] = useState<{ total_files: number; total_size_bytes: number; storage_limit_bytes: number; storage_used_percent: number } | null>(null);
    const [filePreview, setFilePreview] = useState<{ url: string; name: string; type: string } | null>(null);
    const [isDraggingOver, setIsDraggingOver] = useState(false);
    const [deletingFile, setDeletingFile] = useState<string | null>(null);
    const browserUploadRef = useRef<HTMLInputElement>(null);

    const user = useAuthStore(state => state.user);
    const isAuthenticated = user?.isAuthenticated ?? false;

    const {
        isConnected,
        isConnecting,
        error,
        sendMessage: sendWsMessage,
        reconnect,
        connectionStats,
        unreadCount,
        markAsRead,
        messageHistory,
        lastMessage,
    } = useWebSocketStore();

    // ── Voice Bridge integration ───────────────────────────────────────────────
    const handleVoiceInteraction = useCallback(
        (event: VoiceInteractionEvent) => {
            try {
                const ts = new Date(event.ts * 1000);

                // Append the user's spoken message
                setMessages(prev => [
                    ...prev,
                    {
                        id:        `voice-user-${event.ts}`,
                        role:      'sovereign' as const,
                        content:   event.user,
                        timestamp: ts,
                        metadata:  { source: 'voice' },
                    },
                ]);

                // Append the Head of Council's reply
                setMessages(prev => [
                    ...prev,
                    {
                        id:        `voice-reply-${event.ts}`,
                        role:      'head_of_council' as const,
                        content:   event.reply,
                        timestamp: ts,
                        metadata:  { source: 'voice' },
                    },
                ]);
            } catch (err) {
                console.warn('[ChatPage] Failed to append voice interaction:', err);
            }
        },
        [],
    );

    const { status: bridgeStatus } = useVoiceBridge(handleVoiceInteraction);

    // ── AI Chat effects ────────────────────────────────────────────────────────
    useEffect(() => {
        markAsRead();
    }, [markAsRead]);

    useEffect(() => {
        if (isAuthenticated) loadChatHistory();
    }, [isAuthenticated]);

    useEffect(() => {
        if (isConnected) checkVoiceAvailability();
    }, [isConnected]);

    useEffect(() => {
        const unsubscribe = useWebSocketStore.subscribe((state, prevState) => {
            if (
                state.lastMessage &&
                state.lastMessage !== prevState.lastMessage &&
                state.lastMessage.type === 'message'
            ) {
                const msg = state.lastMessage;
                const messageId = msg.timestamp || crypto.randomUUID();
                if (processedMessageIds.current.has(messageId)) return;
                processedMessageIds.current.add(messageId);
                const newMessage: Message = {
                    id: messageId,
                    role: msg.role || 'head_of_council',
                    content: msg.content,
                    timestamp: new Date(),
                    metadata: msg.metadata,
                };
                setMessages(prev => [...prev, newMessage]);
                if (msg.metadata?.task_created) toast.success(`Task ${msg.metadata.task_id} created`);
            }
        });
        return () => unsubscribe();
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
        }
    }, [input]);

    // ── Inbox effects ──────────────────────────────────────────────────────────
    useEffect(() => {
        if (activeTab === 'inbox' && conversations.length === 0) {
            loadConversations();
        }
    }, [activeTab]);

    useEffect(() => {
        if (activeTab === 'files') {
            loadBrowserFiles();
        }
    }, [activeTab]);

    useEffect(() => {
        const wsMsg = lastMessage as any;
        if (wsMsg?.type === 'message_created') loadConversations();
    }, [lastMessage]);

    useEffect(() => {
        if (selectedId) {
            inboxMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [selectedId, conversations]);

    // ── AI Chat methods ────────────────────────────────────────────────────────
    const checkVoiceAvailability = async () => {
        const status = await voiceApi.checkStatus();
        setVoiceAvailable(status.available);
        setIsLocalMode(status.provider === 'local');
        // Also fetch available voices and languages
        fetchVoiceOptions();
    };

    const fetchVoiceOptions = async () => {
        try {
            const [voicesRes, langsRes] = await Promise.all([
                fetch('/api/v1/voice/voices', {
                    headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
                }),
                fetch('/api/v1/voice/languages', {
                    headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
                }),
            ]);
            if (voicesRes.ok) {
                const data = await voicesRes.json();
                setAvailableVoices(data.voices || []);
                if (data.default && !selectedVoice) setSelectedVoice(data.default);
            }
            if (langsRes.ok) {
                const data = await langsRes.json();
                setAvailableLanguages(data.languages || []);
            }
        } catch (e) {
            console.warn('Could not fetch voice options', e);
        }
    };

    const handleSpeakMessage = async (messageId: string, content: string) => {
        // If already speaking this message, stop
        if (isSpeaking === messageId) {
            if (audioPlayerRef.current) {
                audioPlayerRef.current.pause();
                audioPlayerRef.current.src = '';
            }
            setIsSpeaking(null);
            return;
        }

        setIsSpeaking(messageId);
        const toastId = toast.loading('Synthesizing speech...');

        try {
            const formData = new FormData();
            formData.append('text', content.slice(0, 4096));
            formData.append('voice', selectedVoice);
            formData.append('speed', '1.0');

            const response = await fetch('/api/v1/voice/synthesize', {
                method: 'POST',
                headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` },
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail?.message || err.detail || 'Synthesis failed');
            }

            const data = await response.json();
            toast.dismiss(toastId);

            // Fetch and play audio
            const audioRes = await fetch(data.audio_url, {
                headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
            });
            const audioBlob = await audioRes.blob();
            const audioUrl = URL.createObjectURL(audioBlob);

            if (audioPlayerRef.current) {
                audioPlayerRef.current.pause();
                URL.revokeObjectURL(audioPlayerRef.current.src);
            }

            const audio = new Audio(audioUrl);
            audioPlayerRef.current = audio;
            audio.onended = () => {
                setIsSpeaking(null);
                URL.revokeObjectURL(audioUrl);
            };
            audio.onerror = () => {
                setIsSpeaking(null);
                toast.error('Audio playback failed');
            };
            audio.play();
        } catch (error: any) {
            toast.dismiss(toastId);
            toast.error(error.message || 'Speech synthesis failed');
            setIsSpeaking(null);
        }
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
                attachments: msg.attachments,
            }));
            setMessages(formattedMessages);
            formattedMessages.forEach(msg => processedMessageIds.current.add(msg.id));
        } catch (error) {
            console.error('Failed to load chat history:', error);
        }
    };

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
                category: f.apiFile!.category,
            }));

        const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'sovereign',
            content: input.trim() || '(file attachment)',
            timestamp: new Date(),
            attachments: attachments.length > 0 ? attachments : undefined,
        };
        setMessages(prev => [...prev, userMessage]);

        const sent = sendWsMessage(JSON.stringify({ content: input.trim(), attachments }));
        if (!sent) toast.error('Failed to send message - not connected');

        setInput('');
        setUploadedFiles([]);
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;

        const newFiles: UploadedFile[] = files.map(file => ({
            id: crypto.randomUUID(),
            file,
            isUploading: true,
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
                        updated[localIndex] = { ...updated[localIndex], apiFile, isUploading: false };
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

    const removeFile = (id: string) => setUploadedFiles(prev => prev.filter(f => f.id !== id));

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
        } catch {
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
        
        const status = await voiceApi.checkStatus();
        setIsLocalMode(status.provider === 'local');
        
        if (status.provider === 'local') {
            startLocalRecording();
        } else {
            startOpenAIRecording();
        }
    };

    const startLocalRecording = async () => {
        try {
            setIsRecording(true);
            setRecordingTime(0);
            setInterimTranscript('');
            
            // Start timer for UI
            recordingIntervalRef.current = setInterval(() => {
                setRecordingTime(prev => prev + 1);
            }, 1000);
            
            // Start local speech recognition
            await localVoice.transcribe(
                (result) => {
                    if (result.isFinal) {
                        setInput(prev => {
                            const separator = prev && !prev.endsWith(' ') ? ' ' : '';
                            return prev + separator + result.text;
                        });
                        setInterimTranscript('');
                    } else {
                        setInterimTranscript(result.text);
                    }
                },
                (error) => {
                    toast.error(`Voice error: ${error}`);
                    stopRecording();
                }
            );
            
            toast.success('Listening... Speak now');
        } catch (error: any) {
            toast.error(`Failed to start: ${error.message}`);
            setIsRecording(false);
        }
    };

    const startOpenAIRecording = async () => {
        try {
            const { recorder, stream } = await voiceApi.startRecording();
            const chunks: BlobPart[] = [];
            
            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };
            
            recorder.onstop = async () => {
                const audioBlob = new Blob(chunks, { type: recorder.mimeType });
                stream.getTracks().forEach(track => track.stop());
                
                toast.loading('Transcribing...', { id: 'transcribing' });
                
                try {
                    const result = await voiceApi.transcribe(audioBlob, selectedLanguage || undefined);
                    setInput(prev => {
                        const separator = prev && !prev.endsWith(' ') ? ' ' : '';
                        return prev + separator + result.text;
                    });
                    toast.success('Voice transcribed', { id: 'transcribing' });
                } catch (error: any) {
                    // If OpenAI fails, try local fallback
                    toast.error('Cloud transcription failed, trying local...', { id: 'transcribing' });
                    setIsLocalMode(true);
                    await startLocalRecording();
                    return;
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
            // If microphone fails, try local as fallback
            toast.error('Recording failed, trying local voice...');
            setIsLocalMode(true);
            await startLocalRecording();
        }
    };

    const stopRecording = async () => {
        if (isLocalMode) {
            // Stop local recognition
            await localVoice.stopTranscribe();
            localVoice.abortTranscribe();
        } else if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            // Stop OpenAI recording
            mediaRecorder.stop();
        }
        
        if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
        }
        
        if (recordingIntervalRef.current) {
            clearInterval(recordingIntervalRef.current);
        }
        
        setMediaRecorder(null);
        setAudioStream(null);
        setIsRecording(false);
        setInterimTranscript('');
    };

    const copyMessage = (content: string) => {
        navigator.clipboard.writeText(content);
        toast.success('Copied');
    };

    // ── Inbox methods ──────────────────────────────────────────────────────────
    const loadConversations = async () => {
        setInboxLoading(true);
        try {
            const res = await inboxApi.getConversations();
            setConversations(res.conversations);
        } catch (err: any) {
            toast.error(err.message || 'Failed to load conversations');
        } finally {
            setInboxLoading(false);
        }
    };

    const handleSendReply = async () => {
        if (!selectedId || !replyContent.trim()) return;
        setIsSending(true);
        try {
            await inboxApi.reply(selectedId, replyContent.trim());
            setReplyContent('');
            await loadConversations();
            toast.success('Reply sent');
        } catch (err: any) {
            toast.error(err.response?.data?.detail || err.message || 'Failed to send reply');
        } finally {
            setIsSending(false);
        }
    };

    // ── File Browser methods ───────────────────────────────────────────────────
    const loadBrowserFiles = async () => {
        setBrowserLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const [listRes, statsRes] = await Promise.all([
                fetch('/api/v1/files/list', { headers: { Authorization: `Bearer ${token}` } }),
                fetch('/api/v1/files/stats', { headers: { Authorization: `Bearer ${token}` } }),
            ]);
            if (listRes.ok) {
                const data = await listRes.json();
                setBrowserFiles(data.files || []);
            }
            if (statsRes.ok) {
                const data = await statsRes.json();
                setBrowserStats(data);
            }
        } catch (e) {
            toast.error('Failed to load files');
        } finally {
            setBrowserLoading(false);
        }
    };

    const handleBrowserUpload = async (fileList: FileList | null) => {
        if (!fileList || fileList.length === 0) return;
        const files = Array.from(fileList);
        const toastId = toast.loading(`Uploading ${files.length} file(s)…`);
        try {
            const response = await fileApi.uploadFiles(files);
            toast.success(`${response.total_uploaded} file(s) uploaded`, { id: toastId });
            await loadBrowserFiles();
        } catch (e: any) {
            toast.error(`Upload failed: ${e.message}`, { id: toastId });
        }
    };

    const handleBrowserDelete = async (filename: string) => {
        setDeletingFile(filename);
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`/api/v1/files/${filename}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error('Delete failed');
            toast.success('File deleted');
            setBrowserFiles(prev => prev.filter(f => f.stored_name !== filename));
            setBrowserStats(prev => prev ? { ...prev, total_files: prev.total_files - 1 } : null);
        } catch {
            toast.error('Failed to delete file');
        } finally {
            setDeletingFile(null);
        }
    };

    const handleBrowserDownload = async (file: BrowserFile) => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(file.url, { headers: { Authorization: `Bearer ${token}` } });
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = file.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast.success('Downloaded');
        } catch {
            toast.error('Download failed');
        }
    };

    const openBrowserPreview = (file: BrowserFile) => {
        const previewUrl = file.url.replace('/download/', '/preview/');
        setFilePreview({ url: previewUrl, name: file.filename, type: file.category });
    };

    const canPreview = (category: string) =>
        category === 'image' || category === 'document' || category === 'video';

    const getBrowserFileIcon = (category: string, size = 'w-5 h-5') => {
        switch (category) {
            case 'image': return <ImageIcon className={size} />;
            case 'video': return <Video className={size} />;
            case 'audio': return <Music className={size} />;
            case 'document': return <FileText className={size} />;
            case 'code': return <Code className={size} />;
            case 'archive': return <Archive className={size} />;
            case 'spreadsheet': return <FileText className={size} />;
            default: return <File className={size} />;
        }
    };

    const getCategoryColor = (category: string) => {
        switch (category) {
            case 'image': return 'text-pink-500 bg-pink-50 dark:bg-pink-500/10 border-pink-100 dark:border-pink-500/20';
            case 'video': return 'text-purple-500 bg-purple-50 dark:bg-purple-500/10 border-purple-100 dark:border-purple-500/20';
            case 'audio': return 'text-blue-500 bg-blue-50 dark:bg-blue-500/10 border-blue-100 dark:border-blue-500/20';
            case 'document': return 'text-red-500 bg-red-50 dark:bg-red-500/10 border-red-100 dark:border-red-500/20';
            case 'code': return 'text-green-500 bg-green-50 dark:bg-green-500/10 border-green-100 dark:border-green-500/20';
            case 'archive': return 'text-yellow-500 bg-yellow-50 dark:bg-yellow-500/10 border-yellow-100 dark:border-yellow-500/20';
            default: return 'text-gray-500 bg-gray-50 dark:bg-gray-500/10 border-gray-100 dark:border-gray-500/20';
        }
    };

    const filteredBrowserFiles = browserFiles.filter(f => {
        const matchesSearch = !browserSearch || f.filename.toLowerCase().includes(browserSearch.toLowerCase());
        const matchesCategory = browserCategory === 'all' || f.category === browserCategory;
        return matchesSearch && matchesCategory;
    });

    const browserCategories = ['all', ...Array.from(new Set(browserFiles.map(f => f.category)))];

    // ── Shared helpers ─────────────────────────────────────────────────────────
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

    const getChannelIcon = (channel?: string) => {
        switch (channel) {
            case 'whatsapp': return <Smartphone className="w-4 h-4" />;
            case 'slack': return <Slack className="w-4 h-4" />;
            case 'email': return <Mail className="w-4 h-4" />;
            case 'telegram': return <MessageCircle className="w-4 h-4" />;
            default: return <MessageCircle className="w-4 h-4" />;
        }
    };

    const renderAttachment = (attachment: Attachment, isUser: boolean) => {
        const isImage = attachment.type?.startsWith('image/') || attachment.category === 'image';

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
                    <button
                        aria-label="Download File"
                        onClick={() => downloadFile(attachment)}
                        className="absolute top-2 right-2 p-1.5 bg-black/40 hover:bg-black/60 text-white rounded-lg opacity-0 group-hover/img:opacity-100 transition-all"
                    >
                        <Download className="w-3.5 h-3.5" />
                    </button>
                </div>
            );
        }

        return (
            <div className="mt-2">
                <div className={`flex items-center gap-3 p-3 rounded-xl max-w-sm ${isUser ? 'bg-white/10' : 'bg-gray-100 dark:bg-[#1e2535]'}`}>
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
                    <button aria-label="Download File" onClick={() => downloadFile(attachment)}
                        className={`p-1.5 rounded-lg transition-colors ${isUser ? 'hover:bg-white/20' : 'hover:bg-gray-200 dark:hover:bg-[#2a3347]'}`}>
                        <Download className="w-4 h-4" />
                    </button>
                </div>
            </div>
        );
    };

    // ── Auth guard ─────────────────────────────────────────────────────────────
    if (!isAuthenticated) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center p-6">
                <div className="text-center max-w-md">
                    <div className="w-20 h-20 bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6">
                        <AlertCircle className="w-10 h-10 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">Authentication Required</h2>
                    <p className="text-gray-500 dark:text-gray-400">Please log in to access the Command Interface</p>
                </div>
            </div>
        );
    }

    const showUnreadBadge = unreadCount > 0;
    const selectedConv = conversations.find(c => c.id === selectedId);

    // ── Render ─────────────────────────────────────────────────────────────────
    return (
        <div className="h-full bg-gray-50 dark:bg-[#0f1117] flex flex-col overflow-hidden transition-colors duration-200">
            <div className="w-full h-full flex flex-col">

                {/* ── Header ──────────────────────────────────────────────────── */}
                <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none">
                    <div className="px-6 py-4 max-w-6xl mx-auto">
                        <div className="flex items-center justify-between">

                            {/* Left: avatar + title (changes with tab) */}
                            <div className="flex items-center gap-4">
                                <div className="relative">
                                    <div className={`w-11 h-11 rounded-2xl flex items-center justify-center shadow-lg ${
                                        activeTab === 'ai'
                                            ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-500/25 dark:shadow-blue-900/40'
                                            : activeTab === 'inbox'
                                            ? 'bg-gradient-to-br from-emerald-500 to-teal-600 shadow-emerald-500/25 dark:shadow-emerald-900/40'
                                            : 'bg-gradient-to-br from-violet-500 to-purple-600 shadow-violet-500/25 dark:shadow-violet-900/40'
                                    }`}>
                                        {activeTab === 'ai'
                                            ? <Crown className="w-5 h-5 text-white" />
                                            : activeTab === 'inbox'
                                            ? <Inbox className="w-5 h-5 text-white" />
                                            : <FolderOpen className="w-5 h-5 text-white" />
                                        }
                                    </div>
                                    {activeTab === 'ai' && (
                                        <div className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-[#161b27] transition-colors duration-300 ${
                                            isConnected ? 'bg-green-500' : 'bg-gray-400 dark:bg-gray-600'
                                        }`} />
                                    )}
                                    {showUnreadBadge && activeTab === 'ai' && (
                                        <div className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
                                            {unreadCount > 9 ? '9+' : unreadCount}
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <h1 className="text-base font-semibold text-gray-900 dark:text-white leading-tight">
                                        {activeTab === 'ai' ? 'Head of Council' : activeTab === 'inbox' ? 'Unified Inbox' : 'File Browser'}
                                    </h1>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
                                        {activeTab === 'ai' ? (
                                            isConnected ? (
                                                <span className="text-green-600 dark:text-green-400 font-medium">Active now</span>
                                            ) : isConnecting ? 'Connecting...' : (
                                                <span className="text-gray-400 dark:text-gray-500">Offline</span>
                                            )
                                        ) : activeTab === 'inbox' ? (
                                            <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                                                {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
                                            </span>
                                        ) : (
                                            <span className="text-violet-600 dark:text-violet-400 font-medium">
                                                {browserStats ? `${browserFiles.length} files · ${((browserStats.total_size_bytes) / (1024 * 1024)).toFixed(1)} MB used` : `${browserFiles.length} files`}
                                            </span>
                                        )}
                                        {activeTab === 'ai' && connectionStats.latencyMs && isConnected && (
                                            <span className="text-green-600 dark:text-green-500">· {connectionStats.latencyMs}ms</span>
                                        )}
                                    </p>
                                </div>
                            </div>

                            {/* Right: tab switcher + reconnect */}
                            <div className="flex items-center gap-3">
                                {activeTab === 'ai' && error && (
                                    <span className="text-sm text-red-600 dark:text-red-400 max-w-xs truncate hidden sm:block">{error}</span>
                                )}
                                {activeTab === 'ai' && !isConnected && !isConnecting && (
                                    <button
                                        onClick={reconnect}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-xl transition-all duration-150 flex items-center gap-2 shadow-sm"
                                    >
                                        <RefreshCw className="w-4 h-4" />
                                        Reconnect
                                    </button>
                                )}
                                {activeTab === 'ai' && isConnecting && (
                                    <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-gray-500">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Connecting...
                                    </div>
                                )}

                                {/* Voice Bridge status pill — shown only on AI tab */}
                                {activeTab === 'ai' && (
                                    <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${
                                        bridgeStatus === 'connected'
                                            ? 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20'
                                            : bridgeStatus === 'connecting'
                                            ? 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-500/10 border-yellow-200 dark:border-yellow-500/20'
                                            : 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-[#1e2535] border-gray-200 dark:border-[#1e2535]'
                                    }`} title={`Voice bridge: ${bridgeStatus}`}>
                                        {bridgeStatus === 'connecting'
                                            ? <Loader2 className="w-3 h-3 animate-spin" />
                                            : bridgeStatus === 'connected'
                                            ? <Mic className="w-3 h-3" />
                                            : <MicOff className="w-3 h-3" />
                                        }
                                        <span className="capitalize">{bridgeStatus === 'connected' ? 'Voice' : bridgeStatus}</span>
                                    </div>
                                )}

                                {/* Tab switcher pill */}
                                <div className="flex items-center bg-gray-100 dark:bg-[#0f1117] rounded-xl p-1 border border-gray-200 dark:border-[#1e2535]">
                                    <button
                                        onClick={() => setActiveTab('ai')}
                                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                                            activeTab === 'ai'
                                                ? 'bg-white dark:bg-[#161b27] text-blue-600 dark:text-blue-400 shadow-sm dark:shadow-[0_1px_4px_rgba(0,0,0,0.3)]'
                                                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                        }`}
                                    >
                                        <Crown className="w-3.5 h-3.5" />
                                        AI Chat
                                    </button>
                                    <button
                                        onClick={() => setActiveTab('inbox')}
                                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                                            activeTab === 'inbox'
                                                ? 'bg-white dark:bg-[#161b27] text-emerald-600 dark:text-emerald-400 shadow-sm dark:shadow-[0_1px_4px_rgba(0,0,0,0.3)]'
                                                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                        }`}
                                    >
                                        <Inbox className="w-3.5 h-3.5" />
                                        Inbox
                                        {conversations.length > 0 && activeTab !== 'inbox' && (
                                            <span className="ml-0.5 bg-emerald-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                                                {conversations.length > 9 ? '9+' : conversations.length}
                                            </span>
                                        )}
                                    </button>
                                    <button
                                        onClick={() => setActiveTab('files')}
                                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                                            activeTab === 'files'
                                                ? 'bg-white dark:bg-[#161b27] text-violet-600 dark:text-violet-400 shadow-sm dark:shadow-[0_1px_4px_rgba(0,0,0,0.3)]'
                                                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                        }`}
                                    >
                                        <FolderOpen className="w-3.5 h-3.5" />
                                        Files
                                        {browserFiles.length > 0 && activeTab !== 'files' && (
                                            <span className="ml-0.5 bg-violet-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                                                {browserFiles.length > 99 ? '99+' : browserFiles.length}
                                            </span>
                                        )}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── AI Chat Tab ──────────────────────────────────────────────── */}
                {activeTab === 'ai' && (
                    <>
                        {/* Messages Area */}
                        <div className="flex-1 overflow-y-auto min-h-0 bg-gray-50 dark:bg-[#0f1117]">
                            <div className="px-6 py-6 max-w-6xl mx-auto">
                                {messages.length === 0 && (
                                    <div className="flex items-center justify-center h-full min-h-[400px]">
                                        <div className="text-center max-w-md">
                                            <div className="w-16 h-16 bg-gradient-to-br from-blue-50 to-purple-50 dark:from-blue-500/10 dark:to-purple-500/10 border border-blue-100 dark:border-blue-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-sm">
                                                <Sparkles className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                                            </div>
                                            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Start a Conversation</h2>
                                            <p className="text-gray-500 dark:text-gray-400 text-sm mb-8">
                                                Chat with the AI to manage tasks, spawn agents, and control your system
                                            </p>
                                            <div className="flex flex-wrap gap-2 justify-center">
                                                {['System status', 'Create task', 'List agents', 'Help'].map((suggestion) => (
                                                    <button
                                                        key={suggestion}
                                                        onClick={() => setInput(suggestion)}
                                                        className="px-4 py-2 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] hover:border-blue-300 dark:hover:border-blue-500/50 hover:bg-blue-50/30 dark:hover:bg-blue-500/5 rounded-xl text-sm text-gray-700 dark:text-gray-300 transition-all duration-150 shadow-sm"
                                                    >
                                                        {suggestion}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}

                                <div className="space-y-6 max-w-4xl mx-auto">
                                    {messages.map((message, index) => {
                                        const isUser = message.role === 'sovereign';
                                        const showAvatar = index === 0 || messages[index - 1].role !== message.role;
                                        const isError = message.metadata?.error || message.content?.includes('⚠️');
                                        const isVoiceMessage = message.metadata?.source === 'voice';

                                        return (
                                            <div key={message.id} className="group">
                                                <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
                                                    <div className={`flex-shrink-0 ${showAvatar ? 'visible' : 'invisible'}`}>
                                                        <div className={`w-9 h-9 rounded-2xl flex items-center justify-center shadow-sm ${
                                                            isUser
                                                                ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-500/25 dark:shadow-blue-900/40'
                                                                : isError
                                                                ? 'bg-orange-100 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20'
                                                                : message.role === 'system'
                                                                ? 'bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20'
                                                                : 'bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20'
                                                        }`}>
                                                            {isUser ? (
                                                                <Crown className="w-4 h-4 text-white" />
                                                            ) : isError ? (
                                                                <AlertCircle className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                                                            ) : message.role === 'system' ? (
                                                                <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />
                                                            ) : (
                                                                <Bot className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                                            )}
                                                        </div>
                                                    </div>

                                                    <div className={`flex-1 ${isUser ? 'flex justify-end' : ''}`}>
                                                        <div className={`inline-block max-w-xl ${isUser ? 'ml-12' : 'mr-12'}`}>
                                                            <div className={`px-4 py-3 rounded-2xl ${
                                                                isUser
                                                                    ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/40'
                                                                    : isError
                                                                    ? 'bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 text-orange-900 dark:text-orange-300'
                                                                    : message.role === 'system'
                                                                    ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-900 dark:text-red-300'
                                                                    : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]'
                                                            }`}>
                                                                <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
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
                                                            <div className={`flex items-center gap-2 mt-1.5 px-1 ${isUser ? 'justify-end' : ''}`}>
                                                                <span className="text-xs text-gray-400 dark:text-gray-500">
                                                                    {formatMessageTime(message.timestamp)}
                                                                </span>
                                                                {/* Voice source badge */}
                                                                {isVoiceMessage && (
                                                                    <span className="flex items-center gap-0.5 text-[10px] text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-[#1e2535] px-1.5 py-0.5 rounded-md">
                                                                        <Mic className="w-2.5 h-2.5" />
                                                                        voice
                                                                    </span>
                                                                )}
                                                                {message.role !== 'system' && (
                                                                    <button aria-label="Copy Message"
                                                                        onClick={() => copyMessage(message.content)}
                                                                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-[#1e2535] rounded-lg transition-all duration-150"
                                                                    >
                                                                        <Copy className="w-3 h-3 text-gray-400 dark:text-gray-500" />
                                                                    </button>
                                                                )}
                                                                {message.role === 'head_of_council' && voiceAvailable && (
                                                                    <button
                                                                        aria-label={isSpeaking === message.id ? 'Stop Speaking' : 'Speak Message'}
                                                                        onClick={() => handleSpeakMessage(message.id, message.content)}
                                                                        className={`opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 dark:hover:bg-[#1e2535] rounded-lg transition-all duration-150 ${
                                                                            isSpeaking === message.id ? 'opacity-100 text-blue-500 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'
                                                                        }`}
                                                                    >
                                                                        {isSpeaking === message.id
                                                                            ? <VolumeX className="w-3 h-3" />
                                                                            : <Volume2 className="w-3 h-3" />
                                                                        }
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

                        {/* Input Area */}
                        <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_-4px_20px_rgba(0,0,0,0.2)]">
                            <div className="px-6 py-4 max-w-6xl mx-auto">
                                {error && !isConnected && (
                                    <div className="mb-3 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-xl flex items-center justify-between">
                                        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
                                            <WifiOff className="w-4 h-4 flex-shrink-0" />
                                            <span>{error}</span>
                                        </div>
                                        <button onClick={reconnect} className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 font-medium transition-colors">
                                            Try Again
                                        </button>
                                    </div>
                                )}

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
                                                    <span className="text-sm text-gray-700 dark:text-gray-300 max-w-[120px] truncate">{file.file.name}</span>
                                                    {file.isUploading && <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />}
                                                    <button aria-label="Remove File" onClick={() => removeFile(file.id)}
                                                        className="p-1 hover:bg-gray-200 dark:hover:bg-[#1e2535] rounded-lg transition-colors text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
                                                        <X className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {isRecording && (
                                    <div className="mb-3 flex items-center justify-between p-3 bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-500/10 dark:to-orange-500/10 border border-red-200 dark:border-red-500/20 rounded-xl">
                                        <div className="flex items-center gap-3">
                                            <div className="flex items-center gap-2">
                                                <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                                                <span className="text-sm font-medium text-red-900 dark:text-red-400">
                                                    {isLocalMode ? 'Listening (Local)' : 'Recording'}
                                                </span>
                                            </div>
                                            <span className="text-sm font-mono font-semibold text-red-900 dark:text-red-400">
                                                {formatRecordingTime(recordingTime)}
                                            </span>
                                            {interimTranscript && (
                                                <span className="text-sm text-gray-500 dark:text-gray-400 italic truncate max-w-xs">
                                                    "{interimTranscript}"
                                                </span>
                                            )}
                                        </div>
                                        <button 
                                            onClick={stopRecording} 
                                            className="px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition-colors"
                                        >
                                            Stop
                                        </button>
                                    </div>
                                )}

                                <div className="flex items-end gap-2">
                                    <div className="relative">
                                        <button aria-label="Attach Files" type="button" onClick={() => setShowFileMenu(!showFileMenu)}
                                            disabled={isRecording || !isConnected}
                                            className="p-2.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-xl transition-all duration-150 disabled:opacity-40">
                                            <Plus className="w-5 h-5" />
                                        </button>
                                        {showFileMenu && (
                                            <>
                                                <div className="fixed inset-0 z-10" onClick={() => setShowFileMenu(false)} />
                                                <div className="absolute bottom-full left-0 mb-2 w-48 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl shadow-lg dark:shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden z-20">
                                                    <button onClick={() => { fileInputRef.current?.click(); setShowFileMenu(false); }}
                                                        className="w-full px-4 py-3 text-left text-sm hover:bg-gray-50 dark:hover:bg-[#1e2535] flex items-center gap-3 transition-colors duration-150">
                                                        <ImageIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                                                        <span className="text-gray-700 dark:text-gray-300">Upload Files</span>
                                                    </button>
                                                    <button onClick={() => { setActiveTab('files'); setShowFileMenu(false); }}
                                                        className="w-full px-4 py-3 text-left text-sm hover:bg-gray-50 dark:hover:bg-[#1e2535] flex items-center gap-3 transition-colors duration-150 border-t border-gray-100 dark:border-[#1e2535]">
                                                        <FolderOpen className="w-4 h-4 text-violet-500 dark:text-violet-400" />
                                                        <span className="text-gray-700 dark:text-gray-300">Browse Files</span>
                                                    </button>
                                                </div>
                                            </>
                                        )}
                                        <input aria-label="Upload Files" ref={fileInputRef} type="file" multiple onChange={handleFileSelect}
                                            className="hidden" accept="image/*,.pdf,.doc,.docx,.txt,.mp4,.mp3" />
                                    </div>

                                    <div className="flex-1 bg-gray-100 dark:bg-[#0f1117] rounded-2xl border border-transparent dark:border-[#1e2535] focus-within:border-blue-500 dark:focus-within:border-blue-500/60 focus-within:bg-white dark:focus-within:bg-[#161b27] transition-all duration-150 shadow-none focus-within:shadow-sm dark:focus-within:shadow-[0_0_0_1px_rgba(59,130,246,0.15)]">
                                        <textarea aria-label="Message" ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
                                            placeholder={isConnected ? 'Type a message...' : 'Reconnecting...'}
                                            disabled={isRecording || !isConnected}
                                            className="w-full px-4 py-3 bg-transparent border-0 resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none disabled:opacity-50 text-[15px]"
                                            rows={1} style={{ maxHeight: '150px' }} />
                                    </div>

                                    <div className="relative">
                                        <div className="flex items-center">
                                            <button type="button" onClick={handleVoiceButtonClick} disabled={!isConnected}
                                                onMouseEnter={() => voiceAvailable === false && setShowVoiceTooltip(true)}
                                                onMouseLeave={() => setShowVoiceTooltip(false)}
                                                className={`p-2.5 rounded-l-xl transition-all duration-150 disabled:opacity-40 ${
                                                    isRecording
                                                        ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/30'
                                                        : voiceAvailable === false
                                                        ? 'text-orange-500 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-500/10'
                                                        : isLocalMode
                                                        ? 'text-green-500 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-500/10'
                                                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535]'
                                                }`}>
                                                {isRecording ? <MicOff className="w-5 h-5" /> : voiceAvailable === false ? <AlertCircle className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                                            </button>
                                            {voiceAvailable && !isRecording && (
                                                <button
                                                    type="button"
                                                    onClick={() => setShowVoiceSettings(v => !v)}
                                                    className="p-1.5 rounded-r-xl text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-all duration-150 border-l border-gray-200 dark:border-[#1e2535]"
                                                    aria-label="Voice Settings"
                                                >
                                                    <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-150 ${showVoiceSettings ? 'rotate-180' : ''}`} />
                                                </button>
                                            )}
                                        </div>

                                        {showVoiceTooltip && voiceAvailable === false && (
                                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2.5 bg-gray-900 dark:bg-[#0f1117] border border-transparent dark:border-[#1e2535] text-white text-xs rounded-xl whitespace-nowrap z-50 shadow-xl">
                                                <div className="font-medium mb-0.5">Voice features unavailable</div>
                                                <div className="text-gray-300 dark:text-gray-400">Add OpenAI provider in Models page</div>
                                                <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-[#0f1117]" />
                                            </div>
                                        )}

                                        {/* Voice Settings Panel */}
                                        {showVoiceSettings && (
                                            <>
                                                <div className="fixed inset-0 z-10" onClick={() => setShowVoiceSettings(false)} />
                                                <div className="absolute bottom-full right-0 mb-2 w-64 bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-2xl shadow-xl dark:shadow-[0_8px_32px_rgba(0,0,0,0.5)] overflow-hidden z-20">
                                                    <div className="px-4 py-3 border-b border-gray-100 dark:border-[#1e2535] flex items-center gap-2">
                                                        <Settings2 className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                                                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">Voice Settings</span>
                                                    </div>

                                                    {/* TTS Voice Selector */}
                                                    <div className="p-4 border-b border-gray-100 dark:border-[#1e2535]">
                                                        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
                                                            <Volume2 className="w-3.5 h-3.5" />
                                                            Speak Voice
                                                        </label>
                                                        <div className="grid grid-cols-2 gap-1.5">
                                                            {(availableVoices.length > 0 ? availableVoices : [
                                                                { id: 'alloy', name: 'Alloy', description: 'Neutral' },
                                                                { id: 'echo', name: 'Echo', description: 'Warm' },
                                                                { id: 'fable', name: 'Fable', description: 'British' },
                                                                { id: 'onyx', name: 'Onyx', description: 'Deep' },
                                                                { id: 'nova', name: 'Nova', description: 'Professional' },
                                                                { id: 'shimmer', name: 'Shimmer', description: 'Bright' },
                                                            ]).map(v => (
                                                                <button
                                                                    key={v.id}
                                                                    onClick={() => setSelectedVoice(v.id)}
                                                                    className={`px-2.5 py-2 rounded-lg text-left transition-all duration-150 ${
                                                                        selectedVoice === v.id
                                                                            ? 'bg-blue-50 dark:bg-blue-500/15 border border-blue-200 dark:border-blue-500/30 text-blue-700 dark:text-blue-300'
                                                                            : 'bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                                                                    }`}
                                                                >
                                                                    <div className="text-xs font-medium">{v.name}</div>
                                                                    <div className="text-[10px] opacity-60 mt-0.5">{v.description}</div>
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>

                                                    {/* STT Language Selector */}
                                                    <div className="p-4">
                                                        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
                                                            <Globe className="w-3.5 h-3.5" />
                                                            Transcription Language
                                                        </label>
                                                        <select
                                                            value={selectedLanguage}
                                                            onChange={e => setSelectedLanguage(e.target.value)}
                                                            className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl text-gray-700 dark:text-gray-300 focus:outline-none focus:border-blue-400 dark:focus:border-blue-500/60 transition-colors"
                                                        >
                                                            <option value="">Auto-detect</option>
                                                            {(availableLanguages.length > 0 ? availableLanguages : [
                                                                { code: 'en', name: 'English' },
                                                                { code: 'es', name: 'Spanish' },
                                                                { code: 'fr', name: 'French' },
                                                                { code: 'de', name: 'German' },
                                                                { code: 'it', name: 'Italian' },
                                                                { code: 'pt', name: 'Portuguese' },
                                                                { code: 'nl', name: 'Dutch' },
                                                                { code: 'zh', name: 'Chinese' },
                                                                { code: 'ja', name: 'Japanese' },
                                                                { code: 'ko', name: 'Korean' },
                                                            ]).map(l => (
                                                                <option key={l.code} value={l.code}>{l.name}</option>
                                                            ))}
                                                        </select>
                                                        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1.5">Hint for Whisper transcription</p>
                                                    </div>
                                                </div>
                                            </>
                                        )}
                                    </div>

                                    <button aria-label="Send" onClick={handleSubmit}
                                        disabled={(!input.trim() && uploadedFiles.length === 0) || isRecording || !isConnected}
                                        className="p-2.5 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 disabled:bg-gray-200 dark:disabled:bg-[#1e2535] disabled:cursor-not-allowed text-white disabled:text-gray-400 dark:disabled:text-gray-600 rounded-xl transition-all duration-150 shadow-md shadow-blue-500/25 dark:shadow-blue-900/30 disabled:shadow-none">
                                        <Send className="w-5 h-5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </>
                )}

                {/* ── Inbox Tab ────────────────────────────────────────────────── */}
                {activeTab === 'inbox' && (
                    <div className="flex-1 flex overflow-hidden">
                        {/* Conversation list */}
                        <div className="w-80 flex-shrink-0 bg-white dark:bg-[#161b27] border-r border-gray-200 dark:border-[#1e2535] flex flex-col">
                            <div className="p-4 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between">
                                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Active Conversations</h2>
                                {inboxLoading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
                            </div>
                            <div className="flex-1 overflow-y-auto">
                                {conversations.length === 0 && !inboxLoading ? (
                                    <div className="p-8 text-center">
                                        <div className="w-12 h-12 bg-gray-100 dark:bg-[#1e2535] rounded-2xl flex items-center justify-center mx-auto mb-3">
                                            <Inbox className="w-6 h-6 text-gray-400 dark:text-gray-500" />
                                        </div>
                                        <p className="text-sm text-gray-500 dark:text-gray-400">No active conversations</p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                                        {conversations.map(conv => {
                                            const latestMsg = conv.messages && conv.messages.length > 0
                                                ? conv.messages[conv.messages.length - 1]
                                                : null;
                                            const externalMsg = conv.messages?.find(m => m.sender_channel);
                                            const channelType = externalMsg?.sender_channel;

                                            return (
                                                <button
                                                    key={conv.id}
                                                    onClick={() => setSelectedId(conv.id)}
                                                    className={`w-full text-left px-4 py-3.5 flex items-center gap-3 transition-colors duration-150 ${
                                                        selectedId === conv.id
                                                            ? 'bg-emerald-50 dark:bg-emerald-500/10 border-r-2 border-emerald-500'
                                                            : 'hover:bg-gray-50 dark:hover:bg-[#1e2535]/50'
                                                    }`}
                                                >
                                                    <div className="w-10 h-10 rounded-full bg-gray-100 dark:bg-[#1e2535] flex items-center justify-center text-gray-500 dark:text-gray-400 flex-shrink-0">
                                                        {getChannelIcon(channelType)}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center justify-between mb-0.5">
                                                            <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                                                {conv.title || 'Unknown Sender'}
                                                            </span>
                                                            {conv.last_message_at && (
                                                                <span className="text-[11px] text-gray-400 dark:text-gray-500 whitespace-nowrap ml-2">
                                                                    {format(new Date(conv.last_message_at), 'h:mm a')}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                            {latestMsg ? latestMsg.content : 'No messages'}
                                                        </p>
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Message thread */}
                        <div className="flex-1 flex flex-col bg-gray-50 dark:bg-[#0f1117]">
                            {!selectedConv ? (
                                <div className="flex-1 flex items-center justify-center">
                                    <div className="text-center">
                                        <div className="w-16 h-16 bg-gray-100 dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-3xl flex items-center justify-center mx-auto mb-4">
                                            <MessageCircle className="w-8 h-8 text-gray-400 dark:text-gray-500" />
                                        </div>
                                        <p className="text-sm text-gray-500 dark:text-gray-400">Select a conversation to view messages</p>
                                    </div>
                                </div>
                            ) : (
                                <>
                                    {/* Thread header */}
                                    <div className="flex-shrink-0 px-6 py-4 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between">
                                        <h3 className="font-semibold text-gray-900 dark:text-white">{selectedConv.title}</h3>
                                        <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${
                                            selectedConv.is_active
                                                ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                                                : 'bg-gray-50 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700'
                                        }`}>
                                            {selectedConv.is_active ? 'Active' : 'Archived'}
                                        </span>
                                    </div>

                                    {/* Messages */}
                                    <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
                                        {selectedConv.messages?.map(msg => {
                                            const isAdmin = msg.role === 'system' || msg.metadata?.sent_by_admin;
                                            const isBot = msg.role === 'head_of_council';
                                            const isUser = !isAdmin && !isBot;

                                            return (
                                                <div key={msg.id} className={`flex max-w-[80%] ${isAdmin ? 'ml-auto' : ''}`}>
                                                    <div className={`p-4 rounded-2xl w-full ${
                                                        isAdmin
                                                            ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/30 rounded-tr-none'
                                                            : isBot
                                                            ? 'bg-white dark:bg-[#161b27] border border-purple-100 dark:border-purple-800/40 text-gray-800 dark:text-gray-200 shadow-sm rounded-tl-none'
                                                            : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm rounded-tl-none'
                                                    }`}>
                                                        {(isUser || isBot) && (
                                                            <div className="flex items-center gap-2 mb-2">
                                                                {isBot ? (
                                                                    <>
                                                                        <Bot className="w-3.5 h-3.5 text-purple-500" />
                                                                        <span className="text-xs font-semibold text-purple-600 dark:text-purple-400">AI Assistant</span>
                                                                    </>
                                                                ) : (
                                                                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 flex items-center gap-1">
                                                                        {getChannelIcon(msg.sender_channel)}
                                                                        {msg.sender_channel || 'Unknown Channel'}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                        <div className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</div>
                                                        <div className={`text-[10px] mt-2 text-right ${isAdmin ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'}`}>
                                                            {format(new Date(msg.created_at), 'h:mm a')}
                                                            {isAdmin && msg.metadata?.channel_routed && (
                                                                <span className="ml-1 opacity-70">(via {msg.metadata.channel_routed})</span>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                        <div ref={inboxMessagesEndRef} />
                                    </div>

                                    {/* Reply input — same style as AI chat input */}
                                    <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_-4px_20px_rgba(0,0,0,0.2)]">
                                        <div className="px-6 py-4">
                                            <div className="flex items-end gap-2">
                                                <div className="flex-1 bg-gray-100 dark:bg-[#0f1117] rounded-2xl border border-transparent dark:border-[#1e2535] focus-within:border-emerald-500 dark:focus-within:border-emerald-500/60 focus-within:bg-white dark:focus-within:bg-[#161b27] transition-all duration-150 shadow-none focus-within:shadow-sm">
                                                    <textarea
                                                        value={replyContent}
                                                        onChange={e => setReplyContent(e.target.value)}
                                                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendReply(); } }}
                                                        placeholder="Type a reply..."
                                                        className="w-full px-4 py-3 bg-transparent border-0 resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none text-[15px]"
                                                        rows={1}
                                                        style={{ maxHeight: '150px' }}
                                                    />
                                                </div>
                                                <button
                                                    onClick={handleSendReply}
                                                    disabled={!replyContent.trim() || isSending}
                                                    className="p-2.5 bg-emerald-600 hover:bg-emerald-700 dark:hover:bg-emerald-500 disabled:bg-gray-200 dark:disabled:bg-[#1e2535] disabled:cursor-not-allowed text-white disabled:text-gray-400 dark:disabled:text-gray-600 rounded-xl transition-all duration-150 shadow-md shadow-emerald-500/25 dark:shadow-emerald-900/30 disabled:shadow-none"
                                                >
                                                    {isSending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                                                </button>
                                            </div>
                                            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                                                Reply will be routed to the user's original channel.
                                            </p>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* ── Files Tab ──────────────────────────────────────────────────────── */}
            {activeTab === 'files' && (
                <div
                    className={`flex-1 flex flex-col overflow-hidden transition-colors duration-150 ${isDraggingOver ? 'bg-violet-50 dark:bg-violet-500/5' : ''}`}
                    onDragOver={e => { e.preventDefault(); setIsDraggingOver(true); }}
                    onDragLeave={() => setIsDraggingOver(false)}
                    onDrop={e => { e.preventDefault(); setIsDraggingOver(false); handleBrowserUpload(e.dataTransfer.files); }}
                >
                    {/* Toolbar */}
                    <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] px-6 py-3">
                        <div className="max-w-6xl mx-auto flex items-center gap-3">
                            {/* Search */}
                            <div className="relative flex-1 max-w-sm">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
                                <input
                                    type="text"
                                    placeholder="Search files…"
                                    value={browserSearch}
                                    onChange={e => setBrowserSearch(e.target.value)}
                                    className="w-full pl-9 pr-3 py-2 text-sm bg-gray-100 dark:bg-[#0f1117] border border-transparent dark:border-[#1e2535] rounded-xl text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-violet-400 dark:focus:border-violet-500/60 focus:bg-white dark:focus:bg-[#161b27] transition-all"
                                />
                            </div>

                            {/* Category filter */}
                            <div className="flex items-center gap-1.5 flex-wrap">
                                {browserCategories.map(cat => (
                                    <button
                                        key={cat}
                                        onClick={() => setBrowserCategory(cat)}
                                        className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all duration-150 ${
                                            browserCategory === cat
                                                ? 'bg-violet-100 dark:bg-violet-500/15 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-500/30'
                                                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-[#1e2535] border border-transparent'
                                        }`}
                                    >
                                        {cat}
                                    </button>
                                ))}
                            </div>

                            <div className="ml-auto flex items-center gap-2">
                                {/* Storage bar */}
                                {browserStats && (
                                    <div className="hidden sm:flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                                        <HardDrive className="w-3.5 h-3.5" />
                                        <div className="w-24 h-1.5 bg-gray-200 dark:bg-[#1e2535] rounded-full overflow-hidden">
                                            <div
                                                className={`h-full rounded-full transition-all ${browserStats.storage_used_percent > 80 ? 'bg-red-500' : 'bg-violet-500'}`}
                                                style={{ width: `${Math.min(browserStats.storage_used_percent, 100)}%` }}
                                            />
                                        </div>
                                        <span>{browserStats.storage_used_percent.toFixed(1)}%</span>
                                    </div>
                                )}

                                {/* Refresh */}
                                <button
                                    onClick={loadBrowserFiles}
                                    disabled={browserLoading}
                                    className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-xl transition-all disabled:opacity-40"
                                    aria-label="Refresh files"
                                >
                                    <RefreshCw className={`w-4 h-4 ${browserLoading ? 'animate-spin' : ''}`} />
                                </button>

                                {/* Upload button */}
                                <button
                                    onClick={() => browserUploadRef.current?.click()}
                                    className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 dark:hover:bg-violet-500 text-white text-sm font-medium rounded-xl transition-all shadow-sm shadow-violet-500/25"
                                >
                                    <UploadCloud className="w-4 h-4" />
                                    Upload
                                </button>
                                <input
                                    ref={browserUploadRef}
                                    type="file"
                                    multiple
                                    className="hidden"
                                    onChange={e => handleBrowserUpload(e.target.files)}
                                />
                            </div>
                        </div>
                    </div>

                    {/* File grid */}
                    <div className="flex-1 overflow-y-auto p-6">
                        <div className="max-w-6xl mx-auto">
                            {browserLoading && browserFiles.length === 0 ? (
                                <div className="flex items-center justify-center h-64">
                                    <div className="flex flex-col items-center gap-3">
                                        <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
                                        <p className="text-sm text-gray-500 dark:text-gray-400">Loading files…</p>
                                    </div>
                                </div>
                            ) : filteredBrowserFiles.length === 0 ? (
                                <div className="flex items-center justify-center h-64">
                                    <div className="text-center">
                                        <div
                                            className={`w-20 h-20 rounded-3xl flex items-center justify-center mx-auto mb-4 border-2 border-dashed transition-colors ${
                                                isDraggingOver
                                                    ? 'border-violet-400 bg-violet-50 dark:bg-violet-500/10 text-violet-400'
                                                    : 'border-gray-300 dark:border-[#1e2535] bg-gray-50 dark:bg-[#161b27] text-gray-300 dark:text-gray-600'
                                            }`}
                                        >
                                            <UploadCloud className="w-8 h-8" />
                                        </div>
                                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                            {browserSearch || browserCategory !== 'all' ? 'No files match your filters' : 'No files yet'}
                                        </p>
                                        <p className="text-xs text-gray-400 dark:text-gray-500">
                                            {browserSearch || browserCategory !== 'all' ? 'Try changing your search or filter' : 'Drop files here or click Upload'}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <>
                                    {/* Drag-drop hint banner */}
                                    {isDraggingOver && (
                                        <div className="mb-4 p-4 bg-violet-50 dark:bg-violet-500/10 border-2 border-dashed border-violet-400 rounded-2xl text-center">
                                            <p className="text-sm font-medium text-violet-700 dark:text-violet-300">Drop files to upload</p>
                                        </div>
                                    )}

                                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                                        {filteredBrowserFiles.map(file => (
                                            <div
                                                key={file.stored_name}
                                                className="group relative bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-2xl overflow-hidden hover:border-violet-300 dark:hover:border-violet-500/40 hover:shadow-md dark:hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)] transition-all duration-150"
                                            >
                                                {/* Thumbnail / Icon area */}
                                                <div className="aspect-square flex items-center justify-center bg-gray-50 dark:bg-[#0f1117] relative overflow-hidden">
                                                    {file.category === 'image' ? (
                                                        <img
                                                            src={`${file.url.replace('/download/', '/preview/')}?token=${localStorage.getItem('access_token')}`}
                                                            alt={file.filename}
                                                            className="w-full h-full object-cover"
                                                            onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                                                        />
                                                    ) : (
                                                        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center border ${getCategoryColor(file.category)}`}>
                                                            {getBrowserFileIcon(file.category, 'w-6 h-6')}
                                                        </div>
                                                    )}

                                                    {/* Hover actions overlay */}
                                                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all duration-150 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                                                        {canPreview(file.category) && (
                                                            <button
                                                                aria-label="Preview file"
                                                                onClick={() => openBrowserPreview(file)}
                                                                className="p-2 bg-white/90 hover:bg-white text-gray-800 rounded-xl shadow transition-all"
                                                            >
                                                                <Eye className="w-4 h-4" />
                                                            </button>
                                                        )}
                                                        <button
                                                            aria-label="Download file"
                                                            onClick={() => handleBrowserDownload(file)}
                                                            className="p-2 bg-white/90 hover:bg-white text-gray-800 rounded-xl shadow transition-all"
                                                        >
                                                            <Download className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            aria-label="Delete file"
                                                            onClick={() => handleBrowserDelete(file.stored_name)}
                                                            disabled={deletingFile === file.stored_name}
                                                            className="p-2 bg-white/90 hover:bg-red-50 text-gray-800 hover:text-red-600 rounded-xl shadow transition-all disabled:opacity-50"
                                                        >
                                                            {deletingFile === file.stored_name
                                                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                                                : <Trash2 className="w-4 h-4" />
                                                            }
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* File info */}
                                                <div className="p-2.5">
                                                    <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate" title={file.filename}>
                                                        {file.filename}
                                                    </p>
                                                    <div className="flex items-center justify-between mt-1">
                                                        <span className="text-[10px] text-gray-400 dark:text-gray-500">{formatFileSize(file.size)}</span>
                                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-md capitalize border ${getCategoryColor(file.category)}`}>
                                                            {file.category}
                                                        </span>
                                                    </div>
                                                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                                                        {format(new Date(file.uploaded_at), 'MMM d, h:mm a')}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
            {/* Image Preview Modal (chat attachments) */}
            {imagePreview && (
                <div className="fixed inset-0 bg-black/90 dark:bg-black/95 z-50 flex items-center justify-center p-6 backdrop-blur-sm" onClick={() => setImagePreview(null)}>
                    <button aria-label="Close Preview" onClick={() => setImagePreview(null)} className="absolute top-6 right-6 p-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors">
                        <X className="w-6 h-6" />
                    </button>
                    <div className="max-w-7xl max-h-full" onClick={(e) => e.stopPropagation()}>
                        <img src={imagePreview.url} alt={imagePreview.name} className="max-w-full max-h-[90vh] object-contain rounded-2xl shadow-2xl" />
                        <div className="mt-4 text-center">
                            <p className="text-white/80 text-sm mb-3">{imagePreview.name}</p>
                            <button
                                onClick={() => { const a = document.createElement('a'); a.href = imagePreview.url; a.download = imagePreview.name; a.click(); }}
                                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-sm rounded-xl transition-colors border border-white/10"
                            >
                                Download
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* File Browser Preview Modal */}
            {filePreview && (
                <div className="fixed inset-0 bg-black/90 dark:bg-black/95 z-50 flex items-center justify-center p-6 backdrop-blur-sm" onClick={() => setFilePreview(null)}>
                    <button aria-label="Close Preview" onClick={() => setFilePreview(null)} className="absolute top-6 right-6 p-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors">
                        <X className="w-6 h-6" />
                    </button>
                    <div className="max-w-5xl w-full max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                        <p className="text-white/80 text-sm mb-3 text-center">{filePreview.name}</p>
                        {filePreview.type === 'image' ? (
                            <img src={`${filePreview.url}?token=${localStorage.getItem('access_token')}`} alt={filePreview.name} className="max-w-full max-h-[80vh] object-contain rounded-2xl shadow-2xl mx-auto" />
                        ) : filePreview.type === 'video' ? (
                            <video
                                src={`${filePreview.url}?token=${localStorage.getItem('access_token')}`}
                                controls
                                className="max-w-full max-h-[80vh] rounded-2xl shadow-2xl mx-auto"
                            />
                        ) : (
                            <iframe
                                src={`${filePreview.url}?token=${localStorage.getItem('access_token')}`}
                                className="w-full flex-1 min-h-[70vh] rounded-2xl shadow-2xl bg-white"
                                title={filePreview.name}
                            />
                        )}
                    </div>
                </div>
            )}
        </div>

    );
}