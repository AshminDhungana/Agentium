/**
 * @description Modal for voice settings and speaker profile enrollment.
 * Supports microphone recording for speaker registration.
 * @example
 * ```tsx
 * import { VoiceSettingsModal } from '@/components/VoiceSettingsModal';
 *
 * <VoiceSettingsModal onClose={close} />
 * ```
 * @param {() => void} props.onClose - Callback to close the modal.
 */
import React, { useState, useEffect, useRef } from 'react';
import { Mic, Trash2, Play, Square, Settings2 } from 'lucide-react';
import { voiceApi } from '@/services/voiceApi';
import { showToast } from '@/hooks/useToast';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { Modal } from '@/components/ui/Modal';

interface SpeakerProfile {
    id: string;
    name: string;
    user_id?: string;
    enrolled_at: string;
    sample_count: number;
    has_embedding: boolean;
}

interface VoiceSettingsModalProps {
    onClose: () => void;
}

export function VoiceSettingsModal({ onClose }: VoiceSettingsModalProps) {
    const [speakers, setSpeakers] = useState<SpeakerProfile[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRecording, setIsRecording] = useState(false);
    const [recordingTime, setRecordingTime] = useState(0);
    const [speakerName, setSpeakerName] = useState('');
    const [isRegistering, setIsRegistering] = useState(false);

    // ── Voice engine config (Jarvis upgrade, Phase H) ──
    const [requireWakeWord, setRequireWakeWord] = useState(true);
    const [ttsVoice, setTtsVoice] = useState('af_bella');
    const [proactiveEnabled, setProactiveEnabled] = useState(false);
    const [isSavingConfig, setIsSavingConfig] = useState(false);
    const [speakerIdentification, setSpeakerIdentification] = useState(false);

    useEffect(() => {
        const saved = localStorage.getItem('voice_engine_config');
        if (saved) {
            try {
                const cfg = JSON.parse(saved);
                setRequireWakeWord(cfg.requireWakeWord ?? true);
                setTtsVoice(cfg.ttsVoice ?? 'af_bella');
                setProactiveEnabled(cfg.proactiveEnabled ?? false);
                setSpeakerIdentification(cfg.speakerIdentification ?? false);
            } catch {
                /* ignore malformed */
            }
        }
        voiceApi.getVoiceConfig().then((cfg: any) => {
            if (cfg) {
                setRequireWakeWord(cfg.requireWakeWord ?? requireWakeWord);
                setTtsVoice(cfg.ttsVoice ?? ttsVoice);
                setProactiveEnabled(cfg.proactiveEnabled ?? proactiveEnabled);
                setSpeakerIdentification(cfg.speakerIdentification ?? speakerIdentification);
            }
        }).catch(() => { /* best-effort */ });
    }, []);

    const saveConfig = async () => {
        setIsSavingConfig(true);
        const cfg = { requireWakeWord, ttsVoice, proactiveEnabled, speakerIdentification };
        localStorage.setItem('voice_engine_config', JSON.stringify(cfg));
        try {
            await voiceApi.setVoiceConfig(cfg);
            showToast.success('Voice engine settings saved');
        } catch {
            showToast.success('Voice engine settings saved locally');
        } finally {
            setIsSavingConfig(false);
        }
    };

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioStreamRef = useRef<MediaStream | null>(null);
    const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    useEffect(() => {
        loadSpeakers();
        return () => stopRecording();
    }, []);

    const loadSpeakers = async () => {
        setIsLoading(true);
        try {
            const res = await voiceApi.getSpeakers();
            setSpeakers(res.speakers || []);
        } catch (error) {
            showToast.error('Failed to load speaker profiles');
        } finally {
            setIsLoading(false);
        }
    };

    const startRecording = async () => {
        if (!speakerName.trim()) {
            showToast.error('Please enter a name for the speaker profile');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioStreamRef.current = stream;
            const recorder = new MediaRecorder(stream);
            mediaRecorderRef.current = recorder;
            chunksRef.current = [];

            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            recorder.onstop = async () => {
                const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
                await handleRegister(blob);
            };

            recorder.start();
            setIsRecording(true);
            setRecordingTime(0);
            recordingIntervalRef.current = setInterval(() => setRecordingTime(p => p + 1), 1000);
        } catch (error: any) {
            showToast.error('Microphone access denied or error occurred');
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop();
        }
        if (audioStreamRef.current) {
            audioStreamRef.current.getTracks().forEach((t) => t.stop());
            audioStreamRef.current = null;
        }
        if (recordingIntervalRef.current) {
            clearInterval(recordingIntervalRef.current);
            recordingIntervalRef.current = null;
        }
        setIsRecording(false);
    };

    const handleRegister = async (blob: Blob) => {
        setIsRegistering(true);
        try {
            await voiceApi.registerSpeaker(blob, speakerName.trim());
            showToast.success('Speaker enrolled successfully');
            setSpeakerName('');
            await loadSpeakers();
        } catch (error: any) {
            showToast.error('Failed to enroll speaker profile. Audio might be too short or unclear.');
        } finally {
            setIsRegistering(false);
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await voiceApi.deleteSpeaker(id);
            showToast.success('Speaker profile deleted');
            await loadSpeakers();
        } catch (error) {
            showToast.error('Failed to delete speaker');
        }
    };

    const titleNode = (
        <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-500/20 flex items-center justify-center">
                <Settings2 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">Voice Settings</h2>
        </div>
    );

    return (
        <Modal open onClose={onClose} title={titleNode} size="md" className="!max-w-lg">
            <div className="p-6 overflow-y-auto flex-1 h-full">
                    {/* ── Voice Engine (Jarvis upgrade, Phase H) ── */}
                    <div className="mb-8">
                        <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-3">Voice Engine</h3>
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 mb-3">
                            <input
                                type="checkbox"
                                checked={requireWakeWord}
                                onChange={(e) => setRequireWakeWord(e.target.checked)}
                                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                            Require wake word
                        </label>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            TTS Voice
                        </label>
                        <select
                            value={ttsVoice}
                            onChange={(e) => setTtsVoice(e.target.value)}
                            className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 mb-3"
                        >
                            {['af_bella', 'am_adam', 'bf_emma', 'bm_george', 'af_nicole', 'af_sarah'].map((v) => (
                                <option key={v} value={v}>{v}</option>
                            ))}
                        </select>
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 mb-4">
                            <input
                                type="checkbox"
                                checked={proactiveEnabled}
                                onChange={(e) => setProactiveEnabled(e.target.checked)}
                                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                            Proactive announcements
                        </label>
                        <button
                            onClick={saveConfig}
                            disabled={isSavingConfig}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            {isSavingConfig ? <LoadingSpinner size="sm" /> : 'Save'}
                        </button>
                    </div>

                    <div className="mb-8">
                        <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-1">Speaker Identification</h3>
                        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 mb-3">
                            <input
                                type="checkbox"
                                checked={speakerIdentification}
                                onChange={(e) => setSpeakerIdentification(e.target.checked)}
                                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                            Enable speaker identification
                        </label>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                            Enroll voices so the AI can identify who is speaking in multi-user settings.
                        </p>

                        <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Speaker Name
                            </label>
                            <input
                                type="text"
                                value={speakerName}
                                onChange={(e) => setSpeakerName(e.target.value)}
                                placeholder="e.g. Host, Alice, Guest 1"
                                disabled={isRecording || isRegistering}
                                className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 mb-4"
                            />
                            <div className="flex items-center justify-between">
                                <div className="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2">
                                    {isRecording && <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
                                    {isRecording ? `Recording... 00:${recordingTime.toString().padStart(2, '0')}` : 'Record a 3-5 second sample.'}
                                </div>
                                <button
                                    onClick={isRecording ? stopRecording : startRecording}
                                    disabled={isRegistering}
                                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                                        isRecording
                                            ? 'bg-red-100 text-red-600 hover:bg-red-200 dark:bg-red-500/20 dark:text-red-400'
                                            : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50'
                                    }`}
                                >
                                    {isRegistering ? <LoadingSpinner size="sm" /> : isRecording ? <Square className="w-4 h-4" fill="currentColor"/> : <Mic className="w-4 h-4" />}
                                    {isRegistering ? 'Processing' : isRecording ? 'Stop Recording' : 'Start Enroll'}
                                </button>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-3">Enrolled Profiles</h3>
                        {isLoading ? (
                            <div className="flex items-center justify-center py-8">
                                <LoadingSpinner size="md" />
                            </div>
                        ) : speakers.length === 0 ? (
                            <div className="text-center py-6 border border-dashed border-gray-200 dark:border-[#1e2535] rounded-2xl">
                                <p className="text-sm text-gray-600 dark:text-gray-400">No speaker profiles enrolled yet.</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {speakers.map((speaker) => (
                                    <div key={speaker.id} className="flex items-center justify-between bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] p-3 rounded-xl shadow-sm">
                                        <div>
                                            <div className="font-medium text-sm text-gray-900 dark:text-white">{speaker.name}</div>
                                            <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                                                Enrolled: {new Date(speaker.enrolled_at).toLocaleDateString()}
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => handleDelete(speaker.id)}
                                            aria-label={`Delete ${speaker.name}`}
                                            title="Delete"
                                            className="p-2 text-gray-600 hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-600 dark:hover:text-gray-600 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                </div>
        </Modal>
    );
}
