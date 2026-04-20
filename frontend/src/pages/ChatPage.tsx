/**
 * ChatPage.tsx
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';
import { useChatStore } from '@/store/chatStore';
import type { Message, MessageMetadata, MessageAttachment as Attachment } from '@/store/chatStore';
import { inboxApi, UnifiedConversation, UnifiedMessage } from '@/services/inboxApi';
import { api } from '@/services/api';
import {
    Send, Crown, Bot, AlertCircle, Wifi, WifiOff, CheckCircle,
    RefreshCw, Paperclip, Image as ImageIcon, File, X, Mic, MicOff, Pause,
    Download, Copy, Sparkles, Code, FileText, Video, Music, Archive,
    Maximize2, MoreHorizontal, Smile, Plus, MessageCircle, Smartphone,
    Slack, Mail, Inbox, Volume2, VolumeX, Settings2, ChevronDown, Globe,
    FolderOpen, Trash2, Eye, UploadCloud, HardDrive, Search, Filter,
} from 'lucide-react';
import { format, isToday, isYesterday } from 'date-fns';
import { showToast } from '@/hooks/useToast';
import { fileApi, UploadedFile as ApiUploadedFile } from '@/services/fileApi';
import { voiceApi } from '@/services/voiceApi';
import { chatApi } from '@/services/chatApi';
import { localVoice } from '@/services/localVoice';
import { useVoiceBridge } from '@/hooks/useVoiceBridge';
import { VoiceInteractionEvent } from '@/services/voiceBridge';
import { VoiceSettingsModal } from '@/components/VoiceSettingsModal';
import { EmptyState } from '@/components/ui/EmptyState';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ── Types ─────────────────────────────────────────────────────────────────────

interface UploadedFile {
    id: string;
    file: File;
    preview?: string;
    apiFile?: ApiUploadedFile;
    isUploading?: boolean;
    uploadError?: string;
}

// Message, MessageMetadata, and Attachment are imported from @/store/chatStore

type ActiveTab = 'ai' | 'inbox' | 'files';

interface BrowserFile {
    filename: string;
    stored_name: string;
    url: string;
    size: number;
    category: string;
    uploaded_at: string;
}

// ── Module-level constants ────────────────────────────────────────────────────

/** Maximum dedup-set size — moved out of component to avoid re-creation on render (Issue 14) */
const MAX_PROCESSED_IDS = 500;

/**
 * Static Tailwind class map for tab active text colours.
 * Avoids dynamic `text-${color}-600` strings that Tailwind JIT cannot detect
 * and will purge in production builds (Issue 10).
 */
