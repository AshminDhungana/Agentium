import { useState, useEffect, useRef } from 'react';
import { Mic, Trash2, Square, Settings2, UserPlus, Info, Radio, Volume2, Ear, Wifi, WifiOff, RefreshCw, ChevronRight } from 'lucide-react';
import { voiceApi, type VoiceProvidersResponse, type VoiceDbConfig } from '@/services/voiceApi';
import { voiceBridgeService, BridgeStatus } from '@/services/voiceBridge';
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

type SettingsTab = 'engine' | 'speaker' | 'about';

const TABS: { key: SettingsTab; label: string; icon: typeof Settings2 }[] = [
  { key: 'engine', label: 'Engine', icon: Radio },
  { key: 'speaker', label: 'Speaker ID', icon: Ear },
  { key: 'about', label: 'About', icon: Info },
];

export function VoiceSettingsModal({ onClose }: VoiceSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>('engine');

  // ── Engine state ──
  const [requireWakeWord, setRequireWakeWord] = useState(true);
  const [ttsVoice, setTtsVoice] = useState('am_adam');
  const [ttsProvider, setTtsProvider] = useState<'kokoro' | 'openai'>('kokoro');
  const [proactiveEnabled, setProactiveEnabled] = useState(false);
  const [speakerIdentification, setSpeakerIdentification] = useState(false);
  const [voiceMode, setVoiceMode] = useState<'push-to-talk' | 'open-mic'>('push-to-talk');
  const [isSavingConfig, setIsSavingConfig] = useState(false);

  // ── Provider/voice data ──
  const [providersData, setProvidersData] = useState<VoiceProvidersResponse | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<'all' | 'kokoro' | 'openai'>('all');

  // ── Speaker state ──
  const [speakers, setSpeakers] = useState<SpeakerProfile[]>([]);
  const [isLoadingSpeakers, setIsLoadingSpeakers] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [speakerName, setSpeakerName] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);

  // ── Bridge state ──
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>(voiceBridgeService.status);

  // ── Media recorder refs ──
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const recordingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // ── Load config on mount ──
  useEffect(() => {
    const saved = localStorage.getItem('voice_engine_config');
    if (saved) {
      try {
        const cfg = JSON.parse(saved);
        setRequireWakeWord(cfg.requireWakeWord ?? true);
        setTtsVoice(cfg.ttsVoice ?? 'am_adam');
        setTtsProvider(cfg.ttsProvider ?? 'kokoro');
        setProactiveEnabled(cfg.proactiveEnabled ?? false);
        setSpeakerIdentification(cfg.speakerIdentification ?? false);
        setVoiceMode(cfg.voiceMode ?? 'push-to-talk');
      } catch { /* ignore */ }
    }
    Promise.all([
      voiceApi.getVoiceConfigDb(),
      voiceApi.getVoiceProviders(),
    ]).then(([cfg, providers]) => {
      if (cfg) {
        setRequireWakeWord(cfg.require_wake_word);
        setTtsVoice(cfg.tts_voice);
        setTtsProvider(cfg.tts_provider);
        setProactiveEnabled(cfg.proactive_enabled);
        setSpeakerIdentification(cfg.speaker_identification);
      }
      if (providers) {
        setProvidersData(providers);
      }
    }).catch(() => {});
    loadSpeakers();
    return voiceBridgeService.onStatusChange(setBridgeStatus);
  }, []);

  const saveConfig = async () => {
    setIsSavingConfig(true);
    const cfg = { requireWakeWord, ttsVoice, ttsProvider, proactiveEnabled, speakerIdentification, voiceMode };
    localStorage.setItem('voice_engine_config', JSON.stringify(cfg));
    try {
      await voiceApi.setVoiceConfigDb({
        require_wake_word: requireWakeWord,
        tts_voice: ttsVoice,
        tts_provider: ttsProvider,
        proactive_enabled: proactiveEnabled,
        speaker_identification: speakerIdentification,
      });
      showToast.success('Voice engine settings saved');
    } catch {
      showToast.success('Voice engine settings saved locally');
    } finally {
      setIsSavingConfig(false);
    }
  };

  // ── Speaker methods ──
  const loadSpeakers = async () => {
    setIsLoadingSpeakers(true);
    try {
      const res = await voiceApi.getSpeakers();
      setSpeakers(res.speakers || []);
    } catch {
      showToast.error('Failed to load speaker profiles');
    } finally {
      setIsLoadingSpeakers(false);
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
      recordingIntervalRef.current = setInterval(() => setRecordingTime((p) => p + 1), 1000);
    } catch {
      showToast.error('Microphone access denied');
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
      showToast.error('Failed to enroll speaker. Audio might be too short or unclear.');
    } finally {
      setIsRegistering(false);
    }
  };

  const handleDeleteSpeaker = async (id: string) => {
    try {
      await voiceApi.deleteSpeaker(id);
      showToast.success('Speaker profile deleted');
      await loadSpeakers();
    } catch {
      showToast.error('Failed to delete speaker');
    }
  };

  const handleConnectBridge = () => {
    voiceBridgeService.connect().catch(() => {});
  };

  // ── Header ──
  const header = (
    <div className="flex items-center gap-4">
      <div className="relative w-11 h-11 flex-shrink-0">
        <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
          <Radio className="w-5 h-5 text-white" />
        </div>
        <span className={`absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-[#161b27] transition-colors ${
          bridgeStatus === 'connected' ? 'bg-emerald-500'
          : bridgeStatus === 'connecting' ? 'bg-amber-400'
          : bridgeStatus === 'error' ? 'bg-red-500'
          : 'bg-gray-400'
        }`} />
      </div>
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">Voice Settings</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Voice bridge · Engine · Speaker identification</p>
      </div>
    </div>
  );

  return (
    <Modal open onClose={onClose} title={header} size="lg" className="!max-w-xl">
      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-gray-100 dark:bg-[#0f1117] rounded-xl p-1 border border-gray-200 dark:border-[#1e2535]">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 flex-1 justify-center ${
              activeTab === key
                ? 'bg-white dark:bg-[#161b27] text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Engine Tab ── */}
      {activeTab === 'engine' && (
        <div className="space-y-6">
          {/* Wake word + Voice mode */}
          <div className="grid grid-cols-2 gap-4">
            <label className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl cursor-pointer transition-colors hover:border-blue-300 dark:hover:border-blue-500/40">
              <input
                type="checkbox"
                checked={requireWakeWord}
                onChange={(e) => setRequireWakeWord(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <div>
                <span className="text-sm font-medium text-gray-900 dark:text-white">Wake word</span>
                <p className="text-xs text-gray-500 dark:text-gray-400">Require "Hey Agentium"</p>
              </div>
            </label>

            <label className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl cursor-pointer transition-colors hover:border-blue-300 dark:hover:border-blue-500/40">
              <input
                type="checkbox"
                checked={proactiveEnabled}
                onChange={(e) => setProactiveEnabled(e.target.checked)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <div>
                <span className="text-sm font-medium text-gray-900 dark:text-white">Proactive</span>
                <p className="text-xs text-gray-500 dark:text-gray-400">AI-initiated announcements</p>
              </div>
            </label>
          </div>

          {/* Voice mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Voice Mode</label>
            <div className="flex gap-2">
              {(['push-to-talk', 'open-mic'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setVoiceMode(mode)}
                  className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                    voiceMode === mode
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400'
                      : 'border-gray-200 dark:border-[#1e2535] text-gray-600 dark:text-gray-400 bg-white dark:bg-transparent hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {mode === 'push-to-talk' ? <Mic className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                  {mode === 'push-to-talk' ? 'Push to Talk' : 'Open Mic'}
                </button>
              ))}
            </div>
          </div>

          {/* TTS Provider & Voice */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">TTS Provider</label>
            <div className="flex gap-1 mb-4">
              {(['all', 'kokoro', 'openai'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setSelectedProvider(p)}
                  className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                    selectedProvider === p
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400'
                      : 'border-gray-200 dark:border-[#1e2535] text-gray-500 dark:text-gray-500 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {p === 'all' ? 'All' : p === 'kokoro' ? 'Kokoro (Offline)' : 'OpenAI (Cloud)'}
                </button>
              ))}
            </div>

            {providersData && (
              <>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Voice</label>
                <select
                  value={ttsVoice}
                  onChange={(e) => {
                    const val = e.target.value;
                    setTtsVoice(val);
                    const kokoroPrefixes = ['af_', 'am_', 'bf_', 'bm_', 'cf_', 'in_', 'au_'];
                    const provider = kokoroPrefixes.some(p => val.startsWith(p)) ? 'kokoro' : 'openai';
                    setTtsProvider(provider);
                  }}
                  className="w-full bg-white dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
                >
                  {(() => {
                    const allEntries = Object.entries(providersData.providers)
                      .filter(([name]) => selectedProvider === 'all' || name === selectedProvider);
                    const availableEntries = allEntries.filter(([, info]) => info.available);
                    const providerEntries = availableEntries.length > 0 ? availableEntries : allEntries;
                    return providerEntries.flatMap(([name, info]) =>
                      info.voices.map((v) => (
                        <option key={`${name}:${v.id}`} value={v.id}>
                          {v.name} ({v.gender}) — {name === 'openai' ? 'Cloud' : 'Offline'}
                        </option>
                      ))
                    );
                  })()}
                </select>

                {(() => {
                  const allEntries = Object.entries(providersData.providers)
                    .filter(([name]) => selectedProvider === 'all' || name === selectedProvider);
                  const unavailable = allEntries.filter(([, info]) => !info.available);
                  return unavailable.map(([name]) => (
                    <p key={`notice:${name}`} className="text-xs text-amber-500 mt-2">
                      {name === 'kokoro'
                        ? 'Kokoro engine not installed on the server. Configure an OpenAI API key or install Kokoro.'
                        : 'OpenAI API key not configured. Add one in Models settings or use Kokoro.'}
                    </p>
                  ));
                })()}

                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  {ttsProvider === 'openai'
                    ? 'Requires OpenAI API key configured in Models page'
                    : 'Offline Kokoro TTS — always available'}
                </p>
              </>
            )}
          </div>

          {/* Save */}
          <div className="flex items-center justify-between pt-2 border-t border-gray-100 dark:border-[#1e2535]">
            <span className="text-xs text-gray-500 dark:text-gray-400">Changes saved automatically</span>
            <button
              onClick={saveConfig}
              disabled={isSavingConfig}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isSavingConfig ? <LoadingSpinner size="sm" /> : 'Save'}
            </button>
          </div>
        </div>
      )}

      {/* ── Speaker ID Tab ── */}
      {activeTab === 'speaker' && (
        <div className="space-y-6">
          {/* Enable toggle */}
          <label className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-xl cursor-pointer transition-colors hover:border-blue-300 dark:hover:border-blue-500/40">
            <input
              type="checkbox"
              checked={speakerIdentification}
              onChange={(e) => setSpeakerIdentification(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <div>
              <span className="text-sm font-medium text-gray-900 dark:text-white">Speaker Identification</span>
              <p className="text-xs text-gray-500 dark:text-gray-400">Enroll voices so the AI can identify who is speaking in multi-user settings.</p>
            </div>
          </label>

          {/* Enrollment */}
          <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <UserPlus className="w-4 h-4 text-blue-500" />
              <span className="text-sm font-medium text-gray-900 dark:text-white">Enroll a Speaker</span>
            </div>
            <input
              type="text"
              value={speakerName}
              onChange={(e) => setSpeakerName(e.target.value)}
              placeholder="e.g. Host, Alice, Guest 1"
              disabled={isRecording || isRegistering}
              className="w-full bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-blue-500 mb-3"
            />
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-2">
                {isRecording && <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
                {isRecording ? `Recording... 00:${recordingTime.toString().padStart(2, '0')}` : 'Record a 3–5 second sample.'}
              </div>
              <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={isRegistering}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
                  isRecording
                    ? 'bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-500/30'
                    : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50'
                }`}
              >
                {isRegistering ? <LoadingSpinner size="sm" /> : isRecording ? <Square className="w-4 h-4" fill="currentColor" /> : <Mic className="w-4 h-4" />}
                {isRegistering ? 'Processing' : isRecording ? 'Stop Recording' : 'Start Enroll'}
              </button>
            </div>
          </div>

          {/* Enrolled profiles */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Enrolled Profiles</h3>
            {isLoadingSpeakers ? (
              <div className="flex items-center justify-center py-6">
                <LoadingSpinner size="md" />
              </div>
            ) : speakers.length === 0 ? (
              <div className="text-center py-6 border border-dashed border-gray-200 dark:border-[#1e2535] rounded-2xl">
                <p className="text-sm text-gray-500 dark:text-gray-400">No speaker profiles enrolled yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {speakers.map((speaker) => (
                  <div key={speaker.id} className="flex items-center justify-between bg-white dark:bg-[#161b27] border border-gray-200 dark:border-[#1e2535] p-3 rounded-xl">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-white text-xs font-bold">
                        {speaker.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-medium text-sm text-gray-900 dark:text-white">{speaker.name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          Enrolled {new Date(speaker.enrolled_at).toLocaleDateString()} · {speaker.sample_count} sample{speaker.sample_count !== 1 ? 's' : ''}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteSpeaker(speaker.id)}
                      aria-label={`Delete ${speaker.name}`}
                      className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── About Tab ── */}
      {activeTab === 'about' && (
        <div className="space-y-6">
          {/* Bridge connection */}
          <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                {bridgeStatus === 'connected' ? (
                  <Wifi className="w-4 h-4 text-emerald-500" />
                ) : bridgeStatus === 'connecting' ? (
                  <LoadingSpinner size="xs" />
                ) : (
                  <WifiOff className="w-4 h-4 text-gray-400" />
                )}
                <span className="text-sm font-medium text-gray-900 dark:text-white">Voice Bridge</span>
              </div>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                bridgeStatus === 'connected' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400'
                : bridgeStatus === 'connecting' ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400'
                : bridgeStatus === 'error' ? 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400'
                : 'bg-gray-100 dark:bg-gray-500/20 text-gray-600 dark:text-gray-400'
              }`}>
                {bridgeStatus === 'connected' ? 'Connected' : bridgeStatus === 'connecting' ? 'Connecting…' : bridgeStatus === 'error' ? 'Error' : 'Offline'}
              </span>
            </div>

            {bridgeStatus !== 'connected' && (
              <button
                onClick={handleConnectBridge}
                disabled={bridgeStatus === 'connecting'}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${bridgeStatus === 'connecting' ? 'animate-spin' : ''}`} />
                {bridgeStatus === 'connecting' ? 'Connecting…' : 'Connect Bridge'}
              </button>
            )}
          </div>

          {/* Install info */}
          <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <ChevronRight className="w-4 h-4 text-blue-500" />
              <span className="text-sm font-medium text-gray-900 dark:text-white">Installation</span>
            </div>
            {bridgeStatus === 'offline' && (
              <>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  The voice bridge runs as a Windows desktop app. Install it from the project root:
                </p>
                <div className="bg-[#0f1117] rounded-xl p-3 mb-2">
                  <code className="text-xs text-green-400 break-all">powershell -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"</code>
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText('powershell -ExecutionPolicy Bypass -File ".\\scripts\\setup.ps1"')}
                  className="text-xs text-blue-500 hover:text-blue-400 transition-colors"
                >
                  Copy to clipboard
                </button>
              </>
            )}
            {bridgeStatus === 'connected' && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Voice bridge is running. WebSocket connection is active.
              </p>
            )}
          </div>

          {/* Version */}
          <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] rounded-2xl p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-900 dark:text-white">Agentium Voice</span>
              <span className="text-xs text-gray-500 dark:text-gray-400">New</span>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Powered by Kokoro TTS · Whisper STT · WebSocket streaming
            </p>
          </div>
        </div>
      )}
    </Modal>
  );
}
