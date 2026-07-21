import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronRight, Mic, Volume2, Radio, Globe, Sliders, Save, Loader2 } from 'lucide-react';
import { voiceApi } from '@/services/voiceApi';
import { useVoiceSettingsStore } from './hooks/useVoiceSettings';
import { useVoiceStore } from '@/stores/voiceStore';
import type { VoiceSettingsProps, VoiceSettings } from './types';

const TABS = [
  { key: 'engine' as const, label: 'Engine', icon: Radio },
  { key: 'voice' as const, label: 'Voice', icon: Volume2 },
  { key: 'network' as const, label: 'Network', icon: Globe },
  { key: 'advanced' as const, label: 'Advanced', icon: Sliders },
] as const;

type TabKey = (typeof TABS)[number]['key'];

function EngineTab({ settings, onChange }: { settings: VoiceSettings; onChange: (key: keyof VoiceSettings, value: any) => void }) {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Wake Word & Mode</h3>
        <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={settings.requireWakeWord}
            onChange={(e) => onChange('requireWakeWord', e.target.checked)}
            className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="font-medium text-white">Require Wake Word</div>
            <div className="text-xs text-gray-500">Listen for "Hey Agentium" before recording</div>
          </div>
        </label>
        <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={settings.proactiveEnabled}
            onChange={(e) => onChange('proactiveEnabled', e.target.checked)}
            className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="font-medium text-white">Proactive Mode</div>
            <div className="text-xs text-gray-500">AI-initiated announcements and suggestions</div>
          </div>
        </label>
        <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={settings.speakerIdentification}
            onChange={(e) => onChange('speakerIdentification', e.target.checked)}
            className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="font-medium text-white">Speaker Identification</div>
            <div className="text-xs text-gray-500">Enroll voices so AI can identify speakers</div>
          </div>
        </label>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Voice Mode</h3>
        <div className="flex gap-2">
          {(['push-to-talk', 'open-mic'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onChange('voiceMode', mode)}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                settings.voiceMode === mode
                  ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                  : 'border-white/10 text-gray-400 hover:border-white/20 hover:text-gray-300 bg-white/5'
              }`}
            >
              {mode === 'push-to-talk' ? <Mic className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
              {mode === 'push-to-talk' ? 'Push to Talk' : 'Open Mic'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function VoiceTab({ settings, onChange }: { settings: VoiceSettings; onChange: (key: keyof VoiceSettings, value: any) => void }) {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">TTS Voice</h3>
        <select
          value={settings.ttsVoice || 'af_bella'}
          onChange={(e) => onChange('ttsVoice', e.target.value)}
          className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500"
        >
          <option value="af_bella">Bella (Female)</option>
          <option value="am_adam">Adam (Male)</option>
          <option value="bf_emma">Emma (British Female)</option>
          <option value="bm_george">George (British Male)</option>
          <option value="af_nicole">Nicole (Female)</option>
          <option value="af_sarah">Sarah (Female)</option>
        </select>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Speech Rate</h3>
        <input
          type="range"
          min="0.5"
          max="2"
          step="0.1"
          value={settings.speechRate || 1}
          onChange={(e) => onChange('speechRate', parseFloat(e.target.value))}
          className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>0.5x</span>
          <span>{settings.speechRate || 1}x</span>
          <span>2x</span>
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Pitch</h3>
        <input
          type="range"
          min="-20"
          max="20"
          step="1"
          value={settings.pitch || 0}
          onChange={(e) => onChange('pitch', parseInt(e.target.value))}
          className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>-20</span>
          <span>{settings.pitch || 0}</span>
          <span>+20</span>
        </div>
      </div>
    </div>
  );
}

function NetworkTab({ settings, onChange }: { settings: VoiceSettings; onChange: (key: keyof VoiceSettings, value: any) => void }) {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">WebSocket Connection</h3>
        <label className="block">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Reconnect Delay (ms)</span>
            <span className="text-white">{settings.reconnectDelay || 2000}</span>
          </div>
          <input
            type="range"
            min="1000"
            max="10000"
            step="500"
            value={settings.reconnectDelay || 2000}
            onChange={(e) => onChange('reconnectDelay', parseInt(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
          />
        </label>
        <label className="block">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Max Reconnect Attempts</span>
            <span className="text-white">{settings.maxReconnectAttempts || 5}</span>
          </div>
          <input
            type="range"
            min="1"
            max="20"
            step="1"
            value={settings.maxReconnectAttempts || 5}
            onChange={(e) => onChange('maxReconnectAttempts', parseInt(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
          />
        </label>
        <label className="block">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Ping Interval (ms)</span>
            <span className="text-white">{settings.pingInterval || 30000}</span>
          </div>
          <input
            type="range"
            min="5000"
            max="120000"
            step="5000"
            value={settings.pingInterval || 30000}
            onChange={(e) => onChange('pingInterval', parseInt(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
          />
        </label>
      </div>
    </div>
  );
}

function AdvancedTab({ settings, onChange, availableInputDevices, availableOutputDevices, isLoadingDevices }: { settings: VoiceSettings; onChange: (key: keyof VoiceSettings, value: any) => void; availableInputDevices: MediaDeviceInfo[]; availableOutputDevices: MediaDeviceInfo[]; isLoadingDevices: boolean }) {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Audio Devices</h3>
        <label className="block">
          <span className="block text-sm text-gray-400 mb-2">Microphone Input</span>
          <select
            value={settings.inputDeviceId}
            onChange={(e) => onChange('inputDeviceId', e.target.value)}
            disabled={isLoadingDevices}
            className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
          >
            <option value="default">Default Device</option>
            {availableInputDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `Microphone ${device.deviceId.slice(0, 8)}...`}
              </option>
            ))}
            {isLoadingDevices && <option disabled>Loading devices...</option>}
          </select>
        </label>
        <label className="block">
          <span className="block text-sm text-gray-400 mb-2">Audio Output</span>
          <select
            value={settings.outputDeviceId}
            onChange={(e) => onChange('outputDeviceId', e.target.value)}
            disabled={isLoadingDevices}
            className="w-full bg-slate-800/50 border border-white/10 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
          >
            <option value="default">Default Device</option>
            {availableOutputDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `Speaker ${device.deviceId.slice(0, 8)}...`}
              </option>
            ))}
            {isLoadingDevices && <option disabled>Loading devices...</option>}
          </select>
        </label>
      </div>

      <div className="space-y-4 pt-4 border-t border-white/10">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Voice Activity Detection</h3>
        <label className="block">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">VAD Sensitivity</span>
            <span className="text-white">{Math.round((settings.vadSensitivity || 0.5) * 100)}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={settings.vadSensitivity || 0.5}
            onChange={(e) => onChange('vadSensitivity', parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">Higher = more sensitive to quiet speech</p>
        </label>
        <label className="block">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Auto-stop Silence (ms)</span>
            <span className="text-white">{settings.autoStopSilence || 1000}ms</span>
          </div>
          <input
            type="range"
            min="500"
            max="5000"
            step="100"
            value={settings.autoStopSilence || 1000}
            onChange={(e) => onChange('autoStopSilence', parseInt(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none accent-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">Stop recording after this much silence</p>
        </label>
      </div>

      <div className="space-y-4 pt-4 border-t border-white/10">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Privacy & Data</h3>
        <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={settings.localProcessingOnly}
            onChange={(e) => onChange('localProcessingOnly', e.target.checked)}
            className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="font-medium text-white">Local Processing Only</div>
            <div className="text-xs text-gray-500">Never send audio to cloud services</div>
          </div>
        </label>
        <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl bg-white/5 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={settings.saveRecordings}
            onChange={(e) => onChange('saveRecordings', e.target.checked)}
            className="w-5 h-5 rounded border-gray-600 text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="font-medium text-white">Save Recordings Locally</div>
            <div className="text-xs text-gray-500">Store audio files for playback and review</div>
          </div>
        </label>
      </div>
    </div>
  );
}

export function VoiceSettings({
  isOpen,
  onClose,
  settings: initialSettings,
  onSettingsChange,
  availableInputDevices = [],
  availableOutputDevices = [],
  className = '',
}: VoiceSettingsProps) {
  const { settings, availableVoices, availableModels, availableLanguages, availableInputDevices: storeInputDevices, availableOutputDevices: storeOutputDevices, loadDevices, updateSettings, resetSettings, isLoadingDevices } = useVoiceSettingsStore();
  const { setAvailableInputDevices, setAvailableOutputDevices } = useVoiceStore();
  const [activeTab, setActiveTab] = useState<TabKey>('engine');
  const [localSettings, setLocalSettings] = useState<VoiceSettings>(initialSettings);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => {
    if (isOpen) {
      setLocalSettings(initialSettings);
      loadDevices();
      setAvailableInputDevices(storeInputDevices);
      setAvailableOutputDevices(storeOutputDevices);
    }
  }, [isOpen, initialSettings, loadDevices, storeInputDevices, storeOutputDevices, setAvailableInputDevices, setAvailableOutputDevices]);

  useEffect(() => {
    if (isOpen) {
      onSettingsChange(localSettings);
    }
  }, [localSettings, isOpen, onSettingsChange]);

  const handleSettingChange = useCallback((key: keyof VoiceSettings, value: VoiceSettings[keyof VoiceSettings]) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
    updateSettings({ [key]: value });
  }, [updateSettings]);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveStatus('saving');
    try {
      const config = {
        requireWakeWord: !!localSettings.requireWakeWord,
        ttsVoice: localSettings.ttsVoice || 'af_bella',
        proactiveEnabled: !!localSettings.proactiveEnabled,
        speakerIdentification: !!localSettings.speakerIdentification,
      };
      await voiceApi.setVoiceConfig(config);
      setSaveStatus('success');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    resetSettings();
    setLocalSettings(initialSettings);
    onSettingsChange(initialSettings);
  };

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const tabsContent: Record<TabKey, React.ReactElement> = {
    engine: <EngineTab settings={localSettings} onChange={handleSettingChange} />,
    voice: <VoiceTab settings={localSettings} onChange={handleSettingChange} />,
    network: <NetworkTab settings={localSettings} onChange={handleSettingChange} />,
    advanced: (
      <AdvancedTab
        settings={localSettings}
        onChange={handleSettingChange}
        availableInputDevices={storeInputDevices}
        availableOutputDevices={storeOutputDevices}
        isLoadingDevices={isLoadingDevices}
      />
    ),
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:p-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-labelledby="voice-settings-title"
        onKeyDown={handleKeyDown}
      >
        <motion.div
          className="w-full max-w-lg bg-slate-900/95 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl overflow-hidden"
          initial={{ opacity: 0, y: '100%' }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: '100%' }}
          transition={{ type: prefersReduced ? 'tween' : 'spring', stiffness: 300, damping: 30, duration: 0.4 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <h2 id="voice-settings-title" className="text-lg font-semibold text-white">
              Voice Settings
            </h2>
            <motion.button
              onClick={onClose}
              className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              aria-label="Close settings"
            >
              <X className="w-5 h-5" />
            </motion.button>
          </div>

          <div className="flex gap-1 px-4 pb-4 border-b border-white/10" role="tablist" aria-label="Settings categories">
            {TABS.map(({ key, label, icon: Icon }) => (
              <motion.button
                key={key}
                role="tab"
                aria-selected={activeTab === key}
                onClick={() => setActiveTab(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 flex-1 justify-center ${
                  activeTab === key
                    ? 'bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-500 hover:text-gray-300 dark:hover:text-gray-300'
                }`}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </motion.button>
            ))}
          </div>

          <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
            {tabsContent[activeTab]}
          </div>

          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
            <motion.button
              onClick={handleReset}
              className="px-4 py-2 rounded-xl text-sm font-medium text-gray-300 bg-white/5 hover:bg-white/10 hover:text-white border border-white/10 transition-colors"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Reset to Defaults
            </motion.button>
            <motion.button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : saveStatus === 'success' ? (
                <>
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Saved
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Settings
                </>
              )}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}