const TAB_ACTIVE_STYLES: Record<ActiveTab, string> = {
    ai:    'text-blue-600 dark:text-blue-400',
    inbox: 'text-emerald-600 dark:text-emerald-400',
    files: 'text-violet-600 dark:text-violet-400',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
    if (bytes < 1024)         return `${bytes} B`;
    if (bytes < 1024 * 1024)  return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(type: string) {
    if (type.startsWith('image/'))  return <ImageIcon className="w-5 h-5" />;
    if (type.startsWith('video/'))  return <Video className="w-5 h-5" />;
    if (type.startsWith('audio/'))  return <Music className="w-5 h-5" />;
    if (type.includes('pdf'))       return <FileText className="w-5 h-5" />;
    if (type.includes('zip') || type.includes('tar')) return <Archive className="w-5 h-5" />;
    if (type.includes('javascript') || type.includes('python') || type.includes('json'))
        return <Code className="w-5 h-5" />;
    return <File className="w-5 h-5" />;
}

function formatTimestamp(date: Date): string {
    if (isToday(date))     return format(date, 'HH:mm');
    if (isYesterday(date)) return `Yesterday ${format(date, 'HH:mm')}`;
    return format(date, 'MMM d, HH:mm');
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChatPage() {
    // ── Tab ───────────────────────────────────────────────────────────────────
    const [activeTab, setActiveTab] = useState<ActiveTab>('ai');

    // ── AI Chat ───────────────────────────────────────────────────────────────
    const [input,          setInput]         = useState('');
    // ── messages live in the Zustand store so they survive navigation ─────────
    const { messages, setMessages } = useChatStore(
        useShallow((s) => ({ messages: s.messages, setMessages: s.setMessages }))
    );
    const [uploadedFiles,  setUploadedFiles] = useState<UploadedFile[]>([]);
    const [isRecording,    setIsRecording]   = useState(false);
    // isPaused was declared here but never consumed — removed (Issue 12)
    const [recordingTime,  setRecordingTime] = useState(0);
    const [showFileMenu,   setShowFileMenu]  = useState(false);
    const [imagePreview,   setImagePreview]  = useState<{ url: string; name: string } | null>(null);
    const [voiceAvailable, setVoiceAvailable] = useState<boolean | null>(null);
    const [showVoiceTooltip, setShowVoiceTooltip] = useState(false);
    const [isLocalMode,    setIsLocalMode]   = useState(false);
    const [interimTranscript, setInterimTranscript] = useState('');
    const [showVoiceSettings, setShowVoiceSettings] = useState(false);
    // Issue 1: initialise to '' so that the API-provided default voice can be applied
    const [selectedVoice,  setSelectedVoice]  = useState('');
    const [selectedLanguage, setSelectedLanguage] = useState('');
    const [availableVoices,  setAvailableVoices]  = useState<{ id: string; name: string; description: string }[]>([]);
    const [availableLanguages, setAvailableLanguages] = useState<{ code: string; name: string }[]>([]);
    const [isSpeaking, setIsSpeaking]  = useState<string | null>(null);
    // Upload progress: maps local UploadedFile id → 0-100 percent
    const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});

    const audioPlayerRef      = useRef<HTMLAudioElement | null>(null);
    const messagesEndRef      = useRef<HTMLDivElement>(null);
    const fileInputRef        = useRef<HTMLInputElement>(null);
    const textareaRef         = useRef<HTMLTextAreaElement>(null);
    const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const mediaRecorderRef    = useRef<MediaRecorder | null>(null);
    const audioStreamRef      = useRef<MediaStream | null>(null);

    /**
     * Dedup set lives in a ref (not React state) — no re-renders,
     * trimmed to MAX_PROCESSED_IDS entries so it never grows unbounded.
     * MAX_PROCESSED_IDS is defined at module scope (Issue 14).
     */
    const processedMessageIds = useRef<Set<string>>(new Set());
    const trackId = useCallback((id: string) => {
        if (processedMessageIds.current.size >= MAX_PROCESSED_IDS) {
            const arr = Array.from(processedMessageIds.current);
            processedMessageIds.current = new Set(arr.slice(Math.floor(MAX_PROCESSED_IDS / 4)));
        }
        processedMessageIds.current.add(id);
    }, []);

    /**
     * FIX #13: tracks whether the LAST messages change was a bulk history load
     * so we can skip the smooth-scroll animation on initial load.
     */
    const isHistoryLoad = useRef(false);

    /**
     * FIX #8: voice options are fetched once and cached; reconnects don't re-fetch
     * unless the previous fetch actually failed.
     */
    const voiceOptionsFetched = useRef(false);

    /**
     * FIX #14: subscribe to websocketStore exactly once.
     */
    const wsSubscribed = useRef(false);

    // ── Inbox ─────────────────────────────────────────────────────────────────
    const [conversations,  setConversations] = useState<UnifiedConversation[]>([]);
    const [selectedId,     setSelectedId]    = useState<string | null>(null);
    const [inboxLoading,   setInboxLoading]  = useState(false);
    const [replyContent,   setReplyContent]  = useState('');
    const [isSending,      setIsSending]     = useState(false);
    const inboxMessagesEndRef = useRef<HTMLDivElement>(null);

    // ── File Browser ──────────────────────────────────────────────────────────
    const [browserFiles,    setBrowserFiles]   = useState<BrowserFile[]>([]);
    const [browserLoading,  setBrowserLoading] = useState(false);
    const [browserSearch,   setBrowserSearch]  = useState('');
    const [browserCategory, setBrowserCategory] = useState('all');
    const [browserStats,    setBrowserStats]   = useState<{
        total_files: number; total_size_bytes: number;
        storage_limit_bytes: number; storage_used_percent: number;
    } | null>(null);
    const [filePreview,    setFilePreview]   = useState<{ url: string; name: string; type: string } | null>(null);
    const [isDraggingOver, setIsDraggingOver] = useState(false);
    const [deletingFile,   setDeletingFile]  = useState<string | null>(null);
    const browserUploadRef = useRef<HTMLInputElement>(null);

    // ── Auth & WS ─────────────────────────────────────────────────────────────
    const user = useAuthStore((s) => s.user);
    const isAuthenticated = user?.isAuthenticated ?? false;

    // Issue 9: useShallow prevents re-renders caused by internal store fields
    // (_pingInterval, _pongTimeout, _messageQueue, etc.) that ChatPage doesn't use.
    const {
        isConnected, isConnecting, error,
        sendMessage: sendWsMessage,
        reconnect, connectionStats,
        unreadCount, markAsRead,
        messageHistory, lastMessage,
    } = useWebSocketStore(
        useShallow((s) => ({
            isConnected:     s.isConnected,
            isConnecting:    s.isConnecting,
            error:           s.error,
            sendMessage:     s.sendMessage,
            reconnect:       s.reconnect,
            connectionStats: s.connectionStats,
            unreadCount:     s.unreadCount,
            markAsRead:      s.markAsRead,
            messageHistory:  s.messageHistory,
            lastMessage:     s.lastMessage,
        }))
    );

    // ── Voice Bridge ──────────────────────────────────────────────────────────
    const handleVoiceInteraction = useCallback((event: VoiceInteractionEvent) => {
        try {
            const ts = new Date(event.ts * 1000);
            const voiceUserId  = `voice-user-${event.ts}`;
            const voiceReplyId = `voice-reply-${event.ts}`;
            if (processedMessageIds.current.has(voiceUserId)) return;
            trackId(voiceUserId);
            trackId(voiceReplyId);
            setMessages((prev) => [
                ...prev,
                { id: voiceUserId,  role: 'sovereign'       as const, content: event.user,  timestamp: ts, metadata: { source: 'voice' } },
                { id: voiceReplyId, role: 'head_of_council' as const, content: event.reply, timestamp: ts, metadata: { source: 'voice' } },
            ]);
        } catch (err) {
            console.warn('[ChatPage] Failed to append voice interaction:', err);
        }
    }, [trackId]);

    const { status: bridgeStatus } = useVoiceBridge(handleVoiceInteraction);

    // ── Effects ───────────────────────────────────────────────────────────────

    // Mark messages as read when on AI tab
    useEffect(() => { markAsRead(); }, [markAsRead]);

    // FIX #8: fetch voice options only once per connection, skip on reconnect
    useEffect(() => {
        if (isConnected && !voiceOptionsFetched.current) {
            checkVoiceAvailability();
        }
    }, [isConnected]);

    // FIX #14 + #2: subscribe to incoming WS messages exactly once
    useEffect(() => {
        if (wsSubscribed.current) return;
        wsSubscribed.current = true;

        const unsubscribe = useWebSocketStore.subscribe((state, prevState) => {
            if (
                state.lastMessage &&
                state.lastMessage !== prevState.lastMessage &&
                state.lastMessage.type === 'message'
            ) {
                const msg = state.lastMessage;

                // FIX #2: prefer server-assigned message_id over timestamp
                const messageId = (msg.message_id as string | undefined) || (msg.timestamp as string | undefined) || crypto.randomUUID();

                if (processedMessageIds.current.has(messageId)) return;
                trackId(messageId);

                const newMessage: Message = {
                    id:        messageId,
                    role:      (msg.role as Message['role']) || 'head_of_council',
                    content:   msg.content as string,
                    timestamp: new Date(),
                    metadata:  msg.metadata as MessageMetadata | undefined,
                };
                // Note: isHistoryLoad.current is NOT reset here to avoid racing
                // with loadChatHistory. It is consumed and reset in the scroll
                // useEffect below (Issue 3).
                setMessages((prev) => [...prev, newMessage]);
                if (msg.metadata?.task_created) {
                    showToast.success(`Task ${msg.metadata.task_id} created`);
                }
            }
        });

        return () => {
            unsubscribe();
            wsSubscribed.current = false;
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Issue 3: Consume isHistoryLoad.current here — not in the WS subscriber —
    // so there is no race between the subscriber and the bulk setMessages call.
    useEffect(() => {
        if (isHistoryLoad.current) {
            isHistoryLoad.current = false; // consume the flag before any scroll
            return;                        // skip smooth-scroll on history load
        }
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
        }
    }, [input]);

    // Inbox: reload on new external message
    useEffect(() => {
        const wsMsg = lastMessage as any;
        if (wsMsg?.type === 'message_created') loadConversations();
    }, [lastMessage]);

    // Inbox: scroll to bottom when conversation selected
    useEffect(() => {
        if (selectedId) inboxMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [selectedId, conversations]);

    // Cleanup mic stream and any in-flight audio on unmount (Issues 5 + 7)
    useEffect(() => {
        return () => {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                mediaRecorderRef.current.stop();
            }
            if (audioStreamRef.current) {
                audioStreamRef.current.getTracks().forEach((t) => t.stop());
            }
            if (recordingIntervalRef.current) {
                clearInterval(recordingIntervalRef.current);
            }
            // Issue 5: stop audio and allow the browser to GC the blob URL
            if (audioPlayerRef.current) {
                audioPlayerRef.current.pause();
                audioPlayerRef.current.src = '';
                audioPlayerRef.current = null;
            }
        };
    }, []);

    // ── AI Chat methods ───────────────────────────────────────────────────────

    const checkVoiceAvailability = async () => {
        try {
            const statusRes = await voiceApi.checkStatus();
            setVoiceAvailable(statusRes.available);
            setIsLocalMode(statusRes.provider === 'local');
            // FIX #8: mark fetched so we don't repeat on every reconnect
            await fetchVoiceOptions();
            voiceOptionsFetched.current = true;
        } catch (e) {
            console.warn('[ChatPage] checkVoiceAvailability failed:', e);
        }
    };

    const fetchVoiceOptions = async () => {
        try {
            // Issue 7: use the api service — it injects the auth header automatically
            // and routes 401s through the global refresh/logout interceptor.
            const [voicesRes, langsRes] = await Promise.all([
                api.get<{ voices: { id: string; name: string; description: string }[]; default?: string }>(
                    '/api/v1/voice/voices',
                ),
                api.get<{ languages: { code: string; name: string }[] }>(
                    '/api/v1/voice/languages',
                ),
            ]);
            setAvailableVoices(voicesRes.data.voices || []);
            // Issue 1: selectedVoice starts as '' (falsy) so this guard now works correctly
            if (voicesRes.data.default && !selectedVoice) setSelectedVoice(voicesRes.data.default);
            setAvailableLanguages(langsRes.data.languages || []);
        } catch (e) {
            console.warn('[ChatPage] Could not fetch voice options:', e);
        }
    };

    /**
     * Load history from API and seed the dedup set so incoming WS messages
     * for already-shown history aren't re-appended.
     * Accepts an AbortSignal so the caller's useEffect can cancel mid-flight (Issue 6).
     */
    const loadChatHistory = useCallback(async (signal?: AbortSignal) => {
        try {
            const history = await chatApi.getHistory(50);

            // Aborted before we could process the response — discard silently
            if (signal?.aborted) return;

            // Empty result (e.g. 500 fallback) — nothing to render, skip state update
            if (!history.messages.length) return;

            const formattedMessages: Message[] = history.messages.map((msg) => ({
                id:          msg.id,
                role:        msg.role,
                content:     msg.content,
                timestamp:   new Date(msg.created_at),
                metadata:    msg.metadata as MessageMetadata | undefined,
                attachments: msg.attachments,
            }));
            // Seed dedup set BEFORE setting state so the WS subscriber ignores these
            formattedMessages.forEach((m) => trackId(m.id));
            isHistoryLoad.current = true; // skip auto-scroll
            setMessages(formattedMessages);
            // Scroll to bottom without animation after history load
            requestAnimationFrame(() => {
                if (!signal?.aborted) {
                    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
                }
            });
        } catch (error) {
            if ((error as any)?.name === 'AbortError' || (error as any)?.name === 'CanceledError') return;
            console.error('[ChatPage] Failed to load chat history:', error);
            showToast.error('Could not load chat history — your new messages will still work.');
        }
    }, [trackId]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() && uploadedFiles.length === 0) return;
        if (!isConnected) {
            showToast.error('Not connected to Head of Council');
            return;
        }

        const attachments = uploadedFiles
            .filter((f) => f.apiFile && !f.uploadError)
            .map((f) => ({
                name:           f.apiFile!.original_name,
                type:           f.apiFile!.type,
                size:           f.apiFile!.size,
                url:            f.apiFile!.url,
                category:       f.apiFile!.category,
                // Forward extracted_text so the backend can inject file content
                // into the AI prompt without a second round-trip to storage.
                extracted_text: f.apiFile!.extracted_text ?? null,
            }));

        // Optimistically append the user message
        const userMsgId = crypto.randomUUID();
        trackId(userMsgId);
        const userMessage: Message = {
            id:          userMsgId,
            role:        'sovereign',
            content:     input.trim() || '(file attachment)',
            timestamp:   new Date(),
            attachments: attachments.length > 0 ? attachments : undefined,
        };
        isHistoryLoad.current = false;
        setMessages((prev) => [...prev, userMessage]);

        // FIX Issue 2: forward attachment metadata over WebSocket — previously only
        // text was sent and the backend never received the file URLs / names.
        sendWsMessage(input.trim() || '(file attachment)', attachments.length > 0 ? attachments : undefined);

        setInput('');
        setUploadedFiles([]);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e as any);
        }
    };

    // ── Voice ─────────────────────────────────────────────────────────────────

    const handleVoiceButtonClick = async () => {
        if (isRecording) { stopRecording(); return; }
        const isAvailable = await voiceApi.requireVoice();
        if (!isAvailable) return;
        const statusRes = await voiceApi.checkStatus();
        setIsLocalMode(statusRes.provider === 'local');
        if (statusRes.provider === 'local') startLocalRecording();
        else startOpenAIRecording();
    };

    const startLocalRecording = async () => {
        try {
            setIsRecording(true);
            setRecordingTime(0);
            setInterimTranscript('');
            recordingIntervalRef.current = setInterval(() => setRecordingTime((p) => p + 1), 1000);
            await localVoice.transcribe(
                (result) => {
                    if (result.isFinal) {
                        setInput((prev) => {
                            const sep = prev && !prev.endsWith(' ') ? ' ' : '';
                            return prev + sep + (result.text ?? '');
                        });
                        setInterimTranscript('');
                    } else {
                        setInterimTranscript(result.text ?? '');
                    }
                },
                () => stopRecording(),
            );
        } catch (err: any) {
            showToast.error(err.message || 'Microphone access denied');
            stopRecording();
        }
    };

    const startOpenAIRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioStreamRef.current = stream;
            const recorder = new MediaRecorder(stream);
            mediaRecorderRef.current = recorder;
            const chunks: Blob[] = [];

            recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
            recorder.onstop = async () => {
                const blob = new Blob(chunks, { type: 'audio/webm' });
                try {
                    const result = await voiceApi.transcribe(blob, selectedLanguage || undefined);
                    if (result.text) setInput((p) => p + (p ? ' ' : '') + result.text);
                } catch (e: any) {
                    showToast.error(e.message || 'Transcription failed');
                }
            };

            recorder.start();
            setIsRecording(true);
            setRecordingTime(0);
            recordingIntervalRef.current = setInterval(() => setRecordingTime((p) => p + 1), 1000);
        } catch (err: any) {
            showToast.error(err.message || 'Microphone access denied');
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
        }
        // FIX #7: always stop all tracks
        if (audioStreamRef.current) {
            audioStreamRef.current.getTracks().forEach((t) => t.stop());
            audioStreamRef.current = null;
        }
        if (recordingIntervalRef.current) {
            clearInterval(recordingIntervalRef.current);
            recordingIntervalRef.current = null;
        }
        mediaRecorderRef.current = null;
        setIsRecording(false);
        // isPaused state removed — was never consumed anywhere (Issue 12)
        setInterimTranscript('');
    };

    const handleSpeakMessage = async (messageId: string, content: string) => {
        if (isSpeaking === messageId) {
            audioPlayerRef.current?.pause();
            setIsSpeaking(null);
            return;
        }
        const toastId = showToast.loading('Generating speech…');
        try {
            setIsSpeaking(messageId);
            const audioBlob = await voiceApi.synthesize({ text: content, voice: (selectedVoice || 'alloy') as 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer' });
            showToast.dismiss(toastId);
            if (audioBlob && audioBlob.size > 0) {
                const audioUrl = URL.createObjectURL(audioBlob);
                const audio = new Audio(audioUrl);
                audioPlayerRef.current = audio;
                audio.onended = () => { setIsSpeaking(null); URL.revokeObjectURL(audioUrl); };
                audio.onerror = () => { setIsSpeaking(null); URL.revokeObjectURL(audioUrl); showToast.error('Audio playback failed'); };
                audio.play();
            } else {
                // Local browser TTS — synthesize already played it
                setIsSpeaking(null);
            }
        } catch (error: any) {
            showToast.dismiss(toastId);
            showToast.error(error.message || 'Speech synthesis failed');
            setIsSpeaking(null);
        }
    };

    const copyMessage = (content: string) => {
        navigator.clipboard.writeText(content);
        showToast.success('Copied');
    };

    // ── File upload ───────────────────────────────────────────────────────────

    const handleFileSelect = async (files: FileList | null) => {
        if (!files) return;
        for (const file of Array.from(files)) {
            const id = crypto.randomUUID();
            const preview = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined;
            setUploadedFiles((prev) => [
                ...prev,
                { id, file, preview, isUploading: true },
            ]);
            try {
                // Thread progress events through so the chip shows a real percentage
                const response = await fileApi.uploadFiles([file], (pct) => {
                    setUploadProgress((prev) => ({ ...prev, [id]: pct }));
                });
                const apiFile = response.files[0];
                setUploadedFiles((prev) =>
                    prev.map((f) => f.id === id ? { ...f, apiFile, isUploading: false } : f),
                );
                // Clear progress entry once upload is complete
                setUploadProgress((prev) => {
                    const next = { ...prev };
                    delete next[id];
                    return next;
                });
            } catch (error: any) {
                setUploadedFiles((prev) =>
                    prev.map((f) => f.id === id ? { ...f, isUploading: false, uploadError: error.message } : f),
                );
                setUploadProgress((prev) => {
                    const next = { ...prev };
                    delete next[id];
                    return next;
                });
                showToast.error(`Upload failed: ${error.message}`);
            }
        }
    };

    const removeFile = (id: string) =>
        setUploadedFiles((prev) => {
            // Issue 4: revoke object URL before dropping the file to prevent blob leaks
            const target = prev.find((f) => f.id === id);
            if (target?.preview) URL.revokeObjectURL(target.preview);
            return prev.filter((f) => f.id !== id);
        });

    const downloadFile = async (attachment: Attachment) => {
        try {
            if (attachment.data) {
                const a = document.createElement('a');
                a.href = attachment.data; a.download = attachment.name;
                document.body.appendChild(a); a.click(); document.body.removeChild(a);
                showToast.success('Downloaded');
            } else if (attachment.url) {
                // Issue 8: use the authenticated api service so protected file URLs
                // get the correct Authorization header and 401s are handled globally.
                const response = await api.get(attachment.url, { responseType: 'blob' });
                const url      = window.URL.createObjectURL(response.data);
                const a        = document.createElement('a');
                a.href = url; a.download = attachment.name;
                document.body.appendChild(a); a.click(); document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                showToast.success('Downloaded');
            }
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || err.message || 'Download failed');
        }
    };

    // ── Inbox ─────────────────────────────────────────────────────────────────

    const loadConversations = useCallback(async (signal?: AbortSignal) => {
        setInboxLoading(true);
        try {
            const res = await inboxApi.getConversations();
            if (signal?.aborted) return;
            setConversations(res.conversations);
        } catch (err: any) {
            if (err?.name === 'AbortError' || err?.name === 'CanceledError') return;
            showToast.error(err.message || 'Failed to load conversations');
        } finally {
            if (!signal?.aborted) setInboxLoading(false);
        }
    }, []);

    const handleSendReply = async () => {
        if (!selectedId || !replyContent.trim()) return;
        setIsSending(true);
        try {
            await inboxApi.reply(selectedId, replyContent.trim());
            setReplyContent('');
            await loadConversations();
            showToast.success('Reply sent');
        } catch (err: any) {
            showToast.error(err.response?.data?.detail || err.message || 'Failed to send reply');
        } finally {
            setIsSending(false);
        }
    };

    // ── File Browser ──────────────────────────────────────────────────────────

    const loadBrowserFiles = useCallback(async (signal?: AbortSignal) => {
        setBrowserLoading(true);
        try {
            // Issue 7: use the api service — auth header is injected automatically.
            const [listRes, statsRes] = await Promise.all([
                api.get<{ files: BrowserFile[] }>('/api/v1/files/list'),
                api.get<typeof browserStats>('/api/v1/files/stats'),
            ]);
            if (signal?.aborted) return;
            setBrowserFiles(listRes.data.files || []);
            setBrowserStats(statsRes.data);
        } catch (e: any) {
            if (e?.name === 'AbortError' || e?.name === 'CanceledError') return;
            console.error('[ChatPage] loadBrowserFiles:', e);
        } finally {
            if (!signal?.aborted) setBrowserLoading(false);
        }
    }, []);

    // ── Effects that depend on the useCallback functions above ────────────────
    // These must live AFTER the const declarations — useCallback uses `const`,
    // which is not hoisted, so referencing them earlier causes a TS2448 error.

    // Load history from API only when the persisted store is empty (first ever visit,
    // cleared session, or explicit clearHistory call). Zustand persist rehydrates from
    // sessionStorage synchronously before this effect runs, so messages.length > 0
    // means we already have data and do not need an API round-trip.
    useEffect(() => {
        if (!isAuthenticated) return;
        if (messages.length > 0) return; // persisted data already loaded — skip API call
        const controller = new AbortController();
        loadChatHistory(controller.signal);
        return () => controller.abort();
    }, [isAuthenticated, loadChatHistory]); // eslint-disable-line react-hooks/exhaustive-deps

    // Inbox: load when tab switches — cancelled if the tab changes again quickly
    useEffect(() => {
        if (activeTab !== 'inbox' || conversations.length > 0) return;
        const controller = new AbortController();
        loadConversations(controller.signal);
        return () => controller.abort();
    }, [activeTab, loadConversations]); // eslint-disable-line react-hooks/exhaustive-deps

    // Files: load when tab switches — cancelled if the tab changes again quickly
    useEffect(() => {
        if (activeTab !== 'files') return;
        const controller = new AbortController();
        loadBrowserFiles(controller.signal);
        return () => controller.abort();
    }, [activeTab, loadBrowserFiles]);

    const handleBrowserUpload = async (files: FileList | null) => {
        if (!files) return;
        for (const file of Array.from(files)) {
            try {
                await fileApi.uploadFiles([file]);
                showToast.success(`${file.name} uploaded`);
            } catch (e: any) {
                showToast.error(`Failed: ${e.message}`);
            }
        }
        loadBrowserFiles();
    };

    const handleDeleteFile = async (storedName: string) => {
        setDeletingFile(storedName);
        try {
            // Issue 7: use fileApi so the auth header is handled consistently
            await fileApi.deleteFile(storedName);
            showToast.success('File deleted');
            loadBrowserFiles();
        } catch (e: any) {
            showToast.error(e.response?.data?.detail || e.message || 'Delete failed');
        } finally {
            setDeletingFile(null);
        }
    };

    // ── Attachment renderer ───────────────────────────────────────────────────

    const renderAttachment = (attachment: Attachment, isUser: boolean) => {
        if (attachment.type?.startsWith('image/')) {
            const src = attachment.data || attachment.url;
            if (src) return (
                <div key={attachment.name} className="mt-2 relative group">
                    <img
                        src={src} alt={attachment.name}
                        className="max-w-xs max-h-48 rounded-lg object-cover cursor-pointer"
                        onClick={() => setImagePreview({ url: src, name: attachment.name })}
                    />
                    <button onClick={() => downloadFile(attachment)}
                        className="absolute top-2 right-2 p-1.5 bg-black/50 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity text-white">
                        <Download className="w-3.5 h-3.5" />
                    </button>
                </div>
            );
        }
        return (
            <div key={attachment.name} className={`mt-2 flex items-center gap-3 p-3 rounded-xl border ${
                isUser ? 'bg-white/10 border-white/20' : 'bg-gray-50 dark:bg-[#1e2535] border-gray-200 dark:border-[#2a3347]'
            }`}>
                <div className={isUser ? 'text-white/70' : 'text-gray-500 dark:text-gray-400'}>
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
        );
    };

    // ── Auth guard ────────────────────────────────────────────────────────────
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
    const selectedConv    = conversations.find((c) => c.id === selectedId);
    const filteredFiles   = browserFiles.filter((f) => {
        const matchesSearch   = !browserSearch || f.filename.toLowerCase().includes(browserSearch.toLowerCase());
        const matchesCategory = browserCategory === 'all' || f.category === browserCategory;
        return matchesSearch && matchesCategory;
    });

    // ── Render ────────────────────────────────────────────────────────────────
    return (
        <div className="h-full bg-gray-50 dark:bg-[#0f1117] flex flex-col overflow-hidden transition-colors duration-200">
            <div className="w-full h-full flex flex-col">

                {/* ── Header ─────────────────────────────────────────────────── */}
                <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-none">
                    <div className="px-6 py-4 max-w-6xl mx-auto">
                        <div className="flex items-center justify-between">

                            {/* Left: avatar + title */}
                            <div className="flex items-center gap-4">
                                <div className="relative">
                                    <div className={`w-11 h-11 rounded-2xl flex items-center justify-center shadow-lg ${
                                        activeTab === 'ai'    ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-500/25 dark:shadow-blue-900/40'
                                      : activeTab === 'inbox' ? 'bg-gradient-to-br from-emerald-500 to-teal-600 shadow-emerald-500/25 dark:shadow-emerald-900/40'
                                      :                         'bg-gradient-to-br from-violet-500 to-purple-600 shadow-violet-500/25 dark:shadow-violet-900/40'
                                    }`}>
                                        {activeTab === 'ai'    ? <Crown    className="w-5 h-5 text-white" />
                                       : activeTab === 'inbox' ? <Inbox    className="w-5 h-5 text-white" />
                                       :                         <FolderOpen className="w-5 h-5 text-white" />}
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
                                            ) : isConnecting ? 'Connecting…' : (
                                                <span className="text-gray-400 dark:text-gray-500">Offline</span>
                                            )
                                        ) : activeTab === 'inbox' ? (
                                            <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                                                {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
                                            </span>
                                        ) : (
                                            <span className="text-violet-600 dark:text-violet-400 font-medium">
                                                {browserStats
                                                    ? `${browserFiles.length} files · ${((browserStats.total_size_bytes) / (1024 * 1024)).toFixed(1)} MB used`
                                                    : `${browserFiles.length} files`}
                                            </span>
                                        )}
                                        {activeTab === 'ai' && connectionStats.latencyMs && isConnected && (
                                            <span className="text-green-600 dark:text-green-500">· {connectionStats.latencyMs}ms</span>
                                        )}
                                    </p>
                                </div>
                            </div>

                            {/* Right: voice status + reconnect + tabs */}
                            <div className="flex items-center gap-3">
                                {activeTab === 'ai' && error && (
                                    <span className="text-sm text-red-600 dark:text-red-400 max-w-xs truncate hidden sm:block">{error}</span>
                                )}
                                {activeTab === 'ai' && !isConnected && !isConnecting && (
                                    <button onClick={reconnect}
                                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white text-sm font-medium rounded-xl transition-all duration-150 flex items-center gap-2 shadow-sm">
                                        <RefreshCw className="w-4 h-4" /> Reconnect
                                    </button>
                                )}
                                {activeTab === 'ai' && isConnecting && (
                                    <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-gray-500">
                                        <LoadingSpinner size="sm" /> Connecting…
                                    </div>
                                )}

                                {/* Voice Bridge status pill */}
                                {activeTab === 'ai' && (
                                    <div className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${
                                        bridgeStatus === 'connected'
                                            ? 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-500/10 border-green-200 dark:border-green-500/20'
                                            : bridgeStatus === 'connecting'
                                            ? 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-500/10 border-yellow-200 dark:border-yellow-500/20'
                                            : 'text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-[#1e2535] border-gray-200 dark:border-[#1e2535]'
                                    }`} title={`Voice bridge: ${bridgeStatus}`}>
                                        {bridgeStatus === 'connecting' ? <LoadingSpinner size="xs" />
                                         : bridgeStatus === 'connected' ? <Mic className="w-3 h-3" />
                                         : <MicOff className="w-3 h-3" />}
                                        <span className="capitalize">{bridgeStatus === 'connected' ? 'Voice' : bridgeStatus}</span>
                                    </div>
                                )}

                                {/* Tab switcher */}
                                <div className="flex items-center bg-gray-100 dark:bg-[#0f1117] rounded-xl p-1 border border-gray-200 dark:border-[#1e2535]">
                                    {([
                                        { key: 'ai'    as const, icon: Crown,      label: 'AI Chat' },
                                        { key: 'inbox' as const, icon: Inbox,      label: 'Inbox'   },
                                        { key: 'files' as const, icon: FolderOpen, label: 'Files'   },
                                    ] as const).map(({ key, icon: Icon, label }) => (
                                        <button key={key} onClick={() => setActiveTab(key)}
                                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                                                activeTab === key
                                                    // Issue 10: static class map — dynamic text-${color}-* strings
                                                    // are not detected by Tailwind JIT and get purged in production
                                                    ? `bg-white dark:bg-[#161b27] ${TAB_ACTIVE_STYLES[key]} shadow-sm`
                                                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                                            }`}>
                                            <Icon className="w-3.5 h-3.5" />
                                            {label}
                                            {key === 'inbox' && conversations.length > 0 && activeTab !== 'inbox' && (
                                                <span className="ml-0.5 bg-emerald-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                                                    {conversations.length > 9 ? '9+' : conversations.length}
                                                </span>
                                            )}
                                            {key === 'files' && browserFiles.length > 0 && activeTab !== 'files' && (
                                                <span className="ml-0.5 bg-violet-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
                                                    {browserFiles.length > 99 ? '99+' : browserFiles.length}
                                                </span>
                                            )}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* ── AI Chat Tab ────────────────────────────────────────────── */}
                {activeTab === 'ai' && (
                    <>
                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto px-4 py-6">
                            <div className="max-w-3xl mx-auto space-y-6">
                                {messages.length === 0 && (
                                    <div className="h-64 flex items-center justify-center">
                                        <EmptyState
                                            icon={Crown}
                                            title="Head of Council"
                                            description={isConnected ? 'Send a message to your Head of Council.' : 'Connect to start chatting.'}
                                        />
                                    </div>
                                )}

                                {messages.map((message) => {
                                    const isUser  = message.role === 'sovereign';
                                    const isError = message.metadata?.error === true;
                                    return (
                                        <div key={message.id} className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                                            {/* Avatar */}
                                            <div className={`flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center text-white text-xs font-semibold ${
                                                isUser ? 'bg-gradient-to-br from-blue-500 to-blue-600'
                                                       : isError ? 'bg-orange-500' : 'bg-gradient-to-br from-gray-700 to-gray-800'
                                            }`}>
                                                {isUser ? (user?.username?.[0]?.toUpperCase() ?? 'S') : <Bot className="w-4 h-4" />}
                                            </div>

                                            <div className={`flex flex-col max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
                                                <div className={`px-4 py-3 rounded-2xl ${
                                                    isUser  ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-500/20 dark:shadow-blue-900/40'
                                                    : isError ? 'bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20 text-orange-900 dark:text-orange-300'
                                                    : message.role === 'system' ? 'bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-900 dark:text-red-300'
                                                    : 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100 shadow-sm dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)]'
                                                }`}>
                                                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.content}</p>
                                                    {message.attachments?.map((att, i) => (
                                                        <div key={i}>{renderAttachment(att, isUser)}</div>
                                                    ))}
                                                    {message.metadata?.task_created && (
                                                        <div className="mt-3 pt-3 border-t border-white/20 flex items-center gap-2 text-xs">
                                                            <CheckCircle className="w-3.5 h-3.5" />
                                                            Task {message.metadata.task_id} created
                                                        </div>
                                                    )}
                                                </div>
                                                <div className={`flex items-center gap-2 mt-1.5 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                                                    <span className="text-xs text-gray-400 dark:text-gray-500">
                                                        {formatTimestamp(message.timestamp)}
                                                    </span>
                                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                        <button onClick={() => copyMessage(message.content)}
                                                            className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500 transition-colors" title="Copy">
                                                            <Copy className="w-3 h-3" />
                                                        </button>
                                                        {!isUser && voiceAvailable && (
                                                            <button onClick={() => handleSpeakMessage(message.id, message.content)}
                                                                className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500 transition-colors" title="Read aloud">
                                                                {isSpeaking === message.id ? <VolumeX className="w-3 h-3" /> : <Volume2 className="w-3 h-3" />}
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                                <div ref={messagesEndRef} />
                            </div>
                        </div>

                        {/* Input bar */}
                        <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535] px-4 py-4">
                            <div className="max-w-3xl mx-auto">
                                {/* File previews */}
                                {uploadedFiles.length > 0 && (
                                    <div className="flex flex-wrap gap-2 mb-3">
                                        {uploadedFiles.map((uf) => (
                                            <div key={uf.id} className="relative flex items-center gap-2 bg-gray-100 dark:bg-[#1e2535] rounded-xl px-3 py-2 text-sm">
                                                {uf.preview
                                                    ? <img src={uf.preview} alt={uf.file.name} className="w-8 h-8 rounded-lg object-cover" />
                                                    : <div className="text-gray-500 dark:text-gray-400">{getFileIcon(uf.file.type)}</div>}
                                                <span className="text-gray-700 dark:text-gray-300 max-w-[120px] truncate text-xs">{uf.file.name}</span>
                                                {/* Show real upload % when available, fall back to spinner */}
                                                {uf.isUploading && (
                                                    uploadProgress[uf.id] !== undefined
                                                        ? <span className="text-xs text-blue-500 font-mono w-8 text-right tabular-nums">{uploadProgress[uf.id]}%</span>
                                                        : <LoadingSpinner size="xs" />
                                                )}
                                                {uf.uploadError && <span title={uf.uploadError}><AlertCircle className="w-3.5 h-3.5 text-red-500" /></span>}
                                                {!uf.isUploading && !uf.uploadError && (
                                                    <span title={uf.apiFile?.extracted_text ? 'Content extracted — AI can read this file' : 'Uploaded'}>
                                                        <CheckCircle className={`w-3.5 h-3.5 ${uf.apiFile?.extracted_text ? 'text-blue-500' : 'text-green-500'}`} />
                                                    </span>
                                                )}
                                                <button onClick={() => removeFile(uf.id)}
                                                    className="ml-1 p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-[#2a3347] text-gray-400">
                                                    <X className="w-3 h-3" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Interim transcript */}
                                {interimTranscript && (
                                    <div className="mb-2 px-3 py-2 bg-blue-50 dark:bg-blue-500/10 rounded-xl text-sm text-blue-600 dark:text-blue-400 italic">
                                        {interimTranscript}…
                                    </div>
                                )}

                                <form onSubmit={handleSubmit} className="flex items-end gap-3">
                                    <div className="flex-1 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl px-4 py-3 focus-within:border-blue-400 dark:focus-within:border-blue-500 transition-colors">
                                        <textarea
                                            ref={textareaRef}
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={handleKeyDown}
                                            placeholder={isConnected ? 'Command the Head of Council…' : 'Connecting…'}
                                            disabled={!isConnected}
                                            className="w-full bg-transparent resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none text-[15px]"
                                            rows={1}
                                            style={{ maxHeight: '150px' }}
                                        />
                                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100 dark:border-[#1e2535]">
                                            <div className="flex items-center gap-1">
                                                <button type="button" onClick={() => setShowFileMenu(!showFileMenu)} title="Attach file"
                                                    className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500 transition-colors">
                                                    <Paperclip className="w-4 h-4" />
                                                </button>
                                                <button type="button" onClick={() => fileInputRef.current?.click()} title="Upload image"
                                                    className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500 transition-colors">
                                                    <ImageIcon className="w-4 h-4" />
                                                </button>
                                                {voiceAvailable && (
                                                    <>
                                                        <button type="button" onClick={handleVoiceButtonClick}
                                                            className={`p-1.5 rounded-lg transition-colors ${
                                                                isRecording
                                                                    ? 'bg-red-100 dark:bg-red-500/20 text-red-500 dark:text-red-400'
                                                                    : 'hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500'
                                                            }`} title={isRecording ? 'Stop recording' : 'Start voice input'}>
                                                            {isRecording ? <Pause className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                                                        </button>
                                                        <button type="button" onClick={() => setShowVoiceSettings(true)}
                                                            className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-[#1e2535] text-gray-400 dark:text-gray-500 transition-colors" title="Voice Settings">
                                                            <Settings2 className="w-4 h-4" />
                                                        </button>
                                                    </>
                                                )}
                                                {isRecording && (
                                                    <span className="text-xs text-red-500 dark:text-red-400 font-mono">
                                                        {String(Math.floor(recordingTime / 60)).padStart(2, '0')}:{String(recordingTime % 60).padStart(2, '0')}
                                                    </span>
                                                )}
                                            </div>
                                            <span className="text-xs text-gray-400 dark:text-gray-500">Enter to send · Shift+Enter for new line</span>
                                        </div>
                                    </div>
                                    <button type="submit"
                                        disabled={(!input.trim() && uploadedFiles.length === 0) || !isConnected}
                                        className="p-3.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 dark:disabled:bg-[#1e2535] disabled:cursor-not-allowed text-white disabled:text-gray-400 dark:disabled:text-gray-600 rounded-2xl transition-all duration-150 shadow-lg shadow-blue-500/25 dark:shadow-blue-900/40 disabled:shadow-none flex-shrink-0">
                                        <Send className="w-5 h-5" />
                                    </button>
                                </form>

                                <input ref={fileInputRef} type="file" className="hidden" multiple
                                    accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.csv,.json,.py,.js,.ts"
                                    onChange={(e) => handleFileSelect(e.target.files)} />
                            </div>
                        </div>
                    </>
                )}

                {/* ── Inbox Tab ──────────────────────────────────────────────── */}
                {activeTab === 'inbox' && (
                    <div className="flex-1 flex overflow-hidden">
                        {/* Conversation list */}
                        <div className="w-80 flex-shrink-0 bg-white dark:bg-[#161b27] border-r border-gray-200 dark:border-[#1e2535] flex flex-col">
                            <div className="p-4 border-b border-gray-200 dark:border-[#1e2535] flex items-center justify-between">
                                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Active Conversations</h2>
                                {inboxLoading && <LoadingSpinner size="sm" className="text-gray-400" />}
                            </div>
                            <div className="flex-1 overflow-y-auto divide-y divide-gray-100 dark:divide-[#1e2535]">
                                {conversations.length === 0 && !inboxLoading ? (
                                    <div className="p-8">
                                        <EmptyState icon={Inbox} title="No active conversations" size="sm" />
                                    </div>
                                ) : conversations.map((conv) => {
                                    const latestMsg   = conv.messages?.at(-1);
                                    const channelType = conv.messages?.find((m: any) => m.sender_channel)?.sender_channel;
                                    return (
                                        <button key={conv.id} onClick={() => setSelectedId(conv.id)}
                                            className={`w-full text-left px-4 py-3.5 flex items-center gap-3 transition-colors duration-150 ${
                                                selectedId === conv.id
                                                    ? 'bg-emerald-50 dark:bg-emerald-500/10'
                                                    : 'hover:bg-gray-50 dark:hover:bg-[#1e2535]'
                                            }`}>
                                            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
                                                {channelType === 'whatsapp' ? <Smartphone className="w-4 h-4" />
                                                 : channelType === 'slack'  ? <Slack        className="w-4 h-4" />
                                                 : channelType === 'email'  ? <Mail          className="w-4 h-4" />
                                                 : <MessageCircle className="w-4 h-4" />}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                                        {conv.title || 'Conversation'}
                                                    </span>
                                                    {latestMsg && (
                                                        <span className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0 ml-2">
                                                            {formatTimestamp(new Date((latestMsg as any).created_at || (latestMsg as any).timestamp))}
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                    {latestMsg?.content || 'No messages'}
                                                </p>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Conversation detail */}
                        <div className="flex-1 flex flex-col bg-gray-50 dark:bg-[#0f1117]">
                            {selectedConv ? (
                                <>
                                    <div className="flex-1 overflow-y-auto p-4 space-y-3">
                                        {selectedConv.messages?.map((msg: any) => (
                                            <div key={msg.id} className={`flex ${msg.role === 'system' ? 'justify-start' : 'justify-end'}`}>
                                                <div className={`max-w-[70%] px-4 py-2.5 rounded-2xl text-sm ${
                                                    msg.role === 'system'
                                                        ? 'bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] text-gray-900 dark:text-gray-100'
                                                        : 'bg-emerald-600 text-white'
                                                }`}>
                                                    {msg.sender_channel && (
                                                        <span className="text-[10px] font-medium uppercase tracking-wide opacity-60 block mb-1">
                                                            via {msg.sender_channel}
                                                        </span>
                                                    )}
                                                    <p className="leading-relaxed">{msg.content}</p>
                                                </div>
                                            </div>
                                        ))}
                                        <div ref={inboxMessagesEndRef} />
                                    </div>
                                    <div className="flex-shrink-0 p-4 bg-white dark:bg-[#161b27] border-t border-gray-200 dark:border-[#1e2535]">
                                        <div className="flex items-end gap-3">
                                            <div className="flex-1 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl px-4 py-3">
                                                <textarea
                                                    value={replyContent}
                                                    onChange={(e) => setReplyContent(e.target.value)}
                                                    placeholder="Type a reply…"
                                                    className="w-full bg-transparent resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none text-sm"
                                                    rows={1}
                                                    style={{ maxHeight: '150px' }}
                                                />
                                            </div>
                                            <button onClick={handleSendReply}
                                                disabled={!replyContent.trim() || isSending}
                                                className="p-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-200 dark:disabled:bg-[#1e2535] disabled:cursor-not-allowed text-white disabled:text-gray-400 dark:disabled:text-gray-600 rounded-xl transition-all duration-150">
                                                {isSending ? <LoadingSpinner size="md" /> : <Send className="w-5 h-5" />}
                                            </button>
                                        </div>
                                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">Reply will be routed to the user's original channel.</p>
                                    </div>
                                </>
                            ) : (
                                <div className="flex-1 flex items-center justify-center">
                                    <EmptyState icon={Inbox} title="Select a conversation" />
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Files Tab ──────────────────────────────────────────────── */}
                {activeTab === 'files' && (
                    <div
                        onDragOver={(e) => { e.preventDefault(); setIsDraggingOver(true); }}
                        onDragLeave={() => setIsDraggingOver(false)}
                        onDrop={(e) => { e.preventDefault(); setIsDraggingOver(false); handleBrowserUpload(e.dataTransfer.files); }}
                        className={`flex-1 flex flex-col overflow-hidden transition-colors duration-150 ${isDraggingOver ? 'bg-violet-50 dark:bg-violet-900/10' : ''}`}>

                        {/* Toolbar */}
                        <div className="flex-shrink-0 bg-white dark:bg-[#161b27] border-b border-gray-200 dark:border-[#1e2535] px-6 py-3 flex items-center gap-3">
                            <div className="flex-1 relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                                <input value={browserSearch} onChange={(e) => setBrowserSearch(e.target.value)}
                                    placeholder="Search files…"
                                    className="w-full pl-9 pr-4 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:border-violet-400 dark:focus:border-violet-500" />
                            </div>
                            <select value={browserCategory} onChange={(e) => setBrowserCategory(e.target.value)}
                                className="px-3 py-2 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl text-sm text-gray-700 dark:text-gray-300 focus:outline-none">
                                <option value="all">All types</option>
                                <option value="image">Images</option>
                                <option value="document">Documents</option>
                                <option value="code">Code</option>
                                <option value="audio">Audio</option>
                                <option value="video">Video</option>
                            </select>
                            <button onClick={() => browserUploadRef.current?.click()}
                                className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium rounded-xl transition-colors shadow-sm">
                                <UploadCloud className="w-4 h-4" /> Upload
                            </button>
                            <input ref={browserUploadRef} type="file" className="hidden" multiple
                                onChange={(e) => handleBrowserUpload(e.target.files)} />
                        </div>

                        {/* Stats bar */}
                        {browserStats && (
                            <div className="flex-shrink-0 px-6 py-2 bg-gray-50 dark:bg-[#0f1117] border-b border-gray-100 dark:border-[#1e2535] flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                                <span className="flex items-center gap-1.5"><HardDrive className="w-3.5 h-3.5" />{browserStats.total_files} files</span>
                                <span>{((browserStats.total_size_bytes) / (1024 * 1024)).toFixed(1)} MB used</span>
                                <div className="flex-1 h-1.5 bg-gray-200 dark:bg-[#1e2535] rounded-full overflow-hidden">
                                    <div className="h-full bg-violet-500 rounded-full transition-all"
                                        style={{ width: `${Math.min(browserStats.storage_used_percent, 100)}%` }} />
                                </div>
                                <span>{browserStats.storage_used_percent.toFixed(1)}%</span>
                            </div>
                        )}

                        {/* File grid */}
                        <div className="flex-1 overflow-y-auto p-6">
                            {isDraggingOver && (
                                <div className="absolute inset-0 z-10 flex items-center justify-center bg-violet-500/10 border-2 border-dashed border-violet-400 rounded-2xl m-4">
                                    <div className="text-center">
                                        <UploadCloud className="w-12 h-12 text-violet-500 mx-auto mb-2" />
                                        <p className="text-violet-600 dark:text-violet-400 font-medium">Drop files to upload</p>
                                    </div>
                                </div>
                            )}

                            {browserLoading ? (
                                <div className="flex items-center justify-center h-48">
                                    <LoadingSpinner size="lg" className="text-violet-500" />
                                </div>
                            ) : filteredFiles.length === 0 ? (
                                <div className="h-48 flex items-center justify-center">
                                    <EmptyState
                                        icon={FolderOpen}
                                        title={browserSearch ? 'No files match your search' : 'No files uploaded yet'}
                                    />
                                </div>
                            ) : (
                                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                                    {filteredFiles.map((f) => (
                                        <div key={f.stored_name}
                                            className="group relative bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-3 hover:border-violet-300 dark:hover:border-violet-500/40 transition-all duration-150">
                                            <div className="w-full aspect-square rounded-xl bg-gray-50 dark:bg-[#0f1117] flex items-center justify-center mb-2 overflow-hidden">
                                                {f.url && (f.filename.match(/\.(jpg|jpeg|png|gif|webp)$/i)) ? (
                                                    <img src={f.url} alt={f.filename} className="w-full h-full object-cover" />
                                                ) : (
                                                    <div className="text-gray-400 dark:text-gray-500 scale-150">
                                                        {getFileIcon(f.category || '')}
                                                    </div>
                                                )}
                                            </div>
                                            <p className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate" title={f.filename}>{f.filename}</p>
                                            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{formatFileSize(f.size)}</p>

                                            {/* Actions overlay */}
                                            <div className="absolute inset-0 bg-black/40 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                                {f.url && (
                                                    <a href={f.url} target="_blank" rel="noreferrer"
                                                        className="p-2 bg-white/20 hover:bg-white/30 rounded-lg text-white transition-colors" title="View">
                                                        <Eye className="w-4 h-4" />
                                                    </a>
                                                )}
                                                <button onClick={() => handleDeleteFile(f.stored_name)}
                                                    disabled={deletingFile === f.stored_name}
                                                    className="p-2 bg-red-500/80 hover:bg-red-500 rounded-lg text-white transition-colors" title="Delete">
                                                    {deletingFile === f.stored_name ? <LoadingSpinner size="sm" /> : <Trash2 className="w-4 h-4" />}
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Image preview modal ─────────────────────────────────────── */}
                {imagePreview && (
                    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={() => setImagePreview(null)}>
                        <div className="relative max-w-4xl max-h-full" onClick={(e) => e.stopPropagation()}>
                            <img src={imagePreview.url} alt={imagePreview.name} className="max-h-[85vh] max-w-full rounded-2xl object-contain" />
                            <button onClick={() => setImagePreview(null)}
                                className="absolute top-3 right-3 p-2 bg-black/50 rounded-xl text-white hover:bg-black/70 transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                    </div>
                )}

                {/* ── Voice Settings Modal ────────────────────────────────────── */}
                {showVoiceSettings && (
                    <VoiceSettingsModal onClose={() => setShowVoiceSettings(false)} />
                )}
            </div>
        </div>
    );
}