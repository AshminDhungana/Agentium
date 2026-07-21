import { useState, useEffect, useCallback } from 'react';
import { X, Mic, MicOff, Settings2 } from 'lucide-react';
import { voiceBridgeService, BridgeStatus, VoiceState, TranscriptEvent } from '@/services/voiceBridge';
import { VoiceOrb } from '@/components/VoiceOrb';

interface VoiceModePanelProps {
  onClose: () => void;
}

const STATE_LABELS: Record<string, string> = {
  idle: 'Voice Ready',
  listening: 'Listening\u2026',
  thinking: 'Thinking\u2026',
  speaking: 'Speaking\u2026',
  interrupted: 'Interrupted',
};

const STATE_COLORS: Record<string, string> = {
  idle: 'text-gray-400',
  listening: 'text-blue-400',
  thinking: 'text-purple-400',
  speaking: 'text-emerald-400',
  interrupted: 'text-amber-400',
};

export function VoiceModePanel({ onClose }: VoiceModePanelProps) {
  const [bridgeStatus, setBridgeStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcripts, setTranscripts] = useState<TranscriptEvent[]>([]);
  const [isMuted, setIsMuted] = useState(false);

  useEffect(() => {
    return voiceBridgeService.onStatusChange(setBridgeStatus);
  }, []);

  useEffect(() => {
    return voiceBridgeService.onStateChange((s) => {
      if (s) setVoiceState(s);
    });
  }, []);

  useEffect(() => {
    return voiceBridgeService.onTranscript((event: TranscriptEvent) => {
      setTranscripts((prev) => [...prev.slice(-49), event]);
    });
  }, []);

  const handleSettings = useCallback(() => {
    window.dispatchEvent(new CustomEvent('open-voice-settings'));
  }, []);

  const handleToggleMute = useCallback(() => {
    setIsMuted((prev) => !prev);
    if (voiceBridgeService.status === 'connected') {
      if (isMuted) {
        voiceBridgeService.connect();
      } else {
        voiceBridgeService.disconnect();
      }
    }
  }, [isMuted]);

  const isActive = bridgeStatus === 'connected';

  return (
    <div className="fixed inset-0 z-50 bg-[#0a0c12] flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4">
        <button
          onClick={handleSettings}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <Settings2 className="w-4 h-4" />
          Voice Settings
        </button>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${STATE_COLORS[voiceState]}`}>
            {STATE_LABELS[voiceState]}
          </span>
          <span className={`w-2 h-2 rounded-full ${
            bridgeStatus === 'connected' ? 'bg-emerald-500'
            : bridgeStatus === 'connecting' ? 'bg-amber-400'
            : 'bg-gray-500'
          }`} />
        </div>

        <button
          onClick={onClose}
          className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          aria-label="Close voice mode"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Center: Orb */}
      <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6">
        <div className="relative">
          <VoiceOrb size={240} state={isActive ? voiceState : 'idle'} />

          {/* Connecting overlay */}
          {bridgeStatus === 'connecting' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-16 h-16 rounded-full border-4 border-blue-500/30 border-t-blue-500 animate-spin" />
            </div>
          )}

          {/* Offline overlay */}
          {bridgeStatus === 'offline' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="bg-[#0a0c12]/80 rounded-full p-6">
                <MicOff className="w-12 h-12 text-gray-600" />
              </div>
            </div>
          )}
        </div>

        {/* State label */}
        <div className="text-center">
          <p className={`text-lg font-semibold ${STATE_COLORS[voiceState]} transition-colors duration-500`}>
            {isActive ? STATE_LABELS[voiceState] : 'Voice Bridge Offline'}
          </p>
          <p className="text-sm text-gray-500 mt-1">
            {!isActive ? 'Run the voice bridge to start speaking'
            : voiceState === 'idle' ? 'Say "Hey Agentium" or tap the mic'
            : ''}
          </p>
        </div>

        {/* Big mic button */}
        <button
          onClick={handleToggleMute}
          className={`w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300 ${
            isMuted || !isActive
              ? 'bg-gray-800 text-gray-500 hover:bg-gray-700'
              : voiceState === 'listening'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/40 scale-110'
                : 'bg-gray-800 text-white hover:bg-gray-700'
          }`}
          aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
        >
          {isMuted || !isActive ? (
            <MicOff className="w-8 h-8" />
          ) : (
            <Mic className="w-8 h-8" />
          )}
        </button>

        {/* Transcripts */}
        {transcripts.length > 0 && (
          <div className="w-full max-w-lg max-h-40 overflow-y-auto space-y-2 px-4">
            {transcripts.slice(-5).map((t, i) => (
              <div
                key={`${t.timestamp}-${i}`}
                className={`px-4 py-2 rounded-xl text-sm ${
                  t.user_text
                    ? 'bg-blue-500/10 text-blue-300 ml-12'
                    : 'bg-gray-800/50 text-gray-300 mr-12'
                }`}
              >
                <span className="text-xs font-medium opacity-60 mr-2">
                  {t.user_text ? 'You' : 'Agentium'}
                </span>
                {t.user_text || t.agent_text}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom bar */}
      <div className="flex items-center justify-center gap-4 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className={`w-1.5 h-1.5 rounded-full ${
            isActive ? 'bg-emerald-500' : 'bg-gray-600'
          }`} />
          {bridgeStatus === 'connected' ? 'Bridge connected'
          : bridgeStatus === 'connecting' ? 'Connecting\u2026'
          : 'Bridge offline'}
        </div>
        <span className="text-gray-700">·</span>
        <span className="text-xs text-gray-500">
          {isActive
            ? voiceState === 'idle' ? 'Tap mic to speak'
              : voiceState === 'listening' ? 'Speak now'
              : voiceState === 'thinking' ? 'Processing\u2026'
              : voiceState === 'speaking' ? 'Agentium is speaking'
              : ''
            : 'Connect the voice bridge'}
        </span>
      </div>
    </div>
  );
}
